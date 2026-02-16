#!/usr/bin/env python3
"""
Delta地点 データベース挿入テスト

実際にスクレイピングしたデータをデータベースに挿入し、
正常に保存されているかを確認するテストコード。

テスト実施日: 2026/02/16
"""

import logging
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models import LocationData, ObservationData, ScrapedRawData

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """データベース管理クラス"""

    def __init__(self, db_path: str = "test_delta_station.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def initialize_database(self) -> bool:
        """データベースを初期化（スキーマ適用）"""
        logger.info("✓ データベース初期化")
        try:
            schema_path = Path("database/schema.sql")
            if not schema_path.exists():
                logger.error(f"  → 失敗: スキーマファイルが見つかりません: {schema_path}")
                return False

            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()

            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")  # 外部キー制約を有効化
            self.conn.executescript(schema_sql)
            self.conn.commit()

            logger.info(f"  → 成功: {self.db_path} を初期化しました")
            return True
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def insert_location(self, location: LocationData) -> bool:
        """観測地点データを挿入"""
        logger.info("✓ 観測地点データの挿入")
        try:
            # 既に存在するかチェック
            cursor = self.conn.execute(
                "SELECT id FROM locations WHERE location_name = ?",
                (location.location_name,)
            )
            existing = cursor.fetchone()

            if existing:
                logger.info(f"  → スキップ: 既に登録済み (ID: {existing[0]})")
                return True

            # 挿入
            self.conn.execute(
                """
                INSERT INTO locations (id, location_name, location_address, source_url)
                VALUES (?, ?, ?, ?)
                """,
                (location.id, location.location_name, location.location_address, location.source_url)
            )
            self.conn.commit()

            logger.info(f"  → 成功: ID={location.id}, 地点名={location.location_name}")
            logger.info(f"  → LocationData: {location.model_dump_json(ensure_ascii=False)}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"  → 失敗: 一意制約違反 {e}")
            return False
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def insert_observation(self, observation: ObservationData) -> bool:
        """観測データを挿入"""
        logger.info("✓ 観測データの挿入")
        try:
            # 既に存在するかチェック（observed_at がUNIQUE）
            cursor = self.conn.execute(
                "SELECT id FROM observations WHERE observed_at = ?",
                (observation.observed_at,)
            )
            existing = cursor.fetchone()

            if existing:
                logger.info(f"  → スキップ: 既に登録済み (ID: {existing[0]}, 観測日時: {observation.observed_at})")
                return True

            # 挿入
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

            logger.info(f"  → 成功: 観測日時={observation.observed_at}")
            logger.info(f"  → ObservationData: {observation.model_dump_json(ensure_ascii=False)}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"  → 失敗: 一意制約違反またはデータ整合性エラー {e}")
            return False
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def verify_data(self) -> bool:
        """データが正しく挿入されたか確認"""
        logger.info("✓ データ確認")
        try:
            # 観測地点数を確認
            cursor = self.conn.execute("SELECT COUNT(*) FROM locations")
            location_count = cursor.fetchone()[0]
            logger.info(f"  → locations テーブル: {location_count} 件")

            # 観測データ数を確認
            cursor = self.conn.execute("SELECT COUNT(*) FROM observations")
            observation_count = cursor.fetchone()[0]
            logger.info(f"  → observations テーブル: {observation_count} 件")

            # 最新の観測データを取得して表示
            cursor = self.conn.execute(
                """
                SELECT
                    o.id, l.location_name, o.observed_at, o.captured_at,
                    o.cumulative_rainfall, o.temperature, o.wind_speed,
                    o.road_temperature, o.road_condition,
                    o.image_filename
                FROM observations o
                JOIN locations l ON o.location_id = l.id
                ORDER BY o.observed_at DESC
                LIMIT 1
                """
            )
            latest = cursor.fetchone()

            if latest:
                logger.info("  → 最新の観測データ:")
                logger.info(f"      ID: {latest[0]}")
                logger.info(f"      観測地点: {latest[1]}")
                logger.info(f"      観測日時: {latest[2]}")
                logger.info(f"      撮影日時: {latest[3]}")
                logger.info(f"      累加雨量: {latest[4]} mm")
                logger.info(f"      気温: {latest[5]} ℃")
                logger.info(f"      風速: {latest[6]} m/s")
                logger.info(f"      路面温度: {latest[7]} ℃")
                logger.info(f"      路面状況: {latest[8]}")
                logger.info(f"      画像: {latest[9]}")

            return True
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def close(self):
        """データベース接続を閉じる"""
        if self.conn:
            self.conn.close()


class DeltaStationScraper:
    """Delta地点観測データスクレイパー（test_scraper.pyから移植）"""

    def __init__(self, url: str, image_dir: str = "images"):
        self.url = url
        self.soup: Optional[BeautifulSoup] = None
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(exist_ok=True)

    def fetch_html(self) -> bool:
        """HTMLを取得してパース"""
        logger.info("✓ HTMLの取得")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            self.soup = BeautifulSoup(response.text, 'lxml')
            logger.info(f"  → 成功: ステータスコード {response.status_code}")
            return True
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def scrape(self) -> Optional[ScrapedRawData]:
        """データをスクレイピング"""
        logger.info("✓ データ抽出")
        try:
            data = {}

            # 観測日時
            text = self.soup.get_text()
            match = re.search(r'観測日時[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text)
            if match:
                data['observed_at'] = match.group(1).strip()
                logger.info(f"  → 観測日時: {data['observed_at']}")

            # 撮影日時
            match = re.search(r'撮影日時[：:]\s*(\d{2}/\d{2})\s+(\d{2}:\d{2})', text)
            if match:
                year = data['observed_at'][:4] if 'observed_at' in data else str(datetime.now().year)
                month_day = match.group(1)
                time = match.group(2)
                data['captured_at'] = f"{year}-{month_day.replace('/', '-')} {time}"
                logger.info(f"  → 撮影日時: {data['captured_at']}")

            # 住所
            div = self.soup.find('div', class_='style3')
            if div:
                data['location_address'] = div.get_text().strip()
                logger.info(f"  → 住所: {data['location_address']}")

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
                logger.info(f"  → 画像URL: {data['image_url']}")

            logger.info("  → 成功: すべてのデータを抽出")

            # ScrapedRawDataに変換
            return ScrapedRawData(**data)
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return None

    def download_image(self, image_url: str, image_filename: str) -> bool:
        """画像をダウンロードして保存"""
        logger.info("✓ 画像ダウンロード")
        try:
            image_path = self.image_dir / image_filename

            # 既に存在する場合はスキップ
            if image_path.exists():
                logger.info(f"  → スキップ: 既に存在します ({image_filename})")
                return True

            # 画像をダウンロード
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=30)
            response.raise_for_status()

            # 保存
            with open(image_path, 'wb') as f:
                f.write(response.content)

            file_size = len(response.content)
            logger.info(f"  → 成功: {image_filename} ({file_size:,} bytes)")
            logger.info(f"  → 保存先: {image_path}")
            return True
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False


def main():
    """メイン実行"""
    logger.info("=" * 60)
    logger.info("Delta地点 データベース挿入テスト")
    logger.info("テスト実施日: 2026/02/16")
    logger.info("=" * 60)

    # データベース初期化
    db = DatabaseManager()
    if not db.initialize_database():
        logger.error("データベース初期化に失敗しました")
        return 1

    # 観測地点データ（No.1: 作並宿）
    location = LocationData(
        id=1,
        location_name="作並宿",
        location_address="仙台市青葉区作並字神前西",
        source_url="http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html"
    )

    # 観測地点を挿入
    if not db.insert_location(location):
        logger.error("観測地点の挿入に失敗しました")
        db.close()
        return 1

    # スクレイピング実行
    scraper = DeltaStationScraper(location.source_url)
    if not scraper.fetch_html():
        logger.error("HTML取得に失敗しました")
        db.close()
        return 1

    raw_data = scraper.scrape()
    if not raw_data:
        logger.error("データ抽出に失敗しました")
        db.close()
        return 1

    # 画像ファイル名生成
    timestamp = raw_data.observed_at.replace('-', '').replace(':', '').replace(' ', '_')
    image_filename = f"{timestamp}_DR-74125-l.jpg"

    # ObservationDataに変換（Pydanticバリデーション実行）
    logger.info("✓ データバリデーション")
    try:
        observation = raw_data.to_observation(
            location_id=location.id,
            image_filename=image_filename
        )
        logger.info("  → 成功: バリデーション完了")
    except Exception as e:
        logger.error(f"  → 失敗: バリデーションエラー {e}")
        db.close()
        return 1

    # 画像をダウンロード
    if not scraper.download_image(observation.image_url, observation.image_filename):
        logger.warning("画像のダウンロードに失敗しましたが、処理を続行します")

    # 観測データを挿入
    if not db.insert_observation(observation):
        logger.error("観測データの挿入に失敗しました")
        db.close()
        return 1

    # データ確認
    if not db.verify_data():
        logger.error("データ確認に失敗しました")
        db.close()
        return 1

    # クリーンアップ
    db.close()

    # 画像ディレクトリの確認
    image_count = len(list(scraper.image_dir.glob("*.jpg")))

    logger.info("=" * 60)
    logger.info("🎉 すべてのテストに成功しました！")
    logger.info(f"データベースファイル: {db.db_path}")
    logger.info(f"画像ディレクトリ: {scraper.image_dir} ({image_count} 件)")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
