"""
코스피 전종목 티커 목록 수집.

data.krx.co.kr(MDC 통계 API)은 봇 차단이 강해서 접근이 막히지만,
KIND(kind.krx.co.kr) 상장법인목록 다운로드 페이지는 예전 방식의 단순 HTML 테이블이라
차단 없이 접근 가능 — 이걸로 대체.
"""

from __future__ import annotations

import csv
import re
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

KIND_URL_TMPL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&marketType={market}"

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_CSV = DATA_DIR / "kospi_tickers.csv"


def _fetch_market_list(market_type: str) -> pd.DataFrame:
    resp = requests.get(KIND_URL_TMPL.format(market=market_type), timeout=15)
    resp.encoding = "euc-kr"
    tables = pd.read_html(StringIO(resp.text), flavor="lxml")
    df = tables[0][["회사명", "종목코드", "업종"]].rename(
        columns={"회사명": "name", "종목코드": "ticker", "업종": "industry"}
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    # 소스 데이터에 동일 종목이 "지역" 컬럼만 다른 값으로 중복 등록된 경우가 있어(15건 확인,
    # 2026-08-03 — 지역 표기가 바뀌는 과도기라 신/구 행정구역명으로 각각 한 줄씩 잡힌 것으로 추정,
    # 나머지 컬럼은 완전히 동일) 종목코드 기준으로 중복 제거.
    return df.drop_duplicates(subset="ticker", keep="first")


def fetch_kospi_tickers() -> pd.DataFrame:
    df = _fetch_market_list("stockMkt")
    return df.sort_values("ticker").reset_index(drop=True)


def fetch_all_listed_names() -> set[str]:
    """중복상장(계열사 상장) 판정용 — 코스피+코스닥 전체 상장사명 집합.

    회사명은 원문 그대로 반환하고, 정규화(㈜/공백 제거 등)는 normalize_corp_name으로 맞춰서 비교.
    """
    kospi = _fetch_market_list("stockMkt")
    kosdaq = _fetch_market_list("kosdaqMkt")
    return set(kospi["name"]) | set(kosdaq["name"])


def normalize_corp_name(name: str) -> str:
    """"㈜하이트진로", "하이트진로(주)", "하이트진로 " 등 표기 차이를 없애고 비교하기 위함."""
    return re.sub(r"[㈜()주식회사\s]", "", name or "")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = fetch_kospi_tickers()
    df[["ticker", "name", "industry"]].to_csv(OUTPUT_CSV, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"{len(df)}개 코스피 종목 → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
