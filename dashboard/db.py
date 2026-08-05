"""
Supabase 연동: 가중치 프리셋(닉네임 기반)과 top-30 정성 점수를 저장/조회.

Supabase 프로젝트가 아직 없거나 secrets가 설정되지 않은 로컬 개발 환경에서는
모든 함수가 조용히 비활성화되어(None/빈 값 반환) 대시보드 나머지 기능은 그대로 동작한다.

필요한 테이블 (Supabase SQL Editor에서 1회 생성, README 참고):
  presets(nickname text primary key, weights jsonb, updated_at timestamptz default now())
  qual_scores(ticker text primary key, profit_sustainable boolean,
              growth_potential text, management text, global_brand boolean,
              editor text, updated_at timestamptz default now())
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


def save_preset(nickname: str, weights: dict) -> None:
    client = _get_client()
    if client is None:
        return
    client.table("presets").upsert({"nickname": nickname, "weights": weights}).execute()


def load_preset(nickname: str) -> dict | None:
    client = _get_client()
    if client is None:
        return None
    resp = client.table("presets").select("weights").eq("nickname", nickname).limit(1).execute()
    if resp.data:
        return resp.data[0]["weights"]
    return None


def save_qual_score(ticker: str, qual: dict, editor: str) -> None:
    client = _get_client()
    if client is None:
        return
    row = {"ticker": ticker, "editor": editor, **qual}
    client.table("qual_scores").upsert(row).execute()


def load_all_qual_scores() -> dict[str, dict]:
    client = _get_client()
    if client is None:
        return {}
    resp = client.table("qual_scores").select("*").execute()
    return {row["ticker"]: row for row in resp.data}
