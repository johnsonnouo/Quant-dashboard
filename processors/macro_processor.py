# processors/macro_processor.py
"""宏觀總經與跨市場數據運算處理模組。

本模組遵循「關注點分離」原則，嚴格專注於純業務邏輯與向量化數據運算，
絕不發起任何網路或 HTTP 請求。主要功能包含多市場時間序列對齊 (ffill/bfill)、
移動平均線 (MA) 計算、乖離率 (Bias) 以及台積電 ADR 溢價率時間序列計算。
"""

import logging
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MacroProcessor:
    """宏觀總經時間序列處理器。

    負責處理跨市場收盤報價對齊、平滑移動平均線與 ADR 溢折價指標計算。
    """

    @staticmethod
    def _ensure_datetime_index(
        df: pd.DataFrame,
        date_col: str = "Date",
    ) -> pd.DataFrame:
        """確保 DataFrame 以 DatetimeIndex 排序，並回傳獨立副本。

        Args:
            df (pd.DataFrame): 原始輸入 DataFrame。
            date_col (str): 日期欄位名稱。

        Returns:
            pd.DataFrame: 具有標準化 DatetimeIndex 且由舊到新排序的 DataFrame。
        """
        data = df.copy()
        if date_col in data.columns:
            data[date_col] = pd.to_datetime(data[date_col])
            data.set_index(date_col, inplace=True)
        elif not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)

        data.sort_index(inplace=True)
        return data

    def calculate_moving_averages(
        self,
        df: pd.DataFrame,
        windows: Optional[List[int]] = None,
        price_col: str = "Close",
    ) -> pd.DataFrame:
        """計算單一資產收盤價之多天期移動平均線 (MA) 與乖離率 (Bias)。

        Args:
            df (pd.DataFrame): 包含日期與價格之 DataFrame。
            windows (Optional[List[int]]): 移動平均週期清單，預設 [20, 60]。
            price_col (str): 用於計算均線的欄位名稱，預設為 'Close'。

        Returns:
            pd.DataFrame: 包含原數據、各均線欄位 (MA_{window}) 與乖離率 (Bias_{window}) 之 DataFrame。

        Raises:
            ValueError: 當 price_col 不存在於輸入資料時拋出。
        """
        if price_col not in df.columns:
            raise ValueError(f"輸入之 DataFrame 缺少計算欄位: '{price_col}'")

        data = df.copy()
        target_windows = windows or [20, 60]

        for w in target_windows:
            if w <= 0:
                continue
            ma_col_name = f"MA_{w}"
            bias_col_name = f"Bias_{w}_Pct"

            # 向量化滾動計算平均線 (最少需要 1 筆即可開始計算，避免全為 NaN)
            data[ma_col_name] = data[price_col].rolling(window=w, min_periods=1).mean()

            # 向量化計算乖離率: (Price - MA) / MA * 100
            data[bias_col_name] = np.where(
                data[ma_col_name] > 0,
                ((data[price_col] - data[ma_col_name]) / data[ma_col_name]) * 100.0,
                0.0,
            )

        return data

    def align_multi_series(
        self,
        series_dict: Dict[str, pd.DataFrame],
        price_col: str = "Close",
        join_how: str = "outer",
    ) -> pd.DataFrame:
        """將多個不同市場與商品之 DataFrame 根據日期 (Index) 進行 join 對齊。

        跨市場（如美股與台股）因節慶或天候休市日不一，常產生日期斷層。
        本方法透過前向填充 (ffill) 與後向填充 (bfill) 填補非重疊交易日的缺失值。

        Args:
            series_dict (Dict[str, pd.DataFrame]): 商品名稱對應之 DataFrame 字典
                (例如 {'SOX': df_sox, 'TSM': df_tsm, 'USDTWD': df_fx})。
            price_col (str): 各 DataFrame 中代表價格的欄位名稱，預設 'Close'。
            join_how (str): 合併策略 ('outer', 'inner')，預設為 'outer'。

        Returns:
            pd.DataFrame: 以 Date 為索引，各商品名稱為欄位的收盤價矩陣總表。
        """
        if not series_dict:
            return pd.DataFrame()

        extracted_series: Dict[str, pd.Series] = {}

        for name, df in series_dict.items():
            if df.empty:
                logger.warning("商品 %s 傳入空 DataFrame，將予略過", name)
                continue

            clean_df = self._ensure_datetime_index(df)
            if price_col in clean_df.columns:
                series = clean_df[price_col].astype(float)
                # 剔除完全重複之索引日期
                series = series[~series.index.duplicated(keep="last")]
                extracted_series[name] = series
            else:
                logger.warning("商品 %s 未找到指定欄位 '%s'", name, price_col)

        if not extracted_series:
            return pd.DataFrame()

        # 向量化 Outer Join 對齊日期維度
        aligned_df = pd.DataFrame(extracted_series)
        aligned_df.sort_index(inplace=True)

        if join_how == "outer":
            # 先用前一交易日價格前向填充 (ffill)，最前面少數日期再用後向填充 (bfill)
            aligned_df.ffill(inplace=True)
            aligned_df.bfill(inplace=True)

        return aligned_df

    def calculate_adr_premium(
        self,
        tsm_df: pd.DataFrame,
        tw2330_df: pd.DataFrame,
        usdtwd_df: pd.DataFrame,
        adr_ratio: float = 5.0,
        price_col: str = "Close",
    ) -> pd.DataFrame:
        """計算台積電 ADR 相對於台股 2330 普通股之溢折價率歷史序列。

        計算公式:
            TSM_TW_Equiv = (TSM 收盤價 * USDTWD 匯率) / adr_ratio
            ADR_Premium_Pct = ((TSM_TW_Equiv - TSMC_TW) / TSMC_TW) * 100

        Args:
            tsm_df (pd.DataFrame): 台積電 ADR (美股代號: TSM) 之歷史 DataFrame。
            tw2330_df (pd.DataFrame): 台股台積電 (2330.TW) 之歷史 DataFrame。
            usdtwd_df (pd.DataFrame): 美元兌新台幣匯率之歷史 DataFrame。
            adr_ratio (float): ADR 與普通股換算比率，預設 5.0 (1 ADR = 5 普通股)。
            price_col (str): 收盤價格欄位名稱，預設 'Close'。

        Returns:
            pd.DataFrame: 包含對齊後的 TSM_ADR, TSMC_TW, USDTWD,
                         TSM_TW_Equiv 以及 ADR_Premium_Pct 之 DataFrame。
        """
        series_dict = {
            "TSM_ADR": tsm_df,
            "TSMC_TW": tw2330_df,
            "USDTWD": usdtwd_df,
        }

        # 跨市場休市日對齊
        aligned = self.align_multi_series(series_dict, price_col=price_col, join_how="outer")

        required = ["TSM_ADR", "TSMC_TW", "USDTWD"]
        for col in required:
            if col not in aligned.columns:
                raise ValueError(f"缺少必要對齊商品資料: '{col}'")

        result = aligned[required].copy()

        # 向量化運算 ADR 折合台幣價格
        result["TSM_TW_Equiv"] = (result["TSM_ADR"] * result["USDTWD"]) / adr_ratio

        # 向量化運算溢折價百分比
        result["ADR_Premium_Pct"] = np.where(
            result["TSMC_TW"] > 0,
            ((result["TSM_TW_Equiv"] - result["TSMC_TW"]) / result["TSMC_TW"]) * 100.0,
            0.0,
        )

        return result
