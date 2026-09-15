# fetchers/tdcc_fetcher.py
"""台灣集中保管結算所 (TDCC) 股權分散表數據獲取模組。

本模組繼承 BaseFetcher，主要從台灣集中保管結算所 (TDCC) 查詢並解析
個別股票每週公佈之「股權分散表」(各級距持股人數、股數與佔比)，
並自動計算 400 張以上大戶、千張大戶及 10 張以下散戶的籌碼集中度。
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
import pandas as pd

from config.settings import DEFAULT_TIMEOUT
from fetchers.base import BaseFetcher, DataFetchError

logger = logging.getLogger(__name__)


class TDCCFetcher(BaseFetcher):
    """集保結算所 (TDCC) 股權分散表數據獲取器。

    提供查詢上市櫃個股之持股級距人數、股數、庫存比例，以及大戶/散戶籌碼集中度計算。
    """

    TDCC_URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """初始化 TDCCFetcher。

        Args:
            timeout (int): 請求超時時間。
        """
        super().__init__(timeout=timeout)

    @staticmethod
    def _clean_stock_code(stock_code: str) -> str:
        """清洗股票代碼，例如 '2330.TW' -> '2330'。"""
        return re.sub(r"[^0-9]", "", stock_code)

    @staticmethod
    def _to_int(val: Any) -> int:
        """安全轉換字串或浮點數為整數，相容千分位逗號與小數點字串 (如 '218028.0')。"""
        if pd.isna(val) or val is None:
            return 0
        s = str(val).replace(",", "").strip()
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _to_float(val: Any) -> float:
        """安全轉換字串為浮點數，去除百分比與逗號。"""
        if pd.isna(val) or val is None:
            return 0.0
        s = str(val).replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except (ValueError, TypeError):
            return 0.0

    def fetch_available_dates(self) -> List[str]:
        """獲取集保結算所當前提供查詢的歷史日期清單 (由新到舊)。

        Returns:
            List[str]: 日期字串清單 (例如 ['20260911', '20260904', ...])。

        Raises:
            DataFetchError: 無法連線或無法解析日期時拋出。
        """
        logger.info("獲取 TDCC 可查詢日期清單")
        try:
            html = self.get_text(self.TDCC_URL)
            soup = BeautifulSoup(html, "html.parser")
            select_tag = soup.find("select", {"id": "scaDates"}) or soup.find("select", {"name": "scaDate"})
            if select_tag:
                dates = [
                    opt.get("value", "").strip()
                    for opt in select_tag.find_all("option")
                    if opt.get("value", "").strip()
                ]
                if dates:
                    return dates
            raise DataFetchError(
                message="未能從 TDCC 頁面解析出日期下拉清單",
                endpoint=self.TDCC_URL,
            )
        except Exception as exc:
            if isinstance(exc, DataFetchError):
                raise exc
            raise DataFetchError(
                message=f"連線至 TDCC 失敗: {str(exc)}",
                endpoint=self.TDCC_URL,
            ) from exc

    def fetch_distribution_table(
        self,
        stock_code: str,
        date_str: Optional[str] = None,
    ) -> pd.DataFrame:
        """獲取指定股票於指定日期（預設為最新一週）之股權分散表。

        Args:
            stock_code (str): 股票代號 (例如 '2330' 或 '2330.TW')。
            date_str (Optional[str]): 查詢日期 (格式 'YYYYMMDD')，預設為最新公告日。

        Returns:
            pd.DataFrame: 包含 1~15 級距之 DataFrame:
                - `Level`: 序號 (1~15)
                - `Holding_Range`: 持股分級 (例如 '1-999', '1,000-5,000', ..., '1,000,001以上')
                - `Holders_Count`: 持股人數
                - `Total_Shares`: 持有股數
                - `Percentage`: 占集保庫存數比例 (%)

        Raises:
            DataFetchError: 查詢失敗或查無該股票股權分散表時拋出。
        """
        code = self._clean_stock_code(stock_code)
        logger.info("查詢股票 %s 之集保股權分散表 (日期: %s)", code, date_str or "最新週")

        try:
            # 1. 取得最新表單頁面與 SYNCHRONIZER_TOKEN
            get_resp = self.get_text(self.TDCC_URL)
            soup_get = BeautifulSoup(get_resp, "html.parser")

            token_tag = soup_get.find("input", {"name": "SYNCHRONIZER_TOKEN"})
            token = token_tag.get("value") if token_tag else ""

            fir_date_tag = soup_get.find("input", {"name": "firDate"})
            latest_date = fir_date_tag.get("value") if fir_date_tag else ""

            query_date = date_str or latest_date

            if not query_date:
                available = self.fetch_available_dates()
                query_date = available[0] if available else ""

            # 2. 構建 POST Payload
            payload = {
                "SYNCHRONIZER_TOKEN": token,
                "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock",
                "method": "submit",
                "firDate": query_date,
                "scaDate": query_date,
                "sqlMethod": "StockNo",
                "stockNo": code,
            }

            post_resp = self._request_raw(
                method="POST",
                url=self.TDCC_URL,
                data=payload,
            )

            # 3. 解析回傳 HTML 表格
            dfs = pd.read_html(io.StringIO(post_resp.text))

        except Exception as exc:
            if isinstance(exc, DataFetchError):
                raise exc
            raise DataFetchError(
                message=f"獲取股票 {code} 股權分散表失敗: {str(exc)}",
                endpoint=self.TDCC_URL,
            ) from exc

        target_df: Optional[pd.DataFrame] = None
        for df in dfs:
            # 尋找包含 15 個級距的表格 (加上合計列約 16~17 列)
            if df.shape[0] >= 15 and df.shape[1] >= 4:
                target_df = df
                break

        if target_df is None:
            raise DataFetchError(
                message=f"查無股票 {code} 於 {query_date} 之股權分散資料",
                endpoint=self.TDCC_URL,
            )

        # 整理欄位
        target_df.columns = [str(c).strip() for c in target_df.columns]
        # 標準 5 欄: 序號, 持股/單位分級, 人數, 股數/單位數, 占集保庫存數比例%
        clean_rows: List[Dict[str, Any]] = []

        for _, row in target_df.iterrows():
            level_num = self._to_int(row.iloc[0])
            # 只取 1~15 級距，跳過合計或其他文字列
            if level_num < 1 or level_num > 15:
                continue

            range_text = str(row.iloc[1]).strip()
            holders_count = self._to_int(row.iloc[2])
            shares_count = self._to_int(row.iloc[3])
            percentage = self._to_float(row.iloc[4])

            clean_rows.append({
                "Level": level_num,
                "Holding_Range": range_text,
                "Holders_Count": holders_count,
                "Total_Shares": shares_count,
                "Percentage": percentage,
            })

        if not clean_rows:
            raise DataFetchError(
                message=f"解析股票 {code} 股權分散表格各級距數據失敗",
                endpoint=self.TDCC_URL,
            )

        res_df = pd.DataFrame(clean_rows)
        res_df["Level"] = pd.to_numeric(res_df["Level"], errors="coerce").fillna(0).astype(int)
        res_df["Holders_Count"] = pd.to_numeric(res_df["Holders_Count"], errors="coerce").fillna(0).astype(int)
        res_df["Total_Shares"] = pd.to_numeric(res_df["Total_Shares"], errors="coerce").fillna(0).astype("int64")
        res_df["Percentage"] = pd.to_numeric(res_df["Percentage"], errors="coerce").fillna(0.0).astype(float)
        res_df.sort_values(by="Level", inplace=True)
        res_df.reset_index(drop=True, inplace=True)
        return res_df

    def fetch_large_holders_summary(
        self,
        stock_code: str,
        date_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        """計算指定股票之「大戶籌碼集中度」與「散戶分佈」結構摘要。

        常態劃分規則:
            - 散戶群體 (< 10 張): 級距 1~3 (1~9,999 股)
            - 中實戶群體 (10~400 張): 級距 4~11 (10,000~399,999 股)
            - 大戶群體 (>= 400 張): 級距 12~15 (400,000 股以上)
            - 超級千張大戶 (>= 1000 張): 級距 15 (1,000,001 股以上)

        Args:
            stock_code (str): 股票代號。
            date_str (Optional[str]): 查詢日期。

        Returns:
            Dict[str, Any]: 包含大戶比例、千張大戶比例、散戶比例與總股東人數等結構字典。
        """
        df = self.fetch_distribution_table(stock_code=stock_code, date_str=date_str)

        total_holders = int(df["Holders_Count"].sum())
        total_shares = int(df["Total_Shares"].sum())

        # 散戶: Level 1 ~ 3
        retail_df = df[df["Level"] <= 3]
        retail_pct = float(retail_df["Percentage"].sum())
        retail_holders = int(retail_df["Holders_Count"].sum())

        # 中實戶: Level 4 ~ 11
        medium_df = df[(df["Level"] >= 4) & (df["Level"] <= 11)]
        medium_pct = float(medium_df["Percentage"].sum())

        # 大戶 (400張以上): Level 12 ~ 15
        large_400_df = df[df["Level"] >= 12]
        large_400_pct = float(large_400_df["Percentage"].sum())
        large_400_holders = int(large_400_df["Holders_Count"].sum())

        # 千張大戶 (1000張以上): Level 15
        large_1000_df = df[df["Level"] == 15]
        large_1000_pct = float(large_1000_df["Percentage"].sum())
        large_1000_holders = int(large_1000_df["Holders_Count"].sum())

        return {
            "stock_code": self._clean_stock_code(stock_code),
            "total_holders": total_holders,
            "total_shares": total_shares,
            "retail_under_10_tickets": {
                "percentage": round(retail_pct, 2),
                "holders": retail_holders,
            },
            "medium_10_to_400_tickets": {
                "percentage": round(medium_pct, 2),
            },
            "large_over_400_tickets": {
                "percentage": round(large_400_pct, 2),
                "holders": large_400_holders,
            },
            "large_over_1000_tickets": {
                "percentage": round(large_1000_pct, 2),
                "holders": large_1000_holders,
            },
        }
