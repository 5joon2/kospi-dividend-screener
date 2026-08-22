"""S&P 500 저평가 우량 배당주 스코어링 대시보드 — 메인 페이지 (dashboard/app.py의 미국판).

별도 디렉터리(dashboard_us/)로 둔 이유: Streamlit은 진입 스크립트와 같은 폴더의
pages/ 를 자동으로 사이드바 내비게이션에 붙이는데, dashboard/ 안에 app_us.py를
같이 두면 KOSPI판 pages(정성평가 입력 등)가 미국판 사이드바에도 그대로 섞여
나온다 — 그래서 이 파일은 dashboard/가 아니라 별도 폴더에 두고, db.py/scoring.py는
경로만 추가해서 그대로 재사용한다(중복 구현 아님).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from scoring import (  # noqa: E402
    score_global_brand,
    score_growth_potential,
    score_management,
    score_profit_sustainability,
)

import db  # noqa: E402

MARKET = "us"

DATA_CSV = Path(__file__).parent.parent / "data" / "us_scores_quant.csv"
HISTORY_CSV = Path(__file__).parent.parent / "data" / "us_score_history.csv"
TOP_N_FOR_QUAL = 30
HISTORY_TOP_N = 20  # pipeline/run_pipeline_us.py의 HISTORY_TOP_N과 동일한 값
YAHOO_STOCK_URL = "https://finance.yahoo.com/quote/{ticker}"

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
    # 미국판은 자회사 상장 여부를 판정할 무료 데이터 소스가 없어 평가 자체를 안 함 —
    # dual_listed는 항상 False로 고정, 즉 이 항목은 사실상 상수 만점(TODO: README 참고).
    "score_dual_listed": ("중복상장 여부", "dual_listed", lambda v: "평가 안 함(항상 만점)"),
    "score_dividend_yield": ("배당수익률", "dividend_yield_pct", lambda v: f"{v:.2f}%"),
    "score_quarterly_dividend": ("분기배당 실시", "quarterly_dividend", lambda v: "예" if v else "아니요"),
    "score_dividend_increase_years": ("배당 연속 인상 연수", "dividend_increase_years", lambda v: f"{int(v)}년"),
    "score_buyback_regular": ("정기 자사주매입·소각", "buyback_cancel_regular", lambda v: "예" if v else "아니요"),
    "score_cancel_ratio": ("소각 비율(근사치)", "cancel_ratio_pct", lambda v: f"{v:.2f}%"),
    "score_treasury_ratio": ("자사주 보유 비율", "treasury_ratio_pct", lambda v: f"{v:.2f}%"),
}
QUAL_RAW_DISPLAY = {
    "score_profit_sustainability": ("이익 지속가능성", "profit_sustainable", lambda v: "예" if v else "아니요/미입력"),
    "score_growth_potential": ("미래 성장 잠재력", "growth_potential", lambda v: v or "미입력"),
    "score_management": ("경영진 평가", "management", lambda v: v or "미입력"),
    "score_global_brand": ("세계적 브랜드 보유", "global_brand", lambda v: "예" if v else "아니요/미입력"),
}

st.set_page_config(page_title="S&P 500 저평가 우량 배당주", layout="wide")


def load_quant_scores() -> pd.DataFrame:
    if not DATA_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(DATA_CSV, dtype={"ticker": str})


def load_history() -> pd.DataFrame:
    if not HISTORY_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(HISTORY_CSV, dtype={"ticker": str})


def render_rank_trend_chart(history: pd.DataFrame) -> None:
    if history.empty:
        st.caption("이 규모 구간은 아직 히스토리 데이터가 없습니다.")
        return

    if history["date"].nunique() < 2:
        today_df = history.sort_values("rank")
        fig = px.bar(
            today_df, x="quant_subtotal", y="name", orientation="h",
            labels={"quant_subtotal": "정량 점수", "name": ""},
            text="quant_subtotal",
        )
        fig.update_yaxes(autorange="reversed")
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


def render_ticker_score_trend(
    history: pd.DataFrame, ticker: str, name: str, qual_subtotal: float, qual_evaluated: bool,
) -> None:
    ticker_history = history[history["ticker"] == ticker].sort_values("date") if not history.empty else history
    if ticker_history.empty:
        st.caption(f"{name}은(는) 아직 규모별 상위 {HISTORY_TOP_N}위 안에 든 기록이 없어 추이를 볼 수 없습니다.")
        return

    if qual_evaluated:
        st.caption(f"✅ 정성평가 입력됨 — 정성 소계 {qual_subtotal:.0f}점(기본 가중치 기준)을 아래 추이에 반영했습니다.")
    else:
        st.caption("⚠️ 정성평가 미입력 — 정성 소계 0점으로 계산돼서, 정성평가를 받은 다른 종목보다 최종 점수가 낮게 보일 수 있어요.")

    if ticker_history["date"].nunique() < 2:
        st.caption(f"{name}의 히스토리가 아직 하루치뿐이라 추이를 그릴 수 없어요 — 내일부터 쌓입니다.")
        return

    ticker_history = ticker_history.copy()
    ticker_history["final_score"] = ticker_history["quant_subtotal"] + qual_subtotal

    st.markdown(f"**{name} 최종 점수 추이** (정량 + 정성, 기본 가중치 기준)")
    fig_score = px.line(
        ticker_history, x="date", y="final_score", markers=True,
        labels={"date": "날짜", "final_score": "최종 점수"},
    )
    fig_score.update_layout(height=280)
    st.plotly_chart(fig_score, width="stretch")
    st.caption("정성 부분은 과거 날짜에도 지금의 정성평가 값을 그대로 적용한 값이에요 — 정성평가 자체는 날짜별로 기록되지 않습니다.")

    st.markdown(f"**{name} 순위 추이** (S&P 500 내 규모 구분 기준, 정량)")
    fig_rank = px.line(
        ticker_history, x="date", y="rank", markers=True,
        labels={"date": "날짜", "rank": "순위"},
    )
    fig_rank.update_yaxes(autorange="reversed", dtick=1)
    fig_rank.update_layout(height=280)
    st.plotly_chart(fig_rank, width="stretch")


def compute_qual_scores(tickers: list[str]) -> pd.DataFrame:
    raw = db.load_all_qual_scores(market=MARKET)
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
    qual_entry = db.load_all_qual_scores(market=MARKET).get(row["ticker"], {})
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
    st.sidebar.caption("KOSPI 대시보드와는 별도로 저장됩니다(같은 닉네임이어도 안 섞임).")
    nickname = st.sidebar.text_input("닉네임", key="preset_nickname")
    col1, col2 = st.sidebar.columns(2)
    if col1.button("저장", width="stretch", disabled=not nickname):
        db.save_preset(nickname, weights, market=MARKET)
        st.sidebar.success(f"'{nickname}' 프리셋 저장됨")
    if col2.button("불러오기", width="stretch", disabled=not nickname):
        loaded = db.load_preset(nickname, market=MARKET)
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
    st.title("S&P 500 저평가 우량 배당주 스코어링")
    st.caption(
        "⚠️ KOSPI판을 그대로 미국 주식에 이식한 실험판입니다 — 자사주매입/소각/보유비율, "
        "중복상장 여부 등 일부 항목은 무료 데이터 한계로 근사치이거나 평가를 생략했습니다. "
        "자세한 내용은 '채점기준표' 페이지 참고."
    )

    quant_df = load_quant_scores()
    if quant_df.empty:
        st.warning(
            f"{DATA_CSV} 가 없습니다. 먼저 `uv run pipeline/run_pipeline_us.py --mock`(또는 실데이터 모드)를 실행하세요."
        )
        return
    for col in ("recent_dividend_record_date", "recent_dividend_pay_date"):
        if col not in quant_df.columns:
            quant_df[col] = ""
        quant_df[col] = quant_df[col].fillna("-")

    if "gics_sector" not in quant_df.columns:
        quant_df["gics_sector"] = "미분류"
    if "market_cap" not in quant_df.columns:
        quant_df["market_cap"] = 0
    quant_df["gics_sector"] = quant_df["gics_sector"].fillna("미분류")

    market_cap_rank = quant_df["market_cap"].rank(ascending=False, method="first")
    # bins는 반드시 단조증가해야 해서(pd.cut 제약), 종목 수가 100/300보다 적은
    # 경우(--mock 테스트 데이터 등)엔 중복되는 경계를 걸러내고 라벨 수도 맞춰 자름
    # (2026-08-22, AppTest로 mock 데이터 렌더링 중 "bins must increase monotonically" 발견).
    n = len(quant_df)
    size_bins = sorted({0, min(100, n), min(300, n), n})
    size_labels = ["대형주(1~100위)", "중형주(101~300위)", "소형주(301위~)"][: len(size_bins) - 1]
    quant_df["규모구분"] = pd.cut(market_cap_rank, bins=size_bins, labels=size_labels)

    weights = sidebar_weights()

    quant_df["is_top30_candidate"] = quant_df.groupby("규모구분", observed=True)["quant_subtotal"].rank(
        ascending=False, method="first"
    ) <= TOP_N_FOR_QUAL

    valid_per = quant_df[quant_df["per"] > 0]
    valid_pbr = quant_df[quant_df["pbr"] > 0]
    sector_median_per = valid_per.groupby("gics_sector")["per"].median()
    sector_median_pbr = valid_pbr.groupby("gics_sector")["pbr"].median()
    quant_df["섹터중앙값_per"] = quant_df["gics_sector"].map(sector_median_per)
    quant_df["섹터중앙값_pbr"] = quant_df["gics_sector"].map(sector_median_pbr)
    quant_df["per_상대값"] = (quant_df["per"] / quant_df["섹터중앙값_per"] - 1) * 100
    quant_df["pbr_상대값"] = (quant_df["pbr"] / quant_df["섹터중앙값_pbr"] - 1) * 100

    qual_df = compute_qual_scores(quant_df["ticker"].astype(str).tolist())
    df = quant_df.merge(qual_df, on="ticker", how="left")

    weighted_quant = sum(df[k] * w for k, w in weights.items() if k in QUANT_ITEMS)
    weighted_qual = sum(df[k] * w for k, w in weights.items() if k in QUAL_ITEMS)
    df["weighted_total"] = weighted_quant + weighted_qual

    df = df.sort_values("weighted_total", ascending=False).reset_index(drop=True)

    st.subheader("필터")
    filter_cols = st.columns(5)
    with filter_cols[0]:
        sectors = st.multiselect("GICS 섹터", sorted(df["gics_sector"].unique()), placeholder="전체 섹터")
    with filter_cols[1]:
        size_groups = st.multiselect(
            "기업 규모", ["대형주(1~100위)", "중형주(101~300위)", "소형주(301위~)"],
            default=["대형주(1~100위)"],
            help="S&P 500 안에서의 시가총액 순위 1~100위/101~300위/301위 이하 — "
            "미국 시장 전체 기준 대/중/소형주 구분이 아니라 S&P 500 내 상대 순위입니다.",
        )
    with filter_cols[2]:
        min_yield = st.number_input("배당수익률 최소(%)", min_value=0.0, value=0.0, step=0.5)
    with filter_cols[3]:
        max_per = st.number_input("PER 최대 (0=제한없음)", min_value=0.0, value=0.0, step=1.0)
    with filter_cols[4]:
        max_pbr = st.number_input("PBR 최대 (0=제한없음)", min_value=0.0, value=0.0, step=0.1)

    if sectors:
        df = df[df["gics_sector"].isin(sectors)]
    if size_groups:
        df = df[df["규모구분"].isin(size_groups)]
    if min_yield > 0:
        df = df[df["dividend_yield_pct"] >= min_yield]
    if max_per > 0:
        df = df[(df["per"] > 0) & (df["per"] <= max_per)]
    if max_pbr > 0:
        df = df[(df["pbr"] > 0) & (df["pbr"] <= max_pbr)]

    df = df.reset_index(drop=True)
    df.insert(0, "순위", df.index + 1)

    if df.empty:
        st.warning("필터 조건에 맞는 종목이 없습니다. 조건을 완화해보세요.")
        return

    df["종목명"] = df.apply(
        lambda r: YAHOO_STOCK_URL.format(ticker=r["ticker"]) + "#" + r["name"], axis=1
    )
    df["배당수익률 표시"] = df["dividend_yield_pct"].apply(
        lambda v: "N/A ⚠️" if v < 0 else f"{v:.2f}%"
    )
    df["시가총액 표시"] = df["market_cap"].apply(lambda v: f"${v / 1e9:,.1f}B" if v else "-")
    df["PER 상대값 표시"] = df["per_상대값"].apply(
        lambda v: f"{v:+.0f}%" if pd.notna(v) else "-"
    )
    df["PBR 상대값 표시"] = df["pbr_상대값"].apply(
        lambda v: f"{v:+.0f}%" if pd.notna(v) else "-"
    )

    compact_cols = {
        "순위": "순위",
        "종목명": "종목명",
        "weighted_total": "총점(가중치 반영)",
        "배당수익률 표시": "배당수익률(%)",
    }
    extra_cols = {
        "ticker": "티커",
        "quant_subtotal": "정량 소계",
        "is_top30_candidate": "정성평가 대상",
        "gics_sector": "GICS 섹터",
        "per": "PER",
        "PER 상대값 표시": "PER(섹터중앙값 대비)",
        "pbr": "PBR",
        "PBR 상대값 표시": "PBR(섹터중앙값 대비)",
        "시가총액 표시": "시가총액",
        "규모구분": "기업 규모",
        "recent_dividend_record_date": "최근 배당락일",
    }

    show_all_cols = st.toggle(
        "전체 컬럼 보기",
        value=False,
        help="기본은 모바일에서도 보기 편하게 핵심 컬럼만 표시합니다. "
        "PER·PBR·배당일 등 나머지 컬럼은 이 토글을 켜면 볼 수 있어요.",
    )
    display_cols = {**compact_cols, **extra_cols} if show_all_cols else compact_cols

    st.caption("종목명을 클릭하면 야후 파이낸스 페이지로 이동합니다.")
    st.dataframe(
        df[list(display_cols.keys())].rename(columns=display_cols),
        width="stretch",
        hide_index=True,
        column_config={
            "종목명": st.column_config.LinkColumn(display_text=r"#(.+)$"),
            "배당수익률(%)": st.column_config.Column(
                help="최근 12개월 지급 배당금 합계(yfinance) ÷ 현재가 × 100."
            ),
            "총점(가중치 반영)": st.column_config.Column(
                help="정량 9개 + 정성 4개 항목 점수에 사이드바 가중치를 곱해 합산한 값. "
                "항목별 배점 내역은 아래 '배점 상세 보기'에서 종목을 선택하면 볼 수 있어요."
            ),
            "최근 배당락일": st.column_config.Column(
                help="가장 최근 배당의 배당락일(ex-dividend date) — yfinance는 배당기준일/"
                "지급일을 따로 구분해서 주지 않아 배당락일만 표시합니다."
            ),
            "PER(섹터중앙값 대비)": st.column_config.Column(
                help="같은 GICS 섹터 종목들의 PER 중앙값과 비교한 값. "
                "-30%면 섹터 내에서 상대적으로 저평가, +30%면 상대적으로 고평가라는 뜻."
            ),
            "PBR(섹터중앙값 대비)": st.column_config.Column(
                help="같은 GICS 섹터 종목들의 PBR 중앙값과 비교한 값. -30%면 섹터 내 상대적 저평가."
            ),
            "시가총액": st.column_config.Column(help="yfinance 기준 오늘자 시가총액 (billion USD)."),
        },
    )

    st.caption(
        f"총 {len(df)}개 종목 · 대형/중형/소형주 각각 정량 데이터 기준 상위 {TOP_N_FOR_QUAL}개씩"
        f"(최대 {TOP_N_FOR_QUAL * 3}개)만 '정성평가 입력' 페이지에서 사람이 직접 점수를 넣을 수 있습니다."
    )

    st.divider()
    st.subheader("섹터 분포")
    top_n_for_chart = st.slider("상위 몇 개 종목의 섹터 분포를 볼까요?", 5, min(100, len(df)), min(20, len(df)))
    chart_source = df.head(top_n_for_chart)["gics_sector"].value_counts().reset_index()
    chart_source.columns = ["섹터", "종목 수"]
    fig_sector = px.pie(chart_source, names="섹터", values="종목 수", hole=0.4)
    fig_sector.update_layout(height=420)
    st.plotly_chart(fig_sector, width="stretch")

    st.divider()
    st.subheader("배점 상세 보기")
    options = [f"{r['순위']}. {r['name']} ({r['ticker']})" for _, r in df.iterrows()]
    picked = st.selectbox("종목을 선택하면 항목별 배점 내역을 볼 수 있어요", options, index=None,
                           placeholder="종목 선택...")
    if picked:
        picked_ticker = picked.split("(")[-1].rstrip(")")
        selected = df.loc[df["ticker"] == picked_ticker].iloc[0]
        render_score_breakdown(selected, weights)

        qual_subtotal = sum(selected[k] for k in QUAL_ITEMS)
        qual_evaluated = picked_ticker in db.load_all_qual_scores(market=MARKET)
        render_ticker_score_trend(load_history(), picked_ticker, selected["name"], qual_subtotal, qual_evaluated)

    st.divider()
    st.subheader("일별 TOP 20 순위 변화")
    history = load_history()
    if not history.empty and "size_group" not in history.columns:
        st.caption("규모별 구분 이전 히스토리라 표시할 수 없습니다 — 다음 자동 갱신부터 반영됩니다.")
    else:
        tabs = st.tabs(["대형주", "중형주", "소형주"])
        for tab, group in zip(tabs, ["대형주", "중형주", "소형주"]):
            with tab:
                group_history = history[history["size_group"] == group] if not history.empty else history
                render_rank_trend_chart(group_history)


if __name__ == "__main__":
    main()
