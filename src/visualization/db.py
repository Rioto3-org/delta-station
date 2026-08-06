"""PostgreSQL access helpers for the Streamlit dashboard."""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd
import psycopg


def query_dataframe(query: str, params: Sequence[Any] = ()) -> pd.DataFrame:
    """Execute a read-only query and return rows as a DataFrame."""
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [description.name for description in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)


def query_one(query: str, params: Sequence[Any] = ()) -> tuple[Any, ...] | None:
    """Execute a read-only query and return one row."""
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()
