# gas-delta-station

Delta地点観測データを **Google Apps Script (GAS)** で取得し、スプレッドシート＋Driveにバッファするスクレイパー。

## なぜGASか（背景）

本体（`delta-station`）はk3s上のCronJobで15分ごとに観測データを取得しているが、**自宅サーバのハード保守（RAM交換など）で停止させると、その間の観測が欠損する**。元画像は固定パス `image/DR-74125-l.jpg` で毎回上書きされ、後から遡って取得できないため、可用性が要求される。

そこで「常時稼働が必要な取得部分」をGoogleのインフラに肩代わりさせ、スプレッドシート/Driveに1ヶ月程度バッファする。Python側は1〜2日ごとのバッチでそこからDBへ取り込む（＝取り込みは自宅サーバが落ちていても後追いできる）。

- **取得（このプロジェクト / GAS）**: 15分ごと。可用性が要る部分。
- **取り込み（`delta-station` / Python・別途）**: 低頻度バッチ。冪等（`observed_at` UNIQUE）。

## 設計方針：純粋ロジック + アダプタ + ビルド

GASは `UrlFetchApp` / `SpreadsheetApp` / `DriveApp` などのグローバルサービスに依存し、そのままではローカルで動かせない。そこで：

1. **リスクの高いロジック（HTMLパース・正規化）を「純粋関数」に隔離** → GAS非依存なので、保存した実HTMLフィクスチャに対して **Nodeでローカル単体テスト**できる。
2. **I/O（fetch・シート・Drive）はアダプタ層に隔離** → 本番は `gas` アダプタ、ローカルは `node` アダプタ。同じ `pipeline` / `core` が両方で動く。
3. **esbuildでバンドル** → GASはESモジュールを実行時解釈できないため、`dist/Code.gs` に単一バンドル化し、トリガー対象の `main` / `setupTrigger` をグローバル関数として露出させる。

### ディレクトリ構成

```
gas-delta-station/
├── src/
│   ├── core/                 # ★純粋ロジック（GAS非依存・テスト対象）
│   │   ├── config.js         #   取得URL・地点定数
│   │   ├── parse.js          #   parseHtml(html) → 生データ（from_html相当）
│   │   ├── normalize.js      #   数値/路面状況の正規化（validator相当）
│   │   ├── observation.js    #   検証済みレコード生成（範囲チェック含む）
│   │   └── filename.js       #   画像ファイル名生成
│   ├── adapters/
│   │   ├── gas.js            # 本番: UrlFetchApp / SpreadsheetApp / DriveApp
│   │   └── node.js           # ローカル: curl(execSync) + TextDecoder + fs
│   ├── pipeline.js           # coreとadapterを結線（両環境共通・同期）
│   └── entry.js              # main() / cleanup() / setupTrigger()（GASグローバル関数）
├── test/
│   ├── parse.test.js         # 実HTMLフィクスチャでパース検証
│   └── normalize.test.js     # models.pyのテスト値と突き合わせ
├── fixtures/
│   └── delta_sample.html     # 実ページ（Shift_JIS生バイト）
├── scripts/
│   └── dry-run.mjs           # ローカルで全工程を実行（push不要）
├── build.mjs                 # esbuild: src → dist/Code.gs
├── appsscript.json           # マニフェスト（TZ=Asia/Tokyo, スコープ）
├── vitest.config.js
├── package.json
└── dist/                     # ビルド成果物（clasp push対象・gitignore）
    ├── Code.gs
    └── appsscript.json
```

### データフロー

```
[15分トリガー (GAS)]
     │
     ▼
adapter.fetchText  ── UrlFetchApp + getContentText("Shift_JIS")
     ▼
parseHtml          ── 正規表現で observed_at / 気象データ / 画像URL 抽出
     ▼
buildObservation   ── "19.6℃"→19.6, "----"→null, 範囲チェック
     ▼
hasObservedAt?  ──[既存]→ スキップ（冪等 = DBのUNIQUE相当）
     │[新規]
     ▼
fetchBytes → saveImage(Drive)   ── 取得時点で画像を必ず保存（後から取れないため）
     ▼
appendObservation  ── observations シートに1行追記（imported=false）
```

## スプレッドシートのスキーマ（Python取り込みとの契約点）

`observations` シートの1行目ヘッダーが、Python側バッチ取り込みとの**契約**。列の並び順ではなく**列名**で取り込むこと（列を足しても壊れないように）。

| 列 | 説明 | 対応するDBカラム |
|---|---|---|
| `observed_at` | 観測日時（UNIQUEキー） | observations.observed_at |
| `captured_at` | 撮影日時 | captured_at |
| `cumulative_rainfall` | 累加雨量(mm) | cumulative_rainfall |
| `temperature` | 気温(℃) | temperature |
| `wind_speed` | 風速(m/s) | wind_speed |
| `road_temperature` | 路面温度(℃) | road_temperature |
| `road_condition` | 路面状況（`----`は空） | road_condition |
| `image_filename` | 画像ファイル名 | image_filename |
| `image_drive_id` | **Drive上の画像ファイルID**（GAS固有） | ―（取り込み時に画像回収に使用） |
| `image_url` | 元画像URL | image_url |
| `location_name` | 地点名 | locations経由 |
| `created_at` | シート追記時刻 | ― |
| `imported` | 取り込み済みフラグ | ―（バッチが未取込行だけ拾う） |

### 日時カラム（observed_at / captured_at）の扱い：Sheets側のフォーマットは信用しない

