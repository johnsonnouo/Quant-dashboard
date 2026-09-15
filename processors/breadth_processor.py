# processors/breadth_processor.py
"""台股大盤市場廣度 (Market Breadth) 與騰落指標 (AD Line) 運算模組。

本模組遵循「關注點分離」原則，純粹接收大盤上漲與下跌家數之時間序列 DataFrame，
利用 pandas 向量化計算「每日淨上漲家數 (Net Advances)」與「累積騰落指標 (AD Line)」，
並可計算其平滑均線以供判斷大盤真假突破與量價背離。
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class BreadthProcessor:
    """市場廣度與騰落指標處理器。

    負責計算每日淨上漲家數、累加騰落指標 (Advance-Decline Line) 及多天期平滑趨勢線。
    """

    def calculate_net_advances(
        self,
        df: pd.DataFrame,
        up_col: str = "up_count",
        down_col: str = "down_count",
        date_col: str = "Date",
    ) -> pd.DataFrame:
        """計算每日「淨上漲家數 (Net Advances)」。

        計算公式:
            Net_Advances = 上漲家數 (Up_Count) - 下跌家數 (Down_Count)

        Args:
            df (pd.DataFrame): 包含上漲與下跌家數之 DataFrame。
            up_col (str): 上漲家數欄位名稱，預設 'up_count' (相容大小寫)。
            down_col (str): 下跌家數欄位名稱，預設 'down_count' (相容大小寫)。
            date_col (str): 日期欄位名稱，預設 'Date'。

        Returns:
            pd.DataFrame: 包含原始數據與 'Net_Advances' 欄位之 DataFrame。

        Raises:
            ValueError: 當找不到上漲或下跌家數欄位時拋出。
        """
        if df.empty:
            return pd.DataFrame()

        data = df.copy()

        # 欄位容錯匹配
        actual_up = next((c for c in data.columns if c.lower() == up_col.lower()), None)
        actual_down = next((c for c in data.columns if c.lower() == down_col.lower()), None)

        if not actual_up or not actual_down:
            # 支援中文字元欄位
            actual_up = next((c for c in data.columns if "上漲" in str(c)), actual_up)
            actual_down = next((c for c in data.columns if "下跌" in str(c)), actual_down)

        if not actual_up or not actual_down:
            raise ValueError(f"輸入 DataFrame 缺少上漲或下跌家數欄位 (預期: '{up_col}', '{down_col}')")

        # 排序時間序列
        actual_date = next((c for c in data.columns if c.lower() == date_col.lower()), None)
        if actual_date:
            data[actual_date] = pd.to_datetime(data[actual_date])
            data.sort_values(by=actual_date, inplace=True)

        # 向量化轉換數值並清除缺失值
        data[actual_up] = pd.to_numeric(data[actual_up], errors="coerce").fillna(0.0)
        data[actual_down] = pd.to_numeric(data[actual_down], errors="coerce").fillna(0.0)

        # 向量化計算淨上漲家數
        data["Net_Advances"] = data[actual_up] - data[actual_down]

        data.reset_index(drop=True, inplace=True)
        return data

    def calculate_ad_line(
        self,
        df: pd.DataFrame,
        up_col: str = "up_count",
        down_col: str = "down_count",
        initial_value: float = 0.0,
        ma_windows: Optional[List[int]] = None,
    ) -> pd.DataFrame:
        """計算台股市場的「累積騰落指標 (Advance-Decline Line, AD Line)」。

        騰落指標為全市場股票漲跌家數差異之累積和 (Cumulative Sum)。
        當加權指數持續破新高，但 AD Line 卻走平甚至下滑時，代表權值股掩護出貨之「背離現象」；
        反之，指數回檔而 AD Line 率先走揚時，代表中小型股普遍轉強。

        計算公式:
            AD_Line_t = AD_Line_{t-1} + (上漲家數_t - 下跌家數_t)

        Args:
            df (pd.DataFrame): 包含上漲與下跌家數之時間序列 DataFrame。
            up_col (str): 上漲家數欄位名稱。
            down_col (str): 下跌家數欄位名稱。
            initial_value (float): AD Line 初始累積基準值，預設 0.0。
            ma_windows (Optional[List[int]]): AD Line 移動平均線週期清單，預設 [10, 20]。

        Returns:
            pd.DataFrame: 包含 Net_Advances, AD_Line 以及各平滑均線 (AD_Line_MA_{w}) 之 DataFrame。
        """
        if df.empty:
            return pd.DataFrame()

        # 1. 計算每日淨上漲家數
        data = self.calculate_net_advances(df, up_col=up_col, down_col=down_col)

        # 2. 向量化累加 (Cumulative Sum)
        data["AD_Line"] = initial_value + data["Net_Advances"].cumsum()

        # 3. 計算平滑均線
        windows = ma_windows or [10, 20]
        for w in windows:
            if w <= 0:
                continue
            ma_col = f"AD_Line_MA_{w}"
            data[ma_col] = data["AD_Line"].rolling(window=w, min_periods=1).mean().round(1)

        # 4. 判斷短期市場動能偏向 (例如 AD Line 高於 10MA 視為廣度擴張)
        if f"AD_Line_MA_{windows[0]}" in data.columns:
            data["Breadth_Status"] = np.where(
                data["AD_Line"] >= data[f"AD_Line_MA_{windows[0]}"],
                "Expanding",
                "Contracting",
            )

        return data

    def calculate_advance_decline_ratio(
        self,
        df: pd.DataFrame,
        up_col: str = "up_count",
        down_col: str = "down_count",
        window: int = 10,
    ) -> pd.DataFrame:
        """計算滾動週期內之「騰落比率 (ADR, Advance-Decline Ratio)」。

        計算公式:
            ADR = (N 日累計上漲家數) / (N 日累計下跌家數) * 100

        Args:
            df (pd.DataFrame): 包含每日漲跌家數之 DataFrame。
            up_col (str): 上漲欄位名稱。
            down_col (str): 下跌欄位名稱。
            window (int): 滾動視窗天數，預設 10 日。

        Returns:
            pd.DataFrame: 包含 ADR 指標數值之 DataFrame。
        """
        data = self.calculate_net_advances(df, up_col=up_col, down_col=down_col)
        actual_up = next(c for c in data.columns if "up" in c.lower() or "上漲" in str(c))
        actual_down = next(c for c in data.columns if "down" in c.lower() or "下跌" in str(c))

        rolling_up = data[actual_up].rolling(window=window, min_periods=1).sum()
        rolling_down = data[actual_down].rolling(window=window, min_periods=1).sum()

        # 避免除以 0
        data[f"ADR_{window}"] = np.where(
            rolling_down > 0,
            (rolling_up / rolling_down) * 100.0,
            100.0,
        ).round(2)

        return data
