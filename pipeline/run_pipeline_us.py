"""
미국(S&P 500) 파이프라인 진입점 (run_pipeline.py의 미국판):
종목별 원시 데이터 수집(yfinance + SEC EDGAR) → scoring.py로 채점 → data/us_scores_quant.csv 저장.

KOSPI 파이프라인과 구조는 동일(mock 모드, 실패 종목 재시도, 규모별 히스토리 누적)하되
데이터 소스가 다르고 일부 항목은 타협/근사가 들어간다 — 각 타협 지점은 아래
fetch_live_quant_us()의 주석과 README "미국판 타협 사항" 절 참고.
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
from us_exclusions import EXCLUDED_GICS_SECTORS  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_CSV = DATA_DIR / "us_scores_quant.csv"
TICKER_LIST_CSV = DATA_DIR / "sp500_tickers.csv"
HISTORY_CSV = DATA_DIR / "us_score_history.csv"
HISTORY_TOP_N = 20

FIELDNAMES = [
    "ticker", "name",
    "per", "pbr", "dividend_yield_pct", "quarterly_dividend",
    "dividend_increase_years", "buyback_cancel_regular", "cancel_ratio_pct",
    "treasury_ratio_pct", "dual_listed",
    "score_per", "score_pbr", "score_dual_listed", "score_dividend_yield",
    "score_quarterly_dividend", "score_dividend_increase_years",
    "score_buyback_regular", "score_cancel_ratio", "score_treasury_ratio",
    "quant_subtotal",
    # 채점과 무관한 참고 정보 (필터/탐색용)
    "gics_sector", "market_cap", "recent_dividend_record_date", "recent_dividend_pay_date",
]

MOCK_UNIVERSE = [
    ("AAPL", "AAPL", "Apple Inc.", "Information Technology", "0000320193"),
    ("MSFT", "MSFT", "Microsoft Corporation", "Information Technology", "0000789019"),
    ("JNJ", "JNJ", "Johnson & Johnson", "Health Care", "0000200406"),
    ("PG", "PG", "Procter & Gamble", "Consumer Staples", "0000080424"),
    ("KO", "KO", "Coca-Cola Company", "Consumer Staples", "0000021344"),
    ("XOM", "XOM", "Exxon Mobil Corporation", "Energy", "0000034088"),
    ("JPM", "JPM", "JPMorgan Chase & Co.", "Financials", "0000019617"),
    ("V", "V", "Visa Inc.", "Financials", "0001403161"),
    ("WMT", "WMT", "Walmart Inc.", "Consumer Staples", "0000104169"),
    ("HD", "HD", "Home Depot Inc.", "Consumer Discretionary", "0000354950"),
]


def generate_mock_quant(ticker: str) -> QuantInput:
    rng = random.Random(ticker)
    return QuantInput(
        per=round(rng.uniform(5, 30), 2),
        pbr=round(rng.uniform(0.5, 10.0), 2),
        dual_listed=False,  # 미국판은 이 항목 자체를 평가하지 않음 (아래 타협 사항 참고)
        dividend_yield_pct=round(rng.uniform(0.0, 5.0), 2),
        quarterly_dividend=rng.random() < 0.6,
        dividend_increase_years=rng.choice([0, 0, 2, 3, 5, 7, 10, 12]),
        buyback_cancel_regular=rng.random() < 0.5,
        cancel_ratio_pct=round(rng.uniform(0, 3), 2),
        treasury_ratio_pct=round(rng.uniform(0, 8), 2),
    )


def generate_mock_extra(gics_sector: str) -> dict:
    rng = random.Random(gics_sector)
    return {
        "gics_sector": gics_sector,
        "market_cap": round(rng.uniform(1e10, 3e12), 0),
        "recent_dividend_record_date": "",
        "recent_dividend_pay_date": "",
    }


def load_ticker_list() -> list[tuple[str, str, str, str, str]]:
    """(ticker, yfinance_ticker, name, gics_sector, cik) 목록. REIT 등 제외 섹터는 걸러냄."""
    if not TICKER_LIST_CSV.exists():
        raise FileNotFoundError(
            f"{TICKER_LIST_CSV} 가 없습니다. 먼저 `uv run pipeline/fetch_sp500_tickers.py`를 실행하세요."
        )
    with TICKER_LIST_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            (row["ticker"], row["yfinance_ticker"], row["name"], row["gics_sector"], row["cik"])
            for row in reader
            if row["gics_sector"] not in EXCLUDED_GICS_SECTORS
        ]


def fetch_live_quant(yfinance_ticker: str, cik: str, gics_sector: str = "") -> tuple[QuantInput, dict]:
    """(채점용 QuantInput, 채점과 무관한 참고정보 dict).

    KOSPI판(fetch_dart.py+fetch_kis.py 조합)과 달리 여기는 두 소스(yfinance/SEC EDGAR)를
    섞어 쓴다. 데이터 소스별 타협 사항은 각 fetch 모듈의 모듈 docstring 참고.
    """
    from fetch_sec_edgar import SecEdgarClient
    from fetch_yfinance import YFinanceClient

    yf_client = fetch_live_quant._yf_client
    sec_client = fetch_live_quant._sec_client
    if yf_client is None:
        yf_client = fetch_live_quant._yf_client = YFinanceClient()
    if sec_client is None:
        sec_client = fetch_live_quant._sec_client = SecEdgarClient()

    price = yf_client.price_metrics(yfinance_ticker)
    dividends = yf_client.dividend_history(yfinance_ticker)
    current_price = price.get("current_price")

    dividend_yield = yf_client.dividend_yield_pct(dividends, current_price)
    quarterly = yf_client.has_quarterly_dividend(dividends)
    increase_years = yf_client.dividend_increase_years(dividends)

    # SEC EDGAR는 CIK가 없으면(위키 표 파싱 실패 등) 자사주 관련 항목을 평가할 수 없음 —
    # 결측을 0점으로 깔되, PER/PBR/배당 관련 항목은 그대로 반영.
    treasury_ratio = 0.0
    buyback_regular = False
    cancel_ratio = 0.0
    if cik:
        treasury_ratio = sec_client.treasury_ratio_pct(cik) or 0.0
        buyback_regular, cancel_ratio = sec_client.buyback_regular_and_cancel_ratio(cik)

    extra = {
        "gics_sector": gics_sector,
        "market_cap": price.get("market_cap") or 0,
        # yfinance dividends의 인덱스는 배당락일(ex-dividend date)이지, KIS 배당일정처럼
        # "배당기준일(record date)"과 "배당지급일(pay date)"을 구분해서 주지 않음 —
        # 그대로 record_date 자리에만 넣고 pay_date는 비워둠 (TODO: 필요하면 별도 소스로 보강).
        "recent_dividend_record_date": dividends.index[-1].date().isoformat() if not dividends.empty else "",
        "recent_dividend_pay_date": "",
    }

    return QuantInput(
        per=price["per"],
        pbr=price["pbr"],
        dual_listed=False,  # 미국판은 이 항목을 평가하지 않음 — score_dual_listed()가 만점(5점) 처리
        dividend_yield_pct=dividend_yield,
        quarterly_dividend=quarterly,
        dividend_increase_years=increase_years,
        buyback_cancel_regular=buyback_regular,
        cancel_ratio_pct=cancel_ratio,
        treasury_ratio_pct=treasury_ratio,
    ), extra


fetch_live_quant._yf_client = None
fetch_live_quant._sec_client = None


def _build_row(ticker: str, name: str, quant: QuantInput, extra: dict) -> dict:
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
        "gics_sector": extra.get("gics_sector", ""),
        "market_cap": extra.get("market_cap") or 0,
        "recent_dividend_record_date": extra.get("recent_dividend_record_date", ""),
        "recent_dividend_pay_date": extra.get("recent_dividend_pay_date", ""),
    }


def _process_universe(
    universe: list[tuple[str, str, str, str, str]], mock: bool, label: str
) -> tuple[list[dict], list[tuple[str, str, str, str, str, str]]]:
    """종목 목록 하나를 순회해서 (성공한 rows, 실패 목록)을 반환. 재시도 패스에도 재사용."""
    rows: list[dict] = []
    failures: list[tuple[str, str, str, str, str, str]] = []
    for i, (ticker, yf_ticker, name, gics_sector, cik) in enumerate(universe, 1):
        try:
            if mock:
                quant = generate_mock_quant(ticker)
                extra = generate_mock_extra(gics_sector)
            else:
                quant, extra = fetch_live_quant(yf_ticker, cik, gics_sector)
        except Exception as e:  # noqa: BLE001 — 종목 하나 실패로 전체 배치가 죽지 않게
            failures.append((ticker, yf_ticker, name, gics_sector, cik, f"{type(e).__name__}: {e}"))
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
        rows.append(_build_row(ticker, name, quant, extra))
    return rows, failures


def _compute_size_group(rows: list[dict]) -> dict[str, str]:
    """S&P 500 내 시가총액 순위 기준 대형/중형/소형(1~100/101~300/301~위) 분류.

    KOSPI판(KRX 대형/중형/소형주 지수 기준)과 달리 이건 "S&P 500 안에서의 상대 순위"일
    뿐 절대적인 미국 시장 전체의 대/중/소형주 구분은 아님 — 대시보드 문구에서 명시.
    """
    ranked = sorted(rows, key=lambda r: r.get("market_cap") or 0, reverse=True)
    groups: dict[str, str] = {}
    for i, r in enumerate(ranked, 1):
        if i <= 100:
            groups[r["ticker"]] = "대형주"
        elif i <= 300:
            groups[r["ticker"]] = "중형주"
        else:
            groups[r["ticker"]] = "소형주"
    return groups


def _append_history(rows: list[dict]) -> None:
    today = date.today().isoformat()
    history_fields = ["date", "size_group", "ticker", "name", "rank", "quant_subtotal"]

    existing_rows: list[dict] = []
    if HISTORY_CSV.exists():
        with HISTORY_CSV.open(encoding="utf-8") as f:
            existing_rows = [r for r in csv.DictReader(f) if r.get("date") != today]

    size_group_by_ticker = _compute_size_group(rows)
    today_rows = []
    for group in ("대형주", "중형주", "소형주"):
        group_rows = sorted(
            (r for r in rows if size_group_by_ticker.get(r["ticker"]) == group),
            key=lambda r: r["quant_subtotal"], reverse=True,
        )
        for i, r in enumerate(group_rows[:HISTORY_TOP_N], 1):
            today_rows.append({
                "date": today, "size_group": group, "ticker": r["ticker"],
                "name": r["name"], "rank": i, "quant_subtotal": r["quant_subtotal"],
            })

    with HISTORY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=history_fields)
        writer.writeheader()
        writer.writerows(existing_rows + today_rows)

    print(f"히스토리 기록: {today} 대형/중형/소형주 각 top{HISTORY_TOP_N} (총 {len(today_rows)}건) → {HISTORY_CSV}")


def run(mock: bool, max_retry_passes: int = 3) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    universe = MOCK_UNIVERSE if mock else load_ticker_list()

    rows, failures = _process_universe(universe, mock, label="1차")

    retry_pass = 1
    while failures and not mock and retry_pass <= max_retry_passes:
        print(f"--- 재시도 {retry_pass}차 시작: {len(failures)}건 ---", flush=True)
        retry_universe = [(t, yf_t, n, g, c) for t, yf_t, n, g, c, _ in failures]
        retried_rows, failures = _process_universe(retry_universe, mock, label=f"재시도{retry_pass}차")
        rows.extend(retried_rows)
        retry_pass += 1

    rows.sort(key=lambda r: r["quant_subtotal"], reverse=True)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    if not mock:
        _append_history(rows)

    print(f"{len(rows)}개 종목 → {OUTPUT_CSV}")
    if failures:
        print(f"최종 실패 {len(failures)}건 (재시도 {retry_pass - 1}회 후에도 실패):")
        for ticker, _yf_ticker, name, _gics_sector, _cik, err in failures:
            print(f"  {ticker} {name}: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="합성 데이터로 실행 (외부 호출 불필요)")
    args = parser.parse_args()
    run(mock=args.mock)
