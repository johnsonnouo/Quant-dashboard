# fetchers/news_fetcher.py
"""財經晨報與 RSS 即時新聞爬蟲模組。

本模組負責抓取跨國（美股 CNBC、台股 Yahoo 財經）最新 RSS 財經新聞，
清洗 HTML 標籤後組合成結構化文字清單，供 AI 分析師進行盤前重點提煉。
"""

import logging
import re
from typing import List

from bs4 import BeautifulSoup
import feedparser
import requests

from config.settings import DEFAULT_HEADERS, DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

CNBC_INVESTING_RSS = "https://www.cnbc.com/id/15839069/device/rss/rss.html"
YAHOO_TW_FINANCE_RSS = "https://tw.news.yahoo.com/rss/finance"


def _clean_html(raw_html: str) -> str:
    """清理摘要文字中的 HTML 標籤與多餘空白。"""
    if not raw_html:
        return ""
    # 使用 BeautifulSoup 去除標籤
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    # 去除多餘空格與換行
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_morning_news(max_items_per_source: int = 10) -> str:
    """抓取美股 (CNBC) 與台股 (Yahoo 財經) 最新 RSS 新聞並組合成結構文字。

    Args:
        max_items_per_source (int): 每個來源最多提取的新聞筆數，預設 10 筆。

    Returns:
        str: 標註來源並包含標題與摘要的整潔長字串。
    """
    sections: List[str] = []

    # 1. 抓取美股 CNBC 投資新聞
    try:
        logger.info("正在抓取美股 CNBC RSS 新聞: %s", CNBC_INVESTING_RSS)
        resp_cnbc = requests.get(
            CNBC_INVESTING_RSS,
            headers=DEFAULT_HEADERS,
            timeout=DEFAULT_TIMEOUT,
        )
        if resp_cnbc.status_code == 200:
            feed_cnbc = feedparser.parse(resp_cnbc.content)
            cnbc_articles: List[str] = []
            for i, entry in enumerate(feed_cnbc.entries[:max_items_per_source], 1):
                title = getattr(entry, "title", "").strip()
                summary = _clean_html(getattr(entry, "summary", ""))
                if title:
                    item_str = f"{i}. 標題: {title}"
                    if summary:
                        item_str += f"\n   摘要: {summary}"
                    cnbc_articles.append(item_str)

            if cnbc_articles:
                sections.append("【美股新聞 (CNBC)】\n" + "\n".join(cnbc_articles))
            else:
                logger.warning("CNBC RSS 回傳內容無有效項目")
        else:
            logger.warning("CNBC RSS 請求失敗，狀態碼: %d", resp_cnbc.status_code)
    except Exception as exc:
        logger.error("抓取美股 CNBC RSS 發生錯誤，將予略過: %s", str(exc))

    # 2. 抓取台股 Yahoo 財經新聞
    try:
        logger.info("正在抓取台股 Yahoo 財經 RSS 新聞: %s", YAHOO_TW_FINANCE_RSS)
        resp_yahoo = requests.get(
            YAHOO_TW_FINANCE_RSS,
            headers=DEFAULT_HEADERS,
            timeout=DEFAULT_TIMEOUT,
        )
        if resp_yahoo.status_code == 200:
            feed_yahoo = feedparser.parse(resp_yahoo.content)
            yahoo_articles: List[str] = []
            for i, entry in enumerate(feed_yahoo.entries[:max_items_per_source], 1):
                title = getattr(entry, "title", "").strip()
                summary = _clean_html(getattr(entry, "summary", ""))
                if title:
                    item_str = f"{i}. 標題: {title}"
                    if summary:
                        item_str += f"\n   摘要: {summary}"
                    yahoo_articles.append(item_str)

            if yahoo_articles:
                sections.append("【台股新聞】\n" + "\n".join(yahoo_articles))
            else:
                logger.warning("Yahoo TW 財經 RSS 回傳內容無有效項目")
        else:
            logger.warning("Yahoo TW 財經 RSS 請求失敗，狀態碼: %d", resp_yahoo.status_code)
    except Exception as exc:
        logger.error("抓取台股 Yahoo 財經 RSS 發生錯誤，將予略過: %s", str(exc))

    if not sections:
        return "未能成功抓取到任何即時財經新聞，請檢查網路連線或稍後再試。"

    return "\n\n" + "=" * 40 + "\n\n".join(sections)
