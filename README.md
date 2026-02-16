# Delta地点 観測データベースシステム

国土交通省東北地方整備局の道路情報ページから定点観測データ（気象・路面状況・カメラ画像）を15分間隔で自動取得し、SQLiteデータベースに保存するシステム。

## 概要

このプロジェクト自体が「Delta地点観測データベースシステム」として機能します。
分析スクリプトや他のアプリケーションは、`outputs/database/delta_station.db` を直接参照してデータを利用できます。

### 主な機能

- **自動スクレイピング**: 15分間隔で観測データを取得
- **データベース保存**: SQLiteに気象データを記録
- **画像アーカイブ**: 観測カメラ画像をローカル保存
- **冪等性保証**: 重複データは自動スキップ（observed_at UNIQUE制約）

## クイックスタート

### ローカル環境で実行（開発・テスト用）

```bash
# 1. 依存パッケージのインストール
pip install uv
uv sync

# 2. 自動実行の開始（15分間隔）
make start

# 3. 状態確認
make status

# 4. 停止
make stop
```

### Docker環境で実行（本番運用推奨）

```bash
# 1. Dockerイメージをビルド
make docker-build

# 2. コンテナを起動（15分間隔で自動実行）
make docker-start

# 3. ログをリアルタイム確認
make docker-logs

# 4. コンテナの状態確認
make docker-status

# 5. コンテナを停止
make docker-stop
```

**Docker環境の利点：**
- 完全な環境再現性（OS、Python、依存関係すべて固定）
- ホストシステムへの影響なし
- デプロイが簡単（どこでも同じ環境）
- 将来的な分析基盤との統合が容易

## データの利用

### データベースへのアクセス

```python
import sqlite3
import pandas as pd

# データベースに接続
DB_PATH = "/path/to/delta-station/outputs/database/delta_station.db"
conn = sqlite3.connect(DB_PATH)

# データ取得
df = pd.read_sql("""
    SELECT
        o.observed_at,
        o.temperature,
        o.wind_speed,
        o.road_temperature,
        l.location_name
    FROM observations o
    JOIN locations l ON o.location_id = l.id
    WHERE o.observed_at >= '2026-02-01'
    ORDER BY o.observed_at
""", conn)

conn.close()
```

### 画像ファイル

```
outputs/images/20260216_1100_DR-74125-l.jpg
```

画像ファイル名は `YYYYMMDD_HHMM_[地点ID].jpg` の形式です。

## プロジェクト構成

```
delta-station/
├── src/                    # ソースコード
│   ├── scraper.py         # 本番スクリプト
│   └── models.py          # データモデル
├── tests/                  # テストコード
├── database/               # スキーマ定義
│   └── schema.sql
├── docs/                   # ドキュメント
│   ├── DEPLOYMENT.md      # デプロイ手順
│   ├── ARCHITECTURE.md    # 設計思想
│   └── MIGRATION.md       # 移行戦略
├── outputs/                # 実行結果（.gitignore対象）
│   ├── database/          # データベース
│   │   └── delta_station.db
│   ├── images/            # 観測画像
│   └── scraper.log        # 実行ログ
├── Makefile               # 運用コマンド
└── README.md              # 本ファイル
```

## 運用コマンド

### ローカル実行コマンド

| コマンド | 説明 |
|---------|------|
| `make start` | 再起動（停止してから開始） |
| `make run` | 15分間隔の自動実行を開始 |
| `make stop` | 自動実行を停止 |
| `make status` | 実行状態とログを確認 |

### Docker実行コマンド

| コマンド | 説明 |
|---------|------|
| `make docker-build` | Dockerイメージをビルド |
| `make docker-start` | コンテナを起動（15分間隔で自動実行） |
| `make docker-stop` | コンテナを停止 |
| `make docker-restart` | コンテナを再起動 |
| `make docker-logs` | ログをリアルタイム表示 |
| `make docker-status` | コンテナの状態を確認 |
| `make docker-clean` | コンテナ・イメージを完全削除 |

## データソース

- **URL**: http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html
- **対象地点**: 作並宿（チェーン着脱所）
- **観測項目**: 気温、風速、路面温度、路面状況、累加雨量
- **更新間隔**: 約15分（サイト側）

## システム設計

### 冪等性の保証

`observed_at` カラムにUNIQUE制約を設定することで、データ未更新時は自動的にスキップされます。
これにより、15分間隔で実行してもデータの重複や位相ずれを気にする必要がありません。

詳細は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照してください。

## トラブルシューティング

### データが挿入されない

```bash
# ログを確認
tail -50 outputs/scraper.log
```

**「データ未更新（既存データ）」と表示される場合:**
- 正常動作です。サイト側のデータが更新されていません。

**「HTML取得失敗」と表示される場合:**
- ネットワーク接続を確認
- 次回のcron実行を待つ

### cronが動作しない

```bash
# cronジョブの確認
crontab -l | grep delta-station

# 手動実行で動作確認
make run
```

## 開発

### テスト実行

```bash
# スクレイピングテスト
make test

# データベース挿入テスト（テスト用DBを使用）
make test-db
```

### クリーンアップ

```bash
# キャッシュファイル削除
make clean

# 全データ削除（注意）
rm -rf outputs/
```

## ドキュメント

- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - デプロイメント手順
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - システム設計思想
- [MIGRATION.md](docs/MIGRATION.md) - 将来の移行戦略

## ライセンス

このプロジェクトは個人的な記録・分析用途で開発されています。

## 開発履歴

- **2026/02/16**: MVP実装完了
