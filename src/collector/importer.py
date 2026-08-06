#!/usr/bin/env python3
"""
GASバッファ（スプレッドシート＋Drive）からSQLiteへの取り込みバッチ

1〜2日間隔で実行される想定。GAS側（gas-delta-station）が15分間隔で書き込んだ
observations シートの未取り込み行をDBへ挿入し、Driveの画像をローカルへ回収する。

GAS側はあくまでキャッシュなので、取り込み確認が済んだ行（imported=TRUE）は
Drive画像・シート行ともに削除する。ただし削除の実行はここ（Pythonのサービス
アカウント）ではなく、gas-delta-station側の cleanup トリガー（1日1回）が行う。
理由: DriveApp.createFile() で作成された画像ファイルの所有者は常にGAS実行者
（人間のGoogleアカウント）であり、サービスアカウントは編集者権限があっても
オーナーでないファイルは削除・ゴミ箱移動ができない（403 insufficientFilePermissions）。
GAS側はオーナー権限で動くためこの制約を受けない。

冪等性は2層で担保:
- DBの observed_at UNIQUE制約: 同じ行を2回処理してもデータは重複しない（正しさ）
- シートの imported フラグ: 一度取り込んだ行の画像を再ダウンロードしない（効率）
  imported=TRUEを立てた行は、GAS側のcleanupトリガーが後で削除する。
"""

import io
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))

from .models import LocationData, ObservationData
from .scraper import DatabaseManager

# ログ設定（scraper.logとは分離し、importer専用ログに出す）
LOG_DIR = Path(__file__).parent.parent.parent / "outputs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "importer.log"

logger = logging.getLogger("importer")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    )
    _file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    _file_handler.setFormatter(_formatter)
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)
    logger.addHandler(_stream_handler)
    logger.propagate = False

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly',
]

# gas-delta-station/.clasp.json の parentId（バインド先スプレッドシートID）と一致させる
SPREADSHEET_ID = os.environ.get(
    'GAS_SPREADSHEET_ID', '1LIidQqLRt8gUij3WzKI3_U_Vfg2VsHQJmvGXrYoyIqo'
)
SHEET_NAME = 'observations'
SERVICE_ACCOUNT_FILE = os.environ.get(
    'GOOGLE_SERVICE_ACCOUNT_FILE', 'config/service-account.json'
)

# gas-delta-station/src/adapters/gas.js の HEADER と対応（列名で読むため順序依存にはしない）
IMPORTED_COLUMN = 'M'  # HEADER内の 'imported' の列位置

# Google Sheetsの日付シリアル値の起点（1899-12-30）
SHEETS_EPOCH = datetime(1899, 12, 30)

# "2026-7-28 9:10" のようにゼロ埋めが崩れた文字列も許容する
LOOSE_DATETIME_RE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2})$')


def normalize_sheet_datetime(value) -> str:
    """シート上の日時値を 'YYYY-MM-DD HH:MM' 文字列に正規化する。

    GAS側はA:B列をプレーンテキスト書式にしているが、それでもGoogle Sheetsが
    日付っぽい文字列を裏で操作することがあり、次の2パターンが実際に観測されている:
    - 完全にシリアル値化される（数値として返ってくる）
    - 文字列のまま残るが、時刻のゼロ埋めが崩れる（"09:10" → "9:10"）
    どちらのケースも吸収できるよう、数値・不完全な文字列の両方を正規化する。
    """
    if isinstance(value, (int, float)):
        dt = SHEETS_EPOCH + timedelta(days=value)
        return dt.strftime('%Y-%m-%d %H:%M')

    s = str(value)
    m = LOOSE_DATETIME_RE.match(s)
    if m:
        year, month, day, hour, minute = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}"
    return s


LOCATION = LocationData(
    location_name="作並宿（チェーン着脱所）",
    location_address="宮城県仙台市青葉区作並",
    source_url="http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html",
)


def get_credentials():
    """サービスアカウント鍵から認証情報を取得"""
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )


def fetch_pending_rows(sheets_service) -> list[dict]:
    """observations シートから imported!=TRUE の行を取得（observed_at昇順）"""
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:M",
        valueRenderOption='UNFORMATTED_VALUE',
    ).execute()
    values = result.get('values', [])
    if len(values) < 2:
        return []

    header = values[0]
    rows = []
    for sheet_row_num, raw in enumerate(values[1:], start=2):
        row = dict(zip(header, raw))
        if row.get('imported'):
            continue
        row['_sheet_row'] = sheet_row_num
        rows.append(row)

    rows.sort(key=lambda r: str(r.get('observed_at', '')))
    return rows


def download_image(drive_service, file_id: str, dest: Path) -> bool:
    """Driveの画像ファイルをローカルへダウンロード"""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(buf.getvalue())
        logger.info(f"画像ダウンロード成功: {dest.name}")
        return True
    except Exception as e:
        logger.warning(f"画像ダウンロード失敗 (fileId={file_id}): {e}")
        return False


