#!/usr/bin/env python3
"""
Delta地点 定点観測データ収集スクリプト（本番用）

15分間隔で実行され、観測データをスクレイピングしてデータベースに保存する。
observed_atのUNIQUE制約により、データ未更新時は自動的にスキップされる。
"""

import logging
import sqlite3
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# プロジェクトルートからの相対インポート
sys.path.insert(0, str(Path(__file__).parent))
from models import LocationData, ObservationData, ScrapedRawData


def setup_logging(log_file: str = "outputs/scraper.log"):
    """ログ設定（ファイル出力）"""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # 標準出力にも出力
        ]
    )
    return logging.getLogger(__name__)


class DatabaseManager:
    """データベース管理クラス（本番用）"""

    def __init__(self, db_path: str = "outputs/database/delta_station.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None

    def initialize_database(self) -> bool:
        """データベースを初期化（初回実行時のみ必要）"""
        try:
            schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
            if not schema_path.exists():
                raise FileNotFoundError(f"スキーマファイルが見つかりません: {schema_path}")

            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()

            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.executescript(schema_sql)
            self.conn.commit()
            return True
        except Exception as e:
            if self.conn:
                self.conn.close()
            raise e

    def connect(self) -> bool:
        """既存データベースに接続"""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.execute("PRAGMA foreign_keys = ON")
            return True
        except Exception:
            return False

    def ensure_location(self, location: LocationData) -> bool:
        """観測地点を確認・挿入（初回のみ）"""
        try:
            cursor = self.conn.execute(
                "SELECT id FROM locations WHERE id = ?",
                (location.id,)
            )
            if cursor.fetchone():
                return True  # 既に存在

            self.conn.execute(
                """
                INSERT INTO locations (id, location_name, location_address, source_url)
                VALUES (?, ?, ?, ?)
                """,
                (location.id, location.location_name, location.location_address, location.source_url)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def insert_observation(self, observation: ObservationData) -> tuple[bool, str]:
        """
        観測データを挿入

        Returns:
            (success: bool, message: str)
            - (True, "inserted"): 新規データ挿入成功
            - (True, "duplicate"): 既存データ（スキップ）
            - (False, error_msg): エラー
        """
        try:
            self.conn.execute(
                """
                INSERT INTO observations (
                    location_id, observed_at, captured_at,
                    cumulative_rainfall, temperature, wind_speed,
                    road_temperature, road_condition,
                    image_filename, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.location_id,
                    observation.observed_at,
                    observation.captured_at,
                    observation.cumulative_rainfall,
                    observation.temperature,
                    observation.wind_speed,
                    observation.road_temperature,
                    observation.road_condition,
                    observation.image_filename,
                    observation.image_url
                )
            )
            self.conn.commit()
            return True, "inserted"
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                return True, "duplicate"
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def close(self):
        """データベース接続を閉じる"""
        if self.conn:
            self.conn.close()


class DeltaStationScraper:
    """Delta地点観測データスクレイパー（本番用）"""

    def __init__(self, url: str, image_dir: str = "outputs/images"):
        self.url = url
        self.soup: Optional[BeautifulSoup] = None
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    def fetch_html(self) -> bool:
        """HTMLを取得してパース"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            self.soup = BeautifulSoup(response.text, 'lxml')
            return True
        except Exception:
            return False

    def scrape(self) -> Optional[ScrapedRawData]:
        """データをスクレイピング"""
        try:
            data = {}

            # 観測日時
            text = self.soup.get_text()
            match = re.search(r'観測日時[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text)
            if match:
                data['observed_at'] = match.group(1).strip()

            # 撮影日時
            match = re.search(r'撮影日時[：:]\s*(\d{2}/\d{2})\s+(\d{2}:\d{2})', text)
            if match:
                year = data['observed_at'][:4] if 'observed_at' in data else str(datetime.now().year)
                month_day = match.group(1)
                time = match.group(2)
                data['captured_at'] = f"{year}-{month_day.replace('/', '-')} {time}"

            # 住所
            div = self.soup.find('div', class_='style3')
            if div:
                data['location_address'] = div.get_text().strip()

            # 気象データ
            tables = self.soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) == 2:
                        label = cols[0].get_text().strip()
                        value = cols[1].get_text().strip()

                        if label == '観測地点':
                            data['location_name'] = value
                        elif label == '累加雨量':
                            data['cumulative_rainfall'] = value
                        elif label == '気温':
                            data['temperature'] = value
                        elif label == '風速':
                            data['wind_speed'] = value
                        elif label == '路面温度':
                            data['road_temperature'] = value
                        elif label == '路面状況':
                            data['road_condition'] = value

            # 画像URL
            img_tag = self.soup.find('img', src=re.compile(r'DR-\d+-l\.jpg'))
            if img_tag:
                relative_url = img_tag['src']
                data['image_url'] = urljoin(self.url, relative_url)

            return ScrapedRawData(**data)
        except Exception:
            return None

    def download_image(self, image_url: str, image_filename: str) -> bool:
        """画像をダウンロードして保存"""
        try:
            image_path = self.image_dir / image_filename

            # 既に存在する場合はスキップ
            if image_path.exists():
                return True

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=30)
            response.raise_for_status()

            with open(image_path, 'wb') as f:
                f.write(response.content)

            return True
        except Exception:
            return False


def main():
    """メイン実行"""
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info("Delta地点 観測データ収集開始")
    logger.info("=" * 60)

    # 観測地点データ（No.1: 作並宿）
    location = LocationData(
        id=1,
        location_name="作並宿",
        location_address="仙台市青葉区作並字神前西",
        source_url="http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html"
    )

    # データベース接続
    db = DatabaseManager()
    if not db.connect():
        # 初回実行時はデータベース初期化
        logger.info("データベースを初期化します")
        try:
            db.initialize_database()
            logger.info("✓ データベース初期化完了")
        except Exception as e:
            logger.error(f"✗ データベース初期化失敗: {e}")
            return 1

    # 観測地点を確認・挿入
    if not db.ensure_location(location):
        logger.error("✗ 観測地点の確認・挿入に失敗")
        db.close()
        return 1

    # スクレイピング実行
    scraper = DeltaStationScraper(location.source_url)

    if not scraper.fetch_html():
        logger.error("✗ HTML取得失敗")
        db.close()
        return 1

    raw_data = scraper.scrape()
    if not raw_data:
        logger.error("✗ データ抽出失敗")
        db.close()
        return 1

    logger.info(f"観測日時: {raw_data.observed_at}")

    # 画像ファイル名生成
    timestamp = raw_data.observed_at.replace('-', '').replace(':', '').replace(' ', '_')
    image_filename = f"{timestamp}_DR-74125-l.jpg"

    # バリデーション
    try:
        observation = raw_data.to_observation(
            location_id=location.id,
            image_filename=image_filename
        )
    except Exception as e:
        logger.error(f"✗ バリデーションエラー: {e}")
        db.close()
        return 1

    # 画像ダウンロード
    if scraper.download_image(observation.image_url, observation.image_filename):
        logger.info(f"✓ 画像保存: {observation.image_filename}")
    else:
        logger.warning(f"⚠ 画像ダウンロード失敗（処理続行）")

    # データベース挿入
    success, message = db.insert_observation(observation)

    if success:
        if message == "inserted":
            logger.info(f"✓ 新規データ挿入: {observation.observed_at}")
            logger.info(f"  気温: {observation.temperature}℃, 風速: {observation.wind_speed}m/s")
        elif message == "duplicate":
            logger.info(f"→ データ未更新（既存データ: {observation.observed_at}）")
    else:
        logger.error(f"✗ データ挿入失敗: {message}")
        db.close()
        return 1

    db.close()
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
