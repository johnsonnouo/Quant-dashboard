# fetchers/tw_market_fetcher.py
"""台灣集中市場 (TWSE) 整體市場數據獲取模組。

本模組繼承 BaseFetcher，主要從台灣證券交易所 (TWSE) 官方開放資料及 RWD JSON API 獲取：
1. 大盤「信用交易統計」(全市場融資融券買賣、現償、餘額與金額)。
2. 大盤「市場廣度 (Market Breadth)」(每日上市股票之上漲家數、漲停、下跌家數、跌停、平盤等)。
"""

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from config.settings import DEFAULT_TIMEOUT
from fetchers.base import BaseFetcher, DataFetchError

logger = logging.getLogger(__name__)


class TWMarketFetcher(BaseFetcher):
    """台股大盤市場指標數據獲取器。

    提供大盤融資融券餘額與上漲/下跌家數市場廣度數據。
    """

    TWSE_MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
    TWSE_INDEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """初始化 TWMarketFetcher。

        Args:
            timeout (int): 請求超時時間。
        """
        super().__init__(timeout=timeout)

    @staticmethod
    def _clean_number(val: Any) -> float:
        """將字串中的逗號、千分位及空白清除並轉為數值。"""
        if pd.isna(val) or val is None:
            return 0.0
        s = str(val).replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    @staticmethod
    def _format_date(dt: Optional[datetime.date] = None) -> str:
        """將日期轉換為 TWSE 查詢格式 YYYYMMDD。"""
        target = dt or datetime.date.today()
        return target.strftime("%Y%m%d")

    def fetch_margin_balance(
        self,
        date_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        """獲取指定交易日之台股全市場「融資融券信用交易餘額」統計。

        Args:
            date_str (Optional[str]): 查詢日期，格式為 'YYYYMMDD' (例如 '20260914')。預設為最新交易日。

        Returns:
            Dict[str, Any]: 包含融資餘額(張/仟元)、融券餘額(張)、融資今日增減、融券今日增減等標準化數據。

        Raises:
            DataFetchError: 端點無回應或解析失敗時拋出。
        """
        params: Dict[str, str] = {
            "response": "json",
            "selectType": "MS",  # 信用交易統計全市場
        }
        if date_str:
            params["date"] = date_str

        logger.info("查詢台股大盤融資融券餘額 (日期: %s)", date_str or "最新")
        data = self.get_json(self.TWSE_MARGIN_URL, params=params)

        if not isinstance(data, dict) or data.get("stat") != "OK":
            msg = data.get("stat", "無回應資料") if isinstance(data, dict) else "未知錯誤"
            raise DataFetchError(
                message=f"獲取融資融券餘額失敗: {msg}",
                endpoint=self.TWSE_MARGIN_URL,
            )

        # TWSE tables[0] 通常為信用交易統計
        tables = data.get("tables", [])
        if not tables or not isinstance(tables, list):
            raise DataFetchError(
                message="TWSE 回傳之融資融券表格資料結構不符預期",
                endpoint=self.TWSE_MARGIN_URL,
            )

        table_0 = tables[0]
        fields: List[str] = table_0.get("fields", [])
        rows: List[List[str]] = table_0.get("data", [])
        query_date = data.get("date", date_str or "")

        result: Dict[str, Any] = {
            "date": query_date,
            "margin_purchase_shares": 0.0,       # 融資餘額 (張)
            "margin_purchase_money_thousand": 0.0,  # 融資餘額 (仟元)
            "margin_purchase_change_money": 0.0,    # 融資金額今日增減 (仟元)
            "short_sale_shares": 0.0,             # 融券餘額 (張)
            "short_sale_change_shares": 0.0,      # 融券今日增減 (張)
            "raw_table": [],
        }

        # 欄位順序一般為: 項目, 買進, 賣出, 現金(券)償還, 前日餘額, 今日餘額
        for row in rows:
            if not row or len(row) < 6:
                continue
            item_name = str(row[0]).strip()
            buy = self._clean_number(row[1])
            sell = self._clean_number(row[2])
            redemption = self._clean_number(row[3])
            prev_balance = self._clean_number(row[4])
            curr_balance = self._clean_number(row[5])
            change = curr_balance - prev_balance

            row_record = {
                "item": item_name,
                "buy": buy,
                "sell": sell,
                "redemption": redemption,
                "prev_balance": prev_balance,
                "curr_balance": curr_balance,
                "change": change,
            }
            result["raw_table"].append(row_record)

            if "融資" in item_name and "金額" not in item_name:
                result["margin_purchase_shares"] = curr_balance
            elif "融資金額" in item_name:
                result["margin_purchase_money_thousand"] = curr_balance
                result["margin_purchase_change_money"] = change
            elif "融券" in item_name and "金額" not in item_name:
                result["short_sale_shares"] = curr_balance
                result["short_sale_change_shares"] = change

        return result

    def fetch_market_breadth(
        self,
        date_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        """獲取指定交易日之台股大盤「漲跌家數與市場廣度」統計。

        Args:
            date_str (Optional[str]): 查詢日期，格式為 'YYYYMMDD'。預設為最新交易日。

        Returns:
            Dict[str, Any]: 包含上漲家數、漲停家數、下跌家數、跌停家數、平盤家數與大盤成交金額等統計。

        Raises:
            DataFetchError: 端點回應錯誤或無法解析市場廣度時拋出。
        """
        params: Dict[str, str] = {
            "response": "json",
            "type": "MS",  # 大盤統計
        }
        if date_str:
            params["date"] = date_str

        logger.info("查詢台股大盤市場廣度/漲跌家數 (日期: %s)", date_str or "最新")
        data = self.get_json(self.TWSE_INDEX_URL, params=params)

        if not isinstance(data, dict) or data.get("stat") != "OK":
            msg = data.get("stat", "無回應資料") if isinstance(data, dict) else "未知錯誤"
            raise DataFetchError(
                message=f"獲取市場廣度失敗: {msg}",
                endpoint=self.TWSE_INDEX_URL,
            )

        query_date = data.get("date", date_str or "")
        tables = data.get("tables", [])

        breadth: Dict[str, Any] = {
            "date": query_date,
            "up_count": 0,           # 上漲家數 (含漲停)
            "up_limit_count": 0,     # 漲停家數
            "down_count": 0,         # 下跌家數 (含跌停)
            "down_limit_count": 0,   # 跌停家數
            "unchanged_count": 0,    # 平盤持平家數
            "total_turnover_ntd": 0.0,  # 大盤成交金額 (元)
        }

        def _extract_counts(cell_text: str) -> (int, int):
            """從如 '207(5)' 或 '3,552(16)' 中提取 (總數, 漲跌停數)。"""
            match = re.search(r"([0-9,]+)(?:\(([0-9,]+)\))?", cell_text)
            if match:
                total = int(match.group(1).replace(",", ""))
                limit = int(match.group(2).replace(",", "")) if match.group(2) else 0
                return total, limit
            return 0, 0

        # 遍歷所有表格尋找「漲跌證券數合計」與「大盤成交統計」
        for table in tables:
            if not isinstance(table, dict):
                continue
            title = table.get("title", "")
            data_rows = table.get("data", [])

            # 1. 漲跌證券數合計表格 (包含漲跌與合計關鍵字)
            if "漲跌" in title and "合計" in title:
                for row in data_rows:
                    if len(row) < 3:
                        continue
                    item_type = str(row[0]).strip()
                    # row[2] 通常為純「股票」家數，row[1] 為全市場(含ETF/權證)
                    target_cell = str(row[2]).strip()

                    if "上漲" in item_type:
                        up_t, up_l = _extract_counts(target_cell)
                        breadth["up_count"] = up_t
                        breadth["up_limit_count"] = up_l
                    elif "下跌" in item_type:
                        dn_t, dn_l = _extract_counts(target_cell)
                        breadth["down_count"] = dn_t
                        breadth["down_limit_count"] = dn_l
                    elif "持平" in item_type:
                        flat_t, _ = _extract_counts(target_cell)
                        breadth["unchanged_count"] = flat_t

            # 2. 大盤成交統計資訊
            elif any(k in title for k in ["大盤統計", "成交統計", "大盤資訊"]):
                for row in data_rows:
                    if len(row) >= 2 and any(k in str(row[0]) for k in ["1.一般股票", "一般股票", "合計"]):
                        breadth["total_turnover_ntd"] = self._clean_number(row[1])

        return breadth

    def fetch_margin_history(self, days: int = 15) -> pd.DataFrame:
        """回溯獲取最近 N 個交易日之大盤融資融券餘額變化。

        Args:
            days (int): 回溯交易日天數，預設 15 日。

        Returns:
            pd.DataFrame: 包含日期、融資餘額(億元)、融資增減(億元)、融券餘額(張)、融券增減(張) 之 DataFrame。
        """
        logger.info("獲取近 %d 日大盤融資融券歷史趨勢", days)
        records: List[Dict[str, Any]] = []
        curr_date = datetime.date.today()
        attempts = 0
        max_attempts = days * 2  # 考慮週末與假日

        while len(records) < days and attempts < max_attempts:
            # 跳過週末
            if curr_date.weekday() < 5:
                d_str = curr_date.strftime("%Y%m%d")
                try:
                    res = self.fetch_margin_balance(date_str=d_str)
                    if res["margin_purchase_money_thousand"] > 0:
                        records.append({
                            "Date": res["date"],
                            "Margin_Purchase_Balance_Hundred_Million": round(
                                res["margin_purchase_money_thousand"] / 100000.0, 2
                            ),
                            "Margin_Purchase_Change_Hundred_Million": round(
                                res["margin_purchase_change_money"] / 100000.0, 2
                            ),
                            "Short_Sale_Balance_Shares": res["short_sale_shares"],
                            "Short_Sale_Change_Shares": res["short_sale_change_shares"],
                        })
                except Exception as exc:
                    logger.debug("日期 %s 非交易日或無融資數據: %s", d_str, str(exc))

            curr_date -= datetime.timedelta(days=1)
            attempts += 1

        if not records:
            raise DataFetchError(
                message="在指定天數內未能獲取到任何融資融券歷史數據",
                endpoint=self.TWSE_MARGIN_URL,
            )

        df = pd.DataFrame(records)
        df.sort_values(by="Date", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
