from __future__ import annotations

import time
import requests
from typing import Any, Optional


class HttpClient:
    def __init__(self, timeout: int = 10, retries: int = 2, backoff_seconds: float = 1.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MemeBotV3/1.0"})

    def get_json(self, url: str) -> Optional[Any]:
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except Exception:
                if attempt >= self.retries:
                    return None
                time.sleep(self.backoff_seconds * (attempt + 1))
        return None
