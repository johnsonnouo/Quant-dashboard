# processors/chips_processor.py
"""籌碼面衍生指標與平滑運算處理模組。

本模組遵循「關注點分離」原則，專門對期貨籌碼與集保股權籌碼進行量化運算：
1. 外資台指期未平倉淨口數 (Net OI) 之滾動均線平滑運算 (如 5MA, 10MA, 20MA)。
2. 集保股權分散表之大戶持股比例 (>=400張或千張)、散戶持股比例 (<10張) 與「大戶散戶籌碼差額 (Spread)」指標計算。
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ChipsProcessor:
    """籌碼數據指標處理器。

    負責外資期貨淨留倉均線平滑，以及集保戶大戶散戶持股比例差額 (Spread) 萃取。
    """

    def smooth_foreign_oi(
        self,
        df: pd.DataFrame,
        oi_col: str = "Foreign_Net_OI",
        windows: Optional[List[int]] = None,
        date_col: str = "Date",
    ) -> pd.DataFrame:
        """計算外資台指期未平倉淨多空口數 (Foreign Net OI) 之平滑滾動移動平均線。

        期貨單日留倉易受結算日或避險事件擾動，透過 5MA, 10MA, 20MA 可有效辨別中期籌碼多空趨勢。

        Args:
            df (pd.DataFrame): 包含日期與外資未平倉淨口數之 DataFrame。
            oi_col (str): 未平倉淨口數欄位名稱，預設為 'Foreign_Net_OI' (亦支援相容 'Net_OI')。
            windows (Optional[List[int]]): 移動平均週期，預設 [5, 10, 20]。
            date_col (str): 日期欄位名稱，預設 'Date'。

        Returns:
            pd.DataFrame: 包含原始口數與各均線欄位 (OI_MA_{w}) 以及多空狀態信號之 DataFrame。

        Raises:
            ValueError: 當指定的未平倉口數欄位不存在時拋出。
        """
        data = df.copy()

        # 欄位容錯處理
        target_col = oi_col
        if target_col not in data.columns and "Net_OI" in data.columns:
            target_col = "Net_OI"

        if target_col not in data.columns:
            raise ValueError(f"輸入 DataFrame 缺少外資未平倉口數欄位: '{oi_col}' 或 'Net_OI'")

        # 排序以確保時間序列先後順序
        if date_col in data.columns:
            data[date_col] = pd.to_datetime(data[date_col])
            data.sort_values(by=date_col, inplace=True)

        target_windows = windows or [5, 10, 20]

        # 確保為數值型態
        data[target_col] = pd.to_numeric(data[target_col], errors="coerce").fillna(0.0)

        for w in target_windows:
            if w <= 0:
                continue
            ma_col = f"OI_MA_{w}"
            # 向量化滾動計算平均，min_periods=1 保證起始值不全為 NaN
            data[ma_col] = data[target_col].rolling(window=w, min_periods=1).mean().round(1)

        # 標註最新多空偏向 (例如 5MA > 0 視為偏多，5MA < 0 視為偏空)
        if f"OI_MA_{target_windows[0]}" in data.columns:
            data["OI_Sentiment"] = np.where(
                data[f"OI_MA_{target_windows[0]}"] > 0, "Bullish", "Bearish"
            )

        data.reset_index(drop=True, inplace=True)
        return data

    def calculate_tdcc_spread(
        self,
        df: pd.DataFrame,
        large_threshold_level: int = 12,
        retail_max_level: int = 3,
    ) -> Dict[str, Any]:
        """從單期集保股權分散表計算「大戶持股比例」、「散戶持股比例」及其「籌碼差額 (Spread)」。

        台灣集保標準級距:
            - 級距 1~3: 1 ~ 9,999 股 (< 10 張，散戶指標)
            - 級距 12~15: 400,000 股以上 (>= 400 張，大戶指標)
            - 級距 15: 1,000,001 股以上 (>= 1,000 張，超級千張大戶)

        籌碼差額 (Spread) = 大戶持股比例 (%) - 散戶持股比例 (%)
        數值越高代表籌碼越高度集中於大戶手中，籌碼安定度越強。

        Args:
            df (pd.DataFrame): 包含 Level (1~15) 與 Percentage (%) 欄位之集保股權分散 DataFrame。
            large_threshold_level (int): 大戶起始級距，預設 12 (400張以上)。
            retail_max_level (int): 散戶上限級距，預設 3 (10張以下)。

        Returns:
            Dict[str, Any]: 包含大戶比例、千張大戶比例、散戶比例與大戶散戶差額 (Spread) 之字典。

        Raises:
            ValueError: 資料中未包含 Level 或 Percentage 欄位時拋出。
        """
        if df.empty:
            raise ValueError("傳入之集保分散表 DataFrame 為空")

        data = df.copy()
        # 欄位相容處理
        col_map = {}
        for c in data.columns:
            c_lower = str(c).lower()
            if "level" in c_lower or "序號" in c_lower:
                col_map[c] = "Level"
            elif "percent" in c_lower or "比例" in c_lower:
                col_map[c] = "Percentage"
            elif "holder" in c_lower or "人數" in c_lower:
                col_map[c] = "Holders_Count"
            elif "share" in c_lower or "股數" in c_lower:
                col_map[c] = "Total_Shares"

        data.rename(columns=col_map, inplace=True)

        if "Level" not in data.columns or "Percentage" not in data.columns:
            raise ValueError("集保 DataFrame 必須包含 'Level' 與 'Percentage' 欄位")

        data["Level"] = pd.to_numeric(data["Level"], errors="coerce")
        data["Percentage"] = pd.to_numeric(data["Percentage"], errors="coerce").fillna(0.0)

        # 僅選取 1~15 有效級距
        valid_data = data[(data["Level"] >= 1) & (data["Level"] <= 15)]

        # 向量化計算散戶比例 (Level <= retail_max_level)
        retail_mask = valid_data["Level"] <= retail_max_level
        retail_pct = float(valid_data.loc[retail_mask, "Percentage"].sum())

        # 向量化計算大戶比例 (Level >= large_threshold_level)
        large_mask = valid_data["Level"] >= large_threshold_level
        large_pct = float(valid_data.loc[large_mask, "Percentage"].sum())

        # 向量化計算超級千張大戶比例 (Level == 15)
        super_large_mask = valid_data["Level"] == 15
        super_large_pct = float(valid_data.loc[super_large_mask, "Percentage"].sum())

        # 計算大戶散戶持股差額 (Spread)
        spread = round(large_pct - retail_pct, 2)

        # 計算總人數與總股數 (若存在欄位，採用 pd.to_numeric 進行防禦性轉換)
        total_holders = (
            int(pd.to_numeric(valid_data["Holders_Count"], errors="coerce").fillna(0).sum())
            if "Holders_Count" in valid_data.columns
            else 0
        )
        total_shares = (
            int(pd.to_numeric(valid_data["Total_Shares"], errors="coerce").fillna(0).sum())
            if "Total_Shares" in valid_data.columns
            else 0
        )

        return {
            "retail_ratio_pct": round(retail_pct, 2),
            "large_ratio_pct": round(large_pct, 2),
            "super_large_ratio_pct": round(super_large_pct, 2),
            "large_retail_spread": spread,
            "total_holders": total_holders,
            "total_shares": total_shares,
        }

    def calculate_tdcc_spread_series(
        self,
        weekly_dfs_dict: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """計算多週歷史集保股權分散之籌碼差額 (Spread) 時間序列。

        Args:
            weekly_dfs_dict (Dict[str, pd.DataFrame]): 鍵為日期 (例如 '20260911')，值為當週股權分散 DataFrame。

        Returns:
            pd.DataFrame: 包含 Date、Large_Ratio_Pct、Retail_Ratio_Pct、Large_Retail_Spread 之時間序列 DataFrame。
        """
        records: List[Dict[str, Any]] = []

        for date_str, df in weekly_dfs_dict.items():
            if df.empty:
                continue
            try:
                metrics = self.calculate_tdcc_spread(df)
                records.append({
                    "Date": date_str,
                    "Large_Ratio_Pct": metrics["large_ratio_pct"],
                    "Retail_Ratio_Pct": metrics["retail_ratio_pct"],
                    "Super_Large_Ratio_Pct": metrics["super_large_ratio_pct"],
                    "Large_Retail_Spread": metrics["large_retail_spread"],
                })
            except Exception as exc:
                logger.warning("計算日期 %s 籌碼差額失敗: %s", date_str, str(exc))

        if not records:
            return pd.DataFrame()

        res_df = pd.DataFrame(records)
        res_df["Date"] = pd.to_datetime(res_df["Date"])
        res_df.sort_values(by="Date", inplace=True)
        res_df.reset_index(drop=True, inplace=True)
        return res_df
