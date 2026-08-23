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
from dataclasses import dataclass
from datetime import date

from http_retry import request_with_retry

COMPANY_FACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# 이상치로 판정된 값을 채점에 넘길 때 쓰는 안전한 기본값 — scoring.py의 각 배점
# 구간표에서 "그 외(최저점)" 버킷에 확실히 떨어지도록 일부러 범위를 벗어난 큰 값을
# 씀(예: score_treasury_ratio는 5%를 넘으면 전부 0점). 결측(0점 처리)과 똑같이
# "모르면 후하게 주지 않는다" 방향으로 안전하게 처리하려는 것 — 반대로 낮은 값을
# 기본값으로 쓰면 검증 안 된 수치가 만점을 받는 사고가 날 수 있음(2026-08-22,
# LRCX 자사주비율 136% 이상치를 그대로 뒀으면 "else"라 우연히 0점이었지만,
# 만약 태그 스케일 문제로 음수가 나왔다면 <=0 조건에 걸려 만점을 받았을 것).
SUSPECT_SENTINEL_PCT = 999.0

# XBRL 태그명은 회사마다 어떤 us-gaap 표준 태그를 쓰는지(혹은 회사 자체 확장 태그를
# 쓰는지) 제각각이라, 후보를 여러 개 순회하며 처음 찾은 것을 쓴다
# (DART의 "보통주"/"보통주식" 표기 차이 방어 로직과 같은 종류의 이슈).
TREASURY_SHARES_TAGS = ["TreasuryStockCommonShares", "TreasuryStockShares"]
SHARES_ISSUED_TAGS = ["CommonStockSharesIssued"]
SHARES_OUTSTANDING_TAGS = ["CommonStockSharesOutstanding"]
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


def _instants(concept: dict, unit: str = "shares") -> list[tuple[str, float]]:
    """대차대조표 시점값 전체 이력 — (end 날짜, 값) 목록, end 오름차순."""
    entries = concept.get("units", {}).get(unit, [])
    out = [
        (e.get("end"), e.get("val"))
        for e in sorted(entries, key=lambda e: (e.get("end", ""), e.get("filed", "")))
        if e.get("val") is not None and e.get("end")
    ]
    return out


def _latest_instant(concept: dict, unit: str = "shares") -> tuple[float, str] | None:
    """대차대조표 시점값(자기주식수 등) — end 날짜 기준 최신값."""
    series = _instants(concept, unit)
    if not series:
        return None
    end, val = series[-1]
    return val, end


