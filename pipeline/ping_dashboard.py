"""
Streamlit Community Cloud 대시보드가 비활성으로 잠들지 않도록 주기적으로 "실제 방문"을
흉내 내는 스크립트.

원래는 requests로 단순 GET만 보냈는데, 이건 슬립 방지 효과가 없다는 게 실사용 중
확인됨(2026-08-24 — 핑은 매일 "성공"으로 찍혔는데도 두 대시보드 모두 슬립 상태가
됨). 원인: Streamlit Cloud의 최상위 URL은 모든 앱이 공유하는 정적 프런트엔드 셸을
서빙하고, 실제 앱은 그 안의 iframe에서 별도 웹소켓 세션으로 구동됨 — 즉 GET 하나로는
그 iframe도 안 열리고 앱 컨테이너에 연결도 안 되니, "방문"으로 전혀 집계되지 않았을
가능성이 높음. 그래서 실제 브라우저(Playwright)로 페이지를 열어 iframe이 로드되고
앱 콘텐츠가 실제로 렌더되는 것까지 확인 — 잠들어 있으면 "Yes, get this app back up!"
버튼을 찾아 클릭해서 직접 깨움.
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import Page, sync_playwright

URL = os.environ.get("STREAMLIT_APP_URL")
WAKE_BUTTON_TEXT = "get this app back up"
WAKE_WAIT_MS = 60_000
POLL_INTERVAL_MS = 5_000
MAX_WAIT_MS = 120_000


def _all_frames(page: Page):
    return [page.main_frame, *page.main_frame.child_frames]


def _try_click_wake_button(page: Page) -> bool:
    for frame in _all_frames(page):
        try:
            button = frame.get_by_text(WAKE_BUTTON_TEXT, exact=False)
            if button.count() > 0:
                button.first.click(timeout=5_000)
                return True
        except Exception:  # noqa: BLE001 — 프레임이 detach된 채로 남아있는 경우 등 무시하고 다음 프레임 확인
            continue
    return False


def _app_rendered(page: Page) -> bool:
    """실제 앱 콘텐츠가 렌더됐는지 — Streamlit 메인 컨테이너 존재로 판단(잠든 화면엔 없음)."""
    for frame in _all_frames(page):
        try:
            if frame.locator('[data-testid="stAppViewContainer"]').count() > 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def main() -> int:
    if not URL:
        print("STREAMLIT_APP_URL 환경변수가 설정되지 않았습니다.")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(URL, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(3_000)  # iframe/웹소켓 초기 연결 여유

            if _try_click_wake_button(page):
                print("앱이 잠들어 있었음 — 깨우기 버튼 클릭, 재기동 대기 중")
                page.wait_for_timeout(WAKE_WAIT_MS)

            waited = 0
            while not _app_rendered(page) and waited < MAX_WAIT_MS:
                page.wait_for_timeout(POLL_INTERVAL_MS)
                waited += POLL_INTERVAL_MS

            if not _app_rendered(page):
                print(f"실패: {MAX_WAIT_MS / 1000:.0f}초 대기해도 앱 콘텐츠가 렌더되지 않음")
                return 1

            print(f"성공: {URL} 앱이 실제로 렌더된 것까지 확인")
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"핑 실패: {type(e).__name__}: {e}")
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
