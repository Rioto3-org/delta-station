# 現行アーキテクチャ

## 1. 目的と境界

このリポジトリは、観測データを蓄積・提供するDBシステムと、その運用コードを管理する。時間依存のスクレイピングはGAS側に置き、K3s側はデータ取り込みと永続化に集中する。

## 2. 責務分界

| コンポーネント | 責務 | 保持期間・正本 |
|---|---|---|
| 道路情報ページ | 観測値・画像の公開元 | 外部依存 |
| GAS `main` | 15分ごとの取得、Sheet/Driveへの保存 | バッファ |
| Google Sheets | 観測値、取り込み状態のキュー | Importer成功まで |
| Google Drive | 画像バイナリの一時バッファ | Importer成功後cleanup対象 |
| K3s Importer | GASバッファの読み取り、画像取得、PostgreSQL保存 | 実行Pod |
| PostgreSQL | 観測データと画像の正本 | 永続データ |
| SQLite | 旧運用データのアーカイブ | 更新しない |
| Streamlit | 現行では旧SQLiteを読む分析画面 | PostgreSQL対応は未完了 |

GASからPostgreSQLへ直接接続する構成は採用しない。DB認証をGASへ持ち込まず、既存のK3s/Python実行基盤をImporterとして利用する。

## 3. データフロー

```text
GAS main (15分)
  -> Sheetに観測行を追加 (imported=false)
  -> Driveに画像を保存

K3s importer CronJob (毎日03:00 JST)
  -> imported=false のSheet行を取得
  -> Drive画像を取得
  -> PostgreSQLへ1行ずつ保存
  -> DBコミット後にSheetのimported=trueへ更新

GAS cleanup (setupTrigger実行後、毎日03:00)
  -> imported=true のDrive画像をゴミ箱へ移動
  -> Sheet行を削除
```

Importerは画像取得またはDB保存に失敗した行を`imported=true`にしない。これにより、GAS側のデータを残したまま次回実行で再試行できる。

## 4. 冪等性

PostgreSQLの`delta.observations`は`(location_id, observed_at)`を一意キーとする。Importerは同じ観測時刻を再処理しても重複行を作らず、既存行を更新する。

Sheetの`imported`は削除可否を示すキュー状態であり、DBの正本性を代替しない。`imported=true`への更新はDBコミット後に行う。

## 5. 実行基盤

- Namespace: `delta-station`
- Importer: `delta-station-importer` CronJob
- スケジュール: `0 3 * * *`, `Asia/Tokyo`
- PVC: `delta-station-outputs`
- PostgreSQL: `postgres.postgres-operabase.svc.cluster.local:5432`
- PostgreSQL DB: `delta_station`
- Importerロール: `delta_worker`

旧`delta-station-scraper` CronJobは停止状態を維持する。GASと旧スクレイパーを同時に有効化して二重取得しない。
