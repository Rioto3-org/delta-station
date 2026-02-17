#!/usr/bin/env python3
"""
Delta地点 定点観測データ スクレイパー（本番用）

15分間隔で実行され、観測データをDBに保存し、画像をダウンロードする。
"""

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import requests

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from .models import LocationData, ObservationData, ScrapedRawData

# ログ設定（ファイル出力）
LOG_DIR = Path(__file__).parent.parent.parent / "outputs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scraper.log"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """データベース管理クラス"""

    def __init__(self, db_path: str = "outputs/database/delta_station.db"):
        self.db_path = Path(__file__).parent.parent.parent / db_path
        self.conn: Optional[sqlite3.Connection] = None

    def initialize_database(self) -> bool:
        """データベースとテーブルを初期化"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            schema_path = Path(__file__).parent.parent.parent / "database" / "schema.sql"
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = f.read()

            conn = sqlite3.connect(self.db_path)
            conn.executescript(schema)
            conn.commit()
            conn.close()

            logger.info("データベース初期化完了")
            return True
        except Exception as e:
            logger.error(f"データベース初期化失敗: {e}")
            return False

    def connect(self) -> bool:
        """データベースに接続"""
        try:
            # DBファイルが存在しない、または空の場合は初期化
            if not self.db_path.exists() or self.db_path.stat().st_size == 0:
                logger.info("データベースが存在しないため、初期化します")
                if not self.initialize_database():
                    return False

            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row

            # テーブルが存在するか確認
            cursor = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='locations'"
            )
            if cursor.fetchone() is None:
                logger.warning("テーブルが存在しないため、再初期化します")
                self.conn.close()
                self.conn = None
                if not self.initialize_database():
                    return False
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row

            return True
        except Exception as e:
            logger.error(f"データベース接続失敗: {e}")
            return False

    def ensure_location(self, location: LocationData) -> Optional[int]:
        """観測地点を確認・挿入し、location_idを返す"""
        try:
            cursor = self.conn.execute(
                "SELECT id FROM locations WHERE location_name = ?",
                (location.location_name,)
            )
            row = cursor.fetchone()

            if row:
                return row['id']

            # 新規挿入
            cursor = self.conn.execute(
                """INSERT INTO locations (location_name, location_address, source_url)
                   VALUES (?, ?, ?)""",
                (location.location_name, location.location_address, location.source_url)
            )
            self.conn.commit()
            logger.info(f"新規観測地点を登録: {location.location_name}")
            return cursor.lastrowid

        except Exception as e:
            logger.error(f"観測地点の確認・挿入に失敗: {e}")
            return None

    def insert_observation(self, location_id: int, obs: ObservationData) -> bool:
        """観測データを挿入"""
        try:
            self.conn.execute(
                """INSERT INTO observations (
                    location_id, observed_at, captured_at,
                    cumulative_rainfall, temperature, wind_speed,
                    road_temperature, road_condition,
                    image_filename, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    location_id,
                    obs.observed_at,
                    obs.captured_at,
                    obs.cumulative_rainfall,
                    obs.temperature,
                    obs.wind_speed,
                    obs.road_temperature,
                    obs.road_condition,
                    obs.image_filename,
                    obs.image_url
                )
            )
            self.conn.commit()
            logger.info(f"新規データ挿入成功: {obs.observed_at}")
            return True

        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: observations.observed_at" in str(e):
                logger.info(f"データ未更新（既存データ）: {obs.observed_at}")
            else:
                logger.warning(f"データ挿入時の整合性エラー: {e}")
            return False

        except Exception as e:
            logger.error(f"データ挿入失敗: {e}")
            return False

    def close(self):
        """データベース接続をクローズ"""
        if self.conn:
            self.conn.close()


def download_image(image_url: str, save_path: Path) -> bool:
    """画像をダウンロード"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(response.content)

        logger.info(f"画像ダウンロード成功: {save_path.name}")
        return True

    except Exception as e:
        logger.warning(f"画像ダウンロード失敗: {e}")
        return False


def main():
    """メイン処理"""
    logger.info("=" * 60)
    logger.info("Delta地点観測データ収集開始")
    logger.info("=" * 60)

    # 観測地点情報
    location = LocationData(
        location_name="作並宿（チェーン着脱所）",
        location_address="宮城県仙台市青葉区作並",
        source_url="http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html"
    )

    # データベース接続
    db = DatabaseManager()
    if not db.connect():
        logger.error("データベース接続失敗のため終了")
        return 1

    # 観測地点の確認・登録
    location_id = db.ensure_location(location)
    if location_id is None:
        logger.error("観測地点の確認・挿入に失敗")
        db.close()
        return 1

    # スクレイピング実行
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(location.source_url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        # データ抽出
        raw_data = ScrapedRawData.from_html(response.text, location.source_url)
        observation = raw_data.to_observation(location_id)

        logger.info(f"観測日時: {observation.observed_at}")
        logger.info(f"気温: {observation.temperature}℃")
        logger.info(f"路面温度: {observation.road_temperature}℃")
        logger.info(f"路面状況: {observation.road_condition}")

        # データベースに挿入
        inserted = db.insert_observation(location_id, observation)

        # 画像ダウンロード（新規挿入時のみ）
        if inserted:
            image_dir = Path(__file__).parent.parent.parent / "outputs" / "images"
            image_path = image_dir / observation.image_filename
            download_image(observation.image_url, image_path)

        db.close()

        logger.info("=" * 60)
        logger.info("Delta地点観測データ収集完了")
        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"スクレイピング失敗: {e}")
        db.close()
        return 1


if __name__ == "__main__":
    exit(main())
