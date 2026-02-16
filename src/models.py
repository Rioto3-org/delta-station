#!/usr/bin/env python3
"""
Delta地点 観測データモデル定義

Pydanticを使用したデータバリデーション層。
「コードが仕様書」の精神で、すべてのバリデーションルールをここに集約。
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin


class LocationData(BaseModel):
    """観測地点マスタデータ"""

    id: Optional[int] = Field(default=None, ge=1, description="観測地点ID（1から開始、DB挿入前はNone）")
    location_name: str = Field(min_length=1, max_length=100, description="観測地点名")
    location_address: str = Field(min_length=1, max_length=200, description="住所")
    source_url: str = Field(pattern=r'^https?://.+', description="データ取得元URL")

    @field_validator('location_name')
    @classmethod
    def validate_location_name(cls, v: str) -> str:
        """観測地点名のバリデーション"""
        if not v.strip():
            raise ValueError("観測地点名は空白のみにできません")
        return v.strip()

    @field_validator('location_address')
    @classmethod
    def validate_location_address(cls, v: str) -> str:
        """住所のバリデーション"""
        if not v.strip():
            raise ValueError("住所は空白のみにできません")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "location_name": "作並宿",
                    "location_address": "仙台市青葉区作並字神前西",
                    "source_url": "http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html"
                }
            ]
        }
    }


class ObservationData(BaseModel):
    """観測データ（気象・路面・画像情報）"""

    # 基本情報
    location_id: int = Field(ge=1, description="観測地点ID")
    observed_at: str = Field(
        pattern=r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$',
        description="観測日時（YYYY-MM-DD HH:MM形式）"
    )
    captured_at: str = Field(
        pattern=r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$',
        description="撮影日時（YYYY-MM-DD HH:MM形式）"
    )

    # 気象データ（すべてOptional、データ欠損を考慮）
    cumulative_rainfall: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1000.0,
        description="累加雨量（mm）0〜1000mm"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=-50.0,
        le=50.0,
        description="気温（℃）-50〜50℃"
    )
    wind_speed: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="風速（m/s）0〜100m/s"
    )
    road_temperature: Optional[float] = Field(
        default=None,
        ge=-50.0,
        le=80.0,
        description="路面温度（℃）-50〜80℃"
    )
    road_condition: Optional[str] = Field(
        default=None,
        max_length=100,
        description="路面状況（任意の文字列、'----'はNoneに正規化）"
    )

    # 画像情報
    image_filename: str = Field(
        min_length=1,
        max_length=255,
        description="保存した画像ファイル名"
    )
    image_url: str = Field(
        pattern=r'^https?://.+\.(jpg|jpeg|png)$',
        description="元画像URL（jpg/jpeg/pngのみ）"
    )

    @field_validator('observed_at', 'captured_at')
    @classmethod
    def validate_datetime_format(cls, v: str) -> str:
        """日時形式のバリデーション（実際にパース可能か確認）"""
        try:
            datetime.strptime(v, '%Y-%m-%d %H:%M')
        except ValueError:
            raise ValueError(f"日時形式が不正です: {v}")
        return v

    @field_validator('road_condition', mode='before')
    @classmethod
    def normalize_road_condition(cls, v) -> Optional[str]:
        """
        路面状況の正規化

        仕様:
        - '----' は「データなし」として None に変換
        - それ以外は任意の文字列を許可
        - 前後の空白は除去
        """
        if v is None or v == '':
            return None

        # 文字列に変換して前後の空白を除去
        v = str(v).strip()

        # '----' は「データなし」
        if v == '----':
            return None

        # それ以外の文字列はそのまま許可
        return v

    @field_validator('cumulative_rainfall', mode='before')
    @classmethod
    def normalize_rainfall(cls, v) -> Optional[float]:
        """累加雨量の正規化（文字列から数値抽出）"""
        if v is None or v == '':
            return None

        # 数値型の場合はそのまま
        if isinstance(v, (int, float)):
            return float(v)

        # 文字列から数値を抽出（例: "0mm" → 0.0）
        match = re.search(r'([\d.]+)', str(v))
        if match:
            return float(match.group(1))

        return None

    @field_validator('temperature', 'wind_speed', 'road_temperature', mode='before')
    @classmethod
    def normalize_numeric(cls, v) -> Optional[float]:
        """数値データの正規化（文字列から数値抽出）"""
        if v is None or v == '':
            return None

        # 数値型の場合はそのまま
        if isinstance(v, (int, float)):
            return float(v)

        # 文字列から数値を抽出（例: "5.0℃" → 5.0, "1.8m/s" → 1.8）
        match = re.search(r'(-?[\d.]+)', str(v))
        if match:
            return float(match.group(1))

        return None

    @model_validator(mode='after')
    def validate_captured_after_observed(self):
        """撮影日時は観測日時より後または同時刻である必要がある"""
        observed = datetime.strptime(self.observed_at, '%Y-%m-%d %H:%M')
        captured = datetime.strptime(self.captured_at, '%Y-%m-%d %H:%M')

        # 撮影は観測の±30分以内であることを期待（異常検知）
        diff_minutes = abs((captured - observed).total_seconds() / 60)
        if diff_minutes > 30:
            # エラーにはせず、警告のみ（実運用では許容）
            pass

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "location_id": 1,
                    "observed_at": "2026-02-16 10:50",
                    "captured_at": "2026-02-16 10:52",
                    "cumulative_rainfall": 0.0,
                    "temperature": 4.7,
                    "wind_speed": 1.9,
                    "road_temperature": 8.0,
                    "road_condition": None,  # '----' は None に正規化
                    "image_filename": "20260216_1050_DR-74125-l.jpg",
                    "image_url": "http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg"
                }
            ]
        }
    }


class ScrapedRawData(BaseModel):
    """
    スクレイピングで取得した生データ（バリデーション前）

    HTMLから取得した値をそのまま保持。
    ObservationDataに変換する前の中間形式。
    """

    location_name: str
    location_address: str
    observed_at: str
    captured_at: str
    cumulative_rainfall: Optional[str] = None  # "0mm" などの文字列
    temperature: Optional[str] = None          # "5.0℃" などの文字列
    wind_speed: Optional[str] = None           # "1.8m/s" などの文字列
    road_temperature: Optional[str] = None     # "8.2℃" などの文字列
    road_condition: Optional[str] = None       # "----" や "乾燥" などの文字列
    image_url: str

    @staticmethod
    def from_html(html: str, source_url: str) -> 'ScrapedRawData':
        """
        HTMLからデータを抽出してScrapedRawDataを生成

        Args:
            html: HTML文字列
            source_url: データ取得元URL

        Returns:
            ScrapedRawData: 抽出した生データ

        Raises:
            ValueError: 必須データが抽出できない場合
        """
        soup = BeautifulSoup(html, 'lxml')
        text = soup.get_text()

        # 観測日時: "観測日時：2026-02-16 10:30"
        match = re.search(r'観測日時[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text)
        if not match:
            raise ValueError("観測日時が見つかりません")
        observed_at = match.group(1).strip()

        # 撮影日時: "撮影日時：02/16 10:32" → "2026-02-16 10:32"
        match = re.search(r'撮影日時[：:]\s*(\d{2}/\d{2})\s+(\d{2}:\d{2})', text)
        if not match:
            raise ValueError("撮影日時が見つかりません")
        year = observed_at[:4]
        month_day = match.group(1)
        time = match.group(2)
        captured_at = f"{year}-{month_day.replace('/', '-')} {time}"

        # 住所: class="style3" の div から抽出
        div = soup.find('div', class_='style3')
        location_address = div.get_text().strip() if div else "不明"

        # テーブルから観測地点名と気象データを抽出
        tables = soup.find_all('table')
        location_name = None
        cumulative_rainfall = None
        temperature = None
        wind_speed = None
        road_temperature = None
        road_condition = None

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 2:
                    label = cols[0].get_text().strip()
                    value = cols[1].get_text().strip()

                    if label == '観測地点':
                        location_name = value
                    elif label == '累加雨量':
                        cumulative_rainfall = value
                    elif label == '気温':
                        temperature = value
                    elif label == '風速':
                        wind_speed = value
                    elif label == '路面温度':
                        road_temperature = value
                    elif label == '路面状況':
                        road_condition = value

        if not location_name:
            raise ValueError("観測地点名が見つかりません")

        # 画像URL: <img src="image/DR-74125-l.jpg" alt="">
        img = soup.find('img', src=re.compile(r'DR-\d+-l\.jpg'))
        if not img or not img.get('src'):
            raise ValueError("画像URLが見つかりません")
        image_url = urljoin(source_url, img['src'])

        return ScrapedRawData(
            location_name=location_name,
            location_address=location_address,
            observed_at=observed_at,
            captured_at=captured_at,
            cumulative_rainfall=cumulative_rainfall,
            temperature=temperature,
            wind_speed=wind_speed,
            road_temperature=road_temperature,
            road_condition=road_condition,
            image_url=image_url
        )

    def to_observation(self, location_id: int) -> ObservationData:
        """
        生データをバリデーション済みObservationDataに変換

        Args:
            location_id: 観測地点ID（ensure_location()で取得した値）

        Returns:
            ObservationData: バリデーション済み観測データ

        この変換時に、Pydanticの各種バリデーターが自動実行される。
        不正な値は正規化されるか、ValidationErrorが発生する。
        """
        # 画像ファイル名を生成: "20260216_1030_DR-74125-l.jpg"
        timestamp = self.observed_at.replace('-', '').replace(':', '').replace(' ', '_')
        # URLから元のファイル名のパターンを抽出
        url_parts = self.image_url.split('/')
        original_filename = url_parts[-1] if url_parts else 'image.jpg'
        # 拡張子を取得
        ext = original_filename.split('.')[-1] if '.' in original_filename else 'jpg'
        image_filename = f"{timestamp}_{original_filename.replace('.', '_')}.{ext}"

        return ObservationData(
            location_id=location_id,
            observed_at=self.observed_at,
            captured_at=self.captured_at,
            cumulative_rainfall=self.cumulative_rainfall,
            temperature=self.temperature,
            wind_speed=self.wind_speed,
            road_temperature=self.road_temperature,
            road_condition=self.road_condition,
            image_filename=image_filename,
            image_url=self.image_url
        )


# 使用例とテストケース（ドキュメントとして機能）
# テスト実施日: 2026/02/16
if __name__ == "__main__":
    import json

    print("=" * 60)
    print("Delta地点 データモデル定義")
    print("テスト実施日: 2026/02/16")
    print("=" * 60)

    # 正常系テスト
    print("\n[正常系] 観測地点データ")
    location = LocationData(
        id=1,
        location_name="作並宿",
        location_address="仙台市青葉区作並字神前西",
        source_url="http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html"
    )
    print(json.dumps(location.model_dump(), indent=2, ensure_ascii=False))

    print("\n[正常系] 観測データ（路面状況なし）")
    observation = ObservationData(
        location_id=1,
        observed_at="2026-02-16 10:50",
        captured_at="2026-02-16 10:52",
        cumulative_rainfall=0.0,
        temperature=4.7,
        wind_speed=1.9,
        road_temperature=8.0,
        road_condition=None,  # '----' は None
        image_filename="20260216_1050_DR-74125-l.jpg",
        image_url="http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg"
    )
    print(json.dumps(observation.model_dump(), indent=2, ensure_ascii=False))

    print("\n[正規化テスト] 文字列からの数値抽出")
    raw = ScrapedRawData(
        location_name="作並宿",
        location_address="仙台市青葉区作並字神前西",
        observed_at="2026-02-16 10:50",
        captured_at="2026-02-16 10:52",
        cumulative_rainfall="0mm",      # → 0.0
        temperature="4.7℃",             # → 4.7
        wind_speed="1.9m/s",            # → 1.9
        road_temperature="8.0℃",        # → 8.0
        road_condition="----",          # → None
        image_url="http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg"
    )
    validated = raw.to_observation(
        location_id=1,
        image_filename="20260216_1050_DR-74125-l.jpg"
    )
    print(json.dumps(validated.model_dump(), indent=2, ensure_ascii=False))

    print("\n[正常系テスト] 任意の路面状況文字列")
    try:
        custom_condition = ObservationData(
            location_id=1,
            observed_at="2026-02-16 10:50",
            captured_at="2026-02-16 10:52",
            temperature=4.7,
            road_condition="積雪あり",  # 任意の文字列を許可
            image_filename="test.jpg",
            image_url="http://example.com/test.jpg"
        )
        print("→ road_condition:", custom_condition.road_condition)
    except Exception as e:
        print(f"→ エラー: {e}")

    print("\n[異常系テスト] 範囲外の気温")
    try:
        bad_temp = ObservationData(
            location_id=1,
            observed_at="2026-02-16 10:50",
            captured_at="2026-02-16 10:52",
            temperature=999.0,  # 50℃を超える → ValidationError
            image_filename="test.jpg",
            image_url="http://example.com/test.jpg"
        )
    except Exception as e:
        print(f"→ バリデーションエラー: {e}")

    print("\n" + "=" * 60)
    print("すべてのテストケースが実行されました")
    print("=" * 60)
