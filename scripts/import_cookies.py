"""
import_cookies.py

Cookie-Editor 확장 프로그램으로 내보낸 JSON을 scripts/cookies.json 형식으로 변환합니다.

사용법:
  python scripts/import_cookies.py <내보낸파일.json>

Cookie-Editor 설치:
  Chrome: https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

COOKIE_FILE = Path(__file__).parent / "cookies.json"
TARGET_DOMAIN = "tankauction.com"


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/import_cookies.py <내보낸파일.json>")
        print()
        print("Cookie-Editor 사용 방법:")
        print("  1. Chrome에서 tankauction.com 접속 후 로그인")
        print("  2. Cookie-Editor 확장 아이콘 클릭")
        print("  3. 우측 하단 'Export' → 'Export as JSON' 클릭")
        print("  4. 복사된 내용을 파일로 저장 (예: tank_cookies.json)")
        print("  5. python scripts/import_cookies.py tank_cookies.json 실행")
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"오류: 파일을 찾을 수 없습니다 — {src}")
        sys.exit(1)

    raw = json.loads(src.read_text(encoding="utf-8"))

    # Cookie-Editor 형식: list of dicts with name/value/domain/path/...
    # 배열이 아닌 경우 (단일 객체) 배열로 감싸기
    if isinstance(raw, dict):
        raw = [raw]

    cookies = [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", f".{TARGET_DOMAIN}"),
            "path": c.get("path", "/"),
        }
        for c in raw
        if TARGET_DOMAIN in c.get("domain", "")
    ]

    if not cookies:
        print(f"경고: {TARGET_DOMAIN} 관련 쿠키가 없습니다.")
        print("탱크옥션 페이지에서 내보냈는지 확인하세요.")
        sys.exit(1)

    data = {
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "domain": TARGET_DOMAIN,
        "cookies": cookies,
    }
    COOKIE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {len(cookies)}개 쿠키 저장 → {COOKIE_FILE.name}")
    print("이후 다운로드 작업은 저장된 쿠키를 자동으로 사용합니다.")


if __name__ == "__main__":
    main()
