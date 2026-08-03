"""
한국투자증권 KIS Developers REST API로 코스피 전종목 시세/PER/PBR/배당수익률 수집.

인증: 환경변수 KIS_APP_KEY / KIS_APP_SECRET (apiportal.koreainvestment.com에서 발급).
API 문서: https://apiportal.koreainvestment.com

실키로 전종목(848개) 순회 테스트 중 이 API 도메인에 대한 DNS 해석이 간헐적으로
실패하는 걸 확인(2026-08-03) — http_retry.request_with_retry로 재시도 처리.
"""

from __future__ import annotations

import os
import time

from http_retry import request_with_retry

KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"


class KisClient:
    def __init__(self, app_key: str | None = None, app_secret: str | None = None):
        self.app_key = app_key or os.environ.get("KIS_APP_KEY")
        self.app_secret = app_secret or os.environ.get("KIS_APP_SECRET")
        if not self.app_key or not self.app_secret:
            raise RuntimeError("KIS_APP_KEY / KIS_APP_SECRET이 설정되지 않았습니다.")
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

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
        data = resp.json()
        self._access_token = data["access_token"]
        # expires_in은 보통 초 단위(24시간). 여유를 두고 갱신.
        self._token_expires_at = time.time() + int(data.get("expires_in", 86400)) - 300
        return self._access_token

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
