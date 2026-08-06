#!/usr/bin/env python3
"""Import pending GAS observations and Drive images directly into PostgreSQL."""

from __future__ import annotations

import hashlib
import io
import logging
import mimetypes
import os
import sys
from pathlib import Path

import psycopg
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collector.importer import (  # noqa: E402
    LOCATION,
    SCOPES,
    SHEET_NAME,
    fetch_pending_rows,
    mark_imported,
    normalize_sheet_datetime,
)
from src.collector.models import ObservationData  # noqa: E402


SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "config/service-account.json"
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gas-postgres-importer")


def get_credentials():
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )


def download_image(
    drive_service, file_id: str, filename: str
) -> tuple[bytes, str, str]:
    request = drive_service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    data = buf.getvalue()
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return data, mime_type, hashlib.sha256(data).hexdigest()


def build_observation(row: dict) -> ObservationData:
    return ObservationData(
        location_id=1,
        observed_at=normalize_sheet_datetime(row.get("observed_at", "")),
        captured_at=normalize_sheet_datetime(row.get("captured_at", "")),
        cumulative_rainfall=row.get("cumulative_rainfall"),
        temperature=row.get("temperature"),
        wind_speed=row.get("wind_speed"),
        road_temperature=row.get("road_temperature"),
        road_condition=row.get("road_condition"),
        image_filename=row.get("image_filename", ""),
        image_url=row.get("image_url", ""),
    )


def insert_observation(cur, row: dict, obs: ObservationData, image: tuple[bytes, str, str]):
    image_data, image_mime_type, image_sha256 = image
    cur.execute(
        """
        INSERT INTO delta.locations
            (location_name, location_address, source_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (location_name) DO UPDATE SET
            location_address = EXCLUDED.location_address,
            source_url = EXCLUDED.source_url
        RETURNING id
        """,
        (LOCATION.location_name, LOCATION.location_address, LOCATION.source_url),
    )
    location_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO delta.observations
            (location_id, observed_at, captured_at,
             cumulative_rainfall, temperature, wind_speed,
             road_temperature, road_condition, source_image_url,
             original_filename, image_data, image_mime_type,
             image_byte_size, image_sha256)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            obs.observed_at,
            obs.captured_at,
            obs.cumulative_rainfall,
            obs.temperature,
            obs.wind_speed,
            obs.road_temperature,
            obs.road_condition,
            row.get("image_url"),
            obs.image_filename,
            image_data,
            image_mime_type,
            len(image_data),
            image_sha256,
        ),
    )


def main() -> int:
    logger.info("GAS -> PostgreSQL import start")
    try:
        credentials = get_credentials()
        sheets_service = build("sheets", "v4", credentials=credentials)
        drive_service = build("drive", "v3", credentials=credentials)
        pending = fetch_pending_rows(sheets_service)
    except Exception:
        logger.exception("GAS data fetch failed")
        return 1

    logger.info("pending rows: %d", len(pending))
    if not pending:
        return 0

    processed_rows: list[int] = []
    errors = 0
    try:
        with psycopg.connect() as conn:
            with conn.cursor() as cur:
                for row in pending:
                    try:
                        cur.execute("SAVEPOINT row_import")
                        obs = build_observation(row)
                        drive_id = str(row.get("image_drive_id", "")).strip()
                        if not drive_id:
                            raise ValueError("image_drive_id is empty")
                        image = download_image(drive_service, drive_id, obs.image_filename)
                        insert_observation(cur, row, obs, image)
                        cur.execute("RELEASE SAVEPOINT row_import")
                        processed_rows.append(row["_sheet_row"])
                    except Exception as exc:
                        cur.execute("ROLLBACK TO SAVEPOINT row_import")
                        cur.execute("RELEASE SAVEPOINT row_import")
                        logger.exception(
                            "row failed (sheet_row=%s, observed_at=%s): %s",
                            row.get("_sheet_row"),
                            row.get("observed_at"),
                            exc,
                        )
                        errors += 1
                conn.commit()
    except Exception:
        logger.exception("PostgreSQL connection or transaction failed")
        return 1

    try:
        mark_imported(sheets_service, processed_rows)
    except Exception:
        logger.exception("Sheet update failed; rows remain retryable")
        return 1

    logger.info(
        "import complete: processed=%d errors=%d sheet=%s",
        len(processed_rows),
        errors,
        SHEET_NAME,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
