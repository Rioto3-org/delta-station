#!/usr/bin/env python3
"""
Delta地点 定点観測データ スクレイピングテスト

取得観点：
1. HTMLの取得成功
2. 観測日時の抽出（observed_at）
3. 撮影日時の抽出と変換（captured_at）
4. 住所の抽出（location_address）
5. 観測地点名の抽出（location_name）
6. 気象データの抽出（累加雨量、気温、風速、路面温度、路面状況）
7. 画像URLの抽出と絶対URL化
"""

import logging
import re
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class DeltaStationScraper:
    """Delta地点観測データスクレイパー"""

    def __init__(self, url: str):
        self.url = url
        self.soup: Optional[BeautifulSoup] = None
        self.data: Dict = {}

    def fetch_html(self) -> bool:
        """HTMLを取得してパース"""
        logger.info(f"✓ テスト1: HTMLの取得を開始")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding  # 文字エンコーディング自動判定
            self.soup = BeautifulSoup(response.text, 'lxml')
            logger.info(f"  → 成功: ステータスコード {response.status_code}")
            logger.info(f"  → エンコーディング: {response.encoding}")
            return True
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def extract_observed_at(self) -> bool:
        """観測日時を抽出"""
        logger.info(f"✓ テスト2: 観測日時の抽出")
        try:
            # "観測日時：2026-02-16 10:30" を探す
            text = self.soup.get_text()
            match = re.search(r'観測日時[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text)
            if match:
                self.data['observed_at'] = match.group(1).strip()
                logger.info(f"  → 成功: {self.data['observed_at']}")
                return True
            else:
                logger.error(f"  → 失敗: 観測日時が見つかりませんでした")
                return False
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def extract_captured_at(self) -> bool:
        """撮影日時を抽出して変換"""
        logger.info(f"✓ テスト3: 撮影日時の抽出と変換")
        try:
            # "撮影日時：02/16 10:32" を探す
            text = self.soup.get_text()
            match = re.search(r'撮影日時[：:]\s*(\d{2}/\d{2})\s+(\d{2}:\d{2})', text)
            if match:
                # MM/DD HH:MM → YYYY-MM-DD HH:MM に変換
                month_day = match.group(1)
                time = match.group(2)
                # 観測日時から年を取得
                if 'observed_at' in self.data:
                    year = self.data['observed_at'][:4]
                else:
                    year = str(datetime.now().year)

                captured_str = f"{year}-{month_day.replace('/', '-')} {time}"
                self.data['captured_at'] = captured_str
                logger.info(f"  → 成功: {match.group(1)} {time} → {captured_str}")
                return True
            else:
                logger.error(f"  → 失敗: 撮影日時が見つかりませんでした")
                return False
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def extract_location_address(self) -> bool:
        """住所を抽出"""
        logger.info(f"✓ テスト4: 住所の抽出")
        try:
            # class="style3" の div を探す
            div = self.soup.find('div', class_='style3')
            if div:
                address = div.get_text().strip()
                self.data['location_address'] = address
                logger.info(f"  → 成功: {address}")
                return True
            else:
                logger.error(f"  → 失敗: 住所が見つかりませんでした")
                return False
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def extract_weather_data(self) -> bool:
        """気象データを抽出"""
        logger.info(f"✓ テスト5-6: 気象データの抽出")
        try:
            # テーブルから観測地点名と気象データを探す
            tables = self.soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) == 2:
                        label = cols[0].get_text().strip()
                        value = cols[1].get_text().strip()

                        if label == '観測地点':
                            self.data['location_name'] = value
                            logger.info(f"  → 観測地点: {value}")
                        elif label == '累加雨量':
                            # "0mm" → 0.0
                            num = re.search(r'([\d.]+)', value)
                            self.data['cumulative_rainfall'] = float(num.group(1)) if num else None
                            logger.info(f"  → 累加雨量: {value} → {self.data['cumulative_rainfall']}")
                        elif label == '気温':
                            # "5.0℃" → 5.0
                            num = re.search(r'([\d.]+)', value)
                            self.data['temperature'] = float(num.group(1)) if num else None
                            logger.info(f"  → 気温: {value} → {self.data['temperature']}")
                        elif label == '風速':
                            # "1.8m/s" → 1.8
                            num = re.search(r'([\d.]+)', value)
                            self.data['wind_speed'] = float(num.group(1)) if num else None
                            logger.info(f"  → 風速: {value} → {self.data['wind_speed']}")
                        elif label == '路面温度':
                            # "8.2℃" → 8.2
                            num = re.search(r'([\d.]+)', value)
                            self.data['road_temperature'] = float(num.group(1)) if num else None
                            logger.info(f"  → 路面温度: {value} → {self.data['road_temperature']}")
                        elif label == '路面状況':
                            self.data['road_condition'] = value
                            logger.info(f"  → 路面状況: {value}")

            # 必須項目のチェック
            required = ['location_name', 'cumulative_rainfall', 'temperature',
                       'wind_speed', 'road_temperature', 'road_condition']
            missing = [k for k in required if k not in self.data]

            if missing:
                logger.error(f"  → 失敗: 未取得項目 {missing}")
                return False

            logger.info(f"  → 成功: すべての気象データを取得")
            return True
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def extract_image_url(self) -> bool:
        """画像URLを抽出して絶対URLに変換"""
        logger.info(f"✓ テスト7: 画像URLの抽出")
        try:
            # <img src="image/DR-74125-l.jpg" alt=""> を探す
            img_tag = self.soup.find('img', src=re.compile(r'DR-\d+-l\.jpg'))
            if img_tag:
                relative_url = img_tag['src']
                absolute_url = urljoin(self.url, relative_url)
                self.data['image_url'] = absolute_url
                logger.info(f"  → 相対URL: {relative_url}")
                logger.info(f"  → 絶対URL: {absolute_url}")

                # ファイル名生成（YYYYMMDD_HHMMSS_DR-74125.jpg）
                if 'observed_at' in self.data:
                    timestamp = self.data['observed_at'].replace('-', '').replace(':', '').replace(' ', '_')
                    filename_match = re.search(r'(DR-\d+-l)\.jpg', relative_url)
                    if filename_match:
                        base = filename_match.group(1)
                        filename = f"{timestamp}_{base}.jpg"
                        self.data['image_filename'] = filename
                        logger.info(f"  → 保存ファイル名: {filename}")

                return True
            else:
                logger.error(f"  → 失敗: 画像URLが見つかりませんでした")
                return False
        except Exception as e:
            logger.error(f"  → 失敗: {e}")
            return False

    def run_test(self) -> Dict:
        """すべてのテストを実行"""
        logger.info("=" * 60)
        logger.info("Delta地点 スクレイピングテスト開始")
        logger.info("=" * 60)

        results = {}

        # テスト1: HTML取得
        results['fetch_html'] = self.fetch_html()
        if not results['fetch_html']:
            logger.error("HTML取得に失敗したため、テストを中断します")
            return results

        # テスト2: 観測日時
        results['observed_at'] = self.extract_observed_at()

        # テスト3: 撮影日時
        results['captured_at'] = self.extract_captured_at()

        # テスト4: 住所
        results['location_address'] = self.extract_location_address()

        # テスト5-6: 気象データ
        results['weather_data'] = self.extract_weather_data()

        # テスト7: 画像URL
        results['image_url'] = self.extract_image_url()

        # 結果サマリー
        logger.info("=" * 60)
        logger.info("テスト結果サマリー")
        logger.info("=" * 60)
        success = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"成功: {success}/{total}")

        for test_name, result in results.items():
            status = "✓ PASS" if result else "✗ FAIL"
            logger.info(f"  {status}: {test_name}")

        # 取得データ一覧
        if any(results.values()):
            logger.info("=" * 60)
            logger.info("取得データ一覧")
            logger.info("=" * 60)
            for key, value in self.data.items():
                logger.info(f"  {key}: {value}")

        return results


def main():
    """メイン実行"""
    url = "http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html"

    scraper = DeltaStationScraper(url)
    results = scraper.run_test()

    # すべて成功したか確認
    if all(results.values()):
        logger.info("\n🎉 すべてのテストに成功しました！")
        return 0
    else:
        logger.warning("\n⚠️  一部のテストに失敗しました")
        return 1


if __name__ == "__main__":
    exit(main())
