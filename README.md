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
   → `data/kospi_tickers.csv` (833개 종목, KRX KIND 상장법인목록 다운로드 페이지 사용.
   data.krx.co.kr의 MDC 통계 API는 봇 차단이 심해서 대신 이 경로를 씀. 소스에 중복 행이
   섞여 있어 종목코드 기준으로 자동 제거함). 상장/폐지가 자주 있는 건 아니라 종목 구성은
   가끔(월 1회 정도)만 재실행하면 충분.
2. `DART_API_KEY`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` 환경변수 설정.
3. (선택이지만 권장) `uv run pipeline/health_check.py` — KIS/DART/KIND/Supabase 4곳이
   다 정상 응답하는지 먼저 확인. 실패하면 원인이 뭔지 출력하고 종료.
4. `uv run pipeline/run_pipeline.py` (mock 아님) 실행 — 정량 9개 항목 전부 실데이터로 채워짐.
   실패한 종목은 자동으로 최대 3패스까지 재시도하고, 마지막에 그래도 남은 실패만 출력함.

### KIS 토큰 관련 주의사항
KIS 접근토큰 발급 엔드포인트는 **분당 1회** 제한이 있음(하루 1회가 아님 — 흔히 헷갈리는 부분).
`fetch_kis.py`가 발급받은 토큰을 `.kis_token_cache.json`(gitignore됨)에 캐싱해서 재사용하므로
로컬에서 반복 실행해도 문제없지만, 이 파일을 지우고 여러 프로세스를 동시에/연달아 실행하면
레이트리밋에 걸릴 수 있음 — 그런 경우에도 파이프라인 자체는 65초 백오프 재시도로 복구됨.

## Streamlit Community Cloud 배포

1. 이 레포를 GitHub에 push.
2. share.streamlit.io에서 GitHub 계정으로 로그인 → "New app" → 이 레포 선택,
   main file path는 `dashboard/app.py`.
3. 앱 설정 → Secrets에 위 표의 키들을 `.streamlit/secrets.toml.example` 형식 그대로 붙여넣기.
4. 배포되면 뜨는 공개 URL을 지인들에게 공유. 각자 접속 시 가중치 조정은 세션별로 독립적으로 동작.

## 헬스체크 / 자동 실행

`pipeline/health_check.py`가 KIS/DART/KIND/Supabase 4곳에 가벼운 요청을 하나씩 보내 정상
응답하는지 확인함. GitHub Actions 워크플로(`update_scores.yml`)는 본 파이프라인(30~40분)을
실행하기 전에 이 헬스체크를 먼저 돌려서, 뭔가 죽어있으면 그 자리에서 실패하고 전체 실행을
낭비하지 않음. 헬스체크(또는 파이프라인)가 실패하면 GitHub Actions가 레포 소유자에게
자동으로 이메일 알림을 보냄 — 별도 Slack/Discord 웹훅 설정 없이 기본 제공되는 기능.

## 판정 기준 상세 (나중에 재검토할 수 있는 것들)

책 점수표를 그대로 코드화했지만, 원본 데이터에 없어서 우리가 별도로 정의해야 했던
기준들이 있음 — 나중에 "이 기준이 맞나?" 재검토할 수 있게 여기 정확히 남겨둠.

### 중복상장 여부 (dual_listed)
**정의: "과반 지분(지분율 > 50%) 자회사가 코스피/코스닥에 별도 상장돼 있음" AND
"본인이 지주회사(한국표준산업분류 업종코드 `64992`, 회사본부 및 지주회사)임"**

- 지분율·피투자회사명은 DART `otrCprInvstmntSttus.json`(타법인출자현황)에서, 상장 여부는
  피투자회사명을 코스피+코스닥 전체 상장사명과 대조(정규화 후 비교)해서 판정
  (`_is_majority_owned_and_listed`, `pipeline/run_pipeline.py`)
- 지주회사 여부는 DART `company.json`의 `induty_code == "64992"`로 판정
  (`DartClient.is_holding_company`, `pipeline/fetch_dart.py`)
- **지주회사 조건을 넣은 이유**: 지분율 조건만 보면 순수 지주회사 구조(하이트진로홀딩스↔
  하이트진로)뿐 아니라 M&A로 다른 상장사를 인수한 경우도 다 잡힘 — 예를 들어
  한국타이어앤테크놀로지는 한온시스템 지분 51%를 갖고 있지만 이건 M&A 인수이지
  지주회사 구조가 아님. 2026-08-04에 LG/SK/롯데지주/하이트진로홀딩스/한국앤컴퍼니(전부
  `64992`) vs 한국타이어앤테크놀로지/삼성물산/현대차(전부 다른 코드) 실키로 검증 완료.
- **알려진 한계**: 순수 지주회사인데 업종코드가 어떤 이유로 `64992`가 아니게 등록된
  경우는 놓칠 수 있음(현재까지 발견된 반례는 없음). 손자회사(자회사의 자회사) 상장은
  아직 안 봄 — 1단계 자회사만 확인.

### 배당수익률 (dividend_yield_pct)
**정의: 연간 주당 현금배당금(DART, 사업보고서 기준) ÷ 오늘 현재가(KIS) × 100**

- DART가 공시에 같이 적어주는 `현금배당수익률(%)` 필드를 쓰지 않고 직접 계산함 —
  그 필드는 결산일(예: 2025-12-31) 시점 주가 기준이라 "오늘 이 가격에 사면 배당수익률이
  얼마인가"를 보여주는 이 프로젝트 목적과 안 맞아서(2026-08-04 논의). 네이버증권 등
  대부분의 금융 정보 사이트도 현재가 기준으로 보여줌.
- DART 공시에서 "보통주" 표기가 회사마다 "보통주"/"보통주식" 등으로 달라서, 정확히
  일치하는 문자열 대신 접두어(`startswith`) 비교로 찾음 — 안 그러면 일부 회사(예:
  한국타이어앤테크놀로지)는 배당 데이터가 있는데도 조용히 0으로 나옴 (2026-08-04 발견/수정).
- **이상치 방어(주식분할 등)**: 계산값이 DART 자체 공시 `현금배당수익률(%)`의 3배를
  넘으면 DART 값으로 대체함. 원인 사례: 종목 015360(INVENI)이 2026년 초 주식분할을
  했는데, DART 사업보고서의 "주당 현금배당금"은 분할 전 기준·오늘 현재가는 분할 후
  기준이라 분모/분자 시점이 안 맞아 39.16%라는 비현실적인 값이 나왔음(정상 수치는
  8%대). 원본 공시문서를 파싱해 정확한 분할비율로 보정하는 방법도 검토했으나, DART에
  "주식분할결정"에 대한 구조화된 API가 없어(자기주식취득 등과 달리) 원문 텍스트 파싱이
  필요하고 회사마다 문구가 달라 불안정한 데다, 833종목 중 1건뿐인 드문 케이스라 이
  단순 배수 폴백으로 절충함(2026-08-04). 임계값 3배는 정교한 근거보다는 실용적 선택 —
  진짜 주가 폭락(분할 아닌 경우)까지 억누르지 않으면서 분할발 극단치는 잡아내는 선.
- **임시 N/A 보류**: 3배 폴백으로도 안 걸러지는 극단치 4건(미원화학/INVENI/대한제분/
  현대엘리베이터, 2026-08-04 발견)은 원인 파악 전까지 `dividend_yield_pct=-1`(N/A
  표식)로 임시 처리. 대시보드 "정책 안내" 페이지에 목록과 상태 공개.

### REITs·인프라펀드 제외 (pipeline/exclusions.py)
이 프로젝트는 일반 상장기업 대상 점수표라, REITs·인프라펀드는 애초에 채점 대상에서
제외함(2026-08-04 결정) — 부동산투자회사법 등 별도 회계·공시 체계를 써서 KIS가
PER/PBR을 안 주고 DART 배당 공시 방식도 달라, 자동 채점하면 정량 점수가 대부분 0으로
깔려 부당하게 낮은 점수를 받게 됨. `pipeline/exclusions.py`의 `EXCLUDED_TICKERS`에
26개 종목 하드코딩(이름에 "리츠" 포함 + 맥쿼리인프라/맵스리얼티/KB발해인프라 수동
확인). **주의**: KIND 업종코드("부동산 임대 및 공급업"/"신탁업 및 집합투자업")만으로
거르면 자이에스앤디·SK디앤디·이스타코(부동산 개발회사)·스틱인베스트먼트(PE
운용사)·한국자산신탁·한국토지신탁(신탁 서비스 운영회사) 같은 정상 영업기업까지
잘못 걸러지니, 반드시 이름 패턴 + 수동 확인을 병행할 것. 대시보드 "정책 안내"
페이지에 제외 목록과 근거 공개.

### 업종 / 시가총액 / 업종 내 상대 밸류에이션 (참고정보, 채점과 무관)
- **업종(industry)**: KIND 상장법인목록의 "업종" 컬럼을 그대로 씀(126개 분류,
  `fetch_ticker_list.py`가 `data/kospi_tickers.csv`에 저장). DART 인증키 없이도
  구할 수 있어서 DART 한도와 무관하게 언제든 갱신 가능.
- **시가총액(market_cap)**: KIS `price_metrics()`가 이미 응답에 포함하고 있던
  `hts_avls` 필드를 그냥 꺼내 쓴 것 — 추가 API 호출 없음. 단위는 **억원**(KIS
  네이티브 단위, 한국 금융권에서 흔히 쓰는 표기라 그대로 둠).
- **업종 내 상대 밸류에이션**: 절대 PER/PBR 대신 "같은 업종 종목들의 중앙값 대비
  몇 %"로 대시보드에 표시(`dashboard/app.py`). **평균이 아니라 중앙값**을 쓰는
  이유 — 적자에 가까운 회사는 PER이 수백~수천까지 튀는 경우가 흔해서(2026-08-04
  검수에서 PER 4255 확인) 평균을 쓰면 극소수 종목에 전체 평균이 왜곡됨. 업종 분류
  자체가 126개로 세분화돼 있어 일부 업종은 표본이 작아(2~3개) 중앙값 비교의
  신뢰도가 낮을 수 있음 — 참고용으로만 볼 것.

## 알려진 TODO

- `pipeline/fetch_dart.py`의 `treasury_stock_disclosures()`: `pblntf_detail_ty` 필터가
  실키 테스트에서 적용 안 되는 것 확인 — 지금은 안 쓰고 있음(자사주매입 판정은
  `tsstkAqDecsn.json`으로 대체). 필요해지면 report_nm 텍스트 매칭으로 다시 구현할 것.
- "소각 비율"(cancel_ratio_pct)은 실제 소각 여부를 확인할 방법이 없어 자기주식취득
  결정 규모로 근사 중 — 매입해도 소각 안 하는 경우 과대추정 가능성 있음.
