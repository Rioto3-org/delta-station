# Delta Station

道路情報ページの定点観測データを蓄積するプロジェクトです。現在の本番経路は、GASが観測と一時保存を担当し、K3s上のImporterが1日1回PostgreSQLへ取り込みます。

## 現行構成

```text
道路情報ページ
      |
      v
GAS (15分ごと)
  +-- Google Sheets: 観測データのバッファ
  +-- Google Drive: 画像の一時バッファ
      |
      | 毎日03:00 JST
      v
K3s Importer Pod
      |
      v
PostgreSQL (delta_station)
  observations.image_data に画像バイナリを保存
```

- GASはデータ取得とバッファのみを担当する。
- K3s上のImporterがGoogle Sheets/Driveから読み取り、PostgreSQLへ保存する。
- DB保存成功後、ImporterがSheetの`imported`を更新する。
- GASの`cleanup`トリガー（`setupTrigger`実行後）は、取り込み済み行とDrive画像をゴミ箱へ移動する。
- DB接続用の`delta_worker`とGAS用サービスアカウント鍵はKubernetes Secretで管理し、Gitへ登録しない。

## 現在の状態

- 旧SQLiteからPostgreSQLへの初回移行: 完了
- PostgreSQL画像保存: `observations.image_data`（`bytea`）
- GASからPostgreSQLへの手動Importer確認: 完了
- Importer CronJob定義: 毎日03:00 JST（サーバの適用状態は`kubectl`で確認）
- 旧PythonスクレイパーCronJob: 停止
- 旧SQLite: PVC上にアーカイブとして保持
- Streamlitダッシュボード: 現在はSQLite参照のため、PostgreSQL対応は別作業

## 開発

```bash
uv sync
uv run pytest
```

本番イメージの更新はサーバ上で行います。

```bash
docker build -f Dockerfile.scraper -t localhost:5000/delta-station-scraper:latest .
docker push localhost:5000/delta-station-scraper:latest
```

## 文書

- [ARCHITECTURE.md](docs/ARCHITECTURE.md): 現行の責務分界とデータフロー
- [DATA_MODEL.md](docs/DATA_MODEL.md): PostgreSQLスキーマと画像保存方針
- [OPERATIONS.md](docs/OPERATIONS.md): K3s、Secret、CronJob、確認手順
- [MIGRATION.md](docs/MIGRATION.md): SQLiteからPostgreSQLへの実施記録と復旧方針
- [DEPLOYMENT.md](docs/DEPLOYMENT.md): 現行環境のデプロイ手順
- [gas-delta-station/README.md](gas-delta-station/README.md): GAS側の取得・バッファ仕様

## 対象地点

- 地点: 作並宿（チェーン着脱所）
- URL: <http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html>
- 観測頻度: GAS側で15分ごと
