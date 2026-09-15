# processors/etf_processor.py
"""台灣 ETF 成分股分析與被動資金鎖碼計算模組。

本模組遵循「關注點分離」原則，純粹接收已獲取之 ETF 成分股 DataFrame 字典，
透過向量化分組與透視表運算，計算多檔 ETF 的持股重疊度、被動資金合計鎖碼權重，
並提供篩選核心鎖碼個股之量化分析方法。
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ETFProcessor:
    """ETF 成分股重疊度與被動資金鎖碼分析處理器。

    負責多檔 ETF 成分股交叉比對、持股權重加總與鎖碼程度排行。
    """

    def analyze_overlaps(
        self,
        etf_dict: Dict[str, pd.DataFrame],
        min_overlap: int = 1,
    ) -> pd.DataFrame:
        """分析多檔 ETF 的成分股重疊狀況與合計權重總表。

        計算每一檔個股：
        1. 「被幾檔 ETF 同時持有」 (Overlap_Count)
        2. 「合計的名目權重」 (Total_Weight)
        3. 在各 ETF 中的個別持股權重 (%)

        排序規則：優先依照「被幾檔 ETF 同時持有 (Overlap_Count)」降冪排序，
        次依「合計名目權重 (Total_Weight)」降冪排序，幫助快速鎖定機構與被動資金重倉股。

        Args:
            etf_dict (Dict[str, pd.DataFrame]): 鍵為 ETF 代碼 (例如 '0050')，
                值為成分股 DataFrame (必須包含 Stock_Code, Stock_Name, Weight_Pct 欄位)。
            min_overlap (int): 篩選最少被幾檔 ETF 重疊持有，預設 1。

        Returns:
            pd.DataFrame: 包含 Stock_Code, Stock_Name, Overlap_Count, Total_Weight,
                         以及各檔 ETF 持股比重的綜合分析總表。
        """
        if not etf_dict:
            logger.warning("傳入之 ETF 字典為空，回傳空 DataFrame")
            return pd.DataFrame()

        collected_dfs: List[pd.DataFrame] = []

        for etf_code, df in etf_dict.items():
            if df.empty:
                continue

            # 複製並標準化必要欄位
            sub = df.copy()

            # 若已具備標準欄位則直接提取，否則進行容錯映射
            code_col = next((c for c in sub.columns if c == "Stock_Code"), None)
            if not code_col:
                code_col = next((c for c in sub.columns if "code" in str(c).lower() and "etf" not in str(c).lower()), None)
            if not code_col:
                code_col = next((c for c in sub.columns if "代號" in str(c) or "代碼" in str(c)), None)

            name_col = next((c for c in sub.columns if c == "Stock_Name"), None)
            if not name_col:
                name_col = next((c for c in sub.columns if "name" in str(c).lower() and "etf" not in str(c).lower()), None)
            if not name_col:
                name_col = next((c for c in sub.columns if "名稱" in str(c)), None)

            weight_col = next((c for c in sub.columns if c == "Weight_Pct"), None)
            if not weight_col:
                weight_col = next((c for c in sub.columns if any(k in str(c).lower() for k in ["weight", "比例", "權重"])), None)

            if not (code_col and name_col and weight_col):
                logger.warning("ETF %s 的 DataFrame 缺少必要欄位 (code, name 或 weight)，將予略過", etf_code)
                continue

            sub_clean = pd.DataFrame()
            sub_clean["Stock_Code"] = sub[code_col].astype(str).str.strip()
            sub_clean["Stock_Name"] = sub[name_col].astype(str).str.strip()
            sub_clean["Weight_Pct"] = pd.to_numeric(sub[weight_col], errors="coerce").fillna(0.0)
            sub_clean["ETF_Code"] = str(etf_code).strip()

            collected_dfs.append(sub_clean)

        if not collected_dfs:
            return pd.DataFrame()

        # 合併所有 ETF 之成份股明細
        concat_df = pd.concat(collected_dfs, ignore_index=True)

        # 1. 建立樞紐透視表 (Pivot Table): Index為 (Stock_Code, Stock_Name)，Columns為 ETF_Code
        pivot_df = concat_df.pivot_table(
            index=["Stock_Code", "Stock_Name"],
            columns="ETF_Code",
            values="Weight_Pct",
            aggfunc="sum",
            fill_value=0.0,
        )

        etf_columns = list(pivot_df.columns)

        # 2. 向量化計算重疊持有檔數 (持有權重 > 0 的 ETF 數量)
        pivot_df["Overlap_Count"] = (pivot_df[etf_columns] > 0.0).sum(axis=1).astype(int)

        # 3. 向量化計算合計名目權重總和
        pivot_df["Total_Weight"] = pivot_df[etf_columns].sum(axis=1).round(2)

        # 4. 根據 Overlap_Count 與 Total_Weight 進行降冪排序
        pivot_df.sort_values(
            by=["Overlap_Count", "Total_Weight"],
            ascending=[False, False],
            inplace=True,
        )

        # 5. 篩選門檻
        if min_overlap > 1:
            pivot_df = pivot_df[pivot_df["Overlap_Count"] >= min_overlap]

        result_df = pivot_df.reset_index()

        # 整理欄位顯示順序
        ordered_cols = (
            ["Stock_Code", "Stock_Name", "Overlap_Count", "Total_Weight"]
            + [c for c in etf_columns if c not in ["Stock_Code", "Stock_Name", "Overlap_Count", "Total_Weight"]]
        )
        result_df = result_df[ordered_cols].copy()
        result_df.reset_index(drop=True, inplace=True)
        return result_df

    def find_locked_stocks(
        self,
        etf_dict: Dict[str, pd.DataFrame],
        min_overlap: int = 2,
        min_total_weight: float = 5.0,
    ) -> pd.DataFrame:
        """篩選被多檔被動基金重倉重疊鎖定之「核心鎖碼股」。

        Args:
            etf_dict (Dict[str, pd.DataFrame]): 各 ETF 成分股字典。
            min_overlap (int): 最低重疊 ETF 檔數門檻，預設 2 檔。
            min_total_weight (float): 合計權重最低門檻 (%)，預設 5.0%。

        Returns:
            pd.DataFrame: 符合被動資金高鎖碼標準之個股清單。
        """
        all_overlaps = self.analyze_overlaps(etf_dict=etf_dict, min_overlap=min_overlap)
        if all_overlaps.empty:
            return pd.DataFrame()

        locked = all_overlaps[
            (all_overlaps["Overlap_Count"] >= min_overlap)
            & (all_overlaps["Total_Weight"] >= min_total_weight)
        ].copy()

        locked.reset_index(drop=True, inplace=True)
        return locked
