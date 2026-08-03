# 코스피 저평가 우량 배당주 스코어링 대시보드

책 5장 "종목 선정 기준"의 점수표(PER/PBR/배당수익률/자사주 매입·소각/성장성 등 13개 항목)를
코스피 전종목에 적용해 정량 항목은 자동 채점, 정성 항목(top-30)은 사람이 입력하는 대시보드.

## 아키텍처

```
GitHub Actions(매일) → pipeline/run_pipeline.py
    (fetch_kis.py: 시세/PER/PBR/배당, fetch_dart.py: 재무제표/자사주/배당이력)
    → pipeline/scoring.py로 채점 → data/scores_quant.csv 커밋

Streamlit Community Cloud → dashboard/app.py
    → scores_quant.csv 로드 + 가중치 슬라이더(세션별, 로그인 불필요)
    → dashboard/pages/01_정성평가_입력.py: top-30 정성점수 입력(공유 비밀번호)
    → dashboard/db.py: Supabase에 정성점수 · 가중치 프리셋 저장
```

## 로컬 개발 (uv)

```bash
# 최초 1회
curl -LsSf https://astral.sh/uv/install.sh | sh

# mock 데이터로 파이프라인 + 대시보드 확인 (API 키 불필요)
uv run pipeline/run_pipeline.py --mock
uv run streamlit run dashboard/app.py
```

## 필요한 외부 계정/키

| 항목 | 발급처 | 용도 | 환경변수 / secrets 키 |
|---|---|---|---|
| KIS 앱키/시크릿 | apiportal.koreainvestment.com | 시세, PER/PBR, 배당 | `KIS_APP_KEY`, `KIS_APP_SECRET` |
| DART 인증키 | opendart.fss.or.kr | 재무제표, 자사주 공시, 배당이력 | `DART_API_KEY` |
| Supabase URL/anon key | supabase.com | 정성점수·가중치 프리셋 저장 | `SUPABASE_URL`, `SUPABASE_ANON_KEY` |
| 정성평가 편집 비밀번호 | 직접 정하기 | top-30 정성점수 편집 페이지 보호 | `QUAL_EDIT_PASSWORD` |

로컬에서는 `.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사해서 값을 채우면 됨(git에는 커밋되지 않음).

## Supabase 테이블 생성 (최초 1회, SQL Editor에서 실행)

```sql
create table presets (
  nickname text primary key,
  weights jsonb not null,
  updated_at timestamptz not null default now()
);

create table qual_scores (
  ticker text primary key,
  profit_sustainable boolean,
  growth_potential text,
  management text,
  global_brand boolean,
  editor text,
  updated_at timestamptz not null default now()
);
```

## 실데이터 파이프라인 실행 전 준비

1. 코스피 전종목 티커 목록 생성: `uv run pipeline/fetch_ticker_list.py`
   → `data/kospi_tickers.csv` (848개 종목, KRX KIND 상장법인목록 다운로드 페이지 사용.
   data.krx.co.kr의 MDC 통계 API는 봇 차단이 심해서 대신 이 경로를 씀). 상장/폐지가
   자주 있는 건 아니라 종목 구성은 가끔(월 1회 정도)만 재실행하면 충분.
2. `DART_API_KEY`, `KIS_APP_KEY`, `KIS_APP_SECRET` 환경변수 설정.
3. `uv run pipeline/run_pipeline.py` (mock 아님) 실행 — PER/PBR은 실데이터로 채워짐.

## Streamlit Community Cloud 배포

1. 이 레포를 GitHub에 push.
2. share.streamlit.io에서 GitHub 계정으로 로그인 → "New app" → 이 레포 선택,
   main file path는 `dashboard/app.py`.
3. 앱 설정 → Secrets에 위 표의 키들을 `.streamlit/secrets.toml.example` 형식 그대로 붙여넣기.
4. 배포되면 뜨는 공개 URL을 지인들에게 공유. 각자 접속 시 가중치 조정은 세션별로 독립적으로 동작.

## 알려진 TODO

- `pipeline/run_pipeline.py`의 `fetch_live_quant()`: 중복상장·배당수익률·배당연속인상연수·
  자사주매입소각 등 DART 데이터 매핑 아직 미구현 (현재는 PER/PBR만 실데이터, 나머지는
  TODO 플레이스홀더 — 정성평가 대상 top-30 선정이 quant_subtotal 기준이라 이 항목들이
  채워지기 전까지는 순위가 부정확함)
- `pipeline/fetch_dart.py`의 `treasury_stock_disclosures()`: `pblntf_detail_ty` 필터가
  실키 테스트에서 적용 안 되는 것 확인 — report_nm 텍스트 매칭으로 대체 필요
