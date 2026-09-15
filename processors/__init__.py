# processors/__init__.py
"""商業邏輯與指標計算層模組。

本模組嚴格遵循「關注點分離」原則，不發起任何網路請求，專門接收 DataFrame 數據
並透過 pandas 向量化計算衍生量化指標 (總經均線、ETF 鎖碼股、期貨留倉平滑、騰落指標等)。
"""

from .macro_processor import MacroProcessor
from .etf_processor import ETFProcessor
from .chips_processor import ChipsProcessor
from .breadth_processor import BreadthProcessor

__all__ = [
    "MacroProcessor",
    "ETFProcessor",
    "ChipsProcessor",
    "BreadthProcessor",
]
