"""
DART(전자공시시스템) Open API로 재무제표, 배당 이력, 자사주 매입·소각 공시를 수집.

인증키는 환경변수 DART_API_KEY로 전달 (opendart.fss.or.kr에서 발급).
API 문서: https://opendart.fss.or.kr/guide/main.do
"""

from __future__ import annotations

import io
import os
import zipfile

import requests

DART_BASE_URL = "https://opendart.fss.or.kr/api"


class DartClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DART_API_KEY")
        if not self.api_key:
            raise RuntimeError("DART_API_KEY가 설정되지 않았습니다.")

    def _get(self, endpoint: str, **params) -> dict:
        params["crtfc_key"] = self.api_key
        resp = requests.get(f"{DART_BASE_URL}/{endpoint}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def corp_code_map(self) -> dict[str, str]:
        """종목코드(6자리) → DART 고유번호(corp_code) 매핑.

        corpCode.xml.zip 하나를 통째로 받아오는 엔드포인트라 캐싱해서 재사용할 것.
        """
        resp = requests.get(
            f"{DART_BASE_URL}/corpCode.xml", params={"crtfc_key": self.api_key}, timeout=30
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

    def treasury_stock_disclosures(self, corp_code: str, start_date: str, end_date: str) -> dict:
        """자기주식취득/처분 관련 공시 목록. pblntf_detail_ty=I001(자기주식취득), I002(자기주식처분) 등.

        실키로 확인해보니 이 필터가 적용되지 않고 전체 공시가 반환됨(2026-08-03 테스트).
        report_nm에 "자기주식취득"/"자기주식처분"이 포함된 건만 클라이언트에서
        걸러내는 방식으로 바꿔야 함 — 아직 미수정.
        """
        return self._get(
            "list.json",
            corp_code=corp_code,
            bgn_de=start_date,
            end_de=end_date,
            pblntf_detail_ty="I001",
        )

    def dividend_info(self, corp_code: str, year: str, report_code: str = "11011") -> dict:
        """배당에 관한 사항 (사업보고서 내 배당 관련 상세)."""
        return self._get(
            "alotMatter.json",
            corp_code=corp_code,
            bsns_year=year,
            reprt_code=report_code,
        )


if __name__ == "__main__":
    client = DartClient()
    mapping = client.corp_code_map()
    print(f"corp_code 매핑 {len(mapping)}건 로드")
    samsung_corp_code = mapping.get("005930")
    print("삼성전자 corp_code:", samsung_corp_code)
