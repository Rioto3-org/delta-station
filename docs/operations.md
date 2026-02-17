# Delta Station - 運用ガイド

## A/B デプロイメント方式

Delta Stationでは、安全な本番デプロイのために、スクレイパーコンテナをA/Bの2系統で運用します。

## コンテナ構成

- **scraper-a**: 本番用スクレイパー（通常運用）
- **scraper-b**: 開発/テスト用スクレイパー
- **dashboard**: 観測ダッシュボード（常時起動）

## 開発フロー

### 1. 開発時

**使っていない方のコンテナで開発を行う**

現在scraper-aが本番稼働中の場合、scraper-bを使用：

```bash
# scraper-bで開発・テスト
make docker-scraper-b

# ログ確認
make docker-scraper-b-logs
```

現在scraper-bが本番稼働中の場合、scraper-aを使用：

```bash
# scraper-aで開発・テスト
make docker-scraper-a

# ログ確認
make docker-scraper-a-logs
```

### 2. テスト確認

**最低1回は問題なくデータが保存されることを確認する**

```bash
# ログで実行状況を確認
make docker-scraper-b-logs  # または scraper-a-logs

# データベースを直接確認
sqlite3 outputs/database/delta_station.db "SELECT COUNT(*) FROM observations;"
sqlite3 outputs/database/delta_station.db "SELECT * FROM observations ORDER BY id DESC LIMIT 5;"
```

確認ポイント：
- ✅ スクレイピングが正常に完了している
- ✅ データがDBに正しく保存されている
- ✅ エラーが出ていない
- ✅ 15分間隔で正常に動作している

### 3. 本番切り替え

**テストが成功したら、本番環境を切り替える**

#### パターンA: scraper-a → scraper-b に切り替え

```bash
# 自動切り替え（B起動 → A停止）
make docker-switch-a-to-b
```

これにより：
1. scraper-bが起動（新バージョン）
2. scraper-aが停止（旧バージョン）
3. データ収集は継続（冪等性保証により重複なし）

#### パターンB: scraper-b → scraper-a に切り替え（ロールバック）

```bash
# 自動切り替え（A起動 → B停止）
make docker-switch-b-to-a
```

問題が発生した場合のロールバック用です。

### 4. 状態確認

全コンテナの稼働状況を確認：

```bash
make docker-status-all
```

出力例：
```
=== All Delta Station Containers ===
CONTAINER ID   IMAGE                    STATUS          NAMES
abc123...      delta-station-dashboard  Up 2 hours      delta-station-dashboard
def456...      delta-station-scraper    Up 10 minutes   delta-station-scraper-b
```

## 運用上の注意点

### データベースの冪等性

- A/Bコンテナが同時稼働しても問題ありません
- 同じ観測時刻のデータは `UNIQUE` 制約により重複保存されません
- 切り替え時のデータ欠損を防ぐため、一時的な並行稼働が推奨されます

### ダッシュボードへの影響

- ダッシュボードは常時起動のまま
- スクレイパーの切り替えはダッシュボードに影響しません
- 両者は `outputs/` ボリュームを共有

### ログの確認

```bash
# リアルタイムログ監視
make docker-scraper-a-logs  # または scraper-b-logs
make docker-dashboard-logs

# 最新100行のみ表示
docker logs --tail 100 delta-station-scraper-a
```

## トラブルシューティング

### コンテナが起動しない

```bash
# ビルドキャッシュをクリア
make docker-clean

# 再ビルド
make docker-scraper-a  # または scraper-b
```

### データが保存されない

```bash
# DBファイルの権限確認
ls -l outputs/database/delta_station.db

# コンテナ内で直接確認
docker exec -it delta-station-scraper-a /bin/sh
```

### 切り替えが失敗する

手動で切り替える場合：

```bash
# 新しい方を起動
make docker-scraper-b

# 動作確認後、古い方を停止
make docker-scraper-a-stop
```

## 定期メンテナンス

### 月次確認項目

- [ ] ログファイルのサイズ確認
- [ ] データベースのバックアップ
- [ ] ディスク容量の確認
- [ ] 画像ファイルの整理

### バックアップ

```bash
# データベースバックアップ
cp outputs/database/delta_station.db outputs/database/delta_station_backup_$(date +%Y%m%d).db

# 古いバックアップの削除（30日以前）
find outputs/database/ -name "delta_station_backup_*.db" -mtime +30 -delete
```

## Makefileコマンド一覧

| コマンド | 説明 |
|---------|------|
| `make docker-dashboard` | ダッシュボード起動 |
| `make docker-dashboard-logs` | ダッシュボードログ表示 |
| `make docker-scraper-a` | スクレイパーA起動 |
| `make docker-scraper-a-stop` | スクレイパーA停止 |
| `make docker-scraper-a-logs` | スクレイパーAログ表示 |
| `make docker-scraper-b` | スクレイパーB起動 |
| `make docker-scraper-b-stop` | スクレイパーB停止 |
| `make docker-scraper-b-logs` | スクレイパーBログ表示 |
| `make docker-switch-a-to-b` | A→B切り替え |
| `make docker-switch-b-to-a` | B→A切り替え（ロールバック） |
| `make docker-status-all` | 全コンテナ状態表示 |
| `make docker-clean` | 全コンテナ停止・削除 |
