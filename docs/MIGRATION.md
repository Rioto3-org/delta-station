# データ移行戦略

将来的な分析基盤への移行やスケールアウトに向けた戦略ドキュメント。

**注意:** これはMVP範囲外の将来的な検討事項です。現時点では実装不要ですが、設計判断の参考資料として記録します。

## 移行が必要になるケース

### 1. データ量の増加

**現状（SQLite）の限界:**
- データベースサイズ: 数百GB程度まで
- 同時接続: 読み込みは複数可、書き込みは1つのみ
- 画像ストレージ: ローカルディスク容量に依存

**移行が必要な兆候:**
- 画像が数万枚を超える（ディスク容量圧迫）
- 複数の分析プロセスからの同時アクセス
- リアルタイムダッシュボードの構築

### 2. 複数地点への拡張

現在は「作並宿」1地点のみ。将来的に複数地点を監視する場合。

### 3. 組織的な利用

個人利用から、チームや組織での共有利用に拡大する場合。

## 移行パターン

### パターンA: SQLiteのまま継続

**適用ケース:**
- データ量が数万レコード程度
- 単一ユーザーまたは読み取り専用の複数ユーザー
- シンプルさを優先

**実装:**
```
delta-station/outputs/database/delta_station.db
                     ↓
            分析ツールが直接接続
         （Pandas, DuckDB, Jupyter等）
```

**メリット:**
- 追加の設定不要
- 高速なローカルアクセス
- シンプルなバックアップ（ファイルコピー）

**デメリット:**
- 並行書き込み不可
- ネットワーク越しのアクセスに不向き

---

### パターンB: PostgreSQL/MySQLへの移行

**適用ケース:**
- 複数ユーザーからの同時アクセス
- データウェアハウス構築
- 本格的な分析基盤

#### 移行手順

**1. スキーマ移行**

```sql
-- PostgreSQL用スキーマ
-- database/schema_postgres.sql

CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    location_name VARCHAR(100) UNIQUE NOT NULL,
    location_address VARCHAR(200),
    source_url VARCHAR(500) NOT NULL
);

CREATE TABLE observations (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    observed_at TIMESTAMP NOT NULL UNIQUE,  -- TEXTからTIMESTAMPへ
    captured_at TIMESTAMP NOT NULL,
    cumulative_rainfall REAL,
    temperature REAL,
    wind_speed REAL,
    road_temperature REAL,
    road_condition VARCHAR(100),
    image_filename VARCHAR(255) NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_observed_at ON observations(observed_at DESC);
```

**2. データ移行**

```bash
# 方法1: sqlite3 → CSV → PostgreSQL
sqlite3 delta_station.db <<EOF
.headers on
.mode csv
.output observations.csv
SELECT * FROM observations;
EOF

psql -d target_db -c "\COPY observations FROM 'observations.csv' CSV HEADER"

# 方法2: pgloader（推奨）
apt install pgloader
pgloader delta_station.db postgresql://user:pass@host/dbname
```

**3. スクリプト修正**

```python
# src/scraper.py の修正箇所

# Before
import sqlite3
conn = sqlite3.connect("outputs/database/delta_station.db")

# After
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    database="delta_station",
    user="scraper",
    password="..."
)
```

**メリット:**
- 複数ユーザーからの同時アクセス
- トランザクション性能
- バックアップ・レプリケーション機能

**デメリット:**
- サーバー運用コスト
- 設定の複雑化

---

### パターンC: データレイク統合

**適用ケース:**
- 大規模データ分析
- 他のデータソースとの統合
- クラウドベースの分析基盤

#### 実装例

**1. 定期バックアップ**

```bash
# 毎日0時にS3へアップロード
0 0 * * * aws s3 sync /path/to/delta-station/outputs/ s3://bucket/delta-station/
```

**2. Athena/BigQueryでクエリ**

```sql
-- S3/GCSのパーティション構造
s3://bucket/delta-station/
├── database/delta_station.db
└── images/
    ├── year=2026/
    │   └── month=02/
    │       └── *.jpg

-- Athena等で外部テーブル定義
CREATE EXTERNAL TABLE observations ...
```

**メリット:**
- スケーラビリティ
- 他データとの統合が容易
- コスト効率（使った分だけ課金）

**デメリット:**
- クラウド依存
- レイテンシ増加

---

## 画像データの移行

### 現状（MVP）

```
outputs/images/
└── 20260216_1100_DR-74125-l.jpg
```

### 将来の選択肢

#### オプション1: オブジェクトストレージ（S3/GCS）

