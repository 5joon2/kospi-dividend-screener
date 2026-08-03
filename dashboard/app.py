"""코스피 저평가 우량 배당주 스코어링 대시보드 — 메인 페이지."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).parent))

from scoring import (  # noqa: E402
    score_global_brand,
    score_growth_potential,
    score_management,
    score_profit_sustainability,
)

import db  # noqa: E402

DATA_CSV = Path(__file__).parent.parent / "data" / "scores_quant.csv"
TOP_N_FOR_QUAL = 30

QUANT_ITEMS = {
    "score_per": "PER",
    "score_pbr": "PBR",
    "score_dual_listed": "중복상장 여부",
    "score_dividend_yield": "배당수익률",
    "score_quarterly_dividend": "분기배당 실시",
    "score_dividend_increase_years": "배당 연속 인상 연수",
    "score_buyback_regular": "정기 자사주매입·소각",
    "score_cancel_ratio": "소각 비율",
    "score_treasury_ratio": "자사주 보유 비율",
}
QUAL_ITEMS = {
    "score_profit_sustainability": "이익 지속가능성",
    "score_growth_potential": "미래 성장 잠재력",
    "score_management": "경영진 평가",
    "score_global_brand": "세계적 브랜드 보유",
}

st.set_page_config(page_title="코스피 저평가 우량 배당주", layout="wide")


@st.cache_data
def load_quant_scores() -> pd.DataFrame:
    if not DATA_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(DATA_CSV)


def compute_qual_scores(tickers: list[str]) -> pd.DataFrame:
    raw = db.load_all_qual_scores()
    rows = []
    for ticker in tickers:
        entry = raw.get(ticker, {})
        rows.append({
            "ticker": ticker,
            "score_profit_sustainability": score_profit_sustainability(entry.get("profit_sustainable")),
            "score_growth_potential": score_growth_potential(entry.get("growth_potential")),
            "score_management": score_management(entry.get("management")),
            "score_global_brand": score_global_brand(entry.get("global_brand")),
        })
    return pd.DataFrame(rows)


def sidebar_weights() -> dict[str, float]:
    st.sidebar.header("가중치 조정")
    st.sidebar.caption("항목별 배점에 곱해지는 가중치 (기본 1.0 = 책 원안 그대로)")

    weights: dict[str, float] = {}
    with st.sidebar.expander("저평가 / 이익창출력", expanded=True):
        for key, label in list(QUANT_ITEMS.items())[:3]:
            weights[key] = st.slider(label, 0.0, 3.0, 1.0, 0.1, key=f"w_{key}")
    with st.sidebar.expander("주주환원 의지", expanded=False):
        for key, label in list(QUANT_ITEMS.items())[3:]:
            weights[key] = st.slider(label, 0.0, 3.0, 1.0, 0.1, key=f"w_{key}")
    with st.sidebar.expander("성장 잠재력 / 경쟁력 (정성)", expanded=False):
        for key, label in QUAL_ITEMS.items():
            weights[key] = st.slider(label, 0.0, 3.0, 1.0, 0.1, key=f"w_{key}")

    st.sidebar.divider()
    st.sidebar.subheader("가중치 프리셋")
    nickname = st.sidebar.text_input("닉네임", key="preset_nickname")
    col1, col2 = st.sidebar.columns(2)
    if col1.button("저장", use_container_width=True, disabled=not nickname):
        db.save_preset(nickname, weights)
        st.sidebar.success(f"'{nickname}' 프리셋 저장됨")
    if col2.button("불러오기", use_container_width=True, disabled=not nickname):
        loaded = db.load_preset(nickname)
        if loaded is None:
            st.sidebar.warning("저장된 프리셋이 없습니다")
        else:
            for key, value in loaded.items():
                st.session_state[f"w_{key}"] = value
            st.rerun()
    if not db.is_configured():
        st.sidebar.caption("Supabase 미설정 — 프리셋 저장은 비활성화 상태 (세션 내 조정은 가능)")

    return weights


def main() -> None:
    st.title("코스피 저평가 우량 배당주 스코어링")

    quant_df = load_quant_scores()
    if quant_df.empty:
        st.warning(
            f"{DATA_CSV} 가 없습니다. 먼저 `uv run pipeline/run_pipeline.py --mock`(또는 실데이터 모드)를 실행하세요."
        )
        return

    weights = sidebar_weights()

    quant_df["is_top30_candidate"] = quant_df["quant_subtotal"].rank(
        ascending=False, method="first"
    ) <= TOP_N_FOR_QUAL

    qual_df = compute_qual_scores(quant_df["ticker"].astype(str).tolist())
    df = quant_df.merge(qual_df, on="ticker", how="left")

    weighted_quant = sum(df[k] * w for k, w in weights.items() if k in QUANT_ITEMS)
    weighted_qual = sum(df[k] * w for k, w in weights.items() if k in QUAL_ITEMS)
    df["weighted_total"] = weighted_quant + weighted_qual

    df = df.sort_values("weighted_total", ascending=False).reset_index(drop=True)
    df.insert(0, "순위", df.index + 1)

    display_cols = {
        "순위": "순위",
        "name": "종목명",
        "ticker": "코드",
        "weighted_total": "총점(가중치 반영)",
        "quant_subtotal": "정량 소계",
        "is_top30_candidate": "정성평가 대상",
        "per": "PER",
        "pbr": "PBR",
        "dividend_yield_pct": "배당수익률(%)",
    }
    st.dataframe(
        df[list(display_cols.keys())].rename(columns=display_cols),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        f"총 {len(df)}개 종목 · 정량 데이터 기준 상위 {TOP_N_FOR_QUAL}개 종목만 "
        "'정성평가 입력' 페이지에서 사람이 직접 점수를 넣을 수 있습니다."
    )


if __name__ == "__main__":
    main()
