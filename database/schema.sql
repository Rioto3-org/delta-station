-- Delta地点定点観測データベーススキーマ

-- 観測地点マスタテーブル
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name TEXT NOT NULL UNIQUE, -- 観測地点名 (例: 作並宿)
    location_address TEXT,              -- 住所 (例: 仙台市青葉区作並字神前西)
    source_url TEXT NOT NULL            -- データ取得元URL
);

-- 観測データメインテーブル
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,     -- 観測地点ID (locationsテーブルへの外部キー)
    observed_at TEXT NOT NULL UNIQUE, -- 観測日時 (ISO 8601形式: YYYY-MM-DD HH:MM)
    captured_at TEXT NOT NULL,        -- 撮影日時 (ISO 8601形式: YYYY-MM-DD HH:MM)

    -- 気象データ
    cumulative_rainfall REAL,         -- 累加雨量 (mm)
    temperature REAL,                 -- 気温 (℃)
    wind_speed REAL,                  -- 風速 (m/s)
    road_temperature REAL,            -- 路面温度 (℃)
    road_condition TEXT,              -- 路面状況 (テキスト)

    -- 画像情報
    image_filename TEXT NOT NULL,     -- 保存した画像ファイル名
    image_url TEXT NOT NULL,          -- 元画像URL

    -- メタデータ
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),  -- レコード作成日時

    -- 外部キー制約
    FOREIGN KEY (location_id) REFERENCES locations(id)
);
