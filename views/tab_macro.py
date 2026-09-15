# views/tab_macro.py
"""總經指標與跨市場連動儀表板視圖 (Tab: 總經與美股連動)。

展示費半 (^SOX)、西德州原油 (CL=F)、台積電 ADR 溢折價率歷史走勢，
並提供均線平滑與即時指標卡片。
"""

import streamlit as st
import pandas as pd

from fetchers.macro_fetcher import MacroFetcher
from processors.macro_processor import MacroProcessor
from visualizers.plotters import PlotlyVisualizer

# 實例化繪圖器與處理器
visualizer = PlotlyVisualizer()
processor = MacroProcessor()


@st.cache_data(ttl=3600)
def get_macro_data(period: str = "6mo") -> dict:
    """快取獲取總經數據與計算 ADR 溢價率。"""
    with MacroFetcher() as mf:
        macro_all = mf.fetch_all_macro_history(period=period)
        summary = mf.fetch_latest_summary()
        try:
            adr_df = mf.fetch_adr_premium(period=period)
        except Exception:
            adr_df = pd.DataFrame()

    return {
        "macro_all": macro_all,
        "summary": summary,
        "adr_df": adr_df,
    }


def render_tab_macro() -> None:
    """渲染總經與美股連動頁籤。"""
    st.markdown("### 🌐 國際總經與美股連動即時監控")
    st.caption("即時追蹤費城半導體指數、西德州原油期貨走勢與台積電 ADR 溢折價率，洞察跨市場資金風向。")

    # 控制面板
    col_ctrl, _ = st.columns([2, 4])
    with col_ctrl:
        period_choice = st.select_slider(
            "歷史觀察期間",
            options=["1mo", "3mo", "6mo", "1y", "2y"],
            value="6mo",
            key="macro_period_slider",
        )

    with st.spinner("正在獲取國際總經最新即時數據..."):
        try:
            data = get_macro_data(period=period_choice)
        except Exception as e:
            st.error(f"獲取總經數據發生錯誤: {str(e)}")
            return

    summary = data["summary"]
    macro_all = data["macro_all"]
    adr_df = data["adr_df"]

    # 1. 頂部 KPI 數據卡片
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        sox_info = summary.get("SOX", {})
        st.metric(
            label="費城半導體 (^SOX)",
            value=f"{sox_info.get('price', 0.0):,.1f}",
            delta=f"{sox_info.get('change_pct', 0.0):+.2f}%",
        )

    with c2:
        oil_info = summary.get("OIL", {})
        st.metric(
            label="西德州原油 (CL=F)",
            value=f"${oil_info.get('price', 0.0):,.2f}",
            delta=f"{oil_info.get('change_pct', 0.0):+.2f}%",
        )

    with c3:
        tsm_info = summary.get("TSMC_TW", {})
        st.metric(
            label="台積電 (2330.TW)",
            value=f"{tsm_info.get('price', 0.0):,.0f} 元",
            delta=f"{tsm_info.get('change_pct', 0.0):+.2f}%",
        )

    with c4:
        adr_prem = summary.get("ADR_Premium", {})
        prem_val = adr_prem.get("premium_pct", 0.0)
        st.metric(
            label="台積電 ADR 溢價率",
            value=f"{prem_val:+.2f}%",
            delta=f"折合台幣 {adr_prem.get('tsm_tw_equiv', 0):,.0f} 元",
            delta_color="normal" if prem_val >= 0 else "inverse",
        )

    st.markdown("---")

    # 2. 圖表區域 (分左右兩欄)
    tab_chart1, tab_chart2 = st.tabs(["📊 台積電 ADR 溢折價率分析", "📈 費城半導體與原油走勢"])

    with tab_chart1:
        if not adr_df.empty:
            fig_adr = visualizer.plot_adr_premium(
                df=adr_df,
                date_col="Date",
                premium_col="ADR_Premium_Pct",
                title=f"台積電 ADR 溢折價率走勢 ({period_choice})",
                height=480,
            )
            st.plotly_chart(fig_adr, use_container_width=True)
            st.info("💡 **量化解讀小提示**：當 TSM ADR 溢價率 > +10% 時，通常代表國際買盤強勁，次日台股台積電普通股有極高機率開高向上收斂價差；反之若呈現折價，需留意美股科技股提早提款的風險。")
        else:
            st.warning("暫無足夠之 ADR 歷史數據供繪圖。")

    with tab_chart2:
        if not macro_all.empty:
            macro_reset = macro_all.reset_index()
            date_col = macro_reset.columns[0]

            # 繪製費半與均線
            if "SOX" in macro_reset.columns:
                sox_ma_df = processor.calculate_moving_averages(
                    macro_reset, windows=[20, 60], price_col="SOX"
                )
                fig_sox = visualizer.plot_time_series_line(
                    df=sox_ma_df,
                    x_col=date_col,
                    y_cols=["SOX", "MA_20", "MA_60"],
                    col_names=["費半指數", "月線 (20MA)", "季線 (60MA)"],
                    title=f"費城半導體指數 (^SOX) 與多空均線 ({period_choice})",
                    y_title="指數點數",
                    height=450,
                )
                st.plotly_chart(fig_sox, use_container_width=True)

            # 繪製原油期貨
            if "OIL" in macro_reset.columns:
                fig_oil = visualizer.plot_time_series_line(
                    df=macro_reset,
                    x_col=date_col,
                    y_cols=["OIL"],
                    col_names=["WTI 原油價格 (美元/桶)"],
                    title=f"西德州原油期貨價格 (CL=F) ({period_choice})",
                    y_title="美元/桶",
                    height=380,
                )
                st.plotly_chart(fig_oil, use_container_width=True)
