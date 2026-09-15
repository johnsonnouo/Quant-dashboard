# config/settings.py
"""系統全域組態設定模組。

本模組集中定義了 API 連線參數、重試機制配置、Streamlit 頁面與快取週期、
以及預設市場追蹤標的等常數。
"""

from typing import Final, Dict, List

# ==============================================================================
# 網路請求與重試機制配置 (Network & Retry Configuration)
# ==============================================================================

# 預設 HTTP 請求超時時間 (秒)
DEFAULT_TIMEOUT: Final[int] = 12

# 最大重試次數
DEFAULT_MAX_RETRIES: Final[int] = 3

# Exponential Backoff 因子 (秒)
# 重試等待時間為: {backoff factor} * (2 ** ({retry count} - 1))
DEFAULT_BACKOFF_FACTOR: Final[float] = 0.8

# 需要進行自動重試的 HTTP 狀態碼
RETRY_STATUS_CODES: Final[List[int]] = [429, 500, 502, 503, 504]

# 模擬瀏覽器通用請求標頭 (避免被外部端點阻擋)
DEFAULT_HEADERS: Final[Dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# ==============================================================================
# Streamlit 快取配置 (Caching TTL Configuration)
# ==============================================================================

# 盤中或即時數據快取時間 (15 分鐘 = 900 秒)
CACHE_TTL_REALTIME: Final[int] = 15 * 60

# 盤後數據快取時間 (12 小時 = 43200 秒)
CACHE_TTL_DAILY: Final[int] = 12 * 60 * 60

# 靜態或週頻率數據快取時間 (24 小時 = 86400 秒)
CACHE_TTL_STATIC: Final[int] = 24 * 60 * 60

# ==============================================================================
# 市場預設追蹤標的 (Market Default Tickers)
# ==============================================================================

# 跨市場與總經標的
MACRO_TICKERS: Final[Dict[str, str]] = {
    "SOX": "^SOX",        # 費城半導體指數
    "OIL": "CL=F",        # 西德州原油期貨 (WTI)
    "TSM_ADR": "TSM",     # 台積電 ADR (美股)
    "TSMC_TW": "2330.TW", # 台積電 (台股)
    "USDTWD": "USDTWD=X", # 美元兌新台幣即期匯率
}

# 預設前五大熱門台股 ETF 代號
DEFAULT_ETF_CODES: Final[List[str]] = [
    "0050",   # 元大台灣50
    "0056",   # 元大高股息
    "00878",  # 國泰永續高股息
    "00919",  # 群益台灣精選高息
    "00929",  # 復華台灣科技優息
]

# 台積電 ADR 與普通股換算係數 (1 單位 ADR 兌換 5 股普通股)
TSM_ADR_RATIO: Final[int] = 5
