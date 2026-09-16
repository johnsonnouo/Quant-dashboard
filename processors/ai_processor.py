# processors/ai_processor.py
"""AI 智能文本分析與摘要處理模組。

本模組整合 Google GenAI (Gemini) SDK，負責將晨間新聞、
市場公告及總經事件進行自然語言理解與量化投資觀點提煉。
"""

import logging
from google import genai
import streamlit as st

logger = logging.getLogger(__name__)


def summarize_morning_news(news_articles: str) -> str:
    """使用 Gemini 3.6 Flash 生成台股開盤作戰計畫摘要。

    Args:
        news_articles (str): 包含美股與台股之晨間即時財經新聞清單。

    Returns:
        str: 嚴格遵循 3 大格式的繁體中文分析報告 (控制在 350 字內)。

    Raises:
        KeyError: 當 Streamlit secrets 未設定 GEMINI_API_KEY 時。
        Exception: 呼叫 Gemini API 過程發生其他例外時。
    """
    if "GEMINI_API_KEY" not in st.secrets:
        raise KeyError(
            "未在 Streamlit secrets 中找到 'GEMINI_API_KEY'。請於 .streamlit/secrets.toml 中設定。"
        )

    # 從 Streamlit 保險箱讀取 API Key 實例化 Client
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

    prompt = (
        "你是一位頂尖的跨國量化交易員。現在是台灣時間早上 8 點，距離台股開盤僅剩一小時。"
        "請閱讀以下真實的新聞清單（包含美股與台股），幫我精煉出今日開盤作戰計畫。\n"
        "請嚴格遵循以下 3 點格式輸出（使用繁體中文，總字數控制在 350 字以內，語氣專業具實戰感）：\n\n"
        "1. 【美股盤後總結】：總結昨晚美股收盤核心動態（如科技股、半導體或總經數據）。\n"
        "2. 【台股開盤預演】：分析美股表現對稍後 9 點台股開盤（如大盤、台積電 ADR 連動、AI 概念股）的預期影響與資金動向。\n"
        "3. 【今日焦點】：近期台股本土的關鍵焦點或產業趨勢。\n\n"
        f"【最新財經新聞清單】：\n{news_articles}"
    )

    logger.info("發送即時新聞至 Gemini 3.6 Flash 進行盤前作戰計畫運算...")
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    return response.text or "未能生成有效作戰計畫內容。"
