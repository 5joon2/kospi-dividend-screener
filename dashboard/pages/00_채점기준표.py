"""채점 기준표 — 책 5장 점수표를 한 화면에서 확인하는 참고용 페이지.

pipeline/scoring.py의 실제 로직을 사람이 보기 좋게 옮겨적은 것.
scoring.py의 배점/구간을 바꾸면 이 표도 같이 업데이트할 것.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="채점 기준표", layout="wide")
st.title("채점 기준표")
st.caption("책 5장 \"종목 선정 기준\"의 배점표를 그대로 코드화한 것 — 화살표는 어느 방향이 유리한지를 뜻함")

UP = "▲ 높을수록 유리"
DOWN = "▼ 낮을수록 유리"
GOOD = "✅ 해당하면 유리"

QUANT_BADGE = "🤖 정량 (자동 계산)"
QUAL_BADGE = "🙋 정성 (사람 입력, top-30만)"

CSS = """
<style>
.score-table { width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }
.score-table th, .score-table td {
    border: 1px solid rgba(128,128,128,0.3);
    padding: 8px 12px;
    text-align: center;
    vertical-align: middle;
}
.score-table th { background: rgba(128,128,128,0.12); font-weight: 600; }
.score-table td.crit-name { text-align: left; font-weight: 600; }
.score-table td.direction { white-space: nowrap; font-size: 0.9rem; }
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 0.8rem; margin-top: 4px;
}
.badge.quant { background: rgba(59,130,246,0.15); color: #3b82f6; }
.badge.qual { background: rgba(234,179,8,0.15); color: #b45309; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def render_section(title: str, rows: list[dict]) -> None:
    st.subheader(title)
    html = ['<table class="score-table"><thead><tr>',
            '<th style="text-align:left">항목</th><th>방향</th><th>구간별 배점</th></tr></thead><tbody>']
    for r in rows:
        badge_class = "quant" if r["type"] == QUANT_BADGE else "qual"
        html.append(
            f'<tr><td class="crit-name">{r["name"]}<br>'
            f'<span class="badge {badge_class}">{r["type"]}</span></td>'
            f'<td class="direction">{r["direction"]}</td>'
            f'<td>{r["brackets"]}</td></tr>'
        )
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)


section1 = [
    {"name": "PER", "type": QUANT_BADGE, "direction": DOWN,
     "brackets": "&lt;5 → 20점 · &lt;8 → 15점 · &lt;10 → 10점 · 그 외 → 5점 (적자기업 → 0점)"},
    {"name": "PBR", "type": QUANT_BADGE, "direction": DOWN,
     "brackets": "&lt;0.3 → 5점 · &lt;0.6 → 4점 · &lt;1.0 → 3점 · 그 외 → 0점"},
    {"name": "이익 지속가능성", "type": QUAL_BADGE, "direction": GOOD,
     "brackets": "대체로 지속가능 → 5점 · 불안정 → 0점"},
    {"name": "중복상장 여부", "type": QUANT_BADGE, "direction": GOOD + " (단독상장이 유리)",
     "brackets": "단독상장 → 5점 · 중복상장(자회사·손자회사 상장) → 0점"},
]

section2 = [
    {"name": "배당수익률", "type": QUANT_BADGE, "direction": UP,
     "brackets": "&gt;7% → 10점 · &gt;5% → 7점 · &gt;3% → 5점 · 그 외 → 2점"},
    {"name": "분기배당 실시 여부", "type": QUANT_BADGE, "direction": GOOD,
     "brackets": "예 → 5점 · 아니요 → 0점"},
    {"name": "배당 연속 인상 연수", "type": QUANT_BADGE, "direction": UP,
     "brackets": "10년+ → 5점 · 5년+ → 4점 · 3년+ → 3점 · 그 외 → 0점 (동결은 연속 유지, 인상으로는 미인정)"},
    {"name": "정기적 자사주매입·소각 여부", "type": QUANT_BADGE, "direction": GOOD,
     "brackets": "예(최근 2년 내 2건+) → 7점 · 아니요 → 0점"},
    {"name": "소각 비율", "type": QUANT_BADGE, "direction": UP,
     "brackets": "&gt;2% → 8점 · &gt;1.5% → 5점 · &gt;0.5% → 3점 · 그 외 → 0점"},
    {"name": "자사주 보유비율", "type": QUANT_BADGE, "direction": DOWN,
     "brackets": "없음 → 5점 · &lt;2% → 4점 · &lt;5% → 2점 · 그 외 → 0점"},
]

section3 = [
    {"name": "미래 성장 잠재력", "type": QUAL_BADGE, "direction": UP,
     "brackets": "매우높다 → 10점 · 높다 → 7점 · 보통 → 5점 · 낮다 → 3점"},
    {"name": "경영진 평가", "type": QUAL_BADGE, "direction": UP,
     "brackets": "우수한 경영자 → 10점 · 전문경영자 → 5점 · 저조한 실적 오너경영 → 0점"},
    {"name": "세계적 브랜드 보유 여부", "type": QUAL_BADGE, "direction": GOOD,
     "brackets": "있다 → 5점 · 없다 → 0점"},
]

render_section("① 이익 창출력 / 저평가 여부 / 지속 가능성", section1)
render_section("② 주주환원 의지", section2)
render_section("③ 미래 성장 잠재력 / 기업 경쟁력", section3)

st.divider()
st.markdown(
    f"""
**{QUANT_BADGE}**: `data/scores_quant.csv`에 매일 자동으로 채워지는 값 (9개 항목, 만점 70점)

**{QUAL_BADGE}**: 정량 기준 상위 30개 종목에 한해 [정성평가 입력](정성평가_입력) 페이지에서
사람이 직접 입력 (4개 항목, 만점 30점)

**총점 만점**: 100점
"""
)
