"""정성평가 입력 페이지 (미국판) — 규모(대형/중형/소형주)별 상위 30종목, 공유 비밀번호로 보호된 편집 UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dashboard"))
import db  # noqa: E402

MARKET = "us"

DATA_CSV = Path(__file__).parent.parent.parent / "data" / "us_scores_quant.csv"
TOP_N_FOR_QUAL = 30

GROWTH_OPTIONS = ["매우높다", "높다", "보통", "낮다"]
MANAGEMENT_OPTIONS = ["우수한경영자", "전문경영자", "저조한실적오너경영"]

st.set_page_config(page_title="정성평가 입력 (US)", layout="wide")
st.title("정성평가 입력 (S&P 500)")
st.caption(
    f"대형주/중형주/소형주 각각 정량 데이터 기준 상위 {TOP_N_FOR_QUAL}개씩(최대 {TOP_N_FOR_QUAL * 3}개) — "
    "규모별로 독립 랭킹을 써서 유망한 소형주가 대형주에 밀려 평가 후보에도 못 드는 걸 방지. "
    "KOSPI판과 프리셋/정성평가는 완전히 분리되어 저장됩니다."
)


def check_password() -> bool:
    try:
        expected = st.secrets["QUAL_EDIT_PASSWORD"]
    except (KeyError, FileNotFoundError):
        expected = os.environ.get("QUAL_EDIT_PASSWORD")

    if not expected:
        st.error("QUAL_EDIT_PASSWORD가 설정되지 않았습니다. Streamlit secrets를 확인하세요.")
        return False

    entered = st.text_input("편집 비밀번호", type="password")
    return entered == expected


if not check_password():
    st.stop()

if not DATA_CSV.exists():
    st.warning("data/us_scores_quant.csv 가 없습니다. 파이프라인을 먼저 실행하세요.")
    st.stop()

editor_name = st.text_input("입력자 닉네임 (누가 평가했는지 기록용)")
if not editor_name:
    st.info("닉네임을 입력해야 저장할 수 있습니다.")

quant_df = pd.read_csv(DATA_CSV, dtype={"ticker": str})
if "market_cap" not in quant_df.columns:
    quant_df["market_cap"] = 0

market_cap_rank = quant_df["market_cap"].rank(ascending=False, method="first")
# app_us.py와 동일한 이유로 bins 단조증가 보정 (mock 데이터 등 종목 수가 적을 때 대비).
n = len(quant_df)
size_bins = sorted({0, min(100, n), min(300, n), n})
size_labels = ["대형주", "중형주", "소형주"][: len(size_bins) - 1]
quant_df["규모구분"] = pd.cut(market_cap_rank, bins=size_bins, labels=size_labels)

existing = db.load_all_qual_scores(market=MARKET)


def render_group_editor(group: str) -> None:
    group_df = quant_df[quant_df["규모구분"] == group]
    top_n = group_df.sort_values("quant_subtotal", ascending=False).head(TOP_N_FOR_QUAL)

    rows = []
    for _, r in top_n.iterrows():
        entry = existing.get(r["ticker"], {})
        rows.append({
            "ticker": r["ticker"],
            "종목명": r["name"],
            "이익 지속가능": bool(entry.get("profit_sustainable", False)),
            "성장 잠재력": entry.get("growth_potential") or "보통",
            "경영진": entry.get("management") or "전문경영자",
            "세계적 브랜드": bool(entry.get("global_brand", False)),
        })

    edited = st.data_editor(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        disabled=["ticker", "종목명"],
        column_config={
            "성장 잠재력": st.column_config.SelectboxColumn(options=GROWTH_OPTIONS),
            "경영진": st.column_config.SelectboxColumn(options=MANAGEMENT_OPTIONS),
        },
        key=f"qual_editor_us_{group}",
    )

    if st.button(f"{group} 저장", type="primary", disabled=not editor_name, key=f"save_us_{group}"):
        if not db.is_configured():
            st.error("Supabase가 설정되지 않아 저장할 수 없습니다 (secrets 확인 필요).")
        else:
            for _, row in edited.iterrows():
                db.save_qual_score(
                    row["ticker"],
                    {
                        "profit_sustainable": bool(row["이익 지속가능"]),
                        "growth_potential": row["성장 잠재력"],
                        "management": row["경영진"],
                        "global_brand": bool(row["세계적 브랜드"]),
                    },
                    editor=editor_name,
                    market=MARKET,
                )
            st.success(f"{group} {len(edited)}개 종목 정성평가 저장 완료")


tabs = st.tabs(["대형주", "중형주", "소형주"])
for tab, group in zip(tabs, ["대형주", "중형주", "소형주"]):
    with tab:
        render_group_editor(group)
