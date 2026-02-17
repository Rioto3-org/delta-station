#!/usr/bin/env python3
"""
Delta地点 観測ダッシュボード (Streamlit)

時系列グラフで観測データを可視化。
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="Delta地点 観測ダッシュボード",
    page_icon="🌡️",
    layout="wide"
)

DB_PATH = Path(__file__).parent.parent.parent / "outputs" / "database" / "delta_station.db"


@st.cache_data(ttl=60)
def load_data(hours: int = 168):
    """観測データを読み込み"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = f"""
            SELECT 
                observed_at,
                temperature,
                road_temperature,
                wind_speed,
                cumulative_rainfall,
                road_condition
            FROM observations
            WHERE observed_at >= datetime('now', '-{hours} hours', 'localtime')
            ORDER BY observed_at ASC
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        if not df.empty:
            df['observed_at'] = pd.to_datetime(df['observed_at'])
        
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()


def main():
    st.title("🌡️ Delta地点 定点観測ダッシュボード")
    st.caption("作並宿（チェーン着脱所） - 宮城県仙台市青葉区作並")
    
    # サイドバー設定
    st.sidebar.header("表示設定")
    period = st.sidebar.selectbox(
        "表示期間",
        options=[24, 168, 720],
        format_func=lambda x: f"{x//24}日間" if x >= 24 else f"{x}時間",
        index=1
    )
    
    # データ読み込み
    df = load_data(hours=period)
    
    if df.empty:
        st.warning("データが見つかりません")
        return
    
    # 最新データ表示
    st.header("📊 最新観測データ")
    latest = df.iloc[-1]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        temp_val = latest['temperature']
        if pd.notna(temp_val):
            st.metric("気温", f"{temp_val:.1f}℃")
        else:
            st.metric("気温", "N/A")
    
    with col2:
        road_temp_val = latest['road_temperature']
        if pd.notna(road_temp_val):
            st.metric("路面温度", f"{road_temp_val:.1f}℃")
        else:
            st.metric("路面温度", "N/A")
    
    with col3:
        wind_val = latest['wind_speed']
        if pd.notna(wind_val):
            st.metric("風速", f"{wind_val:.1f}m/s")
        else:
            st.metric("風速", "N/A")
    
    with col4:
        rain_val = latest['cumulative_rainfall']
        if pd.notna(rain_val):
            st.metric("累加雨量", f"{rain_val:.1f}mm")
        else:
            st.metric("累加雨量", "N/A")
    
    # 路面状況
    road_cond = latest['road_condition']
    if pd.notna(road_cond) and road_cond:
        st.info(f"🛣️ **路面状況**: {road_cond}")
    
    st.caption(f"観測日時: {latest['observed_at']}")
    
    # グラフ表示
    st.header("📈 観測データ推移")
    
    # 温度推移
    st.subheader("気温・路面温度の推移")
    fig_temp = go.Figure()
    
    if df['temperature'].notna().any():
        fig_temp.add_trace(go.Scatter(
            x=df['observed_at'],
            y=df['temperature'],
            name='気温',
            line=dict(color='#FF6B6B', width=2),
            mode='lines+markers'
        ))
    
    if df['road_temperature'].notna().any():
        fig_temp.add_trace(go.Scatter(
            x=df['observed_at'],
            y=df['road_temperature'],
            name='路面温度',
            line=dict(color='#4ECDC4', width=2),
            mode='lines+markers'
        ))
    
    fig_temp.update_layout(
        xaxis_title="観測日時",
        yaxis_title="温度 (℃)",
        hovermode='x unified',
        height=400
    )
    st.plotly_chart(fig_temp, use_container_width=True)
    
    # 風速・雨量
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("風速の推移")
        if df['wind_speed'].notna().any():
            fig_wind = px.line(
                df,
                x='observed_at',
                y='wind_speed',
                labels={'observed_at': '観測日時', 'wind_speed': '風速 (m/s)'},
                line_shape='linear'
            )
            fig_wind.update_traces(line_color='#95E1D3')
            fig_wind.update_layout(height=300)
            st.plotly_chart(fig_wind, use_container_width=True)
        else:
            st.info("風速データがありません")
    
    with col2:
        st.subheader("累加雨量の推移")
        if df['cumulative_rainfall'].notna().any():
            fig_rain = px.line(
                df,
                x='observed_at',
                y='cumulative_rainfall',
                labels={'observed_at': '観測日時', 'cumulative_rainfall': '累加雨量 (mm)'},
                line_shape='linear'
            )
            fig_rain.update_traces(line_color='#3B7EA1')
            fig_rain.update_layout(height=300)
            st.plotly_chart(fig_rain, use_container_width=True)
        else:
            st.info("雨量データがありません")
    
    # 統計情報
    st.header("📊 統計情報")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("総レコード数", len(df))
    
    with col2:
        if df['temperature'].notna().any():
            st.metric("平均気温", f"{df['temperature'].mean():.1f}℃")
        else:
            st.metric("平均気温", "N/A")
    
    with col3:
        if df['temperature'].notna().any():
            st.metric("最低気温", f"{df['temperature'].min():.1f}℃")
        else:
            st.metric("最低気温", "N/A")


if __name__ == "__main__":
    main()
