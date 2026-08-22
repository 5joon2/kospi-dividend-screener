"""정책 안내 (미국판) — 이 대시보드가 무엇을 왜 제외/보류하는지 투명하게 공개하는 페이지."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "pipeline"))
from us_exclusions import EXCLUDED_GICS_SECTORS  # noqa: E402

st.set_page_config(page_title="정책 안내 (US)", layout="wide")
st.title("정책 안내 (S&P 500)")
st.caption("이 대시보드가 특정 종목을 왜 제외하거나 보류하는지 여기서 투명하게 공개합니다.")

st.header("① REITs는 투자 대상에서 제외 (GICS Sector 기준)")
st.markdown(
    f"""
이 대시보드는 **일반 상장기업의 저평가 우량 배당주**를 찾는 걸 목표로 합니다.
REITs(부동산투자신탁)는 KOSPI판과 같은 이유로 채점 대상에서 제외했습니다 —
부동산투자신탁 관련 법령을 적용받아 일반 기업과 회계·공시 체계가 다르고,
PER/PBR·자사주 관련 지표가 대부분 결측되거나 왜곡되어 정당한 평가를 받기 어렵습니다.

KOSPI판은 종목명·업종코드를 수동으로 확인한 목록으로 관리하지만, 미국판은
위키피디아 S&P 500 종목표의 **GICS Sector 컬럼이 이미 표준화되어 있어**
아래 섹터에 해당하면 자동으로 제외합니다.
"""
)
st.subheader("제외 GICS 섹터")
st.dataframe(
    [{"GICS Sector": s} for s in sorted(EXCLUDED_GICS_SECTORS)],
    width="stretch",
    hide_index=True,
)
st.caption(
    "⚠️ TODO: GICS Sector만으로는 안 걸러지는 예외(다른 섹터로 분류된 BDC 등 "
    "리츠와 유사한 회계 구조를 쓰는 종목)는 자동 탐지가 안 됩니다 — 발견되는 대로 "
    "수동으로 확인해서 이 목록에 추가할 예정입니다."
)

st.divider()

st.header("② 알려진 이슈 로그")
st.markdown(
    "아직 KOSPI판의 '배당수익률 이상치' 같은 구체적인 데이터 이슈가 발견된 적은 없습니다 "
    "— 미국판은 이제 막 가동을 시작해서 실데이터 검수 이력이 짧습니다. 이상치나 버그가 "
    "발견되면 이 페이지에 기록해나갈 예정입니다. 지금 알려진 구조적 타협 사항은 "
    "'채점기준표' 페이지 하단의 '미국판 타협 사항' 표를 참고하세요."
)
