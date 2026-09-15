# views/__init__.py
"""儀表板各分頁視圖模組。"""

from .tab_macro import render_tab_macro
from .tab_etf_matrix import render_tab_etf_matrix
from .tab_chips import render_tab_chips
from .tab_market_breadth import render_tab_market_breadth

__all__ = [
    "render_tab_macro",
    "render_tab_etf_matrix",
    "render_tab_chips",
    "render_tab_market_breadth",
]
