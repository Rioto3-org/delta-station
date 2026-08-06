# デプロイ手順

## 前提

- サーバ上のリポジトリ: `~/dockers/delta-station`
- K3s namespace: `delta-station`
- ローカルレジストリ: `localhost:5000`
- 本番イメージ: `localhost:5000/delta-station-scraper:latest`

## Importerコードの更新

```bash
cd ~/dockers/delta-station
git pull --ff-only origin feature/postgres-architecture

docker build -f Dockerfile.scraper \
  -t localhost:5000/delta-station-scraper:latest .
docker push localhost:5000/delta-station-scraper:latest
```

## CronJobの更新

```bash
sudo kubectl apply -f k3s-manifests/importer-cronjob.yaml
sudo kubectl get cronjob delta-station-importer -n delta-station
```

適用後の期待値は、`SCHEDULE=0 3 * * *`、`TIMEZONE=Asia/Tokyo`、`SUSPEND=False`。

## GAS側

GAS側は`gas-delta-station`の手順に従ってビルド・デプロイする。初回またはトリガー再設定時はGASエディタで`setupTrigger`を1回実行する。

## 旧スクレイパー

`delta-station-scraper` CronJobは停止状態を維持する。GASと旧Pythonスクレイパーを同時に有効化すると、同一地点の二重取得になるためである。

## デプロイ後確認

```bash
sudo kubectl get pods -n delta-station
sudo kubectl get jobs -n delta-station
sudo kubectl logs job/<job-name> -n delta-station
```

PostgreSQL側で観測件数・最新日時・画像NULL件数を確認してから、正常運用と判断する。
