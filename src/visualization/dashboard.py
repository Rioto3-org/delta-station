#!/usr/bin/env python3
"""
Delta地点 観測ダッシュボード (Streamlit)

時系列グラフで観測データを可視化。
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.visualization.db import query_dataframe, query_one

# ページ設定
st.set_page_config(
    page_title="Delta地点 観測ダッシュボード",
    page_icon="🌡️",
    layout="wide"
)
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        width: 100% !important;
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
    *, *::before, *::after {
        box-sizing: border-box !important;
    }
    [data-testid="stMain"] > div,
    [data-testid="stMain"] .block-container,
    [data-testid="column"],
    [data-testid="stHorizontalBlock"],
    [data-testid="stVerticalBlock"],
    [data-testid="stDataFrame"],
    [data-testid="stPlotlyChart"],
    [data-testid="stImage"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
    }
    [data-testid="stDataFrame"] > div,
    [data-testid="stPlotlyChart"] > div {
        max-width: 100% !important;
        overflow-x: auto !important;
    }
    [data-testid="stImage"] img {
        width: 100% !important;
        max-width: 95vw !important;
        height: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(ttl=60)
def load_data(hours: int = 168):
    """観測データを読み込み"""
    try:
        query = f"""
            SELECT 
                observed_at,
                temperature,
                road_temperature,
                wind_speed,
                cumulative_rainfall,
                road_condition
            FROM delta.observations
            WHERE observed_at >=
                (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Tokyo')
                - (%s * INTERVAL '1 hour')
            ORDER BY observed_at ASC
        """
        df = query_dataframe(query, (hours,))
        
        if not df.empty:
            df['observed_at'] = pd.to_datetime(df['observed_at'])
        
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_image_metadata() -> pd.DataFrame:
    """画像メタデータをDBから読み込み"""
    query = """
        SELECT id, observed_at, captured_at, image_filename,
               image_mime_type, image_byte_size
        FROM delta.observations
        WHERE image_data IS NOT NULL
    """
    query += " ORDER BY observed_at DESC"

    try:
        df = query_dataframe(query)
        if df.empty:
            return df
        df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce")
        df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def load_observation_at(observed_at: str) -> pd.Series | None:
    """指定日時の観測データを1件取得"""
    query = """
        SELECT observed_at, temperature, road_temperature, wind_speed, cumulative_rainfall, road_condition
        FROM delta.observations
        WHERE observed_at = %s
        LIMIT 1
    """
    try:
        row_df = query_dataframe(query, (observed_at,))
        if row_df.empty:
            return None
        row_df["observed_at"] = pd.to_datetime(row_df["observed_at"], errors="coerce")
        return row_df.iloc[0]
    except Exception:
        return None


@st.cache_data(ttl=60)
def load_image(image_id: int) -> tuple[bytes, str] | None:
    """Load one image only when the user selects it."""
    row = query_one(
        """
        SELECT image_data, image_mime_type
        FROM delta.observations
        WHERE id = %s AND image_data IS NOT NULL
        """,
        (image_id,),
    )
    if row is None:
        return None
    return bytes(row[0]), row[1] or "image/jpeg"


def render_image_viewer(selected_row: pd.Series | None) -> str | None:
    """画像表示"""
    st.markdown("**🖼️ 画像プレビュー**")

    if selected_row is None:
        st.info("画像メタデータがありません")
        return None

    if pd.notna(selected_row["captured_at"]):
        st.write(f"撮影日時: {selected_row['captured_at']}")

    image = load_image(int(selected_row["id"]))
    if image is not None:
        image_data, _ = image
        st.image(image_data, caption=str(selected_row["image_filename"]), width=520)
    else:
        st.warning("画像本体が見つかりません（メタデータのみ存在）")

    current_key = "image_viewer_index"
    max_index = int(st.session_state.get("image_viewer_max_index", 0))
    current_index = int(st.session_state.get(current_key, 0))
    nav_prev, nav_next = st.columns(2)
    with nav_prev:
        if st.button("◀ 1つ前", use_container_width=True, disabled=current_index >= max_index):
            st.session_state[current_key] = min(current_index + 1, max_index)
    with nav_next:
        if st.button("1つ次 ▶", use_container_width=True, disabled=current_index <= 0):
            st.session_state[current_key] = max(current_index - 1, 0)

    if pd.isna(selected_row["observed_at"]):
        return None
    return selected_row["observed_at"].strftime("%Y-%m-%d %H:%M")


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
    
    st.header("🧭 最新状況")
    latest = df.iloc[-1]
    image_df = load_image_metadata()
    selected_row = None
    selected_observed_at = None

    if not image_df.empty:
        current_key = "image_viewer_index"
        if current_key not in st.session_state:
            st.session_state[current_key] = 0
        max_index = len(image_df) - 1
        st.session_state["image_viewer_max_index"] = max_index
        current_index = int(st.session_state.get(current_key, 0))
        current_index = min(max(current_index, 0), max_index)
        st.session_state[current_key] = current_index

        current_index = int(st.session_state.get(current_key, 0))
        current_index = min(max(current_index, 0), max_index)
        selected_row = image_df.iloc[current_index]
        if pd.notna(selected_row["observed_at"]):
            selected_observed_at = selected_row["observed_at"].strftime("%Y-%m-%d %H:%M")

    left_col, right_col = st.columns([1.2, 1.0], gap="large")

    with left_col:
        selected_observed_at = render_image_viewer(selected_row)

    with right_col:
        synced = load_observation_at(selected_observed_at) if selected_observed_at else None
        current = synced if synced is not None else latest
        st.markdown("**📊 最新観測データ**")
        st.caption(f"表示中の観測日時: {current['observed_at']}")
        col1, col2 = st.columns(2)
        with col1:
            temp_val = current['temperature']
            if pd.notna(temp_val):
                st.metric("気温", f"{temp_val:.1f}℃")
            else:
                st.metric("気温", "N/A")
        with col2:
            road_temp_val = current['road_temperature']
            if pd.notna(road_temp_val):
                st.metric("路面温度", f"{road_temp_val:.1f}℃")
            else:
                st.metric("路面温度", "N/A")

        col3, col4 = st.columns(2)
        with col3:
            wind_val = current['wind_speed']
            if pd.notna(wind_val):
                st.metric("風速", f"{wind_val:.1f}m/s")
            else:
                st.metric("風速", "N/A")
        with col4:
            rain_val = current['cumulative_rainfall']
            if pd.notna(rain_val):
                st.metric("累加雨量", f"{rain_val:.1f}mm")
            else:
                st.metric("累加雨量", "N/A")

        road_cond = current['road_condition']
        if pd.notna(road_cond) and road_cond:
            st.info(f"🛣️ **路面状況**: {road_cond}")

        st.markdown("**期間統計**")
        stat1, stat2 = st.columns(2)
        with stat1:
            st.metric("総レコード数", len(df))
        with stat2:
            if df['temperature'].notna().any():
                st.metric("最高気温", f"{df['temperature'].max():.1f}℃")
            else:
                st.metric("最高気温", "N/A")

        stat3, stat4 = st.columns(2)
        with stat3:
            if df['temperature'].notna().any():
                st.metric("最低気温", f"{df['temperature'].min():.1f}℃")
            else:
                st.metric("最低気温", "N/A")
        with stat4:
            data_start = df['observed_at'].min()
            data_end = df['observed_at'].max()
            if pd.notna(data_start) and pd.notna(data_end):
                st.caption(
                    f"データ期間: {data_start.strftime('%Y-%m-%d %H:%M')} 〜 "
                    f"{data_end.strftime('%Y-%m-%d %H:%M')}"
                )
            else:
                st.caption("データ期間: N/A")

    st.markdown("**データ期間テーブル（最新20件）**")
    recent_df = (
        df.sort_values("observed_at", ascending=False)
        .head(20)
        .copy()
    )
    if not recent_df.empty:
        table_df = recent_df[
            [
                "observed_at",
                "temperature",
                "road_temperature",
                "wind_speed",
                "cumulative_rainfall",
                "road_condition",
            ]
        ].copy()
        table_df.insert(0, "No", range(1, len(table_df) + 1))
        table_df["observed_at"] = table_df["observed_at"].dt.strftime("%Y-%m-%d %H:%M")
        table_df = table_df.rename(
            columns={
                "observed_at": "観測日時",
                "temperature": "気温(℃)",
                "road_temperature": "路面温度(℃)",
                "wind_speed": "風速(m/s)",
                "cumulative_rainfall": "累加雨量(mm)",
                "road_condition": "路面状況",
            }
        )
        st.dataframe(table_df, use_container_width=True, hide_index=True)
    else:
        st.caption("表示できる観測日時がありません")
    
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
    
if __name__ == "__main__":
    main()
