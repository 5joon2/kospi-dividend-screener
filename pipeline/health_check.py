"""
파이프라인이 의존하는 외부 서비스 4곳(KIS, DART, Supabase, KIND 티커 소스)에
가벼운 요청을 하나씩 날려서 정상 응답하는지 확인.

GitHub Actions에서 본 파이프라인(30~40분) 실행 전에 먼저 돌려서, 뭔가 죽어있으면
전체 실행을 낭비하지 않고 여기서 바로 실패시킨다. 실패하면 GitHub Actions가
레포 소유자에게 자동으로 이메일 알림을 보내준다(별도 웹훅 설정 불필요).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SAMSUNG_TICKER = "005930"
SAMSUNG_CORP_CODE = "00126380"


def check_kis() -> tuple[bool, str]:
    try:
        from fetch_kis import KisClient

        client = KisClient()
        result = client.price_metrics(SAMSUNG_TICKER)
        if result.get("per") is None:
            return False, "응답은 왔는데 per 필드가 비어있음"
        return True, f"OK (삼성전자 PER={result['per']})"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_dart() -> tuple[bool, str]:
    try:
        from fetch_dart import DartClient

        client = DartClient()
        yield_pct = client.dividend_yield_pct(SAMSUNG_CORP_CODE, "2025")
        return True, f"OK (삼성전자 배당수익률={yield_pct}%)"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_ticker_source() -> tuple[bool, str]:
    try:
        from fetch_ticker_list import fetch_kospi_tickers

        df = fetch_kospi_tickers()
        if len(df) < 700:  # 833개 안팎이 정상 — 너무 적으면 소스가 깨진 것
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
        client.table("qual_scores").select("ticker").limit(1).execute()
        return True, "OK"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    checks = [
        ("KIS", check_kis),
        ("DART", check_dart),
        ("KIND 티커 소스", check_ticker_source),
        ("Supabase", check_supabase),
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
