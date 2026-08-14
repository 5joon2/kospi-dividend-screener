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
HISTORY_TOP_N = 20  # pipeline/run_pipeline.py의 HISTORY_TOP_N과 동일한 값 — 히스토리 안내 문구용
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


def load_quant_scores() -> pd.DataFrame:
    # 일부러 캐싱 안 함 — mtime 기반 캐시무효화를 써봤는데 Streamlit Cloud가 git pull할 때
    # 파일 mtime을 기대한 대로 갱신 안 해줘서 매번 수동 Reboot이 필요했던 적이 있음
    # (2026-08-03). 833행짜리 작은 CSV라 매번 새로 읽어도 성능 부담이 없어서,
    # 아예 캐시를 없애 이 문제 자체를 원천 차단.
    if not DATA_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(DATA_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    return df


def load_history() -> pd.DataFrame:
    if not HISTORY_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    return df


def render_rank_trend_chart(history: pd.DataFrame) -> None:
    """history는 이미 특정 size_group으로 필터된 데이터."""
    if history.empty:
        st.caption("이 규모 구간은 아직 히스토리 데이터가 없습니다.")
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


def render_ticker_score_trend(history: pd.DataFrame, ticker: str, name: str) -> None:
    """선택한 종목 하나의 정량 점수·순위 추이(2026-08-14, "특정 기업 눌렀을 때 점수
    변화 추이를 보고 싶다" 요청) — history는 규모 필터링 전 전체 데이터를 받아서
    여기서 ticker로 직접 거른다. history.csv는 규모별 상위 HISTORY_TOP_N위 안에
    든 날만 기록되므로, 순위가 밀린 날은 그 구간이 그래프에서 비게 된다.

    총점(가중치 반영, 정성평가 포함)은 여기 안 나온다 — 그건 사이드바 가중치와
    그날그날의 정성평가 입력값에 좌우되는 "지금 이 세션" 값이라 히스토리로 저장된
    적이 없다. 여기 나오는 건 그 총점의 절반(정량 9개 항목)에 해당하는
    quant_subtotal과 그 기준 순위뿐."""
    ticker_history = history[history["ticker"] == ticker].sort_values("date") if not history.empty else history
    if ticker_history.empty:
        st.caption(f"{name}은(는) 아직 규모별 상위 {HISTORY_TOP_N}위 안에 든 기록이 없어 추이를 볼 수 없습니다.")
        return
    if ticker_history["date"].nunique() < 2:
        st.caption(f"{name}의 히스토리가 아직 하루치뿐이라 추이를 그릴 수 없어요 — 내일부터 쌓입니다.")
        return

    st.markdown(f"**{name} 정량 점수 추이**")
    fig_score = px.line(
        ticker_history, x="date", y="quant_subtotal", markers=True,
        labels={"date": "날짜", "quant_subtotal": "정량 점수"},
    )
    fig_score.update_layout(height=280)
    st.plotly_chart(fig_score, width="stretch")

    st.markdown(f"**{name} 순위 추이** (규모 구분 내)")
    fig_rank = px.line(
        ticker_history, x="date", y="rank", markers=True,
        labels={"date": "날짜", "rank": "순위"},
    )
    fig_rank.update_yaxes(autorange="reversed", dtick=1)
    fig_rank.update_layout(height=280)
    st.plotly_chart(fig_rank, width="stretch")


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
    # 예전 파이프라인 실행분(배당일정 컬럼 추가 전)과의 호환용 — 없으면 빈 값으로 채움.
    # 아직 배당지급일이 공시 안 된 종목은 원본 데이터 자체가 비어있어 NaN이 되는데,
    # 화면에 "NaN"으로 안 보이게 "-"로 통일 (2026-08-04 검수에서 280건 확인, 채점엔 무관).
    for col in ("recent_dividend_record_date", "recent_dividend_pay_date"):
        if col not in quant_df.columns:
            quant_df[col] = ""
        quant_df[col] = quant_df[col].fillna("-")

    # 예전 실행분과의 호환용 (업종/시가총액 컬럼 추가 전) — 없으면 빈 값으로 채움
    if "industry" not in quant_df.columns:
        quant_df["industry"] = "미분류"
    if "market_cap" not in quant_df.columns:
        quant_df["market_cap"] = 0
    quant_df["industry"] = quant_df["industry"].fillna("미분류")

    # KRX가 코스피 대형주/중형주/소형주 지수를 나눌 때 쓰는 것과 같은 기준 —
    # 임의 금액 기준이 아니라 시가총액 순위 1~100/101~300/301~ 로 구분.
    market_cap_rank = quant_df["market_cap"].rank(ascending=False, method="first")
    quant_df["규모구분"] = pd.cut(
        market_cap_rank, bins=[0, 100, 300, len(quant_df)],
        labels=["대형주(1~100위)", "중형주(101~300위)", "소형주(301위~)"],
    )

    weights = sidebar_weights()

    # 규모(대형/중형/소형주)별로 각각 top-30 — 전체 기준으로만 뽑으면 유망한 소형주가
    # 대형주에 밀려 애초에 정성평가 후보에도 못 드는 문제가 있어서(2026-08-05 결정)
    # 규모별 독립 랭킹으로 변경. 최대 30×3=90개가 정성평가 대상이 됨.
    quant_df["is_top30_candidate"] = quant_df.groupby("규모구분", observed=True)["quant_subtotal"].rank(
        ascending=False, method="first"
    ) <= TOP_N_FOR_QUAL

    # 업종 내 상대 밸류에이션 — 절대 PER/PBR 대신 "업종 중앙값 대비 몇 %"로 비교.
    # 평균 대신 중앙값을 쓰는 이유: PER은 이익이 0에 가까운 회사에서 수백~수천까지
    # 튀는 경우가 흔해서(2026-08-04 검수에서 PER 4255 확인) 평균은 그 몇 개에 쉽게 왜곡됨.
    valid_per = quant_df[quant_df["per"] > 0]
    valid_pbr = quant_df[quant_df["pbr"] > 0]
    industry_median_per = valid_per.groupby("industry")["per"].median()
    industry_median_pbr = valid_pbr.groupby("industry")["pbr"].median()
    quant_df["업종중앙값_per"] = quant_df["industry"].map(industry_median_per)
    quant_df["업종중앙값_pbr"] = quant_df["industry"].map(industry_median_pbr)
    quant_df["per_상대값"] = (quant_df["per"] / quant_df["업종중앙값_per"] - 1) * 100
    quant_df["pbr_상대값"] = (quant_df["pbr"] / quant_df["업종중앙값_pbr"] - 1) * 100

    qual_df = compute_qual_scores(quant_df["ticker"].astype(str).tolist())
    df = quant_df.merge(qual_df, on="ticker", how="left")

    weighted_quant = sum(df[k] * w for k, w in weights.items() if k in QUANT_ITEMS)
    weighted_qual = sum(df[k] * w for k, w in weights.items() if k in QUAL_ITEMS)
    df["weighted_total"] = weighted_quant + weighted_qual

    df = df.sort_values("weighted_total", ascending=False).reset_index(drop=True)

    st.subheader("필터")
    filter_cols = st.columns(5)
    with filter_cols[0]:
        industries = st.multiselect("업종", sorted(df["industry"].unique()), placeholder="전체 업종")
    with filter_cols[1]:
        size_groups = st.multiselect(
            "기업 규모", ["대형주(1~100위)", "중형주(101~300위)", "소형주(301위~)"],
            default=["대형주(1~100위)"],
            help="KRX가 코스피 대형주/중형주/소형주 지수를 나눌 때 쓰는 것과 같은 기준 — "
            "시가총액 순위 1~100위/101~300위/301위 이하. 기본값은 대형주만 보이게 "
            "설정돼 있고, 여기서 지우거나 다른 걸 추가하면 됩니다.",
        )
    with filter_cols[2]:
        min_yield = st.number_input("배당수익률 최소(%)", min_value=0.0, value=0.0, step=0.5)
    with filter_cols[3]:
        max_per = st.number_input("PER 최대 (0=제한없음)", min_value=0.0, value=0.0, step=1.0)
    with filter_cols[4]:
        max_pbr = st.number_input("PBR 최대 (0=제한없음)", min_value=0.0, value=0.0, step=0.1)

    if industries:
        df = df[df["industry"].isin(industries)]
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
    # 종목명 셀 자체를 네이버증권 링크로 — URL 뒤에 #종목명을 붙여두고 LinkColumn의
    # display_text 정규식으로 그 부분만 뽑아 보여주는 방식(각 행마다 다른 텍스트를
    # 보여줄 수 있는 유일한 방법 — display_text는 URL 문자열에서만 추출 가능하기 때문).
    df["종목명"] = df.apply(
        lambda r: NAVER_STOCK_URL.format(ticker=r["ticker"]) + "#" + r["name"], axis=1
    )
    # dividend_yield_pct == -1은 "이상치로 확인돼 임시 보류 중"이라는 내부 표식 —
    # 화면에는 숫자 대신 N/A로 보여줌 (2026-08-04, 미원화학/INVENI/대한제분/현대엘리베이터 등)
    df["배당수익률 표시"] = df["dividend_yield_pct"].apply(
        lambda v: "N/A ⚠️" if v < 0 else f"{v:.2f}%"
    )
    df["시가총액 표시"] = df["market_cap"].apply(lambda v: f"{v:,.0f}억원" if v else "-")
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
        "ticker": "코드",
        "quant_subtotal": "정량 소계",
        "is_top30_candidate": "정성평가 대상",
        "industry": "업종",
        "per": "PER",
        "PER 상대값 표시": "PER(업종중앙값 대비)",
        "pbr": "PBR",
        "PBR 상대값 표시": "PBR(업종중앙값 대비)",
        "시가총액 표시": "시가총액",
        "규모구분": "기업 규모",
        "recent_dividend_record_date": "최근 배당기준일",
        "recent_dividend_pay_date": "배당지급일",
    }

    show_all_cols = st.toggle(
        "전체 컬럼 보기",
        value=False,
        help="기본은 모바일에서도 보기 편하게 핵심 컬럼만 표시합니다. "
        "PER·PBR·배당일 등 나머지 컬럼은 이 토글을 켜면 볼 수 있어요.",
    )
    display_cols = {**compact_cols, **extra_cols} if show_all_cols else compact_cols

    # LinkColumn과 on_select(행 선택)를 같은 dataframe에 같이 쓰면 링크 렌더링 자체가
    # 깨지는 걸 확인함(2026-08-03, 실사용 중 발견) — 그래서 링크 전용 표 + 배점 상세는
    # 완전히 분리된 selectbox로 나눔.
    st.caption("종목명을 클릭하면 네이버증권 페이지로 이동합니다.")
    st.dataframe(
        df[list(display_cols.keys())].rename(columns=display_cols),
        width="stretch",
        hide_index=True,
        column_config={
            "종목명": st.column_config.LinkColumn(display_text=r"#(.+)$"),
            "배당수익률(%)": st.column_config.Column(
                help="연간 주당배당금(DART 사업보고서 기준) ÷ 오늘 현재가(KIS) × 100. "
                "결산 시점 주가가 아니라 '오늘 이 가격에 사면 얼마인지' 기준입니다. "
                "네이버증권과 같은 방식이며, 주식분할 등으로 계산값이 비정상적으로 크게 "
                "나오는 경우 DART 공시 수치로 자동 대체됩니다. N/A로 표시된 종목은 "
                "수치가 이상치로 확인돼 원인 파악 전까지 임시로 보류 중인 상태입니다."
            ),
            "총점(가중치 반영)": st.column_config.Column(
                help="정량 9개 + 정성 4개 항목 점수에 사이드바 가중치를 곱해 합산한 값. "
                "항목별 배점 내역은 아래 '배점 상세 보기'에서 종목을 선택하면 볼 수 있어요."
            ),
            "최근 배당기준일": st.column_config.Column(
                help="이 날짜까지 주식을 보유하고 있어야 가장 최근 배당을 받을 수 있었습니다 "
                "(한국예탁결제원 배당일정 기준)."
            ),
            "배당지급일": st.column_config.Column(
                help="배당기준일에 해당하는 배당금이 실제로 지급되는(됐던) 날짜입니다."
            ),
            "PER(업종중앙값 대비)": st.column_config.Column(
                help="같은 업종(KIND 업종분류 기준) 종목들의 PER 중앙값과 비교한 값. "
                "-30%면 업종 내에서 상대적으로 저평가, +30%면 상대적으로 고평가라는 뜻. "
                "평균이 아니라 중앙값을 쓰는 이유는 적자 근처 회사의 PER이 수백~수천까지 "
                "튀는 경우가 많아 평균이 쉽게 왜곡되기 때문입니다."
            ),
            "PBR(업종중앙값 대비)": st.column_config.Column(
                help="같은 업종 종목들의 PBR 중앙값과 비교한 값. -30%면 업종 내 상대적 저평가."
            ),
            "시가총액": st.column_config.Column(help="KIS 기준 오늘자 시가총액 (억원 단위)."),
        },
    )

    st.caption(
        f"총 {len(df)}개 종목 · 대형/중형/소형주 각각 정량 데이터 기준 상위 {TOP_N_FOR_QUAL}개씩"
        f"(최대 {TOP_N_FOR_QUAL * 3}개)만 '정성평가 입력' 페이지에서 사람이 직접 점수를 넣을 수 있습니다."
    )

    st.divider()
    st.subheader("업종 분포")
    top_n_for_chart = st.slider("상위 몇 개 종목의 업종 분포를 볼까요?", 5, min(100, len(df)), min(20, len(df)))
    chart_source = df.head(top_n_for_chart)["industry"].value_counts().reset_index()
    chart_source.columns = ["업종", "종목 수"]
    fig_industry = px.pie(chart_source, names="업종", values="종목 수", hole=0.4)
    fig_industry.update_layout(height=420)
    st.plotly_chart(fig_industry, width="stretch")

    st.divider()
    st.subheader("배점 상세 보기")
    options = [f"{r['순위']}. {r['name']} ({r['ticker']})" for _, r in df.iterrows()]
    picked = st.selectbox("종목을 선택하면 항목별 배점 내역을 볼 수 있어요", options, index=None,
                           placeholder="종목 선택...")
    if picked:
        picked_ticker = picked.split("(")[-1].rstrip(")")
        selected = df.loc[df["ticker"] == picked_ticker].iloc[0]
        render_score_breakdown(selected, weights)
        render_ticker_score_trend(load_history(), picked_ticker, selected["name"])

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
