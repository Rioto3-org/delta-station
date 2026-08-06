# SQLiteからPostgreSQLへの移行

## 移行結果

2026-08-06時点で、初回移行とGASからPostgreSQLへの手動Importer確認は完了した。

- PostgreSQL DB: `delta_station`
- スキーマ: `delta`
- 画像: `delta.observations.image_data`へ`bytea`として保存
- 欠落画像16件: 観測行は保持し、画像列を`NULL`
- 継続取り込み: K3s Importer CronJob

## 採用した判断

PostgreSQLを現在の正本とする。SQLiteは移行元の保存物としてPVC上に残すが、通常運用では更新しない。

GASはPostgreSQLへ直接接続しない。GASはSheet/Driveへバッファし、K3s上のImporterがサービスアカウントとDB接続を管理する。

画像は別テーブルではなく、`observations`に直接保存する。現在は1観測に1画像という対応であり、参照とトランザクションを単純に保てるためである。

## 既存DBの統合SQL

既存のPostgreSQLに旧`delta.images`テーブルが存在する場合は、次のSQLを一度だけ実行する。

```bash
sudo kubectl exec -i postgres-858b6f97d5-hp6c2 \
  -n postgres-operabase -- \
  psql -U app -d delta_station \
  < database/migrate_images_into_observations.sql
```

このSQLは画像バイナリを`observations.image_*`へ移し、旧`delta.images`を削除する。実行前にPostgreSQLバックアップを取得する。

## 検証

```sql
SELECT COUNT(*) FROM delta.observations;
SELECT MIN(observed_at), MAX(observed_at) FROM delta.observations;
SELECT COUNT(*) FROM delta.observations WHERE image_data IS NULL;
SELECT COUNT(*) FROM delta.observations WHERE image_data IS NOT NULL;
```

SQLiteの基準値と、PostgreSQLの観測件数・期間・画像件数を照合する。

## 復旧方針

- 初回移行前のSQLiteと画像ディレクトリを削除しない。
- GASの`imported`を更新するのはPostgreSQL保存成功後だけにする。
- Importer失敗時はSheet/Driveを残し、次回再試行する。
- PostgreSQL側の誤移行はバックアップから復元する。

## 今後の別作業

- StreamlitダッシュボードのPostgreSQL対応
- PostgreSQLバックアップの定期運用確認
- 複数地点対応時のImporter設定分離
