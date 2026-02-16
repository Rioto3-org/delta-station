# Delta地点 定点観測システム 設計書

## 概要
国土交通省東北地方整備局の道路情報ページから、定点観測データ（気象・路面状況・カメラ画像）を10分間隔で自動取得し、SQLiteデータベースに保存するシステム。

## データソース
- URL: http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html
- 更新間隔: 15分（実際の取得は10分間隔で実施）
- 対象地点: 作並宿（チェーン着脱所）

## データベース設計

### テーブル構成

#### 1. locations（観測地点マスタ）
観測地点の基本情報を管理するマスタテーブル。

| カラム名 | 型 | 制約 | 説明 |
|---------|-----|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT | 観測地点ID（No.1から開始） |
| location_name | TEXT | NOT NULL, UNIQUE | 観測地点名 |
| location_address | TEXT | - | 住所 |
| source_url | TEXT | NOT NULL | データ取得元URL |

**初期データ（No.1）:**
- id: 1
- location_name: 作並宿
- location_address: 仙台市青葉区作並字神前西
- source_url: http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html

#### 2. observations（観測データ）
定点観測で取得した気象・路面データと画像情報を記録するテーブル。

| カラム名 | 型 | 制約 | 説明 |
|---------|-----|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT | レコードID |
| location_id | INTEGER | NOT NULL, FOREIGN KEY | 観測地点ID（locationsへの参照） |
| observed_at | TEXT | NOT NULL, UNIQUE | 観測日時（ISO 8601: YYYY-MM-DD HH:MM） |
| captured_at | TEXT | NOT NULL | 撮影日時（ISO 8601: YYYY-MM-DD HH:MM） |
| cumulative_rainfall | REAL | - | 累加雨量（mm） |
| temperature | REAL | - | 気温（℃） |
| wind_speed | REAL | - | 風速（m/s、直前10分間の平均） |
| road_temperature | REAL | - | 路面温度（℃） |
| road_condition | TEXT | - | 路面状況 |
| image_filename | TEXT | NOT NULL | 保存した画像ファイル名 |
| image_url | TEXT | NOT NULL | 元画像URL |
| created_at | TEXT | NOT NULL, DEFAULT | レコード作成日時 |

**UNIQUE制約:** `observed_at` に設定し、同一観測時刻のデータ重複を防止。

## データ取得仕様

### HTMLから抽出する情報

#### 観測日時（observed_at）
```html
<td align="center" class="style2">観測日時：2026-02-16 10:30 </td>
```
- 形式: `YYYY-MM-DD HH:MM`
- 用途: observations.observed_at（UNIQUE制約）

#### 撮影日時（captured_at）
```html
<td align="center" class="style2">撮影日時：02/16 10:32 <br>
```
- 元形式: `MM/DD HH:MM`
- 変換後: `YYYY-MM-DD HH:MM`
- 用途: observations.captured_at

#### 住所（location_address）
```html
<div class="style3">仙台市青葉区作並字神前西</div>
```
- 用途: locations.location_address

#### 気象データ
テーブル内の各行から抽出:
```html
<tr>
    <td bgcolor="#CCCCCC" class="style3">観測地点</td>
    <td bgcolor="#FFFFFF" class="style3">作並宿</td>
</tr>
<tr>
    <td bgcolor="#CCCCCC" class="style3">累加雨量</td>
    <td bgcolor="#FFFFFF" class="style3">0mm</td>
</tr>
<tr>
    <td bgcolor="#CCCCCC" class="style3">気温</td>
    <td bgcolor="#FFFFFF" class="style3">5.0℃</td>
</tr>
<tr>
    <td bgcolor="#CCCCCC" class="style3">風速</td>
    <td bgcolor="#FFFFFF" class="style3">1.8m/s</td>
</tr>
<tr>
    <td bgcolor="#CCCCCC" class="style3">路面温度</td>
    <td bgcolor="#FFFFFF" class="style3">8.2℃</td>
</tr>
<tr>
    <td bgcolor="#CCCCCC" class="style3">路面状況</td>
    <td bgcolor="#FFFFFF" class="style3">----</td>
</tr>
```

| 項目 | 抽出値 | 変換処理 | DB格納値 |
|------|--------|----------|---------|
| 観測地点 | 作並宿 | - | locations.location_name |
| 累加雨量 | 0mm | 数値のみ抽出 | 0.0 |
| 気温 | 5.0℃ | 数値のみ抽出 | 5.0 |
| 風速 | 1.8m/s | 数値のみ抽出 | 1.8 |
| 路面温度 | 8.2℃ | 数値のみ抽出 | 8.2 |
| 路面状況 | ---- | そのまま | ---- |

#### 画像URL
```html
<td align="center"><img src="image/DR-74125-l.jpg" alt=""></td>
```
- 相対パス: `image/DR-74125-l.jpg`
- 絶対URL: `http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg`
- 保存ファイル名形式: `YYYYMMDD_HHMMSS_DR-74125.jpg`
  - 例: `20260216_103000_DR-74125.jpg`

## データサンプル

### 観測データサンプル（2026-02-16 10:30）

```
location_id: 1
observed_at: 2026-02-16 10:30
captured_at: 2026-02-16 10:32
cumulative_rainfall: 0.0
temperature: 5.0
wind_speed: 1.8
road_temperature: 8.2
road_condition: ----
image_filename: 20260216_103000_DR-74125.jpg
image_url: http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg
```

## 実装要件

### 1. HTML取得とパース
- requests + BeautifulSoup4を使用
- タイムアウト設定: 30秒
- エラー時のリトライ: 3回まで

### 2. 画像取得・保存
- 保存先ディレクトリ: `./images/`
- ファイル名形式: `YYYYMMDD_HHMMSS_DR-74125.jpg`
- 画像が既に存在する場合はスキップ

### 3. データベース操作
- SQLite3を使用
- observed_atのUNIQUE制約により重複防止
- 外部キー制約を有効化（PRAGMA foreign_keys = ON）

### 4. エラーハンドリング
- ネットワークエラー
- HTMLパースエラー
- データベースエラー
- 画像ダウンロードエラー

### 5. ログ出力
- 標準出力にログを出力
- 形式: `[YYYY-MM-DD HH:MM:SS] LEVEL: message`
- レベル: INFO, WARNING, ERROR

### 6. cron実行設定
- 実行間隔: 10分ごと
- crontab設定例:
```
*/10 * * * * /usr/bin/python3 /path/to/scraper.py >> /path/to/scraper.log 2>&1
```

## ディレクトリ構成

```
delta-station/
├── README.md              # プロジェクト概要
├── DESIGN.md             # 本設計書
├── schema.sql            # データベーススキーマ
├── scraper.py            # スクレイピングスクリプト（実装予定）
├── requirements.txt      # Python依存パッケージ（実装予定）
├── delta_station.db      # SQLiteデータベース（実行時に生成）
└── images/               # 取得画像保存ディレクトリ（実行時に生成）
    └── 20260216_103000_DR-74125.jpg
```

## 次のステップ
1. scraper.pyの実装
2. requirements.txtの作成
3. データベース初期化スクリプト
4. cron設定の自動化
5. 動作テスト
