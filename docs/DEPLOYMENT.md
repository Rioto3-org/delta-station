# デプロイメントガイド

Delta地点観測データベースシステムの運用開始手順。

## システム概要

このシステムは15分間隔で実行され、以下を自動実行します：
1. 国土交通省の道路情報ページをスクレイピング
2. 気象データをSQLiteデータベースに保存
3. カメラ画像をローカルストレージに保存

## セットアップ手順

### 1. 依存パッケージのインストール

```bash
pip install requests beautifulsoup4 lxml pydantic
```

または

```bash
pip install -r requirements.txt  # TODO: requirements.txt作成
```

### 2. 初回実行テスト

本番スクリプトを手動実行して動作確認：

```bash
make run
```

成功すると以下が生成されます：
- `outputs/database/delta_station.db` - データベース
- `outputs/images/*.jpg` - 観測画像
- `outputs/scraper.log` - 実行ログ

### 3. cronジョブのインストール

15分間隔で自動実行するよう設定：

```bash
make install-cron
```

これにより、以下のcronジョブが登録されます：
```
*/15 * * * * cd /path/to/delta-station && make run >> /path/to/delta-station/outputs/scraper.log 2>&1
```

**実行タイミング:** 毎時0分、15分、30分、45分

### 4. 動作確認

cronジョブの状態とログを確認：

```bash
make status
```

## 運用コマンド

| コマンド | 説明 |
|---------|------|
| `make run` | 手動実行（デバッグ用） |
| `make status` | cronジョブ状態とログ確認 |
| `make uninstall-cron` | cronジョブ削除 |
| `make test` | スクレイピングテスト |
| `make test-db` | DB挿入テスト |

## データの所在

```
delta-station/
└── outputs/
    ├── database/
    │   └── delta_station.db      # 観測データDB
    ├── images/
    │   └── *.jpg                  # 観測画像
    └── scraper.log                # 実行ログ
```

## トラブルシューティング

### データが挿入されない

**原因:** サイト側のデータが更新されていない

**ログ例:**
```
→ データ未更新（既存データ: 2026-02-16 10:30）
```

**対応:** 正常動作。次回更新を待つ。

### HTML取得失敗

**原因:** ネットワークエラーまたはサイト側の問題

**ログ例:**
```
✗ HTML取得失敗
```

**対応:**
1. ネットワーク接続を確認
2. 手動で再実行: `make run`
3. 次回のcron実行を待つ

### 画像ダウンロード失敗

**原因:** 画像URLの変更またはネットワークエラー

**ログ例:**
```
⚠ 画像ダウンロード失敗（処理続行）
```

**対応:** データベースには記録されるため、画像のみ後で取得可能。

## 監視のポイント

### 正常運用時のログパターン

15分ごとに以下のいずれか：

**新規データ取得時:**
```
✓ 新規データ挿入: 2026-02-16 11:00
  気温: 4.7℃, 風速: 1.3m/s
```

**データ未更新時:**
```
→ データ未更新（既存データ: 2026-02-16 11:00）
```

### 異常検知

**1時間以上新規データなし:**
```bash
tail -100 outputs/scraper.log | grep "新規データ挿入"
```

最終挿入が1時間以上前 → サイト側の問題の可能性

**エラーが連続:**
```bash
tail -100 outputs/scraper.log | grep "✗"
```

連続してエラー → 調査が必要

## アンインストール

```bash
# cronジョブ削除
make uninstall-cron

# データ削除（任意）
rm -rf outputs/
```

## 次のステップ

- [ARCHITECTURE.md](ARCHITECTURE.md) - システム設計思想
- [MIGRATION.md](MIGRATION.md) - 将来の移行戦略
