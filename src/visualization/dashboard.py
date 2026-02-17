#!/usr/bin/env python3
"""
Delta地点 観測ダッシュボード (Streamlit)

リアルタイムで観測データのレコード数を表示。
"""

import sqlite3
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Delta地点", page_icon="🌡️")

DB_PATH = Path(__file__).parent.parent.parent / "outputs" / "database" / "delta_station.db"

def get_record_count():
    """観測データの総レコード数を取得"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM observations")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        return f"エラー: {e}"

st.title("🌡️ Delta地点")
st.metric("総レコード数", get_record_count())
