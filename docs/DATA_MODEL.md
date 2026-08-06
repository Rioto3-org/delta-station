# データモデル

## PostgreSQL

接続先DBは`delta_station`、アプリケーションスキーマは`delta`とする。DDLの正本は[database/schema_postgres.sql](../database/schema_postgres.sql)である。

### `delta.locations`

| 列 | 型 | 説明 |
|---|---|---|
| `id` | `bigint` | 観測地点ID |
| `location_name` | `text` | 地点名、一意 |
| `location_address` | `text` | 住所 |
| `source_url` | `text` | 観測元ページ |

### `delta.observations`

| 列 | 型 | 説明 |
|---|---|---|
| `id` | `bigint` | レコードID |
| `location_id` | `bigint` | `locations.id`への参照 |
| `observed_at` | `timestamp` | 観測日時 |
| `captured_at` | `timestamp` | 画像撮影日時 |
| `cumulative_rainfall` | `double precision` | 累加雨量 |
| `temperature` | `double precision` | 気温 |
| `wind_speed` | `double precision` | 風速 |
| `road_temperature` | `double precision` | 路面温度 |
| `road_condition` | `text` | 路面状況 |
| `source_image_url` | `text` | 外部サイトの画像URL |
| `original_filename` | `text` | 論理上の画像ファイル名 |
| `image_data` | `bytea` | 画像本体。欠落時は`NULL` |
| `image_mime_type` | `text` | 例: `image/jpeg` |
| `image_byte_size` | `integer` | バイナリサイズ |
| `image_sha256` | `text` | 画像内容のハッシュ |
| `created_at` | `timestamp` | DBレコード作成日時 |

一意制約は`(location_id, observed_at)`。現在は1地点だが、複数地点へ拡張できる形を維持する。

## 画像の扱い

画像は別テーブルを作らず、観測と1対1で`observations.image_data`に保存する。現在は各観測に固有の画像が対応するため、分離テーブルより参照とトランザクションを単純に保てる。

- 画像形式はバイナリのまま保持されるため、JPEG/PNGの形式情報は失われない。
- `image_mime_type`と`original_filename`で復元・表示に必要な情報を保持する。
- 欠落画像16件は観測レコードを保持し、画像列のみ`NULL`とする。
- `source_image_url`は元URLであり、画像本体の保存場所を表すものではない。

## 認証ロール

| ロール | 用途 |
|---|---|
| `delta_dev` | スキーマ・設計・保守作業 |
| `delta_worker` | Importerの通常書き込み |

Importerは`delta_worker`のみを使用する。Superuserロールをアプリケーションへ渡さない。

## SQLiteとの対応

SQLiteの`locations`/`observations`は旧アーカイブのスキーマであり、現在の書き込み先ではない。PostgreSQL移行時にSQLiteの画像ファイルを読み込み、`image_data`へ格納した。