def mark_imported(sheets_service, sheet_rows: list[int]) -> None:
    """指定した行の imported 列を一括でTRUEにする"""
    if not sheet_rows:
        return
    data = [
        {'range': f"{SHEET_NAME}!{IMPORTED_COLUMN}{r}", 'values': [[True]]}
        for r in sheet_rows
    ]
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'valueInputOption': 'RAW', 'data': data},
    ).execute()
    logger.info(f"シート側を取り込み済みに更新: {len(sheet_rows)}行")


def process_rows(
    pending: list[dict],
    location_id: int,
    db: DatabaseManager,
    drive_service,
    image_dir: Path,
) -> tuple[list[int], int]:
    """未取り込み行を検証・DB挿入・画像取得する（Sheets認証を挟まないため単体テスト可能）

    Returns:
        (処理済みシート行番号のリスト, 検証エラー件数)
    """
    processed_sheet_rows: list[int] = []
    error_count = 0

    for row in pending:
        try:
            obs = ObservationData(
                location_id=location_id,
                observed_at=normalize_sheet_datetime(row.get('observed_at', '')),
                captured_at=normalize_sheet_datetime(row.get('captured_at', '')),
                cumulative_rainfall=row.get('cumulative_rainfall'),
                temperature=row.get('temperature'),
                wind_speed=row.get('wind_speed'),
                road_temperature=row.get('road_temperature'),
                road_condition=row.get('road_condition'),
                image_filename=row.get('image_filename', ''),
                image_url=row.get('image_url', ''),
            )
        except ValidationError as e:
            # このシート行はimportedにしない → 原因修正後、次回再取り込みされる
            logger.warning(f"検証エラー（シート行{row['_sheet_row']}）: {e}")
            error_count += 1
            continue

        # DB挿入はUNIQUE制約により冪等（既存行でも例外にはならない）。
        # 戻り値(新規/重複)は信用しない: insert_observationは重複エラーも
        # 想定外のDBエラーも同じFalseに握りつぶすため、区別できない。
        # 実際にDBへ入っているかは読み返して直接確認する。
        db.insert_observation(location_id, obs)
        row_in_db = db.conn.execute(
            "SELECT 1 FROM observations WHERE observed_at = ? LIMIT 1", (obs.observed_at,)
        ).fetchone() is not None

        if not row_in_db:
            # DB挿入が本当に失敗している(重複ではない) → imported化しない。
            # GAS側cleanupはimported=TRUEの行しか消さないため、データ・画像とも安全。
            logger.error(f"DB挿入の確認に失敗（原因不明のためimported化を見送り）: {obs.observed_at}")
            error_count += 1
            continue

        # imported化するかは「画像がローカルに実在するか」で決める。
        # 過去にDB挿入だけ成功し画像取得に失敗した（例: Driveフォルダ未共有）行でも、
        # ここで自動的にリトライされる。
        image_path = image_dir / obs.image_filename
        if image_path.exists():
            image_ok = True
        else:
            drive_id = row.get('image_drive_id')
            if drive_id:
                image_ok = download_image(drive_service, str(drive_id), image_path)
            else:
                logger.warning(f"image_drive_id が空です（リトライ不可）: {obs.observed_at}")
                image_ok = True  # 画像を永久に取得できないため、imported化して先へ進める

        if image_ok:
            processed_sheet_rows.append(row['_sheet_row'])
        else:
            # imported にしない → 次回実行時に同じ行が再度対象になる（画像だけ再試行される）
            logger.warning(f"画像未取得のため今回はimported化を見送り: {obs.observed_at}")

    return processed_sheet_rows, error_count


def main() -> int:
    logger.info("=" * 60)
    logger.info("GASバッファ取り込み開始")
    logger.info("=" * 60)

    try:
        creds = get_credentials()
    except Exception as e:
        logger.error(f"サービスアカウント認証失敗: {e}")
        return 1

    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    try:
        pending = fetch_pending_rows(sheets_service)
    except Exception as e:
        logger.error(f"シート取得失敗: {e}")
        return 1
    logger.info(f"未取り込み行数: {len(pending)}")

    if not pending:
        logger.info("取り込み対象なし")
        return 0

    db = DatabaseManager()
    if not db.connect():
        logger.error("データベース接続失敗のため終了")
        return 1

    location_id = db.ensure_location(LOCATION)
    if location_id is None:
        logger.error("観測地点の確認・挿入に失敗")
        db.close()
        return 1

    image_dir = Path(__file__).parent.parent.parent / "outputs" / "images"
    processed_sheet_rows, error_count = process_rows(
        pending, location_id, db, drive_service, image_dir
    )

    db.close()

    try:
        mark_imported(sheets_service, processed_sheet_rows)
    except Exception as e:
        logger.error(f"シート更新失敗（DB取り込みは完了済み。次回も再取込されます）: {e}")
        # DBへの挿入自体はUNIQUE制約で冪等なので致命ではない

    logger.info(f"取り込み完了: {len(processed_sheet_rows)}件処理 / エラー{error_count}件")
    logger.info("=" * 60)

    return 1 if processed_sheet_rows == [] and error_count > 0 else 0


if __name__ == "__main__":
    exit(main())
