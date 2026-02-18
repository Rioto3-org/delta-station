#!/usr/bin/env python3
"""ふきのとう分析ページ（MVP）"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="ふきのとう分析", layout="wide")
st.title("ふきのとう分析")

DB_PATH = Path(__file__).parent.parent.parent.parent / "outputs" / "database" / "delta_station.db"
GDD_BASE_TEMP = 0.0
GDD_START_DATE = pd.Timestamp("2026-02-17")
GERMINATION_THRESHOLD = 2.5
GERMINATION_DAYS = 4
AIR_CORRECTION_BETA = 0.03
GDD_PEAK = 25.0


@st.cache_data(ttl=60)
def load_observation_data(hours: int) -> pd.DataFrame:
    """路面温度と気温の時系列を読み込む。"""
    if not DB_PATH.exists():
        return pd.DataFrame()

    query = f"""
        SELECT observed_at, road_temperature, temperature
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
    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    return df.dropna(subset=["road_temperature"])


def estimate_soil_temp(road_series: pd.Series, lag_steps: int, alpha: float) -> pd.Series:
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

df = load_observation_data(period_hours)
if df.empty:
    st.info("路面温度データがありません。")
    st.stop()

sampling_minutes = 10
lag5_steps = int(6 * 60 / sampling_minutes)
df["soil_temp_5cm"] = estimate_soil_temp(df["road_temperature"], lag5_steps, alpha=0.18)

daily = (
    df.assign(observed_date=df["observed_at"].dt.floor("D"))
    .groupby("observed_date", as_index=False)
    .agg(
        soil_temp_5cm_daily_median=("soil_temp_5cm", "median"),
        air_temp_daily_median=("temperature", "median"),
    )
)

model_daily = daily[daily["observed_date"] >= GDD_START_DATE].copy()
model_daily["gdd_component"] = (model_daily["soil_temp_5cm_daily_median"] - GDD_BASE_TEMP).clip(lower=0.0)
model_daily["air_adjust"] = 1 + AIR_CORRECTION_BETA * (model_daily["air_temp_daily_median"] - 5.0).clip(-5.0, 5.0)
model_daily["growth_component"] = (model_daily["gdd_component"] * model_daily["air_adjust"]).clip(lower=0.0)

latest = df.iloc[-1]
today_date = latest["observed_at"].floor("D")
today_daily = daily[daily["observed_date"] == today_date]

soil_now_text = f"{latest['soil_temp_5cm']:.1f}℃" if pd.notna(latest["soil_temp_5cm"]) else "N/A"
today_median_text = (
    f"{float(today_daily.iloc[0]['soil_temp_5cm_daily_median']):.2f}℃"
    if not today_daily.empty and pd.notna(today_daily.iloc[0]["soil_temp_5cm_daily_median"])
    else "N/A"
)
gdd_value = float(model_daily["gdd_component"].sum())
growth_gdd = float(model_daily["growth_component"].sum())
growth_index = 1 + 99 * min(max(growth_gdd / GDD_PEAK, 0.0), 1.0)

recent_days = model_daily.tail(GERMINATION_DAYS)
is_germination_ready = (
    len(recent_days) == GERMINATION_DAYS
    and bool((recent_days["soil_temp_5cm_daily_median"] >= GERMINATION_THRESHOLD).all())
)
if is_germination_ready:
    germination_status = "発芽開始候補: 到達"
elif not model_daily.empty and float(model_daily.iloc[-1]["soil_temp_5cm_daily_median"]) >= GERMINATION_THRESHOLD:
    germination_status = "発芽開始候補: 接近中"
else:
    germination_status = "発芽開始候補: 未到達"

st.warning(
    "初年度モデルのため、地中温度推定・発芽判定・成長指数は仮説ベースです。"
    "実測データが揃い次第、係数としきい値を見直してください。"
)
st.caption("GrowthIndex は相対指標です。1=発芽時点、100=収穫推奨上限の目安（絶対値ではない）。")

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("推定地中温度(5cm)", soil_now_text)
with c2:
    st.metric("本日時点の日中央値(5cm)", today_median_text)
with c3:
    st.metric("累積GDD相当(Tb=0, 中央値, 2/17起算)", f"{gdd_value:.2f}℃日")

st.caption(
    f"起算日: {GDD_START_DATE.strftime('%Y-%m-%d')} / "
    "当日の日中央値は最新観測時刻までのデータで計算"
)

st.header("地中温度推定")
st.markdown(
    "推定式（5cm）:  \n"
    "`T5[t] = T5[t-1] + 0.18 * (Road[t-36] - T5[t-1])`  \n"
    "日中央値式:  \n"
    "`T5_day(d) = median(T5[t] for observed_at[t] in day d)`  \n"
    "- 10分間隔データを前提（36ステップ = 6時間遅れ）  \n"
    "- 推定値は `-5〜25℃` にクリップ"
)

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
        x=daily["observed_date"],
        y=daily["soil_temp_5cm_daily_median"],
        mode="lines+markers",
        name="推定地中温度(5cm) 日中央値",
        line=dict(color="#D64545", width=3),
        marker=dict(size=5),
    )
)
fig.update_layout(
    title="路面温度と推定地中温度(5cm)",
    xaxis_title="観測日時",
    yaxis_title="温度 (℃)",
    hovermode="x unified",
    height=460,
)
st.plotly_chart(fig, use_container_width=True)

st.header("発芽モデル")
st.markdown(
    f"- 判定条件: `日中央値(地中5cm) >= {GERMINATION_THRESHOLD:.1f}℃` が `{GERMINATION_DAYS}日連続`\n"
    "- 0℃未満で即時リセットするルールは採用せず、連続条件のみで判定"
)
st.metric("発芽判定ステータス", germination_status)

st.header("成長モデル")
st.markdown(
    "成長量（1日）:  \n"
    "`g_d = max(Tsoil_day - Tb, 0)`  \n"
    "気温補正:  \n"
    "`c_d = 1 + 0.03 * clamp(Tair_day - 5, -5, 5)`  \n"
    "補正後成長量:  \n"
    "`g'_d = max(g_d * c_d, 0)`  \n"
    "成長指数:  \n"
    "`GrowthIndex = 1 + 99 * clamp(sum(g'_d) / 25, 0, 1)`"
)
gc1, gc2 = st.columns(2)
with gc1:
    st.metric("累積成長量（補正後）", f"{growth_gdd:.2f}℃日")
with gc2:
    st.metric("GrowthIndex", f"{growth_index:.1f}")
