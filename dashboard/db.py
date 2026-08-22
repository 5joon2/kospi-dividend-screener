"""
Supabase 연동: 가중치 프리셋(닉네임 기반)과 top-30 정성 점수를 저장/조회.

Supabase 프로젝트가 아직 없거나 secrets가 설정되지 않은 로컬 개발 환경에서는
모든 함수가 조용히 비활성화되어(None/빈 값 반환) 대시보드 나머지 기능은 그대로 동작한다.

필요한 테이블 (Supabase SQL Editor에서 1회 생성, README 참고):
  presets(nickname text primary key, weights jsonb, updated_at timestamptz default now())
  qual_scores(ticker text primary key, profit_sustainable boolean,
              growth_potential text, management text, global_brand boolean,
              editor text, updated_at timestamptz default now())
  us_presets, us_qual_scores: 위 두 테이블과 완전히 같은 구조 — 미국판 대시보드
  (dashboard_us/app_us.py)가 market="us"로 호출해서 씀. 테이블을 따로 두는 이유는,
  같은 닉네임을 두 대시보드에서 재사용하면 가중치 프리셋이 서로 덮어써지기
  때문(2026-08-22 결정) — ticker는 KOSPI(6자리 숫자)/미국(알파벳) 형식이 서로
  안 겹치니 qual_scores까지 나눌 필요는 없었지만, presets와 테이블 구조를
  통일하는 게 관리하기 편해서 qual_scores도 같이 나눔.
"""

from __future__ import annotations

import os

import streamlit as st


def _get_client():
    # 일부러 캐싱 안 함 — st.cache_resource로 캐싱했다가, Secrets를 나중에 추가해도
    # 앱이 처음 뜰 때 "미설정" 상태로 캐시가 굳어서 수동 Reboot 전까지 계속
    # "Supabase가 설정되지 않았다"고 나오는 문제를 겪음(2026-08-05). Supabase 클라이언트
    # 생성 자체는 가벼운 로컬 작업(네트워크 호출 없음)이라 매번 새로 만들어도 부담 없음.
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_ANON_KEY"]
    except (KeyError, FileNotFoundError):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        return None

    from supabase import create_client

    return create_client(url, key)


def is_configured() -> bool:
    return _get_client() is not None


def _table(name: str, market: str) -> str:
    return f"us_{name}" if market == "us" else name


def save_preset(nickname: str, weights: dict, market: str = "kr") -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.table(_table("presets", market)).upsert({"nickname": nickname, "weights": weights}).execute()
    except Exception as e:  # noqa: BLE001 — 테이블이 아직 없는 등의 이유로 죽여서
        # 대시보드 전체가 크래시하지 않게(모듈 docstring이 약속하는 "조용히 비활성화" 계약).
        # 미국판 테이블(us_presets 등)을 README SQL로 만들기 전에 이 상태를 실제로 겪음
        # (2026-08-22, AppTest로 발견).
        st.sidebar.error(f"프리셋 저장 실패: {e}")


def load_preset(nickname: str, market: str = "kr") -> dict | None:
    client = _get_client()
    if client is None:
        return None
    try:
        resp = (
            client.table(_table("presets", market))
            .select("weights").eq("nickname", nickname).limit(1).execute()
        )
    except Exception:  # noqa: BLE001
        return None
    if resp.data:
        return resp.data[0]["weights"]
    return None


def save_qual_score(ticker: str, qual: dict, editor: str, market: str = "kr") -> None:
    client = _get_client()
    if client is None:
        return
    row = {"ticker": ticker, "editor": editor, **qual}
    try:
        client.table(_table("qual_scores", market)).upsert(row).execute()
    except Exception as e:  # noqa: BLE001
        st.error(f"정성평가 저장 실패: {e}")


def load_all_qual_scores(market: str = "kr") -> dict[str, dict]:
    client = _get_client()
    if client is None:
        return {}
    try:
        resp = client.table(_table("qual_scores", market)).select("*").execute()
    except Exception:  # noqa: BLE001
        return {}
    return {row["ticker"]: row for row in resp.data}
