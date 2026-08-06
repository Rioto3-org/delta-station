# 運用手順

## 通常運用

### CronJob確認

```bash
sudo kubectl get cronjobs -n delta-station
sudo kubectl get jobs -n delta-station
```

Importerは毎日03:00（Asia/Tokyo）に実行される。`concurrencyPolicy: Forbid`により、前回実行中は重複起動しない。

### 手動Importer実行

```bash
sudo kubectl delete job delta-station-importer-manual \
  -n delta-station --ignore-not-found

sudo kubectl create job delta-station-importer-manual \
  --from=cronjob/delta-station-importer \
  -n delta-station

sudo kubectl logs -f job/delta-station-importer-manual \
  -n delta-station
```

### PostgreSQL確認

```bash
sudo kubectl exec -it postgres-858b6f97d5-hp6c2 \
  -n postgres-operabase -- \
  psql -U app -d delta_station
```

```sql
SELECT COUNT(*) FROM delta.observations;
SELECT MIN(observed_at), MAX(observed_at) FROM delta.observations;
SELECT COUNT(*) FROM delta.observations WHERE image_data IS NULL;
```

## Secret

必要なSecretは以下の2つ。値はGitへ保存しない。

- `delta-station-gcp-sa`: `service-account.json`
- `delta-pg-worker`: `PGPASSWORD`

確認時は値を表示せず、キーだけ確認する。

```bash
sudo kubectl describe secret delta-pg-worker -n delta-station
sudo kubectl describe secret delta-station-gcp-sa -n delta-station
```

## GAS cleanup

GASエディタで`setupTrigger`を一度実行すると、以下が設定される。

- `main`: 15分ごとの観測取得
- `cleanup`: 毎日03:00のキャッシュ清掃

ImporterがDB保存後に`imported=true`へ更新した行だけがcleanup対象になる。Driveの画像は完全削除ではなくゴミ箱へ移動される。

## 失敗時の判断

| 状態 | 対応 |
|---|---|
| GAS取得失敗 | GASログとトリガーを確認。Sheet/Driveの未取込行は保持される |
| Importerの認証失敗 | `delta-pg-worker`または`delta-station-gcp-sa`を確認 |
| 画像取得失敗 | `imported`が更新されず、次回再試行される |
| PostgreSQL保存失敗 | Jobログを保存し、Sheet側の行を削除しない |
| cleanup失敗 | Drive/Sheetのデータを残し、次回cleanupで再試行 |

## バックアップ

PostgreSQLのバックアップ手順は、Postgres運用基盤側のバックアップ方針を正本とする。Delta側では、少なくとも移行前にSQLiteファイルと`images`ディレクトリを保持する。

旧SQLiteのPVC上の保存先は、実行環境のPV情報から確認する。ホストパスをアプリケーションの論理モデルとして扱わない。

## 画像の取り出し

```bash
sudo kubectl exec postgres-858b6f97d5-hp6c2 \
  -n postgres-operabase -- psql -U app -d delta_station -At \
  -c "SELECT encode(image_data, 'base64')
      FROM delta.observations
      WHERE image_data IS NOT NULL
      ORDER BY observed_at DESC LIMIT 1;" |
tr -d '\n' | base64 -d > /tmp/delta-latest-image.jpg

file /tmp/delta-latest-image.jpg
```
