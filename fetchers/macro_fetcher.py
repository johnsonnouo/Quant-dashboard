# fetchers/macro_fetcher.py
"""跨市場與宏觀總經數據獲取模組。

本模組繼承 BaseFetcher，主要整合 yfinance 獲取國際市場與台股連動的重要指標，
包含費城半導體指數 (^SOX)、西德州原油期貨 (CL=F)、台積電 ADR (TSM)、
台股台積電 (2330.TW) 以及美元兌新台幣 (USDTWD=X) 匯率，並提供台積電 ADR 溢折價率計算。
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from config.settings import (
    DEFAULT_TIMEOUT,
    MACRO_TICKERS,
    TSM_ADR_RATIO,
)
from fetchers.base import BaseFetcher, DataFetchError

logger = logging.getLogger(__name__)


class MacroFetcher(BaseFetcher):
    """跨市場與總體經濟數據獲取器。

    繼承自 BaseFetcher，提供國際宏觀指數報價與台積電 ADR 溢價率分析數據。
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        custom_tickers: Optional[Dict[str, str]] = None,
    ) -> None:
        """初始化 MacroFetcher。

        Args:
            timeout (int): 請求超時時間。
            custom_tickers (Optional[Dict[str, str]]): 自訂指標字典，預設使用 settings.MACRO_TICKERS。
        """
        super().__init__(timeout=timeout)
        self.tickers: Dict[str, str] = custom_tickers or dict(MACRO_TICKERS)

    def fetch_ticker_history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """獲取指定代碼的歷史 OHLCV 報價數據。

        Args:
            symbol (str): 標的代碼 (例如 '^SOX', 'CL=F', 'TSM', '2330.TW', 'USDTWD=X')。
            period (str): 數據期間，如 '1mo', '3mo', '6mo', '1y', '2y', '5y'。
            interval (str): 數據週期，如 '1d', '1wk'。

        Returns:
            pd.DataFrame: 包含標準欄位 ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'] 的 DataFrame。

        Raises:
            DataFetchError: 當 yfinance 獲取失敗或回傳空數據時拋出。
        """
        logger.info("獲取代號 %s 之歷史報價 (期間: %s, 週期: %s)", symbol, period, interval)
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, timeout=self.timeout)

            if df is None or df.empty:
                raise DataFetchError(
                    message=f"標的 {symbol} 未能獲取到任何歷史數據 (period={period})",
                    endpoint=f"yfinance://{symbol}",
                )

            # 標準化索引與欄位名稱
            df = df.reset_index()
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            elif "Datetime" in df.columns:
                df["Date"] = pd.to_datetime(df["Datetime"]).dt.tz_localize(None)

            cols_needed = ["Date", "Open", "High", "Low", "Close", "Volume"]
            existing_cols = [c for c in cols_needed if c in df.columns]
            result_df = df[existing_cols].copy()
            result_df.sort_values(by="Date", inplace=True)
            result_df.reset_index(drop=True, inplace=True)
            return result_df

        except Exception as exc:
            if isinstance(exc, DataFetchError):
                raise exc
            logger.error("yfinance 獲取 %s 數據時發生未預期錯誤: %s", symbol, str(exc))
            raise DataFetchError(
                message=f"獲取標的 {symbol} 報價失敗: {str(exc)}",
                endpoint=f"yfinance://{symbol}",
            ) from exc

    def fetch_all_macro_history(
        self,
        period: str = "6mo",
    ) -> pd.DataFrame:
        """獲取所有預設總經與連動標的收盤價對照表。

        包含費半 (^SOX)、西德州原油 (CL=F)、台積電 ADR (TSM)、
        台股台積電 (2330.TW) 及 USD/TWD 匯率。

        Args:
            period (str): 歷史數據期間，預設為 '6mo'。

        Returns:
            pd.DataFrame: 以 Date 為索引，各標的名稱為欄位的收盤價 DataFrame。
        """
        logger.info("開始獲取所有宏觀指標歷史收盤價 (期間: %s)", period)
        price_series_dict: Dict[str, pd.Series] = {}

        for name, sym in self.tickers.items():
            try:
                df = self.fetch_ticker_history(symbol=sym, period=period)
                if not df.empty and "Date" in df.columns and "Close" in df.columns:
                    series = df.set_index("Date")["Close"]
                    price_series_dict[name] = series
            except Exception as exc:
                logger.warning("獲取指標 %s (%s) 失敗，略過此項: %s", name, sym, str(exc))

        if not price_series_dict:
            raise DataFetchError(
                message="無法獲取任何宏觀指標數據",
                endpoint="yfinance://macro_all",
            )

        merged_df = pd.DataFrame(price_series_dict)
        merged_df.sort_index(inplace=True)
        # 以前向填充補齊跨市場不同休市日的缺失值
        merged_df.ffill(inplace=True)
        merged_df.bfill(inplace=True)
        return merged_df

    def fetch_adr_premium(
        self,
        period: str = "6mo",
    ) -> pd.DataFrame:
        """計算台積電 ADR (TSM) 相對台股台積電 (2330.TW) 的溢折價率歷史。

        計算公式:
            ADR折合台幣價 = (TSM 收盤價 * USDTWD 匯率) / TSM_ADR_RATIO
            溢價率 (%) = ((ADR折合台幣價 - 2330收盤價) / 2330收盤價) * 100

        Args:
            period (str): 歷史數據期間，預設 '6mo'。

        Returns:
            pd.DataFrame: 包含各標的收盤價、折合台幣價與溢價率 (ADR_Premium_Pct) 的 DataFrame。
        """
        logger.info("計算台積電 ADR 溢價率 (期間: %s)", period)
        macro_df = self.fetch_all_macro_history(period=period)

        required = ["TSM_ADR", "TSMC_TW", "USDTWD"]
        for col in required:
            if col not in macro_df.columns:
                raise DataFetchError(
                    message=f"計算 ADR 溢價率缺少必要指標: {col}",
                    endpoint="yfinance://adr_calc",
                )

        df = macro_df[required].copy()
        # 計算 ADR 換算成台幣之每股價格
        df["TSM_TW_Equiv"] = (df["TSM_ADR"] * df["USDTWD"]) / TSM_ADR_RATIO
        # 計算溢折價比例 (%)
        df["ADR_Premium_Pct"] = (
            (df["TSM_TW_Equiv"] - df["TSMC_TW"]) / df["TSMC_TW"]
        ) * 100.0

        return df

    def fetch_latest_summary(self) -> Dict[str, Any]:
        """獲取各總經標的最新收盤行情與 ADR 溢價率之即時摘要。

        Returns:
            Dict[str, Any]: 各指標最新價格、日漲跌幅(%)與 ADR 溢價率之彙整字典。
        """
        summary: Dict[str, Any] = {}
        for name, sym in self.tickers.items():
            try:
                hist = self.fetch_ticker_history(symbol=sym, period="5d")
                if len(hist) >= 2:
                    curr_price = float(hist["Close"].iloc[-1])
                    prev_price = float(hist["Close"].iloc[-2])
                    change_pct = ((curr_price - prev_price) / prev_price) * 100.0
                    summary[name] = {
                        "symbol": sym,
                        "price": round(curr_price, 2),
                        "change_pct": round(change_pct, 2),
                        "date": hist["Date"].iloc[-1].strftime("%Y-%m-%d"),
                    }
                elif len(hist) == 1:
                    curr_price = float(hist["Close"].iloc[-1])
                    summary[name] = {
                        "symbol": sym,
                        "price": round(curr_price, 2),
                        "change_pct": 0.0,
                        "date": hist["Date"].iloc[-1].strftime("%Y-%m-%d"),
                    }
            except Exception as exc:
                logger.warning("取得標的 %s 最新行情失敗: %s", name, str(exc))

        # 計算最新 ADR 溢價
        if "TSM_ADR" in summary and "TSMC_TW" in summary and "USDTWD" in summary:
            tsm = summary["TSM_ADR"]["price"]
            tw = summary["TSMC_TW"]["price"]
            fx = summary["USDTWD"]["price"]
            if tw > 0:
                adr_equiv = (tsm * fx) / TSM_ADR_RATIO
                premium = ((adr_equiv - tw) / tw) * 100.0
                summary["ADR_Premium"] = {
                    "tsm_tw_equiv": round(adr_equiv, 2),
                    "premium_pct": round(premium, 2),
                }

        return summary
