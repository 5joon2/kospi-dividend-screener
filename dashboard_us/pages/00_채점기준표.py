"""채점 기준표 (미국판) — 책 5장 점수표 + KOSPI판 대비 타협 사항 정리.

pipeline/scoring.py의 실제 로직은 KOSPI판과 100% 동일 — 배점/구간이 아니라
"어떤 데이터로 각 항목을 채우는가"만 다르다. scoring.py의 배점/구간을 바꾸면
이 표도, KOSPI판 00_채점기준표.py도 같이 업데이트할 것.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="채점 기준표 (US)", layout="wide")
st.title("채점 기준표 (S&P 500)")
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
.direction.dir-up { color: #d92b2b; font-weight: 700; }
.direction.dir-other { color: #1a73e8; font-weight: 700; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def render_section(title: str, rows: list[dict]) -> None:
    st.subheader(title)
    html = ['<table class="score-table"><thead><tr>',
            '<th style="text-align:left">항목</th><th>방향</th><th>구간별 배점</th></tr></thead><tbody>']
    for r in rows:
        badge_class = "quant" if r["type"] == QUANT_BADGE else "qual"
        dir_class = "dir-up" if r["direction"].startswith(UP) else "dir-other"
        html.append(
            f'<tr><td class="crit-name">{r["name"]}<br>'
            f'<span class="badge {badge_class}">{r["type"]}</span></td>'
            f'<td class="direction {dir_class}">{r["direction"]}</td>'
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
    {"name": "중복상장 여부 ⚠️", "type": QUANT_BADGE, "direction": GOOD,
     "brackets": "미국판은 이 항목을 평가하지 않고 항상 단독상장(5점)으로 고정 — "
     "아래 '미국판 타협 사항' 참고"},
]

section2 = [
    {"name": "배당수익률", "type": QUANT_BADGE, "direction": UP,
     "brackets": "&gt;7% → 10점 · &gt;5% → 7점 · &gt;3% → 5점 · 그 외 → 2점 "
     "(최근 12개월 지급 배당금 합계 ÷ 오늘 현재가로 계산, yfinance)"},
    {"name": "분기배당 실시 여부", "type": QUANT_BADGE, "direction": GOOD,
     "brackets": "예 → 5점 · 아니요 → 0점 (최근 1년 지급 횟수 3회 이상 → 분기배당)"},
    {"name": "배당 연속 인상 연수", "type": QUANT_BADGE, "direction": UP,
     "brackets": "10년+ → 5점 · 5년+ → 4점 · 3년+ → 3점 · 그 외 → 0점 (동결은 연속 유지, 인상으로는 미인정)"},
    {"name": "정기적 자사주매입·소각 여부 ⚠️", "type": QUANT_BADGE, "direction": GOOD,
     "brackets": "예(최근 3년 내 SEC 공시 기준 2개 회계연도+ 매입) → 7점 · 아니요 → 0점"},
    {"name": "소각 비율 ⚠️", "type": QUANT_BADGE, "direction": UP,
     "brackets": "&gt;2% → 8점 · &gt;1.5% → 5점 · &gt;0.5% → 3점 · 그 외 → 0점 (근사치, 아래 참고)"},
    {"name": "자사주 보유비율 ⚠️", "type": QUANT_BADGE, "direction": DOWN,
     "brackets": "없음 → 5점 · &lt;2% → 4점 · &lt;5% → 2점 · 그 외 → 0점 (근사치, 아래 참고)"},
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
**{QUANT_BADGE}**: `data/us_scores_quant.csv`에 매일 자동으로 채워지는 값 (9개 항목, 만점 70점)

**{QUAL_BADGE}**: 정량 기준 상위 30개 종목에 한해 [정성평가 입력](정성평가_입력) 페이지에서
사람이 직접 입력 (4개 항목, 만점 30점)

**총점 만점**: 100점
"""
)

st.divider()
st.subheader("⚠️ 미국판 타협 사항 (TODO)")
st.caption("KOSPI판(DART/KIS)과 데이터 소스·정확도가 다른 부분. 코드 주석과 README에도 동일하게 기록되어 있음.")
st.markdown(
    """
| 항목 | KOSPI(DART/KIS) | 미국(yfinance/SEC EDGAR) | 타협 내용 |
|---|---|---|---|
| PER/PBR | KIS 실시간 시세 API(증권사 공식값) | yfinance `.info`(야후 자체 계산, 결측 잦음) | 결측 시 0점 처리. **TODO**: 결측률 높으면 유료 API 폴백 검토 |
| **중복상장(자회사 상장) 여부** | DART 타법인출자현황 + 지주회사 업종코드로 정밀 판정 | 무료로 판정할 데이터 소스 없음 | **평가 자체를 생략, 항상 단독상장(만점) 처리**. TODO: 필요해지면 수작업 큐레이션 목록으로 대체 |
| **자사주 정기매입 여부 / 소각비율** | DART 공시 건수·주식수(정확한 주식수 기반) | SEC EDGAR XBRL `TreasuryStockSharesAcquired`(주식수 기반, 공식 규제 데이터) | 데이터 소스 정밀도는 DART급이지만, 미국은 매입 즉시 발행주식을 상각(retire)하는 관행이 흔해 실제 매입이 많아도 비율이 낮게 나올 수 있음. **TODO: 발행주식수 전년대비 감소분 기반으로 재계산 검토** |
| **자사주 보유비율** | DART 주식총수 현황(정확값) | SEC EDGAR XBRL `TreasuryStockCommonShares` ÷ `CommonStockSharesIssued` | 위와 같은 이유로 0이 "결측"인지 "실제로 작음"인지 구분이 안 됨. **TODO: XBRL 태그가 회사마다 달라 방어적 조회 로직 보강 필요** |
| 종목 제외(REIT 등) | 수동 티커 목록(`exclusions.py`) | 위키 GICS Sector="Real Estate" 자동 제외 | 자동화라 더 편함. ETF/BDC 등 GICS로 안 걸러지는 예외는 **TODO**: 수작업 확인 필요 |
| 최근 배당일 표기 | KIS 배당기준일/지급일 둘 다 제공 | yfinance는 배당락일만 제공 | 배당기준일/지급일 구분 없이 배당락일만 표시 |
| 스케줄(cron) | KST 고정(한국은 DST 없음) | ET 기준 UTC 고정 cron | 미국 서머타임 전환 시 실행 시각이 1시간 밀림. **TODO**: DST 대응 cron 분리 여부 검토 |
"""
)
