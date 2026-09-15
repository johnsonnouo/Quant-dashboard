# views/tab_chips.py
"""期貨籌碼與集保股權分散度監控視圖 (Tab: 期貨與集保籌碼)。

展示外資台指期未平倉淨多空口數 (Net OI) 歷史走勢與均線平滑，
並提供輸入框供查詢個別上市櫃股票最新集保股權分散表與大戶散戶持股差額 (Spread)。
"""

import pandas as pd
import streamlit as st

from fetchers.futures_fetcher import FuturesFetcher
from fetchers.tdcc_fetcher import TDCCFetcher
from processors.chips_processor import ChipsProcessor
from visualizers.plotters import PlotlyVisualizer

visualizer = PlotlyVisualizer()
processor = ChipsProcessor()


@st.cache_data(ttl=3600)
def load_futures_data(days: int = 30) -> pd.DataFrame:
    """快取獲取外資期貨留倉口數與平滑指標。"""
    with FuturesFetcher() as ff:
        df_oi = ff.fetch_foreign_net_oi_history(days=days)
    return processor.smooth_foreign_oi(df_oi, windows=[5, 10])


@st.cache_data(ttl=3600)
def load_tdcc_data(stock_code: str) -> dict:
    """快取獲取指定個股之集保股權分散表與籌碼指標。"""
    with TDCCFetcher() as tdf:
        table_df = tdf.fetch_distribution_table(stock_code)
    spread_info = processor.calculate_tdcc_spread(table_df)
    return {
        "table_df": table_df,
        "spread_info": spread_info,
    }


def render_tab_chips() -> None:
    """渲染籌碼監控頁籤。"""
    st.markdown("### 🎯 機構主力與集保大戶籌碼深入追蹤")
    st.caption("即時監控期交所外資台指期留倉多空態度，並透視個別上市櫃股票集保 400 張以上大戶與散戶籌碼流向。")

    # =========================================================================
    # 第一區塊：外資台指期未平倉淨留倉
    # =========================================================================
    st.subheader("1. 期交所外資台指期未平倉淨多空部位 (Net Open Interest)")

    col_ctrl, _ = st.columns([2, 4])
    with col_ctrl:
        oi_days = st.select_slider(
            "歷史觀察天數",
            options=[15, 30, 45, 60],
            value=30,
            key="chips_oi_days",
        )

    with st.spinner("獲取期交所外資未平倉數據..."):
        try:
            oi_df = load_futures_data(days=oi_days)
        except Exception as e:
            st.error(f"獲取期貨籌碼失敗: {str(e)}")
            oi_df = pd.DataFrame()

    if not oi_df.empty:
        latest_row = oi_df.iloc[-1]
        prev_row = oi_df.iloc[-2] if len(oi_df) >= 2 else latest_row
        curr_oi = int(latest_row["Foreign_Net_OI"])
        daily_change = int(latest_row.get("Foreign_Net_Change", curr_oi - int(prev_row["Foreign_Net_OI"])))
        sentiment = latest_row.get("OI_Sentiment", "Neutral")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(
                label="外資最新淨留倉口數",
                value=f"{curr_oi:+,} 口",
                delta=f"{daily_change:+,} 口 (較前日)",
                delta_color="normal" if daily_change >= 0 else "inverse",
            )
        with c2:
            st.metric(
                label="5日平滑均線 (5MA)",
                value=f"{latest_row.get('OI_MA_5', 0):+,.0f} 口",
            )
        with c3:
            st.metric(
                label="10日平滑均線 (10MA)",
                value=f"{latest_row.get('OI_MA_10', 0):+,.0f} 口",
            )
        with c4:
            st.metric(
                label="外資期貨短線情緒",
                value="偏多 Bullish" if sentiment == "Bullish" else "偏空 Bearish",
                delta="空單大於萬口警戒" if curr_oi < -10000 else "留倉相對溫和",
                delta_color="off" if curr_oi >= -10000 else "inverse",
            )

        # 繪製圖表
        fig_oi = visualizer.plot_time_series_line(
            df=oi_df,
            x_col="Date",
            y_cols=["Foreign_Net_OI", "OI_MA_5", "OI_MA_10"],
            col_names=["外資淨未平倉口數", "5日均線", "10日均線"],
            title=f"外資台指期淨留倉口數走勢 ({oi_days} 日)",
            y_title="未平倉口數 (口)",
            height=430,
        )
        st.plotly_chart(fig_oi, use_container_width=True)

    st.markdown("---")

    # =========================================================================
    # 第二區塊：集保結算所個股股權分散表查詢
    # =========================================================================
    st.subheader("2. 集保戶股權分散度與大戶/散戶集中度查詢")

    col_input, col_preset = st.columns([2, 3])
    with col_input:
        target_stock = st.text_input(
            "輸入台股代碼查詢",
            value="2330",
            max_chars=6,
            help="例如輸入 2330 (台積電), 2454 (聯發科), 2317 (鴻海)",
        ).strip()

    with col_preset:
        st.write("快捷熱門標的:")
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("2330 台積電"):
            target_stock = "2330"
        if q2.button("2454 聯發科"):
            target_stock = "2454"
        if q3.button("2317 鴻海"):
            target_stock = "2317"
        if q4.button("2603 長榮"):
            target_stock = "2603"

    if target_stock:
        with st.spinner(f"正在查詢股票 {target_stock} 最新集保股權分散表..."):
            try:
                tdcc_data = load_tdcc_data(target_stock)
            except Exception as e:
                st.error(f"查詢集保股權失敗: {str(e)}")
                return

        table_df = tdcc_data["table_df"]
        info = tdcc_data["spread_info"]

        # 頂部卡片
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric(label="大戶持股比例 (>=400張)", value=f"{info['large_ratio_pct']:.2f}%")
        with m2:
            st.metric(label="散戶持股比例 (<10張)", value=f"{info['retail_ratio_pct']:.2f}%")
        with m3:
            spread = info["large_retail_spread"]
            st.metric(
                label="籌碼差額 Spread (大戶 - 散戶)",
                value=f"{spread:+.2f}%",
                delta="高度集中" if spread > 60 else "分佈平均",
            )
        with m4:
            st.metric(label="千張超級大戶 (>=1000張)", value=f"{info['super_large_ratio_pct']:.2f}%")

        # 繪製級距圖
        fig_tdcc = visualizer.plot_chips_spread(
            distribution_df=table_df,
            title=f"股票 {target_stock} 最新週集保股權級距分佈 (1~15級距)",
            height=460,
        )
        st.plotly_chart(fig_tdcc, use_container_width=True)

        with st.expander(f"📋 查看股票 {target_stock} 完整 1~15 級距明細表格"):
            st.dataframe(table_df, use_container_width=True, hide_index=True)
