"""
전종목을 순회하며 외부 API를 호출하다 보면 일시적인 DNS 해석 실패·5xx·타임아웃이
꽤 자주 섞여 나온다 (실제 848종목 전체 실행 중 KIS 쪽에서 이런 문제를 직접 겪음).
호출 한 번마다 짧게 재시도해서 이런 일시적 오류로 종목 하나가 통째로 실패 처리되는 걸 줄인다.
"""

from __future__ import annotations

import time

import requests

TRANSIENT_EXCEPTIONS = (requests.ConnectionError, requests.Timeout)
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


def request_with_retry(
    method: str, url: str, *, max_attempts: int = 3, backoff_seconds: float = 1.0, **kwargs
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except TRANSIENT_EXCEPTIONS as e:
            last_exc = e
        else:
            if resp.status_code not in RETRYABLE_STATUS_CODES:
                return resp
            last_exc = requests.HTTPError(f"{resp.status_code} 재시도 대상 오류", response=resp)

        if attempt < max_attempts:
            time.sleep(backoff_seconds * attempt)  # 1s, 2s, ...

    raise last_exc
