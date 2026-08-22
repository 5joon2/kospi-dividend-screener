"""
yfinance로 미국 주식 시세/PER/PBR/배당지급이력 수집 (fetch_kis.py의 미국판).

yfinance는 API 키가 필요 없는 대신, `.info`가 야후 자체 계산값이라 PER/PBR이
종목별로 자주 결측되고(특히 최근 상장·특수 자본구조 종목), 대량 순회 시
일시적으로 429(rate limit)나 빈 응답을 겪을 수 있음 — http_retry의 재시도
감각으로 yfinance 예외를 감싸서 재시도한다.

배당수익률은 야후의 info['dividendYield'] 필드를 쓰지 않는다 — 버전에 따라
%/소수 단위가 뒤섞인 이력이 있어(yfinance GitHub 이슈로 여러 건 보고됨) 신뢰하지
않고, DART 배당수익률 계산과 같은 방식(최근 지급 배당금 합계 ÷ 현재가)으로
직접 계산한다.
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import yfinance as yf


def _to_float(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # NaN 방어 (v != v는 NaN일 때만 참)


class YFinanceClient:
    def __init__(self, max_retries: int = 3, retry_wait: float = 2.0):
        self.max_retries = max_retries
        self.retry_wait = retry_wait

    def _with_retry(self, fn):
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except Exception as e:  # yfinance 예외 타입이 버전마다 달라 광범위하게 잡음
                last_exc = e
                if attempt < self.max_retries:
                    time.sleep(self.retry_wait)
        raise last_exc

    def price_metrics(self, ticker: str) -> dict:
        info = self._with_retry(lambda: yf.Ticker(ticker).info)
        return {
            "ticker": ticker,
            "per": _to_float(info.get("trailingPE")),
            "pbr": _to_float(info.get("priceToBook")),
            "market_cap": _to_float(info.get("marketCap")),
            "current_price": _to_float(info.get("currentPrice") or info.get("regularMarketPrice")),
        }

    def dividend_history(self, ticker: str) -> pd.Series:
        """배당락일 기준 주당배당금 이력 (전체 기간)."""
        return self._with_retry(lambda: yf.Ticker(ticker).dividends)

    def dividend_yield_pct(self, dividends: pd.Series, current_price: float | None) -> float:
        """최근 12개월 지급된 배당금 합계 ÷ 현재가 × 100."""
        if dividends.empty or not current_price:
            return 0.0
        cutoff = pd.Timestamp.now(tz=dividends.index.tz) - pd.Timedelta(days=365)
        trailing_12m = dividends[dividends.index >= cutoff].sum()
        return round(float(trailing_12m) / current_price * 100, 2) if trailing_12m else 0.0

    def has_quarterly_dividend(self, dividends: pd.Series, lookback_years: int = 1) -> bool:
        """최근 1년간 지급 횟수가 3회 이상이면 분기배당(연 1~2회 배당 기업과 구분)."""
        if dividends.empty:
            return False
        cutoff = pd.Timestamp.now(tz=dividends.index.tz) - pd.Timedelta(days=365 * lookback_years)
        return int((dividends.index >= cutoff).sum()) >= 3

    def dividend_increase_years(self, dividends: pd.Series, max_years: int = 15) -> int:
        """연도별 배당금 합계를 비교해 연속 인상(동결 포함, 감소 시 중단) 연수 계산.

        DART 쪽(dividend_increase_years)은 회계연도 사업보고서 단위 비교지만,
        여기는 배당락일 기준 캘린더 연도 합계 비교라 기준이 완전히 같지는 않음.

        올해(진행 중이라 아직 완결 안 된 연도)는 비교 대상에서 제외 — 안 그러면
        아직 배당을 다 안 받은 올해 누적치가 작년 전체 합계보다 작게 나와서
        실제로는 인상 중인 종목도 "감소"로 오판된다(2026-08-22, 애플 실키 테스트 중 발견).
        """
        if dividends.empty:
            return 0
        by_year = dividends.groupby(dividends.index.year).sum()
        this_year = date.today().year
        by_year = by_year[by_year.index < this_year].tail(max_years + 1)

        years_desc = sorted(by_year.index, reverse=True)
        streak = 0
        for newer, older in zip(years_desc, years_desc[1:]):
            if by_year[newer] >= by_year[older]:
                streak += 1
            else:
                break
        return streak


if __name__ == "__main__":
    client = YFinanceClient()
    price = client.price_metrics("AAPL")
    print("가격 지표:", price)
    divs = client.dividend_history("AAPL")
    print("배당수익률(%):", client.dividend_yield_pct(divs, price["current_price"]))
    print("분기배당 여부:", client.has_quarterly_dividend(divs))
    print("배당 연속 인상 연수:", client.dividend_increase_years(divs))
