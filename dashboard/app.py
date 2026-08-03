"""코스피 저평가 우량 배당주 스코어링 대시보드 — 메인 페이지."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
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
HISTORY_CSV = Path(__file__).parent.parent / "data" / "score_history.csv"
TOP_N_FOR_QUAL = 30
NAVER_STOCK_URL = "https://finance.naver.com/item/main.naver?code={ticker}"

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

# 배점 상세 패널용 — 각 항목의 (라벨, 원본 데이터 컬럼, 값 표시 방식)
QUANT_RAW_DISPLAY = {
    "score_per": ("PER", "per", lambda v: f"{v:.2f}"),
    "score_pbr": ("PBR", "pbr", lambda v: f"{v:.2f}"),
    "score_dual_listed": ("중복상장 여부", "dual_listed", lambda v: "중복상장" if v else "단독상장"),
    "score_dividend_yield": ("배당수익률", "dividend_yield_pct", lambda v: f"{v:.2f}%"),
    "score_quarterly_dividend": ("분기배당 실시", "quarterly_dividend", lambda v: "예" if v else "아니요"),
    "score_dividend_increase_years": ("배당 연속 인상 연수", "dividend_increase_years", lambda v: f"{int(v)}년"),
    "score_buyback_regular": ("정기 자사주매입·소각", "buyback_cancel_regular", lambda v: "예" if v else "아니요"),
    "score_cancel_ratio": ("소각 비율", "cancel_ratio_pct", lambda v: f"{v:.2f}%"),
    "score_treasury_ratio": ("자사주 보유 비율", "treasury_ratio_pct", lambda v: f"{v:.2f}%"),
}
QUAL_RAW_DISPLAY = {
    "score_profit_sustainability": ("이익 지속가능성", "profit_sustainable", lambda v: "예" if v else "아니요/미입력"),
    "score_growth_potential": ("미래 성장 잠재력", "growth_potential", lambda v: v or "미입력"),
    "score_management": ("경영진 평가", "management", lambda v: v or "미입력"),
    "score_global_brand": ("세계적 브랜드 보유", "global_brand", lambda v: "예" if v else "아니요/미입력"),
}

st.set_page_config(page_title="코스피 저평가 우량 배당주", layout="wide")


@st.cache_data
def _load_quant_scores_cached(_mtime: float) -> pd.DataFrame:
    # _mtime을 캐시 키에 포함시켜서, CSV 파일이 갱신되면(GitHub Actions가 매일 커밋)
    # Streamlit의 소프트 리로드("Updated app!")만으로도 캐시가 자동으로 무효화되게 함 —
    # 이게 없으면 앱을 수동으로 완전히 Reboot해야만 새 데이터가 반영됨(실제로 겪은 문제).
    df = pd.read_csv(DATA_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    return df


def load_quant_scores() -> pd.DataFrame:
    if not DATA_CSV.exists():
        return pd.DataFrame()
    return _load_quant_scores_cached(DATA_CSV.stat().st_mtime)


@st.cache_data
def _load_history_cached(_mtime: float) -> pd.DataFrame:
    df = pd.read_csv(HISTORY_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    return df


def load_history() -> pd.DataFrame:
    if not HISTORY_CSV.exists():
        return pd.DataFrame()
    return _load_history_cached(HISTORY_CSV.stat().st_mtime)


def render_rank_trend_chart() -> None:
    history = load_history()
    if history.empty:
        st.caption("아직 히스토리 데이터가 없습니다 (파이프라인이 최소 1번은 실행돼야 함).")
        return

    if history["date"].nunique() < 2:
        # 하루치뿐일 땐 추이를 그릴 수 없으니, 그날의 top-20 점수를 막대그래프로 대신 보여줌.
        today_df = history.sort_values("rank")
        fig = px.bar(
            today_df, x="quant_subtotal", y="name", orientation="h",
            labels={"quant_subtotal": "정량 점수", "name": ""},
            text="quant_subtotal",
        )
        fig.update_yaxes(autorange="reversed")  # 1등이 위로 오게
        fig.update_layout(height=520, showlegend=False)
        st.plotly_chart(fig, width="stretch")
        st.caption("아직 하루치 데이터뿐이라 오늘의 top-20 점수만 보여드려요 — 내일부터는 순위 변화 추이로 바뀝니다.")
        return

    latest_date = history["date"].max()
    current_top20_tickers = history.loc[history["date"] == latest_date, "ticker"]
    plot_df = history[history["ticker"].isin(current_top20_tickers)].copy()
    plot_df["종목"] = plot_df["name"] + " (" + plot_df["ticker"] + ")"

    fig = px.line(
        plot_df.sort_values("date"),
        x="date", y="rank", color="종목",
        markers=True,
        labels={"date": "날짜", "rank": "순위"},
    )
    fig.update_yaxes(autorange="reversed", dtick=1)
    fig.update_layout(height=520, legend_title_text="", hovermode="closest")
    st.plotly_chart(fig, width="stretch")


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


def render_score_breakdown(row: pd.Series, weights: dict[str, float]) -> None:
    qual_entry = db.load_all_qual_scores().get(row["ticker"], {})
    lines = ["| 항목 | 원본 데이터 | 배점 | 가중치 | 반영 점수 |", "|---|---|---|---|---|"]

    for score_key, (label, raw_key, fmt) in QUANT_RAW_DISPLAY.items():
        raw_display = fmt(row[raw_key])
        score = row[score_key]
        weight = weights.get(score_key, 1.0)
        lines.append(f"| {label} | {raw_display} | {score}점 | ×{weight:.1f} | {score * weight:.1f} |")

    for score_key, (label, raw_key, fmt) in QUAL_RAW_DISPLAY.items():
        raw_display = fmt(qual_entry.get(raw_key))
        score = row[score_key]
        weight = weights.get(score_key, 1.0)
        lines.append(f"| {label} (정성) | {raw_display} | {score}점 | ×{weight:.1f} | {score * weight:.1f} |")

    st.markdown("\n".join(lines))
    st.markdown(f"**총점(가중치 반영): {row['weighted_total']:.1f}점**")


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
    if col1.button("저장", width="stretch", disabled=not nickname):
        db.save_preset(nickname, weights)
        st.sidebar.success(f"'{nickname}' 프리셋 저장됨")
    if col2.button("불러오기", width="stretch", disabled=not nickname):
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
    # 종목명 셀 자체를 네이버증권 링크로 — URL 뒤에 #종목명을 붙여두고 LinkColumn의
    # display_text 정규식으로 그 부분만 뽑아 보여주는 방식(각 행마다 다른 텍스트를
    # 보여줄 수 있는 유일한 방법 — display_text는 URL 문자열에서만 추출 가능하기 때문).
    df["종목명"] = df.apply(
        lambda r: NAVER_STOCK_URL.format(ticker=r["ticker"]) + "#" + r["name"], axis=1
    )

    display_cols = {
        "순위": "순위",
        "종목명": "종목명",
        "ticker": "코드",
        "weighted_total": "총점(가중치 반영)",
        "quant_subtotal": "정량 소계",
        "is_top30_candidate": "정성평가 대상",
        "per": "PER",
        "pbr": "PBR",
        "dividend_yield_pct": "배당수익률(%)",
    }
    st.caption("종목명을 클릭하면 네이버증권으로 이동하고, 행을 선택하면 아래에 배점 상세 내역이 나와요.")
    event = st.dataframe(
        df[list(display_cols.keys())].rename(columns=display_cols),
        width="stretch",
        hide_index=True,
        column_config={
            "종목명": st.column_config.LinkColumn(display_text=r"#(.+)$"),
        },
        on_select="rerun",
        selection_mode="single-row",
    )

    st.caption(
        f"총 {len(df)}개 종목 · 정량 데이터 기준 상위 {TOP_N_FOR_QUAL}개 종목만 "
        "'정성평가 입력' 페이지에서 사람이 직접 점수를 넣을 수 있습니다."
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        selected = df.iloc[selected_rows[0]]
        with st.expander(f"📊 {selected['name']} 배점 상세", expanded=True):
            render_score_breakdown(selected, weights)

    st.divider()
    st.subheader("일별 TOP 20 순위 변화")
    render_rank_trend_chart()


if __name__ == "__main__":
    main()
