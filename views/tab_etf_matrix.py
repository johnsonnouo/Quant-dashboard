# views/tab_etf_matrix.py
"""熱門 ETF 成分股重疊度與被動資金鎖碼分析視圖 (Tab: ETF 籌碼重疊度)。

提供使用者自由勾選多檔熱門台股 ETF (如 0050, 0056, 00878, 00919, 00929)，
自動比對計算成分股重疊次數、合計名目權重，並可視化排行被動資金強力鎖碼的核心標的。
"""

from typing import Dict, List

import pandas as pd
import streamlit as st

from config.settings import DEFAULT_ETF_CODES
from fetchers.etf_fetcher import ETFFetcher
from processors.etf_processor import ETFProcessor
from visualizers.plotters import PlotlyVisualizer

visualizer = PlotlyVisualizer()
processor = ETFProcessor()


@st.cache_data(ttl=3600)
def load_etf_components(etf_codes: List[str]) -> Dict[str, pd.DataFrame]:
    """快取獲取各檔 ETF 最新成分股清單。"""
    result: Dict[str, pd.DataFrame] = {}
    with ETFFetcher() as ef:
        for code in etf_codes:
            try:
                df = ef.fetch_etf_components(code)
                if not df.empty:
                    result[code] = df
            except Exception as e:
                st.warning(f"獲取 ETF {code} 成分股失敗: {str(e)}")
    return result


def render_tab_etf_matrix() -> None:
    """渲染 ETF 成分股矩陣與鎖碼分析頁籤。"""
    st.markdown("### 🧩 熱門 ETF 成分股重疊度與被動資金鎖碼矩陣")
    st.caption("勾選多檔熱門 ETF，交叉運算被動基金共同持有檔數與名目持股權重，快速發掘被動買盤鎖碼核心股。")

    # 控制項：選擇 ETF 標的
    col_sel, col_topn = st.columns([3, 1])

    with col_sel:
        selected_etfs = st.multiselect(
            "選擇欲比對之 ETF 清單",
            options=DEFAULT_ETF_CODES + ["006208", "00713", "00940"],
            default=["0050", "0056", "00878"],
            help="可自由多選，系統將交叉計算被動資金同時建倉的標的",
        )

    with col_topn:
        top_n = st.slider("鎖碼排行顯示前幾名", min_value=5, max_value=30, value=15, step=5)

    if not selected_etfs:
        st.info("請至少選擇 1 檔 ETF 進行分析。")
        return

    with st.spinner(f"正在交叉比對 {', '.join(selected_etfs)} 成分股數據..."):
        etf_dict = load_etf_components(selected_etfs)

    if not etf_dict:
        st.error("未能成功獲取任何所選 ETF 的成分股數據。")
        return

    # 計算重疊矩陣
    overlap_df = processor.analyze_overlaps(etf_dict, min_overlap=1)

    if overlap_df.empty:
        st.warning("查無重疊成份股資料。")
        return

    # 1. 頂部 KPI 卡片
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(label="已比對 ETF 檔數", value=f"{len(etf_dict)} 檔")

    with c2:
        total_unique_stocks = len(overlap_df)
        st.metric(label="成分股總數 (去除重複)", value=f"{total_unique_stocks} 檔")

    with c3:
        multi_held = (overlap_df["Overlap_Count"] >= 2).sum()
        st.metric(label="被 >= 2 檔 ETF 共同持有", value=f"{multi_held} 檔")

    with c4:
        top_locked_stock = overlap_df.iloc[0]
        st.metric(
            label="被動資金鎖碼冠軍",
            value=f"{top_locked_stock['Stock_Name']} ({top_locked_stock['Stock_Code']})",
            delta=f"權重 {top_locked_stock['Total_Weight']:.1f}% ({int(top_locked_stock['Overlap_Count'])}檔持有)",
        )

    st.markdown("---")

    # 2. 圖表區域
    fig = visualizer.plot_etf_overlaps(
        overlap_df=overlap_df,
        top_n=top_n,
        title=f"被動資金鎖碼排行 Top {top_n} (按合計名目權重與持有檔數排序)",
        height=520,
    )
    st.plotly_chart(fig, use_container_width=True)

    # 3. 完整清單明細表格
    with st.expander("📋 查看完整成分股重疊權重交叉總表", expanded=False):
        # 格式化權重顯示
        display_df = overlap_df.copy()
        for col in selected_etfs:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}%" if x > 0 else "-")

        display_df["Total_Weight"] = display_df["Total_Weight"].apply(lambda x: f"{x:.2f}%")

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )
