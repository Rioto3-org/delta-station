BEGIN;

ALTER TABLE delta.observations
    ADD COLUMN IF NOT EXISTS image_data bytea,
    ADD COLUMN IF NOT EXISTS image_mime_type text,
    ADD COLUMN IF NOT EXISTS image_byte_size integer,
    ADD COLUMN IF NOT EXISTS image_sha256 text;

UPDATE delta.observations AS o
SET image_data = i.data,
    image_mime_type = i.mime_type,
    image_byte_size = i.byte_size,
    image_sha256 = i.sha256,
    source_image_url = COALESCE(o.source_image_url, i.source_url),
    original_filename = COALESCE(o.original_filename, i.original_filename)
FROM delta.images AS i
WHERE o.image_id = i.id;

ALTER TABLE delta.observations
    DROP COLUMN IF EXISTS image_id;

DROP TABLE IF EXISTS delta.images;

ALTER TABLE delta.observations
    ALTER COLUMN image_byte_size DROP NOT NULL;

COMMIT;
