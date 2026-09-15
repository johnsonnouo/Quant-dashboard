# fetchers/etf_fetcher.py
"""台灣 ETF 成分股與權重數據獲取模組。

本模組繼承 BaseFetcher，主要獲取台股各檔熱門 ETF (如 0050, 0056, 00878, 00919, 00929 等)
的最新「成分股清單」與「持股權重 (%)」，提供即時解析與多檔 ETF 重疊度交叉分析。
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from config.settings import DEFAULT_ETF_CODES, DEFAULT_TIMEOUT
from fetchers.base import BaseFetcher, DataFetchError

logger = logging.getLogger(__name__)


class ETFFetcher(BaseFetcher):
    """ETF 成分股與持股權重獲取器。

    支援獲取單檔或多檔 ETF 最新成份股代碼、名稱、持股權重百分比與股數。
    """

    MONEYDJ_ETF_URL = "https://www.moneydj.com/ETF/X/Basic/Basic0007.xdjhtm"

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """初始化 ETFFetcher。

        Args:
            timeout (int): 請求超時時間。
        """
        super().__init__(timeout=timeout)

    @staticmethod
    def _clean_etf_code(code: str) -> str:
        """清洗 ETF 代碼，去除 .TW 或空格。"""
        return re.sub(r"[^0-9a-zA-Z]", "", code).upper()

    def fetch_etf_components(self, etf_code: str) -> pd.DataFrame:
        """獲取指定 ETF 之最新成分股清單與投資權重。

        Args:
            etf_code (str): ETF 代號，例如 '0050', '0056', '00878'。

        Returns:
            pd.DataFrame: 包含以下標準化欄位之 DataFrame:
                - `Rank`: 權重排序 (1, 2, 3...)
                - `Stock_Code`: 股票代碼 (例如 '2330')
                - `Stock_Name`: 股票名稱 (例如 '台積電')
                - `Weight_Pct`: 投資比例 / 權重 (%) (例如 57.17)
                - `Shares`: 持有股數

        Raises:
            DataFetchError: 端點無法取得資料或查無成分股時拋出。
        """
        clean_code = self._clean_etf_code(etf_code)
        target_param = f"{clean_code}.TW"
        url = f"{self.MONEYDJ_ETF_URL}?etfid={target_param}"

        logger.info("獲取 ETF %s 成分股與權重清單", clean_code)

        try:
            html_text = self.get_text(url=url, encoding="utf-8")
        except Exception as exc:
            raise DataFetchError(
                message=f"請求 ETF {clean_code} 頁面失敗: {str(exc)}",
                endpoint=url,
            ) from exc

        try:
            dfs = pd.read_html(io.StringIO(html_text))
        except Exception as exc:
            raise DataFetchError(
                message=f"解析 ETF {clean_code} 網頁表格失敗: {str(exc)}",
                endpoint=url,
            ) from exc

        target_df: Optional[pd.DataFrame] = None

        # 搜尋包含個股名稱與持股比例的表格
        for df in dfs:
            col_names = [str(c) for c in df.columns]
            has_name = any("個股名稱" in c or "名稱" in c for c in col_names)
            has_weight = any("投資比例" in c or "比例" in c or "權重" in c for c in col_names)
            if has_name and has_weight and df.shape[0] > 0:
                target_df = df
                break

        if target_df is None or target_df.empty:
            raise DataFetchError(
                message=f"查無 ETF {clean_code} 之成份股資料，請確認代碼是否正確",
                endpoint=url,
            )

        # 整理欄位
        target_df.columns = [str(c).strip() for c in target_df.columns]
        name_col = next(c for c in target_df.columns if "個股名稱" in c or "名稱" in c)
        weight_col = next(c for c in target_df.columns if "比例" in c or "權重" in c)
        shares_col = next((c for c in target_df.columns if "股數" in c), None)

        records: List[Dict[str, Any]] = []

        for _, row in target_df.iterrows():
            raw_name = str(row[name_col]).strip()
            # 格式通常為 '台積電(2330.TW)' 或 '台積電(2330)'
            code_match = re.search(r"\((\d{4,6})(?:\.TW)?\)", raw_name)
            if code_match:
                s_code = code_match.group(1)
                s_name = re.sub(r"\(.*?\)", "", raw_name).strip()
            else:
                s_code = ""
                s_name = raw_name

            raw_weight = str(row[weight_col]).replace("%", "").replace(",", "").strip()
            try:
                weight_pct = float(raw_weight)
            except ValueError:
                weight_pct = 0.0

            shares = 0.0
            if shares_col and shares_col in row:
                raw_shares = str(row[shares_col]).replace(",", "").strip()
                try:
                    shares = float(raw_shares)
                except ValueError:
                    shares = 0.0

            records.append({
                "ETF_Code": clean_code,
                "Stock_Code": s_code,
                "Stock_Name": s_name,
                "Weight_Pct": weight_pct,
                "Shares": shares,
            })

        res_df = pd.DataFrame(records)
        res_df.sort_values(by="Weight_Pct", ascending=False, inplace=True)
        res_df["Rank"] = range(1, len(res_df) + 1)
        # 調整欄位顯示順序
        cols = ["Rank", "Stock_Code", "Stock_Name", "Weight_Pct", "Shares", "ETF_Code"]
        res_df = res_df[cols].reset_index(drop=True)
        return res_df

    def fetch_top_components(
        self,
        etf_code: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """獲取指定 ETF 之權重前 N 大成分股。

        Args:
            etf_code (str): ETF 代號。
            top_n (int): 前幾大成分股，預設 10。

        Returns:
            pd.DataFrame: 前 N 大成分股清單。
        """
        df = self.fetch_etf_components(etf_code=etf_code)
        return df.head(top_n).copy()

    def fetch_multi_etf_overlaps(
        self,
        etf_codes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """比對多檔熱門 ETF 成分股的持股重疊度與個別權重對照表。

        例如比對 0050、0056、00878 是否重疊持有聯發科、鴻海、廣達等。

        Args:
            etf_codes (Optional[List[str]]): ETF 代號清單，預設使用 settings.DEFAULT_ETF_CODES。

        Returns:
            pd.DataFrame: 以個股 (代號+名稱) 為列，各 ETF 權重為欄位的矩陣對照表。
        """
        targets = etf_codes or list(DEFAULT_ETF_CODES[:3])
        logger.info("比對多檔 ETF 重疊度: %s", targets)

        merged_weights: Dict[str, Dict[str, float]] = {}

        for code in targets:
            try:
                comp_df = self.fetch_etf_components(code)
                for _, row in comp_df.iterrows():
                    key = f"{row['Stock_Code']} {row['Stock_Name']}".strip()
                    if key not in merged_weights:
                        merged_weights[key] = {}
                    merged_weights[key][code] = row["Weight_Pct"]
            except Exception as exc:
                logger.warning("比對過程中獲取 ETF %s 失敗: %s", code, str(exc))

        if not merged_weights:
            raise DataFetchError(
                message="未能成功獲取任何指定 ETF 之成分股以進行比對",
                endpoint=self.MONEYDJ_ETF_URL,
            )

        matrix_df = pd.DataFrame.from_dict(merged_weights, orient="index")
        matrix_df.fillna(0.0, inplace=True)
        # 統計出現在多少檔 ETF 中
        matrix_df["Overlap_Count"] = (matrix_df[targets] > 0).sum(axis=1)
        matrix_df.sort_values(by="Overlap_Count", ascending=False, inplace=True)
        return matrix_df
