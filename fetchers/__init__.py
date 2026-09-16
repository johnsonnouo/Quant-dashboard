# fetchers/__init__.py
"""數據爬蟲與 API 請求層模組。

集中匯出所有數據獲取器 (Fetchers) 與自訂例外，供業務邏輯層與 UI 層呼叫。
"""

from .base import BaseFetcher, DataFetchError
from .macro_fetcher import MacroFetcher
from .tw_market_fetcher import TWMarketFetcher
from .futures_fetcher import FuturesFetcher
from .etf_fetcher import ETFFetcher
from .tdcc_fetcher import TDCCFetcher
from .news_fetcher import fetch_morning_news

__all__ = [
    "BaseFetcher",
    "DataFetchError",
    "MacroFetcher",
    "TWMarketFetcher",
    "FuturesFetcher",
    "ETFFetcher",
    "TDCCFetcher",
    "fetch_morning_news",
]
