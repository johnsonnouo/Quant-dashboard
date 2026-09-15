# views/tab_market_breadth.py
"""台股大盤市場廣度與騰落指標 (AD Line) 監控視圖 (Tab: 大盤市場廣度)。

展示台股集中市場每日上漲家數、下跌家數、每日淨上漲家數 (Net Advances)，
以及經典的「累積騰落指標 (Advance-Decline Line, AD Line)」雙軸對比走勢，
用於早期洞察大盤指數與個股整體動態是否產生「多空背離」。
"""

import datetime
from typing import List

import pandas as pd
import streamlit as st

from fetchers.tw_market_fetcher import TWMarketFetcher
from processors.breadth_processor import BreadthProcessor
from visualizers.plotters import PlotlyVisualizer

visualizer = PlotlyVisualizer()
processor = BreadthProcessor()


@st.cache_data(ttl=3600)
def load_market_breadth_history(days: int = 15) -> pd.DataFrame:
    """快取回溯獲取最近 N 個交易日之大盤市場廣度並計算 AD Line。"""
    records: List[dict] = []
    curr_date = datetime.date.today()
    attempts = 0
    max_attempts = days * 2

    with TWMarketFetcher() as tf:
        while len(records) < days and attempts < max_attempts:
            if curr_date.weekday() < 5:
                d_str = curr_date.strftime("%Y%m%d")
                try:
                    res = tf.fetch_market_breadth(date_str=d_str)
                    if res["up_count"] > 0 or res["down_count"] > 0:
                        records.append(res)
                except Exception:
                    pass
            curr_date -= datetime.timedelta(days=1)
            attempts += 1

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    # 由舊至新排序以正確計算 cumsum
    df["Date"] = pd.to_datetime(df["date"])
    df.sort_values(by="Date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # 運算淨上漲家數與累積 AD Line
    ad_df = processor.calculate_ad_line(df, ma_windows=[5, 10])
    return ad_df


def render_tab_market_breadth() -> None:
    """渲染大盤市場廣度頁籤。"""
    st.markdown("### 📊 台股大盤市場廣度與騰落指標 (AD Line)")
    st.caption("透過全體上市股票之每日上漲與下跌家數累加，衡量市場整體真實多空氣氛，防範權值股掩護拉抬之虛胖指數。")

    col_ctrl, _ = st.columns([2, 4])
    with col_ctrl:
        history_days = st.select_slider(
            "歷史觀察天數",
            options=[10, 15, 20, 30],
            value=15,
            key="breadth_days_slider",
        )

    with st.spinner("正在回溯獲取台股大盤市場廣度數據..."):
        breadth_df = load_market_breadth_history(days=history_days)

    if breadth_df.empty:
        st.warning("暫無足夠之市場廣度歷史數據，請確認連線或稍後再試。")
        return

    # 1. 頂部 KPI 卡片
    latest = breadth_df.iloc[-1]
    prev = breadth_df.iloc[-2] if len(breadth_df) >= 2 else latest
    net_adv = int(latest["Net_Advances"])
    turnover_billion = latest["total_turnover_ntd"] / 100000000.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="最新股票上漲家數",
            value=f"{int(latest['up_count'])} 家",
            delta=f"漲停 {int(latest['up_limit_count'])} 家",
        )
    with c2:
        st.metric(
            label="最新股票下跌家數",
            value=f"{int(latest['down_count'])} 家",
            delta=f"跌停 {int(latest['down_limit_count'])} 家",
            delta_color="inverse",
        )
    with c3:
        st.metric(
            label="每日淨上漲家數 (上漲 - 下跌)",
            value=f"{net_adv:+,} 家",
            delta="市場偏多廣度佳" if net_adv > 0 else "市場偏弱偏空",
            delta_color="normal" if net_adv > 0 else "inverse",
        )
    with c4:
        st.metric(
            label="大盤一般股票成交金額",
            value=f"{turnover_billion:,.1f} 億元",
            delta=f"累積騰落線: {latest['AD_Line']:+,.0f}",
        )

    st.markdown("---")

    # 2. 圖表區域
    # 雙 Y 軸線圖：每日淨上漲家數 (左) vs 累積騰落指標 AD Line (右)
    fig_ad = visualizer.plot_dual_axis_line(
        df=breadth_df,
        x_col="Date",
        y1_col="Net_Advances",
        y2_col="AD_Line",
        y1_name="每日淨上漲家數",
        y2_name="累積騰落指標 (AD Line)",
        title=f"台股市場淨上漲家數 vs 騰落指標走勢 (近 {history_days} 交易日)",
        height=500,
    )
    st.plotly_chart(fig_ad, use_container_width=True)

    # 3. 量化教學卡片
    st.info(
        "💡 **騰落指標 (AD Line) 背離研判秘訣**：\n"
        "- **多頭背離**：大盤加權指數拉回整理甚至破底，但騰落指標 AD Line 卻率先止跌築底走揚，代表「中小型股普遍轉強，買氣提前擴散」，後市極具反彈契機。\n"
        "- **空頭背離**：大盤指數看似強勢持續創歷史新高，但 AD Line 卻步步走低，代表「僅有少數高權重權值股在拉抬撐盤，絕大多數個股都在默默出貨下跌」，需嚴防指數假突破後補跌。"
    )
