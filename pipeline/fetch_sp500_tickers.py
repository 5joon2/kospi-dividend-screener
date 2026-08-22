"""
S&P 500 전종목 티커 목록 수집 (fetch_ticker_list.py의 미국판).

위키피디아 "List of S&P 500 companies" 표를 그대로 긁어온다 — 이 표는 Symbol/Security/
GICS Sector/CIK를 전부 포함하고 있어서, SEC EDGAR용 CIK까지 한 번에 확보 가능
(fetch_sec_edgar.py에서 티커→CIK 매핑을 따로 조회할 필요가 없어짐).

주의: 이 표의 Symbol은 복수의결권 종목에서 "BRK.B"처럼 점(.)을 쓰는데, yfinance는
"BRK-B"처럼 하이픈(-)을 기대한다 — 그대로 넘기면 조용히 404/빈 데이터로 돌아옴.
그래서 원본 심볼(공시·표시용)과 yfinance용 심볼을 분리해서 저장한다.
"""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_CSV = DATA_DIR / "sp500_tickers.csv"


def to_yfinance_symbol(symbol: str) -> str:
    return symbol.replace(".", "-")


def fetch_sp500_tickers() -> pd.DataFrame:
    resp = requests.get(WIKI_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text), flavor="lxml")
    df = tables[0][["Symbol", "Security", "GICS Sector", "CIK"]].rename(
        columns={"Symbol": "ticker", "Security": "name", "GICS Sector": "gics_sector", "CIK": "cik"}
    )
    df["yfinance_ticker"] = df["ticker"].apply(to_yfinance_symbol)
    # CIK는 SEC 쪽 규격대로 10자리 0-padding (예: 320193 → 0000320193)
    df["cik"] = df["cik"].astype(str).str.zfill(10)
    return df.sort_values("ticker").reset_index(drop=True)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = fetch_sp500_tickers()
    df[["ticker", "yfinance_ticker", "name", "gics_sector", "cik"]].to_csv(
        OUTPUT_CSV, index=False, quoting=csv.QUOTE_MINIMAL
    )
    print(f"{len(df)}개 S&P 500 종목 → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
