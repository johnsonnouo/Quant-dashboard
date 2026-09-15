# fetchers/base.py
"""基礎數據獲取模組。

本模組定義了數據獲取層的抽象基底類別 (BaseFetcher) 與自訂例外處理 (DataFetchError)，
並配置了自動重試 (Exponential Backoff) 的 HTTP Session，供所有具體 Fetcher 繼承使用。
"""

import abc
import json
import logging
from typing import Any, Dict, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_HEADERS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    RETRY_STATUS_CODES,
)

logger = logging.getLogger(__name__)


class DataFetchError(Exception):
    """數據獲取失敗時拋出的自訂例外類別。

    Attributes:
        message (str): 錯誤詳細訊息。
        status_code (Optional[int]): HTTP 狀態碼 (若有)。
        endpoint (Optional[str]): 請求失敗的目標 URL。
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.endpoint = endpoint

    def __str__(self) -> str:
        base_msg = f"[DataFetchError] {self.message}"
        if self.status_code:
            base_msg += f" (Status: {self.status_code})"
        if self.endpoint:
            base_msg += f" (Endpoint: {self.endpoint})"
        return base_msg


class BaseFetcher(abc.ABC):
    """數據獲取層抽象基底類別 (Abstract Base Class)。

    所有特定市場或資料源的 Fetcher 皆應繼承此類別，享有內建的連線池管理、
    指數退避重試 (Exponential Backoff) 及統一錯誤處理機制。
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """初始化 BaseFetcher 實例並建立配置好重試策略的 requests.Session。

        Args:
            timeout (int): 請求超時秒數，預設為 DEFAULT_TIMEOUT。
            max_retries (int): 遇到暫時性錯誤時的最大重試次數。
            backoff_factor (float): 指數退避乘數。
            custom_headers (Optional[Dict[str, str]]): 自訂額外請求標頭。
        """
        self.timeout = timeout
        self.session = self._init_resilient_session(
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            custom_headers=custom_headers,
        )

    def _init_resilient_session(
        self,
        max_retries: int,
        backoff_factor: float,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> requests.Session:
        """配置具備 Exponential Backoff 機制的 requests.Session。

        Args:
            max_retries (int): 最大重試次數。
            backoff_factor (float): 退避因子。
            custom_headers (Optional[Dict[str, str]]): 額外標頭。

        Returns:
            requests.Session: 設定完成的 Session 連線物件。
        """
        session = requests.Session()

        # 合併全域預設標頭與自訂標頭
        headers = dict(DEFAULT_HEADERS)
        if custom_headers:
            headers.update(custom_headers)
        session.headers.update(headers)

        # 設定重試策略 (涵蓋網路斷線與 429 / 5xx 伺服器錯誤)
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
            raise_on_status=False,  # 由程式統一檢查 status_code 並拋出 DataFetchError
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _request_raw(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """底層 HTTP 請求調度器，封裝了通用的錯誤攔截與轉換。

        Args:
            method (str): HTTP 方法 (GET, POST 等)。
            url (str): 目標端點網址。
            params (Optional[Dict[str, Any]]): 查詢參數。
            data (Optional[Any]): Form-data 內容。
            json_data (Optional[Dict[str, Any]]): JSON 負載內容。
            headers (Optional[Dict[str, str]]): 單次請求專用標頭。
            timeout (Optional[int]): 單次請求自訂超時時間。

        Returns:
            requests.Response: HTTP 回應物件。

        Raises:
            DataFetchError: 連線失敗、超時或伺服器回應非 200 狀態時拋出。
        """
        req_timeout = timeout or self.timeout
        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                data=data,
                json=json_data,
                headers=headers,
                timeout=req_timeout,
            )

            # 檢查 HTTP 狀態碼
            if not (200 <= response.status_code < 300):
                raise DataFetchError(
                    message=f"HTTP 請求失敗，狀態碼為 {response.status_code}，回應預覽: {response.text[:200]}",
                    status_code=response.status_code,
                    endpoint=url,
                )

            return response

        except requests.exceptions.Timeout as exc:
            logger.error("請求目標端點逾時: %s", url)
            raise DataFetchError(
                message=f"連線超時 ({req_timeout}s): {str(exc)}",
                endpoint=url,
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.error("HTTP 請求發生網路或傳輸層例外: %s, 錯誤: %s", url, str(exc))
            raise DataFetchError(
                message=f"網路連線異常: {str(exc)}",
                endpoint=url,
            ) from exc

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Union[Dict[str, Any], list]:
        """發送 GET 請求並自動解析為 JSON 物件。

        Args:
            url (str): 目標端點網址。
            params (Optional[Dict[str, Any]]): 查詢參數。
            headers (Optional[Dict[str, str]]): 額外標頭。
            timeout (Optional[int]): 自訂超時時間。

        Returns:
            Union[Dict[str, Any], list]: 解析後的 JSON 字典或串列。

        Raises:
            DataFetchError: 請求失敗或內容非合法 JSON 時拋出。
        """
        response = self._request_raw(
            method="GET",
            url=url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("解析端點 JSON 失敗: %s, 內容前段: %s", url, response.text[:200])
            raise DataFetchError(
                message=f"伺服器回應內容無法解析為 JSON: {str(exc)}",
                status_code=response.status_code,
                endpoint=url,
            ) from exc

    def get_text(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        encoding: Optional[str] = None,
    ) -> str:
        """發送 GET 請求並取得純文字/HTML 內容。

        Args:
            url (str): 目標端點網址。
            params (Optional[Dict[str, Any]]): 查詢參數。
            headers (Optional[Dict[str, str]]): 額外標頭。
            timeout (Optional[int]): 自訂超時時間。
            encoding (Optional[str]): 指定字元編碼，若未提供則自動偵測 UTF-8 / apparent_encoding。

        Returns:
            str: 回應之純文字內容。
        """
        response = self._request_raw(
            method="GET",
            url=url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        if encoding:
            response.encoding = encoding
        elif response.encoding in (None, "ISO-8859-1"):
            response.encoding = response.apparent_encoding or "utf-8"

        return response.text

    def close(self) -> None:
        """關閉 requests Session 連線池釋放資源。"""
        self.session.close()

    def __enter__(self) -> "BaseFetcher":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
