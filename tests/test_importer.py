#!/usr/bin/env python3
"""
importer.py のローカルテスト（Google認証・ネットワークなしで実行可能）

Sheets/Drive APIはモックし、以下を検証する:
- fetch_pending_rows: imported!=TRUE のみ抽出し observed_at 昇順に並べる
- mark_imported: 指定行のimported列を一括更新するリクエストを組み立てる
- process_rows: 検証NG行はスキップ・DBはUNIQUE制約で冪等・画像は新規挿入時のみ取得

GAS側キャッシュの削除（Drive画像・シート行）は gas-delta-station 側の cleanup
トリガーが担当するため、ここではテストしない（Python側には削除コードが無い）。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collector.importer import (
    fetch_pending_rows,
    mark_imported,
    normalize_sheet_datetime,
    process_rows,
)
from src.collector.scraper import DatabaseManager

TEST_DB_PATH = "outputs/database/test_importer.db"


def make_row(observed_at="2026-02-16 10:50", imported=False, **overrides):
    # observed_atがシリアル値(float)のテストケースでは image_filename を明示的に上書きする前提
    default_image_filename = (
        f"{observed_at.replace('-', '').replace(':', '').replace(' ', '_')}_DR-74125-l.jpg"
        if isinstance(observed_at, str)
        else "placeholder.jpg"
    )
    row = {
        'observed_at': observed_at,
        'captured_at': '2026-02-16 10:52',
        'cumulative_rainfall': 0.0,
        'temperature': 4.7,
        'wind_speed': 1.9,
        'road_temperature': 8.0,
        'road_condition': '',
        'image_filename': default_image_filename,
        'image_drive_id': 'fake-drive-id',
        'image_url': 'http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg',
        'location_name': '作並宿',
        'imported': imported,
    }
    row.update(overrides)
    return row


def sheets_service_returning(rows_as_lists, header):
    """values().get().execute() が固定レスポンスを返すモックSheetsサービス"""
    service = MagicMock()
    service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        'values': [header] + rows_as_lists
    }
    return service


class TestNormalizeSheetDatetime:
    def test_文字列はそのまま(self):
        assert normalize_sheet_datetime('2026-02-16 10:50') == '2026-02-16 10:50'

    def test_シリアル値は日時文字列に変換される(self):
        # 2026-07-28 06:12 相当（実際にSheetsが自動変換した値で確認済み）
        assert normalize_sheet_datetime(46231.25833333333) == '2026-07-28 06:12'

    def test_時刻のゼロ埋めが崩れた文字列も補正される(self):
        # 実際にGoogle SheetsがGAS書き込み後に "09:10"→"9:10" と崩したケースで確認済み
        assert normalize_sheet_datetime('2026-07-28 9:10') == '2026-07-28 09:10'

    def test_月日のゼロ埋めが崩れても補正される(self):
        assert normalize_sheet_datetime('2026-7-8 9:5') == '2026-07-08 09:05'


class TestFetchPendingRows:
    def test_imported行は除外され未取込のみ返る(self):
        header = ['observed_at', 'imported']
        service = sheets_service_returning(
            [['2026-02-16 10:00', True], ['2026-02-16 10:15', False]], header
        )
        pending = fetch_pending_rows(service)
        assert len(pending) == 1
        assert pending[0]['observed_at'] == '2026-02-16 10:15'

    def test_observed_at昇順にソートされる(self):
        header = ['observed_at', 'imported']
        service = sheets_service_returning(
            [['2026-02-16 11:00', False], ['2026-02-16 10:00', False]], header
        )
        pending = fetch_pending_rows(service)
        assert [r['observed_at'] for r in pending] == ['2026-02-16 10:00', '2026-02-16 11:00']

    def test_シート行番号がヘッダー分ずれて記録される(self):
        header = ['observed_at', 'imported']
        service = sheets_service_returning([['2026-02-16 10:00', False]], header)
        pending = fetch_pending_rows(service)
        assert pending[0]['_sheet_row'] == 2  # 1行目はヘッダー

    def test_データ行が無ければ空リスト(self):
        header = ['observed_at', 'imported']
        service = sheets_service_returning([], header)
        assert fetch_pending_rows(service) == []


class TestMarkImported:
    def test_batchUpdateが正しい範囲で呼ばれる(self):
        service = MagicMock()
        mark_imported(service, [2, 5])
        call = service.spreadsheets.return_value.values.return_value.batchUpdate
        call.assert_called_once()
        body = call.call_args.kwargs['body']
        ranges = [d['range'] for d in body['data']]
        assert ranges == ['observations!M2', 'observations!M5']

    def test_空リストなら何も呼ばれない(self):
        service = MagicMock()
        mark_imported(service, [])
        service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


@pytest.fixture
def db():
    db_path = Path(TEST_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    manager = DatabaseManager(db_path=TEST_DB_PATH)
    assert manager.connect()
    yield manager
    manager.close()
    if db_path.exists():
        db_path.unlink()


def make_location_id(db):
    from src.collector.models import LocationData

    return db.ensure_location(
        LocationData(
            location_name="作並宿（チェーン着脱所）",
            location_address="宮城県仙台市青葉区作並",
            source_url="http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html",
        )
    )


class TestProcessRows:
    def test_DB挿入が実際には失敗している場合はimported化されない(self, db, tmp_path, monkeypatch):
        # insert_observationの戻り値は信用できない(重複エラーも想定外エラーも同じFalseに
        # 握りつぶすため)。ここではinsert_observationが呼ばれてもDBに実際には入らない
        # ケース(想定外のDBエラーが握りつぶされた状況)を再現し、読み返し確認で検知できるか検証する。
        location_id = make_location_id(db)
        drive_service = MagicMock()
        monkeypatch.setattr(db, 'insert_observation', lambda *a, **k: False)

        row = make_row()
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image') as mock_dl:
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        assert processed == []  # imported化されない → GAS側で消されない
        assert errors == 1
        mock_dl.assert_not_called()  # DB未確認の時点で画像取得にも進まない

    def test_正常行はDB挿入され画像取得される(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        row = make_row()
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image', return_value=True) as mock_dl:
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        assert processed == [2]
        assert errors == 0
        mock_dl.assert_called_once_with(
            drive_service, 'fake-drive-id', tmp_path / row['image_filename']
        )

    def test_シリアル値の日時でも取り込まれる(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        row = make_row(
            observed_at=46231.25833333333,  # Sheetsが自動変換したシリアル値
            captured_at=46231.258333333333,
            image_filename="20260728_0612_DR-74125-l.jpg",
        )
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image', return_value=True):
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        assert processed == [2]
        assert errors == 0

    def test_範囲外の値は検証エラーとしてスキップされる(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        row = make_row(temperature=999.0)  # 50℃超 → ValidationError
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image') as mock_dl:
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        assert processed == []
        assert errors == 1
        mock_dl.assert_not_called()

    def test_ローカルに画像が既にあれば再ダウンロードしない(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        row = make_row()
        row['_sheet_row'] = 2
        (tmp_path / row['image_filename']).write_bytes(b'already-downloaded')

        with patch('src.collector.importer.download_image') as mock_dl:
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        assert processed == [2]
        assert errors == 0
        mock_dl.assert_not_called()

    def test_同じobserved_atは2回目もDBはスキップされ画像は既存ファイルを使う(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        def fake_download(_service, _file_id, dest):
            dest.write_bytes(b'fake-image-bytes')
            return True

        row = make_row()
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image', side_effect=fake_download) as mock_dl:
            process_rows([row], location_id, db, drive_service, tmp_path)

            row2 = make_row()
            row2['_sheet_row'] = 3
            processed, errors = process_rows([row2], location_id, db, drive_service, tmp_path)

        # DB挿入はUNIQUE制約でスキップされるが、画像は既にあるためシート側は取り込み済みにしてよい
        assert processed == [3]
        assert errors == 0
        mock_dl.assert_called_once()  # 1回目でファイルができたので2回目は呼ばれない

    def test_画像取得に失敗した行はimported化されず次回リトライされる(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        row = make_row()
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image', return_value=False):
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        # DBには挿入されるが、シート側は imported にしない（次回また対象になる）
        assert processed == []
        assert errors == 0

    def test_image_drive_idが空なら取得不能として先へ進む(self, db, tmp_path):
        location_id = make_location_id(db)
        drive_service = MagicMock()

        row = make_row(image_drive_id='')
        row['_sheet_row'] = 2
        with patch('src.collector.importer.download_image') as mock_dl:
            processed, errors = process_rows([row], location_id, db, drive_service, tmp_path)

        assert processed == [2]
        assert errors == 0
        mock_dl.assert_not_called()
