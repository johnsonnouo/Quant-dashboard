# fetchers/futures_fetcher.py
"""台灣期貨交易所 (TAIFEX) 三大法人期貨籌碼數據獲取模組。

本模組繼承 BaseFetcher，主要從台灣期貨交易所官方開放資料下載並解析
三大法人（外資及陸資、投信、自營商）在台指期 (TXF) 等主要期貨契約的
「未平倉淨多空口數 (Net Open Interest)」與當日多空交易變化。
"""

import datetime
import io
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from config.settings import DEFAULT_TIMEOUT
from fetchers.base import BaseFetcher, DataFetchError

logger = logging.getLogger(__name__)


class FuturesFetcher(BaseFetcher):
    """台灣期交所 (TAIFEX) 期貨籌碼數據獲取器。

    提供台指期 (TXF) 三大法人、尤其是外資未平倉淨口數的查詢與分析。
    """

    TAIFEX_DOWN_URL = "https://www.taifex.com.tw/cht/3/futContractsDateDown"

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """初始化 FuturesFetcher。

        Args:
            timeout (int): 請求超時時間。
        """
        super().__init__(timeout=timeout)

    @staticmethod
    def _clean_int(val: Any) -> int:
        """安全清洗並轉換整數口數。"""
        if pd.isna(val) or val is None:
            return 0
        s = str(val).replace(",", "").strip()
        try:
            return int(float(s))
        except ValueError:
            return 0

    def fetch_institutional_positions(
        self,
        start_date: str,
        end_date: str,
        commodity_id: str = "TXF",
    ) -> pd.DataFrame:
        """獲取指定日期區間內期交所三大法人的期貨部位統計數據。

        Args:
            start_date (str): 起始日期，格式為 'YYYY/MM/DD' 或 'YYYY-MM-DD'。
            end_date (str): 結束日期，格式為 'YYYY/MM/DD' 或 'YYYY-MM-DD'。
            commodity_id (str): 商品代號，預設為 'TXF' (大台指期)。

        Returns:
            pd.DataFrame: 整理後的標準化 DataFrame，包含日期、商品名稱、身份別、
                         多方未平倉、空方未平倉、多空未平倉淨口數、當日多空交易淨口數等。

        Raises:
            DataFetchError: 下載失敗或無相符數據時拋出。
        """
        # 標準化日期格式為 YYYY/MM/DD
        s_date = start_date.replace("-", "/")
        e_date = end_date.replace("-", "/")

        payload = {
            "queryStartDate": s_date,
            "queryEndDate": e_date,
            "commodityId": commodity_id,
        }

        logger.info(
            "下載 TAIFEX 三大法人期貨部位 (商品: %s, 區間: %s ~ %s)",
            commodity_id,
            s_date,
            e_date,
        )

        resp = self._request_raw(
            method="POST",
            url=self.TAIFEX_DOWN_URL,
            data=payload,
        )

        # 期交所 CSV 採用 CP950 / MS950 編碼
        try:
            content_str = resp.content.decode("cp950", errors="replace")
        except Exception as exc:
            raise DataFetchError(
                message=f"解碼期交所回應內容失敗: {str(exc)}",
                endpoint=self.TAIFEX_DOWN_URL,
            ) from exc

        try:
            raw_df = pd.read_csv(io.StringIO(content_str))
        except Exception as exc:
            raise DataFetchError(
                message=f"解析期交所 CSV 內容失敗: {str(exc)}",
                endpoint=self.TAIFEX_DOWN_URL,
            ) from exc

        if raw_df.empty:
            raise DataFetchError(
                message=f"期交所於區間 {s_date} ~ {e_date} 未查得任何 {commodity_id} 數據",
                endpoint=self.TAIFEX_DOWN_URL,
            )

        # 欄位清除前後空格
        raw_df.columns = [str(c).strip() for c in raw_df.columns]

        # 欄位對應與清洗 (期交所標準繁中欄位)
        col_map = {
            "日期": "Date",
            "商品名稱": "Commodity",
            "身份別": "Investor_Type",
            "多方未平倉口數": "Long_OI",
            "空方未平倉口數": "Short_OI",
            "多空未平倉口數淨額": "Net_OI",
            "多空交易口數淨額": "Daily_Net_Volume",
        }

        # 驗證必要欄位存在
        for orig_col in ["日期", "身份別", "多空未平倉口數淨額"]:
            if orig_col not in raw_df.columns:
                raise DataFetchError(
                    message=f"期交所回傳格式缺少預期之欄位: {orig_col}",
                    endpoint=self.TAIFEX_DOWN_URL,
                )

        selected_cols = [c for c in col_map.keys() if c in raw_df.columns]
        df = raw_df[selected_cols].rename(columns=col_map).copy()

        # 清洗數值
        for num_col in ["Long_OI", "Short_OI", "Net_OI", "Daily_Net_Volume"]:
            if num_col in df.columns:
                df[num_col] = df[num_col].apply(self._clean_int)

        df["Investor_Type"] = df["Investor_Type"].str.strip()
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df.sort_values(by=["Date", "Investor_Type"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def fetch_foreign_net_oi_history(
        self,
        days: int = 30,
        commodity_id: str = "TXF",
    ) -> pd.DataFrame:
        """專門獲取「外資及陸資」台指期未平倉淨多空口數 (Net OI) 之歷史趨勢。

        外資淨多空部位是台股大盤最關鍵的期現貨避險與方向性先行指標。

        Args:
            days (int): 回溯天數，預設 30 天。
            commodity_id (str): 期貨代碼，預設 'TXF'。

        Returns:
            pd.DataFrame: 包含 Date、Foreign_Net_OI、Foreign_Daily_Change 之時間序列 DataFrame。
        """
        end_dt = datetime.date.today()
        # 考慮非交易日，多抓寬鬆範圍
        start_dt = end_dt - datetime.timedelta(days=int(days * 1.6))

        df_all = self.fetch_institutional_positions(
            start_date=start_dt.strftime("%Y/%m/%d"),
            end_date=end_dt.strftime("%Y/%m/%d"),
            commodity_id=commodity_id,
        )

        # 篩選外資
        foreign_df = df_all[
            df_all["Investor_Type"].str.contains("外資", na=False)
        ].copy()

        if foreign_df.empty:
            raise DataFetchError(
                message="期交所資料中無外資及陸資相關紀錄",
                endpoint=self.TAIFEX_DOWN_URL,
            )

        foreign_df = foreign_df[["Date", "Net_OI", "Daily_Net_Volume"]].copy()
        foreign_df.rename(
            columns={
                "Net_OI": "Foreign_Net_OI",
                "Daily_Net_Volume": "Foreign_Net_Change",
            },
            inplace=True,
        )

        # 截取最近要求的 days 筆交易日
        foreign_df.sort_values(by="Date", inplace=True)
        foreign_df = foreign_df.tail(days).reset_index(drop=True)
        return foreign_df

    def fetch_latest_futures_summary(
        self,
        commodity_id: str = "TXF",
    ) -> Dict[str, Any]:
        """獲取最新一個交易日三大法人的台指期未平倉詳細部位彙整。

        Returns:
            Dict[str, Any]: 包含最新日期、外資、投信、自營商各自的淨多空口數與單日口數變化。
        """
        today = datetime.date.today()
        start = today - datetime.timedelta(days=7)

        df = self.fetch_institutional_positions(
            start_date=start.strftime("%Y/%m/%d"),
            end_date=today.strftime("%Y/%m/%d"),
            commodity_id=commodity_id,
        )

        if df.empty:
            raise DataFetchError(
                message="無法獲取最新期交所數據",
                endpoint=self.TAIFEX_DOWN_URL,
            )

        latest_date = df["Date"].max()
        latest_df = df[df["Date"] == latest_date]

        summary: Dict[str, Any] = {
            "date": latest_date,
            "commodity": commodity_id,
            "foreign": {"net_oi": 0, "daily_change": 0},
            "investment_trust": {"net_oi": 0, "daily_change": 0},
            "dealer": {"net_oi": 0, "daily_change": 0},
        }

        for _, row in latest_df.iterrows():
            inv = str(row["Investor_Type"])
            net_oi = int(row["Net_OI"])
            change = int(row.get("Daily_Net_Volume", 0))

            if "外資" in inv:
                summary["foreign"] = {"net_oi": net_oi, "daily_change": change}
            elif "投信" in inv:
                summary["investment_trust"] = {"net_oi": net_oi, "daily_change": change}
            elif "自營商" in inv:
                summary["dealer"] = {"net_oi": net_oi, "daily_change": change}

        return summary
