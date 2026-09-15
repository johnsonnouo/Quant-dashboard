# main.py
"""台股量化監控儀表板 - 應用程式進入點。

本應用程式基於 Streamlit 與 Plotly 構建，整合宏觀跨市場指標、
熱門 ETF 被動資金鎖碼分析、期貨與集保籌碼追蹤、以及大盤市場廣度騰落線。
"""

import datetime
import streamlit as st

# 1. 頁面全域配置 (必須置於所有 Streamlit 指令最前列)
st.set_page_config(
    page_title="台股量化監控儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. 引入視圖層模組
from views.tab_macro import render_tab_macro
from views.tab_etf_matrix import render_tab_etf_matrix
from views.tab_chips import render_tab_chips
from views.tab_market_breadth import render_tab_market_breadth


# 3. 注入自訂暗黑金融美學 CSS
CUSTOM_DARK_CSS = """
<style>
    /* 全域暗黑底色微調 */
    .stApp {
        background-color: #0b0e14;
        color: #e6edf3;
    }
    
    /* 頂部標題發光漸層 */
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 50%, #f7b731 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    
    .sub-header {
        font-size: 1.0rem;
        color: #8b949e;
        margin-bottom: 1.5rem;
    }

    /* Metric 卡片美化 (深灰微透明玻璃感) */
    div[data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    
    div[data-testid="stMetricLabel"] > label {
        color: #8b949e !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
    }
    
    div[data-testid="stMetricValue"] > div {
        color: #f0f6fc !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
    }

    /* Tabs 標籤美化 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #30363d;
    }

    .stTabs [data-baseweb="tab"] {
        height: 48px;
        background-color: transparent;
        border-radius: 6px 6px 0px 0px;
        color: #8b949e;
        font-weight: 600;
        font-size: 0.95rem;
        padding: 0 20px;
    }

    .stTabs [aria-selected="true"] {
        background-color: #161b22 !important;
        color: #58a6ff !important;
        border-bottom: 2px solid #58a6ff !important;
    }

    /* 側邊欄樣式 */
    section[data-testid="stSidebar"] {
        background-color: #10141d;
        border-right: 1px solid #21262d;
    }
</style>
"""
st.markdown(CUSTOM_DARK_CSS, unsafe_allow_html=True)


def main() -> None:
    """儀表板主入口函數。"""
    
    # 頂部儀表板標題
    st.markdown('<div class="main-header">📈 台股量化即時監控儀表板</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">整合跨市場宏觀聯動・被動 ETF 鎖碼追蹤・三大法人期指籌碼・大盤市場廣度</div>',
        unsafe_allow_html=True,
    )

    # 4. 左側邊欄 (Sidebar)
    with st.sidebar:
        st.markdown("### ⚙️ 系統控制台")
        st.caption("量化數據管線與快取管理中心")
        
        # 清除快取按鈕
        if st.button("🔄 清除快取並重新整理", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.success("已清除所有本機資料快取，重新加載最新數據中...")
            st.rerun()

        st.markdown("---")
        
        # 系統即時資訊
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.markdown(f"**⏰ 系統時間**：`{now_str}`")
        st.markdown("**🛡️ 快取週期**：`1 小時 (3600s)`")
        st.markdown("**🔌 資料來源**：`TWSE / TAIFEX / TDCC / YahooFinance`")
        
        st.markdown("---")
        st.markdown("### 🧭 模組架構導覽")
        st.info(
            "1. **總經與美股連動**：費半、WTI原油與台積電ADR溢折價\n"
            "2. **ETF 籌碼重疊度**：多檔 ETF 重疊持股與被動買盤鎖碼\n"
            "3. **期貨與集保籌碼**：外資留倉均線與個股千張/散戶差額\n"
            "4. **大盤市場廣度**：每日淨上漲家數與騰落指標 (AD Line)"
        )
        
        st.markdown("---")
        st.caption("© 2026 台股量化分析工程系統 · Powered by Streamlit & Plotly")

    # 5. 主畫面 Tabs 頁籤導覽
    tabs = st.tabs([
        "🌐 總經與美股連動",
        "🧩 ETF 籌碼重疊度",
        "🎯 期貨與集保籌碼",
        "📊 大盤市場廣度",
    ])

    with tabs[0]:
        render_tab_macro()

    with tabs[1]:
        render_tab_etf_matrix()

    with tabs[2]:
        render_tab_chips()

    with tabs[3]:
        render_tab_market_breadth()


if __name__ == "__main__":
    main()