@dataclass
class TreasuryCheck:
    value: float  # 채점에 쓸 값 — 이상치면 SUSPECT_SENTINEL_PCT
    raw_ratio: float | None  # 태그값 기준 원계산치(이상치여도 참고용으로 보존)
    suspect: bool
    notes: list[str]


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

    def treasury_ratio_pct(self, cik: str) -> TreasuryCheck:
        """자기주식 보유비율(%) = 자기주식수 ÷ 발행주식총수, 3중 교차검증 포함.

        (2026-08-22, LRCX(Lam Research) 실키 테스트에서 136.7%라는 물리적으로
        불가능한 값을 발견 — 원인 확인해보니 LRCX는 CommonStockSharesIssued를
        발행주식 총수(자기주식 포함)가 아니라 유통주식수(자기주식 제외, 즉
        CommonStockSharesOutstanding과 동일값)로 신고하고 있었음. 회사마다
        같은 태그를 다르게 쓰는 게 실제로 존재해서, 태그 하나만 믿지 않고
        아래 3단계로 검증한다:

        ① 논리적 상한 — 자기주식 ≤ 발행주식총수여야 하므로 0~100% 범위를
           벗어나면 무조건 이상치.
        ② 회계항등식 교차검증 — "발행주식총수 = 유통주식수 + 자기주식수"라는
           항등식으로 역산한 비율((발행주식-유통주식)/발행주식)과 태그 기반
           비율을 비교, 10%p 넘게 벌어지면 태그 자체가 안 맞는 것으로 판단.
        ③ 시계열 급변 검증 — 같은 태그의 직전 신고값 대비 3배 넘게 뛰거나
           줄면(단위·스케일 혼동 가능성) 이상치 의심.

        이상치로 판정되면 채점용 value는 SUSPECT_SENTINEL_PCT(그 항목 최저점
        버킷으로 확실히 떨어지는 값)로 대체 — raw_ratio에는 원래 계산값을
        그대로 보존해 대시보드/로그에서 확인할 수 있게 함.
        """
        gaap = self.company_facts(cik).get("facts", {}).get("us-gaap", {})
        treasury = _find_concept(gaap, TREASURY_SHARES_TAGS)
        issued = _find_concept(gaap, SHARES_ISSUED_TAGS)
        if treasury is None or issued is None:
            return TreasuryCheck(value=0.0, raw_ratio=None, suspect=False, notes=["treasury/issued 태그 없음(결측)"])

        t = _latest_instant(treasury)
        i = _latest_instant(issued)
        if not t or not i or not i[0]:
            return TreasuryCheck(value=0.0, raw_ratio=None, suspect=False, notes=["시점값 없음(결측)"])

        ratio_a = round(t[0] / i[0] * 100, 3)
        notes: list[str] = []
        suspect = False

        # ① 논리적 상한
        if not (0 <= ratio_a <= 100):
            suspect = True
            notes.append(f"0~100% 범위 밖({ratio_a}%)")

        # ② 회계항등식 교차검증
        outstanding = _find_concept(gaap, SHARES_OUTSTANDING_TAGS)
        if outstanding is not None:
            o = _latest_instant(outstanding)
            if o and o[0] and i[0]:
                ratio_b = round((i[0] - o[0]) / i[0] * 100, 3)
                if abs(ratio_a - ratio_b) > 10:
                    suspect = True
                    notes.append(f"태그값({ratio_a}%) vs 회계항등식 역산({ratio_b}%) 불일치")

        # ③ 시계열 급변 검증 (같은 태그의 직전 신고값과 비교)
        t_series = _instants(treasury)
        if len(t_series) >= 2:
            prev_val = t_series[-2][1]
            if prev_val and (t[0] > prev_val * 3 or t[0] < prev_val / 3):
                suspect = True
                notes.append(f"직전 신고값({prev_val:,.0f}) 대비 급변({t[0]:,.0f})")

        value = SUSPECT_SENTINEL_PCT if suspect else ratio_a
        return TreasuryCheck(value=value, raw_ratio=ratio_a, suspect=suspect, notes=notes)

    def buyback_regular_and_cancel_ratio(self, cik: str, lookback_years: int = 3) -> tuple[bool, float, bool, list[str]]:
        """(정기매입 여부, 채점용 소각비율, 이상치 의심 여부, 근거 메모).

        DART 쪽(자기주식취득결정 공시 ≥2건/2년 → 정기적)과 같은 감각으로,
        최근 lookback_years간 실제 매입이 있었던 회계연도가 2개 이상이면 "정기적"으로 판단.
        소각비율은 그 기간 매입 주식수 합계 ÷ 최근 발행주식총수로 근사
        (한국은 "매입→소각" 2단계지만 여기선 매입 주식수 자체를 근사치로 사용, TODO 참고).

        타당성 검증(2026-08-22 추가): ① 0~100% 논리적 상한, ② 같은 기간 실제
        유통주식수 감소분과 비교해 근사치가 터무니없이 크지 않은지 교차검증.
        """
        gaap = self.company_facts(cik).get("facts", {}).get("us-gaap", {})
        acquired = _find_concept(gaap, BUYBACK_SHARES_ACQUIRED_TAGS)
        if acquired is None:
            return False, 0.0, False, ["buyback 태그 없음(결측)"]

        by_fy = _annual_sums(acquired)
        this_year = date.today().year
        recent = {fy: v for fy, v in by_fy.items() if fy >= this_year - lookback_years and v}
        is_regular = len(recent) >= 2

        if not is_regular:
            return False, 0.0, False, []

        issued = _find_concept(gaap, SHARES_ISSUED_TAGS)
        i = _latest_instant(issued) if issued is not None else None
        if not i or not i[0]:
            return is_regular, 0.0, False, ["발행주식 태그 없음 — 소각비율 계산 불가"]

        acquired_sum = sum(recent.values())
        ratio_a = round(acquired_sum / i[0] * 100, 3)
        notes: list[str] = []
        suspect = False

        # ① 논리적 상한
        if not (0 <= ratio_a <= 100):
            suspect = True
            notes.append(f"0~100% 범위 밖({ratio_a}%)")

        # ② 실제 유통주식수 변화와 교차검증 — 매입 규모만큼 유통주식이 실제로
        # 줄었어야 함(신주 발행 등으로 상쇄될 수도 있어 엄격한 일치는 요구하지
        # 않고, 근사치가 실제 감소분의 5배를 넘게 크면 이상치로 봄).
        outstanding = _find_concept(gaap, SHARES_OUTSTANDING_TAGS)
        if outstanding is not None:
            o_series = _instants(outstanding)
            recent_o = [(end, v) for end, v in o_series if int(end[:4]) >= this_year - lookback_years]
            if len(recent_o) >= 2:
                actual_decline = recent_o[0][1] - recent_o[-1][1]  # 기간 초 - 기간 말
                if actual_decline > 0 and acquired_sum > actual_decline * 5:
                    suspect = True
                    notes.append(
                        f"매입 근사치({acquired_sum:,.0f}주)가 실제 유통주식 감소분"
                        f"({actual_decline:,.0f}주)의 5배 초과"
                    )

        value = SUSPECT_SENTINEL_PCT if suspect else ratio_a
        return is_regular, value, suspect, notes


if __name__ == "__main__":
    client = SecEdgarClient()
    apple_cik = "0000320193"
    print("애플 자사주 보유비율:", client.treasury_ratio_pct(apple_cik))
    print("애플 정기매입 여부/소각비율:", client.buyback_regular_and_cancel_ratio(apple_cik))

    lrcx_cik = "0000707549"  # 2026-08-22 실키 테스트에서 태그 불일치 이상치가 발견된 종목
    print("LRCX 자사주 보유비율(이상치 검증 확인용):", client.treasury_ratio_pct(lrcx_cik))
