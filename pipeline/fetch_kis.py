"""
한국투자증권 KIS Developers REST API로 코스피 전종목 시세/PER/PBR/배당수익률 수집.

인증: 환경변수 KIS_APP_KEY / KIS_APP_SECRET (apiportal.koreainvestment.com에서 발급).
API 문서: https://apiportal.koreainvestment.com

실키로 833종목 순회 테스트 중 이 API 도메인에 대한 DNS 해석 실패(간헐적)와
접근토큰 발급 403(짧은 시간에 재발급을 너무 자주 요청해서 발생한 것으로 추정,
2026-08-03)을 둘 다 겪음 — http_retry.request_with_retry로 개별 호출 재시도 처리,
토큰은 파일 캐시로 프로세스 간에도 재사용해서 재발급 자체를 최소화.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from http_retry import request_with_retry

KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_PATH = Path(__file__).parent.parent / ".kis_token_cache.json"


class KisClient:
    def __init__(self, app_key: str | None = None, app_secret: str | None = None):
        self.app_key = app_key or os.environ.get("KIS_APP_KEY")
        self.app_secret = app_secret or os.environ.get("KIS_APP_SECRET")
        if not self.app_key or not self.app_secret:
            raise RuntimeError("KIS_APP_KEY / KIS_APP_SECRET이 설정되지 않았습니다.")
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _load_cached_token(self) -> None:
        if not TOKEN_CACHE_PATH.exists():
            return
        try:
            cached = json.loads(TOKEN_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return
        if cached.get("app_key") != self.app_key:
            return  # 다른 앱키로 캐시된 토큰은 재사용 불가
        if time.time() < cached.get("expires_at", 0):
            self._access_token = cached["access_token"]
            self._token_expires_at = cached["expires_at"]

    def _save_cached_token(self) -> None:
        try:
            TOKEN_CACHE_PATH.write_text(json.dumps({
                "app_key": self.app_key,
                "access_token": self._access_token,
                "expires_at": self._token_expires_at,
            }))
        except OSError:
            pass  # 캐시 저장 실패는 무시 — 토큰 자체는 메모리에 있으니 이번 실행엔 지장 없음

    def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        self._load_cached_token()
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        # KIS 토큰 발급 엔드포인트는 "분당 1회" 제한이 있음(공식 가이드 확인, 1일 1회가 아님).
        # 60초 안에 재시도하면 무조건 또 막히므로 최소 65초는 기다렸다가 재시도.
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                resp = request_with_retry(
                    "POST",
                    f"{KIS_BASE_URL}/oauth2/tokenP",
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self.app_key,
                        "appsecret": self.app_secret,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
            except requests.HTTPError as e:
                last_exc = e
                if attempt < 3:
                    time.sleep(65)
                continue
            data = resp.json()
            self._access_token = data["access_token"]
            # expires_in은 보통 초 단위(24시간). 여유를 두고 갱신.
            self._token_expires_at = time.time() + int(data.get("expires_in", 86400)) - 300
            self._save_cached_token()
            return self._access_token

        raise last_exc

    def _headers(self, tr_id: str) -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    def price_metrics(self, ticker: str) -> dict:
        """국내주식 현재가 시세 조회 — PER/PBR/EPS/BPS/시가총액 등 포함.

        tr_id FHKST01010100 (실전투자/모의투자 공통 조회성 API).
        """
        resp = request_with_retry(
            "GET",
            f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers("FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
            timeout=10,
        )
        resp.raise_for_status()
        output = resp.json().get("output", {})
        return {
            "ticker": ticker,
            "per": _to_float(output.get("per")),
            "pbr": _to_float(output.get("pbr")),
            "eps": _to_float(output.get("eps")),
            "bps": _to_float(output.get("bps")),
            "market_cap": _to_float(output.get("hts_avls")),
        }

    def dividend_info(self, ticker: str) -> dict:
        """예탁결제원 배당 정보 — 배당수익률/주당배당금 등.

        tr_id HHKDB669102C0. 종목코드는 6자리, 조회기간(gb1/cts) 파라미터는
        실제 발급 후 KIS Developers 포털의 "배당일정" 샘플로 재확인 필요.
        """
        resp = request_with_retry(
            "GET",
            f"{KIS_BASE_URL}/uapi/domestic-stock/v1/ksdinfo/dividend",
            headers=self._headers("HHKDB669102C0"),
            params={"CTS": "", "GB1": "0", "F_DT": "", "T_DT": "", "SHT_CD": ticker},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("output", [])


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    client = KisClient()
    print(client.price_metrics("005930"))
