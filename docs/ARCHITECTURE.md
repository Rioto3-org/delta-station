# アーキテクチャ設計

Delta地点観測データベースシステムの設計思想とアーキテクチャ。

## システム設計思想

### このプロジェクト自体がデータベースシステムである

```
delta-station/  ← 「Delta地点観測データベースシステム」として機能
├── outputs/
│   ├── database/delta_station.db  ← データストア
│   └── images/                    ← 画像ストア
└── src/scraper.py                 ← データ更新プロセス
```

**利用者（分析基盤など）の責務:**

```python
# 分析スクリプト例
import sqlite3

DB_PATH = "/path/to/delta-station/outputs/database/delta_station.db"
conn = sqlite3.connect(DB_PATH)

# データ取得
df = pd.read_sql("SELECT * FROM observations WHERE ...", conn)
```

**設計の利点:**
- データの所在が明確
- バックアップ・移行が容易（ディレクトリごとコピー）
- 疎結合な設計（利用側はパスを指定するだけ）
- ポータビリティが高い

## データ更新の冪等性設計

### 問題：サイトの更新周期が不定

公式には「15分間隔で更新」とされているが、実際には：
- 14分〜16分程度のズレがある
- メンテナンス時は更新が止まる
- ネットワーク遅延で取得タイミングがずれる

### 解決策：observed_at UNIQUE制約 + 15分間隔実行

```sql
CREATE TABLE observations (
    observed_at TEXT NOT NULL UNIQUE,  -- この制約が重要
    ...
);
```

**動作フロー:**

```
┌─────────────────┐
│ cron (*/15)     │ 15分ごとに実行
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ スクレイピング   │ HTMLを取得
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ observed_at     │ 2026-02-16 11:00
│ を抽出          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ INSERT試行      │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
 新規？    重複？
    │         │
    ▼         ▼
 挿入成功   スキップ
```

**メリット:**
1. **位相ずれ許容**: サイト更新が14分でも16分でも対応可能
2. **安全性**: 何度実行しても重複しない（冪等性）
3. **シンプル**: 複雑な状態管理が不要

## ファイル構成

### ディレクトリ構造

```
delta-station/
├── src/                    # ソースコード
│   ├── scraper.py         # 本番スクリプト
│   └── models.py          # データモデル（Pydantic）
├── tests/                  # テストコード
│   ├── test_scraper.py    # スクレイピングテスト
│   └── test_db_insert.py  # DB挿入テスト
├── database/               # スキーマ定義（バージョン管理対象）
│   └── schema.sql
├── docs/                   # ドキュメント
│   ├── DEPLOYMENT.md      # デプロイ手順
│   ├── ARCHITECTURE.md    # 本ドキュメント
│   └── MIGRATION.md       # 移行戦略
├── outputs/                # 実行結果（.gitignore対象）
│   ├── database/          # DBファイル
│   │   ├── delta_station.db        # 本番DB
│   │   └── test_delta_station.db   # テスト用DB
│   ├── images/            # 画像ファイル
│   └── scraper.log        # 実行ログ
├── Makefile               # 運用コマンド
├── pyproject.toml         # Python依存関係
└── README.md              # プロジェクト概要
```

### 役割分担

| ディレクトリ | 役割 | Git管理 |
|-------------|------|---------|
| `src/` | 本番コード | ✓ |
| `tests/` | テストコード | ✓ |
| `database/` | スキーマ定義 | ✓ |
| `docs/` | ドキュメント | ✓ |
| `outputs/` | 実行結果 | ✗ (.gitignore) |

## データモデル

### ER図

```
┌─────────────────┐
│ locations       │
├─────────────────┤
│ id (PK)         │◄──┐
│ location_name   │   │
│ location_address│   │
│ source_url      │   │
└─────────────────┘   │
                      │
                      │ FK
                      │
┌─────────────────┐   │
│ observations    │   │
├─────────────────┤   │
│ id (PK)         │   │
│ location_id     │───┘
│ observed_at (UQ)│  ← UNIQUE制約
│ captured_at     │
│ cumulative_...  │
│ temperature     │
│ wind_speed      │
│ road_temperature│
│ road_condition  │
│ image_filename  │
│ image_url       │
└─────────────────┘
```

### Pydanticバリデーション層

```
HTML (生データ)
    ↓
ScrapedRawData (文字列のまま)
    ↓ to_observation()
ObservationData (バリデーション済み)
    ↓
Database (挿入)
```

**バリデーション例:**
- `"5.0℃"` → `5.0` (float)
- `"----"` → `None` (データなし)
- 範囲チェック（気温: -50〜50℃）

## cron管理の設計判断

### なぜsystemd timerではなくcronか

| 項目 | cron | systemd timer |
|------|------|---------------|
| 設定場所 | プロジェクト内（Makefile） | システム全体（/etc/systemd/） |
| 保守性 | ✓ プロジェクト内で完結 | ✗ 設定が分散 |
| ポータビリティ | ✓ 簡単に移行可能 | ✗ 環境依存 |
| 機能 | シンプル | 高機能 |

**結論:** 保守性とポータビリティを優先してcronを採用。

### Makefileによる一元管理

```makefile
install-cron:  # cronジョブを設定
uninstall-cron:  # cronジョブを削除
status:  # 状態確認
```

**メリット:**
- `make install-cron` だけで設定完了
- 設定内容がバージョン管理される
- 環境移行が容易

## スケーラビリティ考察

### 現在の制約

- **単一サーバー運用**: 1台のマシンで完結
- **SQLite**: 並行書き込み不可
- **ローカルストレージ**: 画像は同一マシン

### 将来の拡張可能性

詳細は [MIGRATION.md](MIGRATION.md) を参照。

## セキュリティ考察

### 現在の対策

1. **User-Agent設定**: サイトへの負荷軽減を明示
2. **タイムアウト設定**: 30秒でリトライなし
3. **エラーハンドリング**: 異常時は次回実行を待つ

### 考慮事項

- **アクセス頻度**: 15分間隔（過度なアクセスではない）
- **robots.txt**: 対象サイトは公共情報で制限なし
- **利用目的**: 個人的な記録・分析用途

## 運用設計

### ログ戦略

```
outputs/scraper.log  # 全実行履歴
```

**ログレベル:**
- `INFO`: 正常動作（新規データ、重複スキップ）
- `WARNING`: 軽微な問題（画像DL失敗）
- `ERROR`: 重大な問題（HTML取得失敗、DB障害）

### 監視のポイント

1. **データ更新頻度**: 1時間以上新規データなし → 調査
2. **エラー率**: 連続してエラー → 対応必要
3. **ディスク容量**: 画像累積による容量圧迫

## まとめ

このシステムは以下の原則に基づいて設計されています：

1. **冪等性**: 何度実行しても安全
2. **自己完結性**: プロジェクト内で完結
3. **ポータビリティ**: 環境移行が容易
4. **シンプルさ**: 複雑な依存関係を避ける
5. **拡張性**: 将来の移行を考慮した設計