```python
# 画像保存時にS3へアップロード
import boto3

s3 = boto3.client('s3')
s3.upload_file(
    local_path,
    'delta-station-images',
    f'images/{year}/{month}/{filename}'
)

# DBには S3 URL を記録
image_url = f"s3://delta-station-images/images/2026/02/{filename}"
```

**メリット:**
- 容量制限なし
- 耐久性・可用性が高い
- CDN配信が可能

#### オプション2: 圧縮アーカイブ

```bash
# 古いデータを月次でアーカイブ
tar -czf images_202601.tar.gz outputs/images/202601*.jpg
mv images_202601.tar.gz archives/
```

**メリット:**
- ストレージ効率
- バックアップが容易

---

## 移行時のチェックリスト

### 事前準備

- [ ] **フルバックアップ**
  ```bash
  tar -czf delta-station_backup_$(date +%Y%m%d).tar.gz delta-station/outputs/
  ```

- [ ] **データ整合性確認**
  ```sql
  -- レコード数
  SELECT COUNT(*) FROM observations;

  -- 日時の連続性チェック
  SELECT observed_at, LAG(observed_at) OVER (ORDER BY observed_at) AS prev
  FROM observations
  WHERE ...
  ```

- [ ] **テスト環境での移行練習**
  - 本番データのコピーで実施
  - スクリプト動作確認

### 移行実行

- [ ] **ダウンタイム通知**
  - cron停止: `make uninstall-cron`
  - 利用者への通知

- [ ] **データ移行スクリプト実行**
  - スキーマ作成
  - データインポート
  - インデックス作成

- [ ] **整合性チェック**
  ```sql
  -- 移行前後でレコード数が一致するか
  SELECT COUNT(*) FROM observations;
  ```

### 移行後

- [ ] **スクリプトの接続先変更**
  - `src/scraper.py` の DB接続先
  - `src/models.py` の修正（必要に応じて）

- [ ] **画像パスの整合性確認**
  ```python
  # DBのimage_filenameとファイルシステムの整合性
  import os
  for row in cursor.execute("SELECT image_filename FROM observations"):
      assert os.path.exists(f"outputs/images/{row[0]}")
  ```

- [ ] **cron再開**
  ```bash
  make install-cron
  ```

- [ ] **1週間の監視期間**
  - ログ確認
  - データ挿入確認
  - エラー監視

---

## データベース設計の拡張検討

### 複数地点対応（将来）

現在の `locations` テーブル設計により、複数地点の追加は容易：

```sql
-- 新規地点の追加
INSERT INTO locations (id, location_name, location_address, source_url)
VALUES (
    2,
    '関山峠',
    '山形県上山市関山',
    'http://www2.thr.mlit.go.jp/sendai/html/DR-XXXXX.html'
);
```

スクリプト側の修正:

```python
# 複数地点に対応
LOCATIONS = [
    LocationData(id=1, name="作並宿", ...),
    LocationData(id=2, name="関山峠", ...),
]

for location in LOCATIONS:
    scraper = DeltaStationScraper(location.source_url)
    # ...
```

### 分析用ビュー

```sql
-- 時系列分析用ビュー
CREATE VIEW daily_stats AS
SELECT
    DATE(observed_at) as date,
    location_id,
    AVG(temperature) as avg_temp,
    MAX(temperature) as max_temp,
    MIN(temperature) as min_temp,
    AVG(wind_speed) as avg_wind
FROM observations
GROUP BY DATE(observed_at), location_id;
```

---

## コスト試算（参考）

### クラウド移行時のコスト概算

**前提:**
- 15分間隔 = 1日96回 × 365日 = 35,040レコード/年
- 画像サイズ: 平均50KB

**AWS S3（画像ストレージ）:**
- 容量: 35,040枚 × 50KB ≈ 1.75GB/年
- コスト: $0.023/GB/月 × 1.75GB ≈ $0.04/月

**AWS RDS（PostgreSQL）:**
- db.t3.micro: $0.017/時間 ≈ $12/月
- ストレージ: 20GB ≈ $2.30/月

**合計:** 約$15/月（年間$180）

---

## まとめ

### 当面の方針（MVP）

- SQLite + ローカルストレージで運用
- データ量・アクセスパターンを観察
- 移行判断は実際の利用状況を見て決定

### 移行の判断基準

| 指標 | 現状維持 | 移行検討 |
|------|---------|---------|
| データ量 | < 10万レコード | > 10万レコード |
| 画像枚数 | < 5万枚 | > 5万枚 |
| 同時アクセス | 読み取りのみ | 複数書き込み |
| 利用形態 | 個人 | チーム/組織 |

**重要:** 移行は必要になってから実施。過度な先行投資を避ける。
