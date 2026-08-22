"""
미국판 파이프라인이 의존하는 외부 서비스(yfinance, SEC EDGAR, 위키피디아 티커 소스,
Supabase us_qual_scores)에 가벼운 요청을 하나씩 날려서 정상 응답하는지 확인
(health_check.py의 미국판 — 구조 동일).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

AAPL_TICKER = "AAPL"
AAPL_CIK = "0000320193"


def check_yfinance() -> tuple[bool, str]:
    try:
        from fetch_yfinance import YFinanceClient

        client = YFinanceClient()
        result = client.price_metrics(AAPL_TICKER)
        if result.get("current_price") is None:
            return False, "응답은 왔는데 current_price 필드가 비어있음"
        return True, f"OK (애플 현재가={result['current_price']})"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_sec_edgar() -> tuple[bool, str]:
    try:
        from fetch_sec_edgar import SecEdgarClient

        client = SecEdgarClient()
        ratio = client.treasury_ratio_pct(AAPL_CIK)
        return True, f"OK (애플 자사주 보유비율={ratio}%)"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_ticker_source() -> tuple[bool, str]:
    try:
        from fetch_sp500_tickers import fetch_sp500_tickers

        df = fetch_sp500_tickers()
        if len(df) < 480:  # 503개 안팎이 정상 — 너무 적으면 소스(위키 표 구조)가 깨진 것
            return False, f"종목 수가 비정상적으로 적음 ({len(df)}개)"
        return True, f"OK ({len(df)}개 종목)"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_supabase() -> tuple[bool, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        return False, "SUPABASE_URL / SUPABASE_ANON_KEY 미설정"
    try:
        from supabase import create_client

        client = create_client(url, key)
        client.table("us_qual_scores").select("ticker").limit(1).execute()
        return True, "OK"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    checks = [
        ("yfinance", check_yfinance),
        ("SEC EDGAR", check_sec_edgar),
        ("S&P 500 티커 소스(위키피디아)", check_ticker_source),
        ("Supabase(us_qual_scores)", check_supabase),
    ]

    all_ok = True
    for name, fn in checks:
        ok, message = fn()
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {message}")
        all_ok = all_ok and ok

    if not all_ok:
        print("\n헬스체크 실패 — 파이프라인을 실행하지 않습니다.")
        return 1

    print("\n모든 서비스 정상.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
