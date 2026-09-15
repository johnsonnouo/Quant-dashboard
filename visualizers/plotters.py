# visualizers/plotters.py
"""Plotly 暗黑系金融數據視覺化繪圖模組。

本模組封裝了基於 Plotly 的專業圖表生成器，統一設定 template='plotly_dark'，
專為量化交易與台股監控儀表板提供雙 Y 軸對比圖、ADR 溢折價分析圖、
籌碼大戶散戶差額圖、以及 ETF 重疊鎖碼長條圖。
"""

from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class PlotlyVisualizer:
    """專業暗黑金融主題圖表生成器。

    所有圖表統一採用 plotly_dark 深色底圖、半透明網格線與高對比金融配色。
    """

    DARK_BG = "#0e1117"
    CARD_BG = "#161b22"
    GRID_COLOR = "#21262d"
    FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, Roboto, sans-serif"

    # 專業金融調色盤
    COLOR_PRIMARY = "#00d2ff"     # 亮青藍
    COLOR_SECONDARY = "#3a7bd5"   # 科技藍
    COLOR_ACCENT = "#f7b731"      # 琥珀金
    COLOR_BULL = "#eb4d4b"        # 台股紅 (上漲/偏多)
    COLOR_BEAR = "#20bf6b"        # 台股綠 (下跌/偏空)
    COLOR_PURPLE = "#a55eea"      # 霓虹紫
    COLOR_ORANGE = "#fa8231"      # 亮橙色

    def __init__(self) -> None:
        """初始化 PlotlyVisualizer。"""
        pass

    def _apply_dark_layout(
        self,
        fig: go.Figure,
        title: str,
        height: int = 480,
        show_legend: bool = True,
    ) -> go.Figure:
        """為圖表套用統一之暗黑系佈局與精緻排版。"""
        fig.update_layout(
            template="plotly_dark",
            title={
                "text": f"<b>{title}</b>",
                "y": 0.95,
                "x": 0.03,
                "xanchor": "left",
                "yanchor": "top",
                "font": {"size": 18, "color": "#f1f2f6", "family": self.FONT_FAMILY},
            },
            paper_bgcolor=self.DARK_BG,
            plot_bgcolor=self.CARD_BG,
            height=height,
            margin=dict(l=40, r=40, t=60, b=40),
            showlegend=show_legend,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(0,0,0,0)",
                font=dict(size=12, color="#ced6e0"),
            ),
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="#1e272e",
                font_size=13,
                font_family=self.FONT_FAMILY,
            ),
        )
        fig.update_xaxes(
            showgrid=True,
            gridcolor=self.GRID_COLOR,
            linecolor=self.GRID_COLOR,
            zeroline=False,
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor=self.GRID_COLOR,
            linecolor=self.GRID_COLOR,
            zeroline=False,
        )
        return fig

    def plot_dual_axis_line(
        self,
        df: pd.DataFrame,
        x_col: str,
        y1_col: str,
        y2_col: str,
        y1_name: str,
        y2_name: str,
        title: str,
        y1_color: str = COLOR_PRIMARY,
        y2_color: str = COLOR_ACCENT,
        height: int = 480,
    ) -> go.Figure:
        """繪製雙 Y 軸線圖。

        常用於：大盤指數/收盤價 (左軸 Y1) vs 累積騰落指標 AD Line / 期貨淨留倉 (右軸 Y2)。

        Args:
            df (pd.DataFrame): 數據來源 DataFrame。
            x_col (str): X 軸欄位 (如 Date)。
            y1_col (str): 主 Y 軸數值欄位。
            y2_col (str): 次 Y 軸數值欄位。
            y1_name (str): 主 Y 軸圖例名稱。
            y2_name (str): 次 Y 軸圖例名稱。
            title (str): 圖表標題。
            y1_color (str): 主線色彩。
            y2_color (str): 次線色彩。
            height (int): 圖表高度。

        Returns:
            go.Figure: Plotly 雙軸圖表物件。
        """
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 主 Y 軸線
        fig.add_trace(
            go.Scatter(
                x=df[x_col],
                y=df[y1_col],
                name=y1_name,
                line=dict(color=y1_color, width=2.2),
                mode="lines",
            ),
            secondary_y=False,
        )

        # 次 Y 軸線 (虛線或微透光強調背離)
        fig.add_trace(
            go.Scatter(
                x=df[x_col],
                y=df[y2_col],
                name=y2_name,
                line=dict(color=y2_color, width=2.0, dash="dot"),
                mode="lines",
            ),
            secondary_y=True,
        )

        self._apply_dark_layout(fig, title=title, height=height)

        fig.update_yaxes(
            title_text=f"<b>{y1_name}</b>",
            secondary_y=False,
            title_font=dict(color=y1_color, size=13),
            tickfont=dict(color=y1_color),
        )
        fig.update_yaxes(
            title_text=f"<b>{y2_name}</b>",
            secondary_y=True,
            title_font=dict(color=y2_color, size=13),
            tickfont=dict(color=y2_color),
            showgrid=False,
        )

        return fig

    def plot_adr_premium(
        self,
        df: pd.DataFrame,
        date_col: str = "Date",
        premium_col: str = "ADR_Premium_Pct",
        title: str = "台積電 ADR 溢折價率趨勢 (TSM vs 2330.TW)",
        height: int = 460,
    ) -> go.Figure:
        """繪製台積電 ADR 溢折價率走勢圖 (包含 0 軸基準線與溢價/折價著色區間)。

        Args:
            df (pd.DataFrame): 包含日期與 ADR 溢價率之 DataFrame。
            date_col (str): 日期欄位名稱 (若在索引中則自動取用)。
            premium_col (str): 溢價率百分比欄位。
            title (str): 圖表標題。
            height (int): 圖表高度。

        Returns:
            go.Figure: Plotly 圖表物件。
        """
        plot_df = df.copy()
        if date_col not in plot_df.columns and isinstance(plot_df.index, pd.DatetimeIndex):
            plot_df = plot_df.reset_index()
            date_col = plot_df.columns[0]

        x_vals = plot_df[date_col]
        y_vals = plot_df[premium_col]

        fig = go.Figure()

        # 1. 繪製 0 軸基準參考線
        fig.add_hline(
            y=0,
            line_width=1.5,
            line_dash="dash",
            line_color="#747d8c",
            annotation_text="平價基準線 (0%)",
            annotation_position="bottom right",
            annotation_font=dict(color="#a4b0be", size=11),
        )

        # 2. 繪製溢折價長條柱狀體 (正溢價以亮金/紅展示，負折價以青藍展示)
        colors = np.where(y_vals >= 0, self.COLOR_ACCENT, self.COLOR_PRIMARY)
        fig.add_trace(
            go.Bar(
                x=x_vals,
                y=y_vals,
                name="溢折價率 (%)",
                marker=dict(color=colors, line=dict(width=0)),
                opacity=0.85,
            )
        )

        # 3. 疊加滾動均線 (若有足夠數據)
        if len(y_vals) >= 5:
            ma5 = y_vals.rolling(5, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=ma5,
                    name="5日均線",
                    line=dict(color="#ffffff", width=1.5),
                    mode="lines",
                )
            )

        self._apply_dark_layout(fig, title=title, height=height)
        fig.update_yaxes(
            title_text="溢折價率 (%)",
            ticksuffix="%",
            zeroline=True,
            zerolinecolor="#747d8c",
        )

        return fig

    def plot_chips_spread(
        self,
        distribution_df: pd.DataFrame,
        title: str = "股權籌碼級距分佈 (大戶 vs 散戶持股佔比)",
        height: int = 460,
    ) -> go.Figure:
        """繪製集保結算所 1~15 級距持股比例柱狀圖，並高亮散戶 (1~3) 與大戶 (12~15)。

        Args:
            distribution_df (pd.DataFrame): 包含 Level (1~15), Holding_Range, Percentage (%) 之 DataFrame。
            title (str): 圖表標題。
            height (int): 圖表高度。

        Returns:
            go.Figure: Plotly 圖表物件。
        """
        df = distribution_df.copy()
        level_col = "Level" if "Level" in df.columns else df.columns[0]
        range_col = "Holding_Range" if "Holding_Range" in df.columns else df.columns[1]
        pct_col = "Percentage" if "Percentage" in df.columns else df.columns[4]

        # 根據級距進行高亮區分:
        # 1~3: 散戶群體 (<10張) -> 淺紫/淡藍
        # 4~11: 中實戶 (10~400張) -> 深灰藍
        # 12~15: 大戶/千張大戶 (>=400張) -> 醒目金黃色
        colors = []
        hover_texts = []
        for _, row in df.iterrows():
            lvl = int(row[level_col])
            pct = float(row[pct_col])
            rng = str(row[range_col])
            if lvl <= 3:
                colors.append("#3867d6")
                group = "散戶群體 (<10張)"
            elif lvl >= 12:
                colors.append(self.COLOR_ACCENT)
                group = "大戶/千張大戶 (>=400張)"
            else:
                colors.append("#4b6584")
                group = "中實戶 (10~400張)"

            hover_texts.append(f"級距 {lvl}: {rng}<br>佔比: {pct}%<br>類別: {group}")

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=df[range_col].astype(str),
                y=df[pct_col],
                text=df[pct_col].apply(lambda x: f"{x:.1f}%"),
                textposition="outside",
                textfont=dict(color="#f1f2f6", size=11),
                marker=dict(color=colors),
                hoverinfo="text",
                hovertext=hover_texts,
                name="持股佔比 (%)",
            )
        )

        self._apply_dark_layout(fig, title=title, height=height, show_legend=False)
        fig.update_xaxes(title_text="持股分級 (股數)", tickangle=-30)
        fig.update_yaxes(title_text="佔集保總庫存比例 (%)", ticksuffix="%")

        return fig

    def plot_etf_overlaps(
        self,
        overlap_df: pd.DataFrame,
        top_n: int = 15,
        title: str = "熱門 ETF 重疊持股被動資金鎖碼排行榜",
        height: int = 480,
    ) -> go.Figure:
        """繪製多檔 ETF 重疊持股長條圖 (顯示被持有檔數與合計名目權重)。

        Args:
            overlap_df (pd.DataFrame): 由 ETFProcessor 產出之重疊度分析總表。
            top_n (int): 展示前幾名核心個股，預設 15。
            title (str): 圖表標題。
            height (int): 圖表高度。

        Returns:
            go.Figure: Plotly 水平長條圖物件。
        """
        if overlap_df.empty:
            return go.Figure()

        plot_df = overlap_df.head(top_n).copy()
        # 反轉以便在水平長條圖中由上往下排名第一名在最上方
        plot_df = plot_df.iloc[::-1].reset_index(drop=True)

        stock_labels = plot_df["Stock_Code"] + " " + plot_df["Stock_Name"]

        fig = go.Figure()

        # 繪製水平長條圖
        fig.add_trace(
            go.Bar(
                y=stock_labels,
                x=plot_df["Total_Weight"],
                orientation="h",
                name="合計名目權重 (%)",
                marker=dict(
                    color=plot_df["Total_Weight"],
                    colorscale="Tealgrn",
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="權重%", font=dict(color="#ced6e0", size=11)),
                        tickfont=dict(color="#ced6e0"),
                        len=0.7,
                    ),
                ),
                text=plot_df.apply(
                    lambda r: f"{r['Total_Weight']:.1f}% ({int(r['Overlap_Count'])}檔)",
                    axis=1,
                ),
                textposition="outside",
                textfont=dict(color="#f1f2f6", size=11),
                hovertemplate="<b>%{y}</b><br>合計名目權重: %{x:.2f}%<extra></extra>",
            )
        )

        self._apply_dark_layout(fig, title=title, height=height, show_legend=False)
        fig.update_xaxes(title_text="合計名目權重 (%)", ticksuffix="%")
        fig.update_yaxes(title_text="個股代號與名稱")

        return fig

    def plot_time_series_line(
        self,
        df: pd.DataFrame,
        x_col: str,
        y_cols: List[str],
        col_names: Optional[List[str]] = None,
        title: str = "時間序列走勢圖",
        y_title: str = "數值",
        height: int = 460,
    ) -> go.Figure:
        """繪製單軸多條時間序列折線圖 (支援多均線對比)。

        Args:
            df (pd.DataFrame): 數據來源 DataFrame。
            x_col (str): 時間軸欄位。
            y_cols (List[str]): 繪製折線欄位清單。
            col_names (Optional[List[str]]): 折線名稱清單。
            title (str): 標題。
            y_title (str): Y 軸標籤。
            height (int): 高度。

        Returns:
            go.Figure: Plotly 圖表物件。
        """
        fig = go.Figure()
        colors = [
            self.COLOR_PRIMARY,
            self.COLOR_ACCENT,
            self.COLOR_PURPLE,
            self.COLOR_ORANGE,
            self.COLOR_BULL,
        ]

        names = col_names or y_cols
        for i, (col, name) in enumerate(zip(y_cols, names)):
            if col not in df.columns:
                continue
            color = colors[i % len(colors)]
            dash = "solid" if i == 0 else "dot"
            width = 2.2 if i == 0 else 1.6

            fig.add_trace(
                go.Scatter(
                    x=df[x_col],
                    y=df[col],
                    name=name,
                    mode="lines",
                    line=dict(color=color, width=width, dash=dash),
                )
            )

        self._apply_dark_layout(fig, title=title, height=height)
        fig.update_yaxes(title_text=f"<b>{y_title}</b>")
        return fig