GAS側は`observations!A:B`列（`observed_at`/`captured_at`）を`setNumberFormat('@')`でプレーンテキスト書式にし、`"YYYY-MM-DD HH:MM"`形式の文字列を書き込んでいる（[gas.js](src/adapters/gas.js)の`ensureDatetimeColumnsAreText`）。

しかし実運用で、**プレーンテキスト書式にしてもGoogle Sheetsが裏で文字列を操作することがある**と判明した。同じ列・同じコードで書き込まれたにもかかわらず、実際に以下の崩れ方が両方観測されている。

| 崩れ方 | 例 |
|---|---|
| 完全にシリアル値化（日付型の内部表現） | `46231.42361111111`（1899-12-30起点の経過日数） |
| 文字列のままゼロ埋めだけ崩れる | `"09:10"` → `"9:10"` |

観測データを取得する正規表現（[parse.js](src/core/parse.js)）は時刻を`\d{2}:\d{2}`（2桁固定）でしかマッチしないため、GASが値を捕まえた時点では必ず正しい`"09:10"`形式である。つまりこの崩れは**GAS→Sheetsへの書き込み後に、Sheets側で発生している**。

**対応方針:** Sheets側で「常に1つの正確な文字列表現である」ことを保証しようとするのは諦め、**消費側（Python）でどんな表現が来ても同じ日時として正規化する**設計にした。

実装は`delta-station/src/collector/importer.py`の`normalize_sheet_datetime()`:

```python
def normalize_sheet_datetime(value) -> str:
    if isinstance(value, (int, float)):
        # シリアル値 → 1899-12-30起点で日時に変換
        dt = SHEETS_EPOCH + timedelta(days=value)
        return dt.strftime('%Y-%m-%d %H:%M')
    # ゼロ埋めが崩れた文字列 → 各要素を再フォーマット（正しい文字列ならそのまま）
    ...
```

数値でも、ゼロ埋めが崩れた文字列でも、正しい文字列でも、最終的に必ず`"YYYY-MM-DD HH:MM"`の正規形にしてからPydantic検証・DB保存に回す。

**教訓:** Google Sheetsを構造化データの受け渡しに使う場合、日時っぽい列は「書き込んだ文字列がそのまま読み返せる」ことを信頼せず、**消費側で値レベルの正規化を行う**こと。GAS側のプレーンテキスト化はそれでも意味がある（崩れる頻度を減らす可能性がある）ので残しているが、それに依存しない設計にしてある。

## ローカルテスト（2段構え）

### 段1：純粋ロジックの単体テスト（必須・オフライン）

```bash
npm test
```

`fixtures/delta_sample.html`（実ページのShift_JIS生バイト）を `TextDecoder('shift_jis')` で復号し、`parseHtml` / `buildObservation` などの結果を検証する。**復号＋パースの結合**を数十msでオフライン検証できる。

### 段2：全工程のドライラン（実サイトへ・push不要）

```bash
npm run dry-run
```

`node` アダプタで取得→パース→正規化→保存までローカル実行し、`.dry-run-out/`（gitignore）にCSVと画像を書き出す。**文字コードと画像取得を、GASへデプロイする前に潰せる。** 本番と同じ `src/core` `src/pipeline` を通るのが要点。

## ビルドとデプロイ（GAS）

> clasp のログインと `.clasp.json`（scriptId）は環境固有。`.clasp.json` はgitignore対象。

```bash
npm run build     # dist/Code.gs, dist/appsscript.json を生成
clasp push        # dist/ を push（.clasp.json の rootDir は "dist" にすること）
```

初回のみGAS側で必要な設定：

1. `.clasp.json` の `rootDir` を `"dist"` に変更（バンドル成果物だけをpushする）。
2. スクリプトプロパティ `IMAGE_FOLDER_ID` に、画像保存先Driveフォルダのidを設定。
3. GASエディタで `main` を1回手動実行し、権限（外部リクエスト/スプレッドシート/Drive）を承認。
4. `setupTrigger` を1回実行し、15分間隔の取得トリガーと、1日1回（3時）のキャッシュ削除（`cleanup`）トリガーを設置。

## 実装メモ（移植時の落とし穴）

- **文字コードはShift_JIS**。GASは `getContentText("Shift_JIS")`、Nodeは `TextDecoder('shift_jis')` で明示復号する（未指定だと日本語ラベルが化けてパース失敗）。
- **テーブル行のラベルは完全一致で拾う**。ページには `※ 累加雨量説明` `・ 注意書き` など、同じ2セル構造の説明行があるため、部分一致だと誤爆する。
- **画像は新規挿入時に取得時点で保存**。固定パスで上書きされるため、バッチ時にまとめて取る設計にはできない。
- **pipelineは同期**で書く。GASの `UrlFetchApp` 等は同期APIで、GASトリガーはPromiseを待たないため。node アダプタも `execSync` で同期に揃えている。
- **日時列(observed_at/captured_at)はSheets側でフォーマットが崩れることがある**（プレーンテキスト化しても）。詳細は上記「[日時カラムの扱い](#日時カラムobserved_at--captured_atの扱いsheets側のフォーマットは信用しない)」を参照。

## npm スクリプト

| コマンド | 説明 |
|---|---|
| `npm test` | 純粋ロジックの単体テスト（vitest） |
| `npm run test:watch` | テストのウォッチ実行 |
| `npm run dry-run` | 実サイトに対し全工程をローカル実行 |
| `npm run build` | esbuildで `dist/Code.gs` を生成 |
| `npm run push` | build → `clasp push` |
