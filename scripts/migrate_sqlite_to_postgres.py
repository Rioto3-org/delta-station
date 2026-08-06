#!/usr/bin/env python3
"""Migrate the frozen SQLite dataset, including image bytes, into PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import os
import sqlite3
from pathlib import Path

import psycopg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not args.dry_run and not args.dsn and not os.environ.get("PGHOST"):
        parser.error("--dsn, DATABASE_URL, or PGHOST is required")
    return args


def image_payload(images_dir: Path, filename: str) -> tuple[bytes, str, str]:
    path = images_dir / filename
    if not path.is_file():
        raise FileNotFoundError(f"image is missing: {path}")
    data = path.read_bytes()
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return data, mime_type, hashlib.sha256(data).hexdigest()


def validate_images(rows: list[sqlite3.Row], images_dir: Path) -> list[str]:
    return [
        row["image_filename"]
        for row in rows
        if not (images_dir / row["image_filename"]).is_file()
    ]


def migrate(args: argparse.Namespace) -> tuple[int, int]:
    sqlite_conn = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(
        """
        SELECT o.*, l.location_name, l.location_address, l.source_url AS location_source_url
        FROM observations o
        JOIN locations l ON l.id = o.location_id
        ORDER BY o.observed_at, o.id
        """
    ).fetchall()

    missing = validate_images(rows, args.images)
    if args.dry_run:
        print(f"observations={len(rows)}")
        print(f"missing_images={len(missing)}")
        for filename in missing:
            print("missing_image=" + filename)
        return len(rows), len(missing)
    if missing:
        print(f"missing_images_skipped={len(missing)}")

    inserted = 0
    pg_connect = lambda: psycopg.connect(args.dsn) if args.dsn else psycopg.connect()
    with pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            for offset in range(0, len(rows), args.batch_size):
                batch = rows[offset : offset + args.batch_size]
                for row in batch:
                    cur.execute(
                        """
                        INSERT INTO delta.locations
                            (id, location_name, location_address, source_url)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (location_name) DO UPDATE SET
                            location_address = EXCLUDED.location_address,
                            source_url = EXCLUDED.source_url
                        RETURNING id
                        """,
                        (
                            row["location_id"],
                            row["location_name"],
                            row["location_address"],
                            row["location_source_url"],
                        ),
                    )
                    location_id = cur.fetchone()[0]

                    image_path = args.images / row["image_filename"]
                    image_data = None
                    image_mime_type = None
                    image_byte_size = None
                    image_sha256 = None
                    if image_path.is_file():
                        image_data, image_mime_type, image_sha256 = image_payload(
                            args.images, row["image_filename"]
                        )
                        image_byte_size = len(image_data)

                    cur.execute(
                        """
                        INSERT INTO delta.observations
                            (location_id, observed_at, captured_at,
                             cumulative_rainfall, temperature, wind_speed,
                             road_temperature, road_condition, source_image_url,
                             original_filename, image_data, image_mime_type,
                             image_byte_size, image_sha256, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (location_id, observed_at) DO UPDATE SET
                            captured_at = EXCLUDED.captured_at,
                            cumulative_rainfall = EXCLUDED.cumulative_rainfall,
                            temperature = EXCLUDED.temperature,
                            wind_speed = EXCLUDED.wind_speed,
                            road_temperature = EXCLUDED.road_temperature,
                            road_condition = EXCLUDED.road_condition,
                            source_image_url = EXCLUDED.source_image_url,
                            original_filename = EXCLUDED.original_filename,
                            image_data = EXCLUDED.image_data,
                            image_mime_type = EXCLUDED.image_mime_type,
                            image_byte_size = EXCLUDED.image_byte_size,
                            image_sha256 = EXCLUDED.image_sha256
                        """,
                        (
                            location_id,
                            row["observed_at"],
                            row["captured_at"],
                            row["cumulative_rainfall"],
                            row["temperature"],
                            row["wind_speed"],
                            row["road_temperature"],
                            row["road_condition"],
                            row["image_url"],
                            row["image_filename"],
                            image_data,
                            image_mime_type,
                            image_byte_size,
                            image_sha256,
                            row["created_at"],
                        ),
                    )
                    inserted += 1
                pg_conn.commit()
                print(f"migrated={min(offset + len(batch), len(rows))}/{len(rows)}")

            for table in ("locations", "observations"):
                cur.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('delta.{table}', 'id'),
                        GREATEST(COALESCE(MAX(id), 1), 1),
                        true
                    )
                    FROM delta.{table}
                    """
                )
            pg_conn.commit()

    sqlite_conn.close()
    return inserted, 0


if __name__ == "__main__":
    args = parse_args()
    migrated, missing = migrate(args)
    if missing:
        raise SystemExit(2)
    print(f"completed={migrated}")
