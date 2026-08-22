"""
투자 대상에서 의도적으로 제외하는 종목 목록 (exclusions.py의 미국판).

KOSPI 쪽은 REIT 여부를 수동으로 확인한 티커 목록으로 관리하지만(exclusions.py 참고),
S&P 500은 위키피디아 종목표에 GICS Sector가 이미 붙어 있어서 "Real Estate" 섹터를
자동으로 걸러낼 수 있다 — 회계·공시 체계가 일반 기업과 달라 정량 점수가 대부분
0으로 깔리는 문제는 KOSPI와 동일한 이유.

TODO: GICS Sector로 안 걸러지는 예외(BDC 등 리츠와 유사한 회계 구조를 쓰는 비-부동산
섹터 종목)는 자동 탐지가 안 됨 — 수작업 확인 필요.
"""

from __future__ import annotations

EXCLUDED_GICS_SECTORS: set[str] = {
    "Real Estate",
}
