"""Streamlit Community Cloud 대시보드가 비활성으로 잠들지 않도록 주기적으로 접속하는 스크립트."""

import os
import sys

import requests

URL = os.environ.get("STREAMLIT_APP_URL")


def main() -> int:
    if not URL:
        print("STREAMLIT_APP_URL 환경변수가 설정되지 않았습니다.")
        return 1

    try:
        resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"대시보드 핑 실패: {exc}")
        return 1

    print(f"대시보드 핑 성공: status={resp.status_code} final_url={resp.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
