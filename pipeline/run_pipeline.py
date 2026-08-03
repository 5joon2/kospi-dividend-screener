"""
파이프라인 진입점: 종목별 원시 데이터 수집 → scoring.py로 채점 → data/scores_quant.csv 저장.

두 가지 모드:
  --mock  : 외부 API 없이 합성 데이터로 대시보드 개발/검증용 CSV 생성
  (기본)   : KIS Developers + DART Open API로 실데이터 수집 (앱키 발급 후 사용)

미해결 항목(TODO): 코스피 "전종목" 티커 목록을 안정적으로 얻는 방법.
KIS REST API에는 전종목 목록 엔드포인트가 없어 종목마스터 파일 파싱이 필요하고,
DART corpCode.xml은 코스피/코스닥 구분 없이 상장사 전체가 섞여 있음.
1차로는 data/kospi_tickers.csv (ticker,name 2열)를 수동/별도 스크립트로 준비해서 사용.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
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


def fetch_live_quant(ticker: str) -> QuantInput:
    from fetch_dart import DartClient
    from fetch_kis import KisClient

    kis = fetch_live_quant._kis_client
    dart = fetch_live_quant._dart_client
    if kis is None:
        kis = fetch_live_quant._kis_client = KisClient()
    if dart is None:
        dart = fetch_live_quant._dart_client = DartClient()

    price = kis.price_metrics(ticker)
    # TODO: dividend_info / financial_statements / treasury_stock_disclosures 응답을
    # 실제 키 발급 후 확인하면서 아래 필드 매핑을 채워야 함. 지금은 PER/PBR만 실데이터.
    return QuantInput(
        per=price["per"],
        pbr=price["pbr"],
        dual_listed=False,  # TODO: DART 계열사 상장 여부로 채우기
        dividend_yield_pct=0.0,  # TODO: dart.dividend_info()로 채우기
        quarterly_dividend=False,  # TODO
        dividend_increase_years=0,  # TODO
        buyback_cancel_regular=False,  # TODO
        cancel_ratio_pct=0.0,  # TODO
        treasury_ratio_pct=0.0,  # TODO
    )


fetch_live_quant._kis_client = None
fetch_live_quant._dart_client = None


def run(mock: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    universe = MOCK_UNIVERSE if mock else load_ticker_list()

    rows = []
    for ticker, name in universe:
        quant = generate_mock_quant(ticker, name) if mock else fetch_live_quant(ticker)
        breakdown = score_stock(quant, QualInput())  # 정성 항목은 대시보드에서 채움
        rows.append({
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
        })

    rows.sort(key=lambda r: r["quant_subtotal"], reverse=True)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)}개 종목 → {OUTPUT_CSV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="합성 데이터로 실행 (API 키 불필요)")
    args = parser.parse_args()
    run(mock=args.mock)
