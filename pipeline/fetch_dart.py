"""
DART(전자공시시스템) Open API로 재무제표, 배당 이력, 자사주 매입·소각 공시를 수집.

인증키는 환경변수 DART_API_KEY로 전달 (opendart.fss.or.kr에서 발급).
API 문서: https://opendart.fss.or.kr/guide/main.do

아래 엔드포인트들은 실키로 직접 호출해서 필드명을 확인한 것 (2026-08-03, 삼성전자 기준):
- alotMatter.json (배당에 관한 사항): 보통주 "현금배당수익률(%)" · "주당 현금배당금(원)" 포함
- stockTotqySttus.json (주식의 총수 현황): "합계" 행에 발행주식총수(istc_totqy)/자기주식수(tesstk_co)
- tsstkAqDecsn.json (자기주식취득결정): 취득예정 주식수·목적(aq_pp) 등
  * 자기주식취득결정은 "Acq"가 아니라 "Aq"로 줄여 씀 — 흔히 헷갈리는 부분.
"""

from __future__ import annotations

import io
import os
import zipfile

from http_retry import request_with_retry

DART_BASE_URL = "https://opendart.fss.or.kr/api"


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").strip()
    if cleaned in ("", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


class DartClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DART_API_KEY")
        if not self.api_key:
            raise RuntimeError("DART_API_KEY가 설정되지 않았습니다.")

    def _get(self, endpoint: str, **params) -> dict:
        params["crtfc_key"] = self.api_key
        resp = request_with_retry("GET", f"{DART_BASE_URL}/{endpoint}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def corp_code_map(self) -> dict[str, str]:
        """종목코드(6자리) → DART 고유번호(corp_code) 매핑.

        corpCode.xml.zip 하나를 통째로 받아오는 엔드포인트라 캐싱해서 재사용할 것.
        """
        resp = request_with_retry(
            "GET", f"{DART_BASE_URL}/corpCode.xml", params={"crtfc_key": self.api_key}, timeout=30
        )
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])

        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_bytes)
        mapping = {}
        for node in root.findall("list"):
            stock_code = (node.findtext("stock_code") or "").strip()
            corp_code = (node.findtext("corp_code") or "").strip()
            if stock_code:
                mapping[stock_code] = corp_code
        return mapping

    def financial_statements(self, corp_code: str, year: str, report_code: str = "11011") -> dict:
        """사업보고서 기준 단일회사 전체 재무제표 조회.

        report_code 11011=사업보고서(4분기), 11012=반기, 11013=1분기, 11014=3분기
        """
        return self._get(
            "fnlttSinglAcntAll.json",
            corp_code=corp_code,
            bsns_year=year,
            reprt_code=report_code,
            fs_div="CFS",  # 연결재무제표
        )

    def dividend_info(self, corp_code: str, year: str, report_code: str = "11011") -> dict:
        """배당에 관한 사항 (사업보고서 내 배당 관련 상세)."""
        return self._get(
            "alotMatter.json",
            corp_code=corp_code,
            bsns_year=year,
            reprt_code=report_code,
        )

    def _dividend_field(
        self, corp_code: str, year: str, se: str, report_code: str = "11011", stock_knd: str = "보통주"
    ) -> float | None:
        data = self.dividend_info(corp_code, year, report_code)
        for row in data.get("list", []):
            if row.get("se") == se and row.get("stock_knd") == stock_knd:
                return _parse_number(row.get("thstrm"))
        return None

    def dividend_yield_pct(self, corp_code: str, year: str) -> float | None:
        """사업보고서 기준 보통주 현금배당수익률(%)."""
        return self._dividend_field(corp_code, year, "현금배당수익률(%)")

    def common_dps(self, corp_code: str, year: str, report_code: str = "11011") -> float | None:
        """보통주 주당 현금배당금(원)."""
        return self._dividend_field(corp_code, year, "주당 현금배당금(원)", report_code=report_code)

    def has_quarterly_dividend(self, corp_code: str, year: str) -> bool:
        """1분기보고서에 주당 현금배당금이 존재하면 분기배당을 실시하는 것으로 판단."""
        return self.common_dps(corp_code, year, report_code="11013") is not None

    def dividend_increase_years(self, corp_code: str, latest_year: int, max_years: int = 15) -> int:
        """연속 배당 인상(동결 포함, 감소 시 중단) 연수.

        최신 연도부터 거슬러 올라가며 보통주 주당배당금을 비교 — 전년 대비
        감소한 해가 나오면 즉시 멈춤. 데이터가 없는 연도가 나와도 멈춤.
        """
        dps_by_year: dict[int, float] = {}
        for offset in range(max_years + 1):
            year = latest_year - offset
            dps = self.common_dps(corp_code, str(year))
            if dps is None:
                break
            dps_by_year[year] = dps

        years_desc = sorted(dps_by_year, reverse=True)
        streak = 0
        for newer, older in zip(years_desc, years_desc[1:]):
            if dps_by_year[newer] >= dps_by_year[older]:
                streak += 1
            else:
                break
        return streak

    def stock_totals(self, corp_code: str, year: str, report_code: str = "11011") -> dict:
        """주식의 총수 현황 (발행주식총수/자기주식수 등)."""
        return self._get(
            "stockTotqySttus.json", corp_code=corp_code, bsns_year=year, reprt_code=report_code
        )

    def treasury_ratio_pct(self, corp_code: str, year: str) -> float | None:
        """자기주식 보유비율(%) = 자기주식수 / 발행주식총수(자기주식 포함)."""
        data = self.stock_totals(corp_code, year)
        for row in data.get("list", []):
            if row.get("se") == "합계":
                total = _parse_number(row.get("istc_totqy"))
                treasury = _parse_number(row.get("tesstk_co"))
                if total:
                    return round(treasury / total * 100, 3) if treasury is not None else 0.0
        return None

    def treasury_acquisitions(self, corp_code: str, start_date: str, end_date: str) -> list[dict]:
        """자기주식취득결정 공시 목록 (주요사항보고서, tsstkAqDecsn)."""
        data = self._get("tsstkAqDecsn.json", corp_code=corp_code, bgn_de=start_date, end_de=end_date)
        return data.get("list", [])

    def investee_holdings(self, corp_code: str, year: str) -> list[dict]:
        """타법인출자현황 — 피투자회사명(inv_prm)/지분율(trmend_blce_qota_rt) 등.

        상장여부 필드는 없어서, 반환된 피투자회사명을 상장사명 집합과 대조해서
        "자회사·손자회사 상장 여부(중복상장)"를 판정하는 데 사용 (run_pipeline.py 참고).
        """
        data = self._get("otrCprInvstmntSttus.json", corp_code=corp_code, bsns_year=year, reprt_code="11011")
        return data.get("list", [])


if __name__ == "__main__":
    client = DartClient()
    mapping = client.corp_code_map()
    print(f"corp_code 매핑 {len(mapping)}건 로드")
    corp_code = mapping.get("005930")
    print("삼성전자 corp_code:", corp_code)
    print("배당수익률(%):", client.dividend_yield_pct(corp_code, "2025"))
    print("분기배당 여부:", client.has_quarterly_dividend(corp_code, "2025"))
    print("배당 연속 인상 연수:", client.dividend_increase_years(corp_code, 2025))
    print("자사주 보유비율(%):", client.treasury_ratio_pct(corp_code, "2025"))
    acquisitions = client.treasury_acquisitions(corp_code, "20240101", "20261231")
    print("최근 자사주취득결정 건수:", len(acquisitions))
