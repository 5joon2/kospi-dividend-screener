"""정성평가 입력 페이지 — 정량 상위 30종목에 한해 공유 비밀번호로 보호된 편집 UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
import db  # noqa: E402

DATA_CSV = Path(__file__).parent.parent.parent / "data" / "scores_quant.csv"
TOP_N_FOR_QUAL = 30

GROWTH_OPTIONS = ["매우높다", "높다", "보통", "낮다"]
MANAGEMENT_OPTIONS = ["우수한경영자", "전문경영자", "저조한실적오너경영"]

st.set_page_config(page_title="정성평가 입력", layout="wide")
st.title("정성평가 입력 (top-30)")


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
    st.warning("data/scores_quant.csv 가 없습니다. 파이프라인을 먼저 실행하세요.")
    st.stop()

editor_name = st.text_input("입력자 닉네임 (누가 평가했는지 기록용)")
if not editor_name:
    st.info("닉네임을 입력해야 저장할 수 있습니다.")

quant_df = pd.read_csv(DATA_CSV)
quant_df["ticker"] = quant_df["ticker"].astype(str).str.zfill(6)
top30 = quant_df.sort_values("quant_subtotal", ascending=False).head(TOP_N_FOR_QUAL)

existing = db.load_all_qual_scores()

rows = []
for _, r in top30.iterrows():
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
    use_container_width=True,
    hide_index=True,
    disabled=["ticker", "종목명"],
    column_config={
        "성장 잠재력": st.column_config.SelectboxColumn(options=GROWTH_OPTIONS),
        "경영진": st.column_config.SelectboxColumn(options=MANAGEMENT_OPTIONS),
    },
    key="qual_editor",
)

if st.button("저장", type="primary", disabled=not editor_name):
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
            )
        st.success(f"{len(edited)}개 종목 정성평가 저장 완료")
