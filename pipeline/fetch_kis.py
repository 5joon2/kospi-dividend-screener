"""
한국투자증권 KIS Developers REST API로 코스피 전종목 시세/PER/PBR/배당수익률 수집.

인증: 환경변수 KIS_APP_KEY / KIS_APP_SECRET (apiportal.koreainvestment.com에서 발급).
API 문서: https://apiportal.koreainvestment.com

주의: 이 파일은 KIS 앱키를 아직 발급받기 전에 문서 기준으로 작성한 초안입니다.
실제 키로 첫 실행할 때 응답 필드명/tr_id가 문서와 다르면 바로 잡아야 합니다 —
`uv run pipeline/fetch_kis.py`로 삼성전자(005930) 하나만 먼저 테스트해볼 것.
"""

from __future__ import annotations

import os
import time

import requests

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

        resp = requests.post(
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
        resp = requests.get(
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
        resp = requests.get(
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


def load_kospi_ticker_list() -> list[str]:
    """코스피 전종목 코드 목록.

    KIS REST API에는 '전종목 목록' 전용 엔드포인트가 없어 KRX/KIS가 배포하는
    종목마스터 파일(kospi_code.mst)을 내려받아 파싱하는 게 표준적인 방법.
    1차 버전에서는 DART corpCode.xml에서 얻은 상장 종목 코드 목록으로 대체 가능
    (run_pipeline.py에서 fetch_dart.corp_code_map() 결과를 그대로 사용).
    """
    raise NotImplementedError(
        "코스피 종목 목록은 run_pipeline.py에서 DART corp_code_map()으로 대체 수집합니다."
    )


if __name__ == "__main__":
    client = KisClient()
    print(client.price_metrics("005930"))
