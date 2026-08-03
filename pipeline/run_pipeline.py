"""
파이프라인 진입점: 종목별 원시 데이터 수집 → scoring.py로 채점 → data/scores_quant.csv 저장.

두 가지 모드:
  --mock  : 외부 API 없이 합성 데이터로 대시보드 개발/검증용 CSV 생성
  (기본)   : KIS Developers + DART Open API로 실데이터 수집

코스피 전종목 티커 목록은 fetch_ticker_list.py로 미리 생성해둔
data/kospi_tickers.csv (ticker,name 2열)를 사용.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scoring import QualInput, QuantInput, score_stock  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_CSV = DATA_DIR / "scores_quant.csv"
TICKER_LIST_CSV = DATA_DIR / "kospi_tickers.csv"

FIELDNAMES = [
    "ticker", "name",
    "per", "pbr", "dividend_yield_pct", "quarterly_dividend",
    "dividend_increase_years", "buyback_cancel_regular", "cancel_ratio_pct",
    "treasury_ratio_pct", "dual_listed",
    "score_per", "score_pbr", "score_dual_listed", "score_dividend_yield",
    "score_quarterly_dividend", "score_dividend_increase_years",
    "score_buyback_regular", "score_cancel_ratio", "score_treasury_ratio",
    "quant_subtotal",
]

# mock 모드용 샘플 (실제 티커/이름이지만 재무 수치는 합성치)
MOCK_UNIVERSE = [
    ("005930", "삼성전자"),
    ("033780", "KT&G"),
    ("055550", "신한지주"),
    ("105560", "KB금융"),
    ("024110", "기업은행"),
    ("000810", "삼성화재"),
    ("051910", "LG화학"),
    ("035420", "NAVER"),
    ("015760", "한국전력"),
    ("009540", "HD한국조선해양"),
]


def generate_mock_quant(ticker: str, name: str) -> QuantInput:
    rng = random.Random(ticker)  # 티커 고정 시드 → 매번 같은 결과
    return QuantInput(
        per=round(rng.uniform(3, 20), 2),
        pbr=round(rng.uniform(0.2, 2.0), 2),
        dual_listed=rng.random() < 0.3,
        dividend_yield_pct=round(rng.uniform(0.5, 8.0), 2),
        quarterly_dividend=rng.random() < 0.4,
        dividend_increase_years=rng.choice([0, 0, 2, 3, 5, 7, 10, 12]),
        buyback_cancel_regular=rng.random() < 0.3,
        cancel_ratio_pct=round(rng.uniform(0, 3), 2),
        treasury_ratio_pct=round(rng.uniform(0, 8), 2),
    )


def load_ticker_list() -> list[tuple[str, str]]:
    if not TICKER_LIST_CSV.exists():
        raise FileNotFoundError(
            f"{TICKER_LIST_CSV} 가 없습니다. 코스피 전종목 티커 목록을 먼저 준비하세요 "
            "(KIS 앱키 발급 후 종목마스터 파일 파싱 또는 수동 준비)."
        )
    with TICKER_LIST_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [(row["ticker"], row["name"]) for row in reader]


def _latest_fiscal_year() -> int:
    """DART 사업보고서는 회계연도 종료 후 대개 3월 말까지 제출되므로,
    그 전에는 아직 최신 연도 데이터가 없을 수 있어 한 해 더 과거로 잡음."""
    today = date.today()
    return today.year - 1 if today.month >= 4 else today.year - 2


def _is_majority_owned_and_listed(holding: dict, listed_names: set[str]) -> bool:
    from fetch_dart import _parse_number
    from fetch_ticker_list import normalize_corp_name

    pct = _parse_number(holding.get("trmend_blce_qota_rt"))
    if pct is None or pct <= 50:  # "자회사"로 볼 수 있는 과반 지분만 인정
        return False
    return normalize_corp_name(holding.get("inv_prm", "")) in listed_names


def fetch_live_quant(ticker: str) -> QuantInput:
    from fetch_dart import DartClient, _parse_number
    from fetch_kis import KisClient
    from fetch_ticker_list import fetch_all_listed_names, normalize_corp_name

    kis = fetch_live_quant._kis_client
    dart = fetch_live_quant._dart_client
    corp_map = fetch_live_quant._corp_map
    listed_names = fetch_live_quant._listed_names
    if kis is None:
        kis = fetch_live_quant._kis_client = KisClient()
    if dart is None:
        dart = fetch_live_quant._dart_client = DartClient()
    if corp_map is None:
        corp_map = fetch_live_quant._corp_map = dart.corp_code_map()
    if listed_names is None:
        listed_names = fetch_live_quant._listed_names = {
            normalize_corp_name(n) for n in fetch_all_listed_names()
        }

    price = kis.price_metrics(ticker)
    corp_code = corp_map.get(ticker)

    if corp_code is None:
        # DART 미등록 종목(상장 직후 등) — 배당/자사주 관련은 계산 불가, PER/PBR만 반영
        return QuantInput(
            per=price["per"], pbr=price["pbr"], dual_listed=False,
            dividend_yield_pct=0.0, quarterly_dividend=False, dividend_increase_years=0,
            buyback_cancel_regular=False, cancel_ratio_pct=0.0, treasury_ratio_pct=0.0,
        )

    year = _latest_fiscal_year()
    dividend_yield = dart.dividend_yield_pct(corp_code, str(year)) or 0.0
    quarterly = dart.has_quarterly_dividend(corp_code, str(year))
    increase_years = dart.dividend_increase_years(corp_code, year)
    treasury_ratio = dart.treasury_ratio_pct(corp_code, str(year)) or 0.0

    acquisitions = dart.treasury_acquisitions(corp_code, f"{year - 1}0101", f"{year + 1}1231")
    buyback_regular = len(acquisitions) >= 2  # 최근 2년 내 취득결정 2건 이상 → "정기적"으로 간주

    # 소각 비율 근사치: 실제 "소각"까지 확인 가능한 필드가 없어, 최근 취득결정들의
    # 취득예정 주식수 합계 / 발행주식총수로 근사함 (매입=소각이 아닐 수 있어 과대추정 가능성 있음, TODO).
    cancel_ratio = 0.0
    if buyback_regular and acquisitions:
        stock_data = dart.stock_totals(corp_code, str(year))
        total_shares = next(
            (_parse_number(r.get("istc_totqy")) for r in stock_data.get("list", []) if r.get("se") == "합계"),
            None,
        )
        if total_shares:
            acquired = sum(_parse_number(a.get("aqpln_stk_ostk")) or 0 for a in acquisitions)
            cancel_ratio = round(acquired / total_shares * 100, 3)

    # 중복상장: 타법인출자현황에서 지분율 50% 초과(자회사)인 피투자회사명이
    # 코스피/코스닥 상장사명 집합에 있으면 True.
    holdings = dart.investee_holdings(corp_code, str(year))
    dual_listed = any(_is_majority_owned_and_listed(h, listed_names) for h in holdings)

    return QuantInput(
        per=price["per"],
        pbr=price["pbr"],
        dual_listed=dual_listed,
        dividend_yield_pct=dividend_yield,
        quarterly_dividend=quarterly,
        dividend_increase_years=increase_years,
        buyback_cancel_regular=buyback_regular,
        cancel_ratio_pct=cancel_ratio,
        treasury_ratio_pct=treasury_ratio,
    )


fetch_live_quant._kis_client = None
fetch_live_quant._dart_client = None
fetch_live_quant._corp_map = None
fetch_live_quant._listed_names = None


def _build_row(ticker: str, name: str, quant: QuantInput) -> dict:
    breakdown = score_stock(quant, QualInput())  # 정성 항목은 대시보드에서 채움
    return {
        "ticker": ticker,
        "name": name,
        "per": quant.per,
        "pbr": quant.pbr,
        "dividend_yield_pct": quant.dividend_yield_pct,
        "quarterly_dividend": quant.quarterly_dividend,
        "dividend_increase_years": quant.dividend_increase_years,
        "buyback_cancel_regular": quant.buyback_cancel_regular,
        "cancel_ratio_pct": quant.cancel_ratio_pct,
        "treasury_ratio_pct": quant.treasury_ratio_pct,
        "dual_listed": quant.dual_listed,
        "score_per": breakdown.items["per"],
        "score_pbr": breakdown.items["pbr"],
        "score_dual_listed": breakdown.items["dual_listed"],
        "score_dividend_yield": breakdown.items["dividend_yield"],
        "score_quarterly_dividend": breakdown.items["quarterly_dividend"],
        "score_dividend_increase_years": breakdown.items["dividend_increase_years"],
        "score_buyback_regular": breakdown.items["buyback_regular"],
        "score_cancel_ratio": breakdown.items["cancel_ratio"],
        "score_treasury_ratio": breakdown.items["treasury_ratio"],
        "quant_subtotal": breakdown.quant_subtotal,
    }


def _process_universe(
    universe: list[tuple[str, str]], mock: bool, label: str
) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """종목 목록 하나를 순회해서 (성공한 rows, 실패 목록)을 반환. 재시도 패스에도 재사용."""
    rows: list[dict] = []
    failures: list[tuple[str, str, str]] = []
    for i, (ticker, name) in enumerate(universe, 1):
        try:
            quant = generate_mock_quant(ticker, name) if mock else fetch_live_quant(ticker)
        except Exception as e:  # noqa: BLE001 — 종목 하나 실패로 전체 배치가 죽지 않게
            failures.append((ticker, name, f"{type(e).__name__}: {e}"))
            print(f"[{label} {i}/{len(universe)}] {ticker} {name} 실패: {type(e).__name__}: {e}", flush=True)
            continue
        if not mock:
            print(
                f"[{label} {i}/{len(universe)}] {ticker} {name} "
                f"PER={quant.per} PBR={quant.pbr} 배당수익률={quant.dividend_yield_pct}% "
                f"분기배당={quant.quarterly_dividend} 연속인상={quant.dividend_increase_years}년 "
                f"자사주매입={quant.buyback_cancel_regular} 자사주비율={quant.treasury_ratio_pct}%",
                flush=True,
            )
        rows.append(_build_row(ticker, name, quant))
    return rows, failures


def run(mock: bool, max_retry_passes: int = 3) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    universe = MOCK_UNIVERSE if mock else load_ticker_list()

    rows, failures = _process_universe(universe, mock, label="1차")

    # 실패한 종목만 모아서 재시도 — 대부분 일시적 오류(DNS/5xx/타임아웃)라 재시도하면 살아남.
    retry_pass = 1
    while failures and not mock and retry_pass <= max_retry_passes:
        print(f"--- 재시도 {retry_pass}차 시작: {len(failures)}건 ---", flush=True)
        retry_universe = [(t, n) for t, n, _ in failures]
        retried_rows, failures = _process_universe(retry_universe, mock, label=f"재시도{retry_pass}차")
        rows.extend(retried_rows)
        retry_pass += 1

    rows.sort(key=lambda r: r["quant_subtotal"], reverse=True)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)}개 종목 → {OUTPUT_CSV}")
    if failures:
        print(f"최종 실패 {len(failures)}건 (재시도 {retry_pass - 1}회 후에도 실패):")
        for ticker, name, err in failures:
            print(f"  {ticker} {name}: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="합성 데이터로 실행 (API 키 불필요)")
    args = parser.parse_args()
    run(mock=args.mock)
