"""
책 5장 "종목 선정 기준"의 삼성전자 점수표를 그대로 코드화한 배점 로직.

정량 항목(9개): PER, PBR, 중복상장 여부, 배당수익률, 분기배당 실시 여부,
배당 연속 인상 연수, 정기적 자사주매입·소각 여부, 소각 비율, 자사주 보유 비율
→ pipeline이 수집한 데이터로 자동 계산.

정성 항목(4개): 이익 지속가능성, 미래 성장 잠재력, 경영진 평가, 세계적 브랜드 보유 여부
→ 기본값은 미평가(0점)이며, 대시보드에서 top-30에 대해 사람이 입력하면 갱신됨.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------- 정량 항목 ----------

def score_per(per: float | None) -> int:
    if per is None or per <= 0:
        return 0
    if per < 5:
        return 20
    if per < 8:
        return 15
    if per < 10:
        return 10
    return 5


def score_pbr(pbr: float | None) -> int:
    if pbr is None or pbr <= 0:
        return 0
    if pbr < 0.3:
        return 5
    if pbr < 0.6:
        return 4
    if pbr < 1.0:
        return 3
    return 0


def score_dual_listed(dual_listed: bool) -> int:
    """자회사·손자회사 중복상장 여부. 단독상장이 만점."""
    return 0 if dual_listed else 5


def score_dividend_yield(yield_pct: float) -> int:
    if yield_pct > 7:
        return 10
    if yield_pct > 5:
        return 7
    if yield_pct > 3:
        return 5
    return 2


def score_quarterly_dividend(is_quarterly: bool) -> int:
    return 5 if is_quarterly else 0


def score_dividend_increase_years(years: int) -> int:
    if years >= 10:
        return 5
    if years >= 5:
        return 4
    if years >= 3:
        return 3
    return 0


def score_buyback_regular(is_regular: bool) -> int:
    return 7 if is_regular else 0


def score_cancel_ratio(is_regular: bool, cancel_ratio_pct: float) -> int:
    """정기적 소각을 하지 않으면 해당없음(0점). 하는 경우에만 비율로 채점."""
    if not is_regular:
        return 0
    if cancel_ratio_pct > 2:
        return 8
    if cancel_ratio_pct > 1.5:
        return 5
    if cancel_ratio_pct > 0.5:
        return 3
    return 0


def score_treasury_ratio(treasury_ratio_pct: float) -> int:
    if treasury_ratio_pct <= 0:
        return 5
    if treasury_ratio_pct < 2:
        return 4
    if treasury_ratio_pct < 5:
        return 2
    return 0


# ---------- 정성 항목 (사람 입력, 기본값 0) ----------

GROWTH_POTENTIAL_SCORES = {"매우높다": 10, "높다": 7, "보통": 5, "낮다": 3}
MANAGEMENT_SCORES = {"우수한경영자": 10, "전문경영자": 5, "저조한실적오너경영": 0}


def score_profit_sustainability(sustainable: bool | None) -> int:
    return 5 if sustainable else 0


def score_growth_potential(level: str | None) -> int:
    return GROWTH_POTENTIAL_SCORES.get(level, 0)


def score_management(level: str | None) -> int:
    return MANAGEMENT_SCORES.get(level, 0)


def score_global_brand(has_brand: bool | None) -> int:
    return 5 if has_brand else 0


@dataclass
class QuantInput:
    per: float | None
    pbr: float | None
    dual_listed: bool
    dividend_yield_pct: float
    quarterly_dividend: bool
    dividend_increase_years: int
    buyback_cancel_regular: bool
    cancel_ratio_pct: float
    treasury_ratio_pct: float


@dataclass
class QualInput:
    profit_sustainable: bool | None = None
    growth_potential: str | None = None
    management: str | None = None
    global_brand: bool | None = None


@dataclass
class ScoreBreakdown:
    items: dict[str, int] = field(default_factory=dict)

    @property
    def quant_subtotal(self) -> int:
        quant_keys = (
            "per", "pbr", "dual_listed", "dividend_yield", "quarterly_dividend",
            "dividend_increase_years", "buyback_regular", "cancel_ratio", "treasury_ratio",
        )
        return sum(self.items[k] for k in quant_keys)

    @property
    def qual_subtotal(self) -> int:
        qual_keys = ("profit_sustainability", "growth_potential", "management", "global_brand")
        return sum(self.items[k] for k in qual_keys)

    @property
    def total(self) -> int:
        return self.quant_subtotal + self.qual_subtotal


def score_quant(q: QuantInput) -> dict[str, int]:
    return {
        "per": score_per(q.per),
        "pbr": score_pbr(q.pbr),
        "dual_listed": score_dual_listed(q.dual_listed),
        "dividend_yield": score_dividend_yield(q.dividend_yield_pct),
        "quarterly_dividend": score_quarterly_dividend(q.quarterly_dividend),
        "dividend_increase_years": score_dividend_increase_years(q.dividend_increase_years),
        "buyback_regular": score_buyback_regular(q.buyback_cancel_regular),
        "cancel_ratio": score_cancel_ratio(q.buyback_cancel_regular, q.cancel_ratio_pct),
        "treasury_ratio": score_treasury_ratio(q.treasury_ratio_pct),
    }


def score_qual(q: QualInput) -> dict[str, int]:
    return {
        "profit_sustainability": score_profit_sustainability(q.profit_sustainable),
        "growth_potential": score_growth_potential(q.growth_potential),
        "management": score_management(q.management),
        "global_brand": score_global_brand(q.global_brand),
    }


def score_stock(quant: QuantInput, qual: QualInput | None = None) -> ScoreBreakdown:
    items = score_quant(quant)
    items.update(score_qual(qual or QualInput()))
    return ScoreBreakdown(items=items)


if __name__ == "__main__":
    # 책 예시(삼성전자)와 같은 구조로 값을 넣어 배점 규칙이 표대로 동작하는지 눈으로 확인.
    # 실제 수치는 책이 발행된 시점 기준이 아니라 예시용 추정치이므로 책의 "37점"과
    # 정확히 일치하지 않을 수 있음 — 여기서 검증하는 건 총점이 아니라 구간별 배점 규칙.
    sample_quant = QuantInput(
        per=13.0,
        pbr=1.1,
        dual_listed=True,
        dividend_yield_pct=2.1,
        quarterly_dividend=True,
        dividend_increase_years=0,
        buyback_cancel_regular=False,
        cancel_ratio_pct=0.0,
        treasury_ratio_pct=0.0,
    )
    sample_qual = QualInput(
        profit_sustainable=True,
        growth_potential="매우높다",
        management="전문경영자",
        global_brand=True,
    )
    breakdown = score_stock(sample_quant, sample_qual)
    for k, v in breakdown.items.items():
        print(f"{k:28s} {v:3d}")
    print("-" * 32)
    print(f"{'quant_subtotal':28s} {breakdown.quant_subtotal:3d}")
    print(f"{'qual_subtotal':28s} {breakdown.qual_subtotal:3d}")
    print(f"{'total':28s} {breakdown.total:3d}")
