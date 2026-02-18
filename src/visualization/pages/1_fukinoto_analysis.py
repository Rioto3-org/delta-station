#!/usr/bin/env python3
"""ふきのとう分析ページ（MVP）"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="ふきのとう分析", layout="wide")
st.title("ふきのとう分析")

st.warning(
    "初年度モデルのため、この地中温度推定は仮説ベースです。"
    "実測データが揃い次第、係数やしきい値を見直してください。"
)

DB_PATH = Path(__file__).parent.parent.parent.parent / "outputs" / "database" / "delta_station.db"


@st.cache_data(ttl=60)
def load_road_temperature(hours: int) -> pd.DataFrame:
    """路面温度の時系列を読み込む。"""
    if not DB_PATH.exists():
        return pd.DataFrame()

    query = f"""
        SELECT observed_at, road_temperature
        FROM observations
        WHERE observed_at >= datetime('now', '-{hours} hours', 'localtime')
          AND road_temperature IS NOT NULL
        ORDER BY observed_at ASC
    """
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql(query, conn)
    if df.empty:
        return df
    df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce")
    df = df.dropna(subset=["observed_at"]).copy()
    df["road_temperature"] = pd.to_numeric(df["road_temperature"], errors="coerce")
    return df.dropna(subset=["road_temperature"])


def estimate_soil_temp(
    road_series: pd.Series,
    lag_steps: int,
    alpha: float,
) -> pd.Series:
    """一次遅れモデルで地中温度を推定する。"""
    shifted = road_series.shift(lag_steps)
    est = shifted.copy()
    est.iloc[:] = pd.NA

    first_valid = shifted.first_valid_index()
    if first_valid is None:
        return est
    est.loc[first_valid] = float(shifted.loc[first_valid])

    start_pos = shifted.index.get_loc(first_valid)
    for i in range(start_pos + 1, len(shifted)):
        prev = est.iloc[i - 1]
        current = shifted.iloc[i]
        if pd.isna(current) or pd.isna(prev):
            est.iloc[i] = prev
            continue
        est.iloc[i] = float(prev) + alpha * (float(current) - float(prev))
    return est.astype("float64").clip(lower=-5.0, upper=25.0)


period_hours = st.sidebar.selectbox(
    "表示期間",
    options=[24, 72, 168, 720],
    format_func=lambda h: f"{h // 24}日間" if h >= 24 else f"{h}時間",
    index=2,
)

df = load_road_temperature(period_hours)
if df.empty:
    st.info("路面温度データがありません。")
    st.stop()

sampling_minutes = 10
lag5_steps = int(6 * 60 / sampling_minutes)
lag10_steps = int(12 * 60 / sampling_minutes)

df["soil_temp_5cm"] = estimate_soil_temp(df["road_temperature"], lag5_steps, alpha=0.18)
df["soil_temp_10cm"] = estimate_soil_temp(df["road_temperature"], lag10_steps, alpha=0.10)

latest = df.iloc[-1]
left, right = st.columns(2)
with left:
    st.metric("推定地中温度(5cm)", f"{latest['soil_temp_5cm']:.1f}℃" if pd.notna(latest["soil_temp_5cm"]) else "N/A")
with right:
    st.metric("推定地中温度(10cm)", f"{latest['soil_temp_10cm']:.1f}℃" if pd.notna(latest["soil_temp_10cm"]) else "N/A")

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=df["observed_at"],
        y=df["road_temperature"],
        mode="lines",
        name="路面温度",
        line=dict(color="#888888", width=1.5),
    )
)
fig.add_trace(
    go.Scatter(
        x=df["observed_at"],
        y=df["soil_temp_5cm"],
        mode="lines",
        name="推定地中温度(5cm)",
        line=dict(color="#2E86AB", width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=df["observed_at"],
        y=df["soil_temp_10cm"],
        mode="lines",
        name="推定地中温度(10cm)",
        line=dict(color="#E07A5F", width=2),
    )
)
fig.update_layout(
    title="路面温度と推定地中温度",
    xaxis_title="観測日時",
    yaxis_title="温度 (℃)",
    hovermode="x unified",
    height=460,
)
st.plotly_chart(fig, use_container_width=True)
