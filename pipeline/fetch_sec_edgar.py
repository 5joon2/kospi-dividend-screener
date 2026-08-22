"""
SEC EDGAR XBRL companyfacts API로 자사주(자기주식) 관련 공시 데이터 수집 (fetch_dart.py의 미국판).

DART처럼 실주식수 기준 공식 규제 데이터라 yfinance 현금흐름표(금액 기반)보다 정밀하지만,
회계 관행 자체가 한국과 다르다는 점에 유의 — 미국(특히 델라웨어 법인)은 자사주를
매입 즉시 발행주식에서 상각(retire)하는 경우가 흔해서, 그런 회사는 TreasuryStockCommonShares가
매입을 많이 해도 0에 가깝게 나온다. 이 경우 "자사주 보유비율" 0은 결측이 아니라
회계처리 방식 차이로 인한 실제 값이다 — 정성적으로 다르게 해석해야 함(README 참고, TODO).

인증키 불필요, 대신 SEC 정책상 식별 가능한 User-Agent 헤더가 필수.
실키 테스트 중 확인한 점(2026-08-22): User-Agent에 URL(http로 시작하는 문자열)이
들어가면 SEC WAF가 403으로 차단함 — "이름 + 이메일" 형식(예: "회사명 admin@example.com")만
통과됨. 기본값은 예시용 더미 이메일이라, 실제 운영 시에는 환경변수 SEC_USER_AGENT에
진짜 연락 가능한 이메일을 넣는 게 SEC 정책 취지에 맞음(TODO).

CIK(10자리)는 fetch_sp500_tickers.py가 위키피디아 S&P 500 표에서 이미 받아와
data/sp500_tickers.csv에 저장해두므로, 여기서는 별도 티커→CIK 매핑을 하지 않는다
— 위키 표에서 CIK 컬럼이 빠지면(TODO) SEC가 공개하는
https://www.sec.gov/files/company_tickers.json 으로 대체해야 함.
"""

from __future__ import annotations

import os
from datetime import date

from http_retry import request_with_retry

COMPANY_FACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# XBRL 태그명은 회사마다 어떤 us-gaap 표준 태그를 쓰는지(혹은 회사 자체 확장 태그를
# 쓰는지) 제각각이라, 후보를 여러 개 순회하며 처음 찾은 것을 쓴다
# (DART의 "보통주"/"보통주식" 표기 차이 방어 로직과 같은 종류의 이슈).
TREASURY_SHARES_TAGS = ["TreasuryStockCommonShares", "TreasuryStockShares"]
SHARES_ISSUED_TAGS = ["CommonStockSharesIssued"]
# TreasuryStockSharesAcquired류는 "매입 후 보유" 회계를 쓰는 회사만 씀 — 애플처럼
# 매입 즉시 소각(retire)하는 회사는 이 태그가 아예 없고 대신
# StockRepurchasedAndRetiredDuringPeriodShares를 씀(2026-08-22, 애플 실키로 확인:
# TreasuryStockCommonShares/TreasuryStockSharesAcquired 둘 다 없고 이 태그만 존재).
# 후보를 순서대로 시도해서 회사마다 다른 회계 관행을 커버.
BUYBACK_SHARES_ACQUIRED_TAGS = [
    "TreasuryStockSharesAcquired",
    "StockRepurchasedDuringPeriodShares",
    "StockRepurchasedAndRetiredDuringPeriodShares",
]


def _find_concept(gaap: dict, candidates: list[str]) -> dict | None:
    for name in candidates:
        if name in gaap:
            return gaap[name]
    return None


def _latest_instant(concept: dict, unit: str = "shares") -> tuple[float, str] | None:
    """대차대조표 시점값(자기주식수 등) — end 날짜 기준 최신값."""
    entries = concept.get("units", {}).get(unit, [])
    if not entries:
        return None
    entries = sorted(entries, key=lambda e: (e.get("end", ""), e.get("filed", "")))
    latest = entries[-1]
    val = latest.get("val")
    return (val, latest.get("end")) if val is not None else None


def _annual_sums(concept: dict, unit: str = "shares") -> dict[int, float]:
    """연간 흐름값(자사주 매입 주식수 등) — 10-K(사업보고서격) 기준 회계연도(fy)별 신고값만.

    10-Q(분기)까지 섞으면 같은 회계연도 안에서 중복 집계될 수 있어 연간 보고서만 사용.
    """
    entries = concept.get("units", {}).get(unit, [])
    by_fy: dict[int, float] = {}
    for e in entries:
        if e.get("form") not in ("10-K", "10-K/A"):
            continue
        fy, val = e.get("fy"), e.get("val")
        if fy is None or val is None:
            continue
        by_fy[fy] = val
    return by_fy


class SecEdgarClient:
    def __init__(self, user_agent: str | None = None):
        self.user_agent = user_agent or os.environ.get(
            "SEC_USER_AGENT", "kospi-dividend-screener admin@example.com"
        )

    def company_facts(self, cik: str) -> dict:
        resp = request_with_retry(
            "GET",
            COMPANY_FACTS_URL_TMPL.format(cik=cik),
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def treasury_ratio_pct(self, cik: str) -> float | None:
        """자기주식 보유비율(%) = 자기주식수 ÷ 발행주식총수. 태그 자체가 없으면 None
        (결측), 태그는 있는데 값이 0이면 실제로 매입 즉시 소각하는 회사일 수 있음(위 모듈독스트링 참고)."""
        gaap = self.company_facts(cik).get("facts", {}).get("us-gaap", {})
        treasury = _find_concept(gaap, TREASURY_SHARES_TAGS)
        issued = _find_concept(gaap, SHARES_ISSUED_TAGS)
        if treasury is None or issued is None:
            return None
        t = _latest_instant(treasury)
        i = _latest_instant(issued)
        if not t or not i or not i[0]:
            return None
        return round(t[0] / i[0] * 100, 3)

    def buyback_regular_and_cancel_ratio(self, cik: str, lookback_years: int = 3) -> tuple[bool, float]:
        """(최근 N년 내 자사주매입 정기 실시 여부, 근사 소각비율).

        DART 쪽(자기주식취득결정 공시 ≥2건/2년 → 정기적)과 같은 감각으로,
        최근 lookback_years간 실제 매입이 있었던 회계연도가 2개 이상이면 "정기적"으로 판단.
        소각비율은 그 기간 매입 주식수 합계 ÷ 최근 발행주식총수로 근사
        (한국은 "매입→소각" 2단계지만 여기선 매입 주식수 자체를 근사치로 사용, TODO 참고).
        """
        gaap = self.company_facts(cik).get("facts", {}).get("us-gaap", {})
        acquired = _find_concept(gaap, BUYBACK_SHARES_ACQUIRED_TAGS)
        if acquired is None:
            return False, 0.0

        by_fy = _annual_sums(acquired)
        this_year = date.today().year
        recent = {fy: v for fy, v in by_fy.items() if fy >= this_year - lookback_years and v}
        is_regular = len(recent) >= 2

        cancel_ratio = 0.0
        if is_regular:
            issued = _find_concept(gaap, SHARES_ISSUED_TAGS)
            i = _latest_instant(issued) if issued is not None else None
            if i and i[0]:
                cancel_ratio = round(sum(recent.values()) / i[0] * 100, 3)
        return is_regular, cancel_ratio


if __name__ == "__main__":
    client = SecEdgarClient()
    apple_cik = "0000320193"
    print("애플 자사주 보유비율(%):", client.treasury_ratio_pct(apple_cik))
    print("애플 정기매입 여부/소각비율:", client.buyback_regular_and_cancel_ratio(apple_cik))
