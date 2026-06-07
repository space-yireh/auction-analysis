"""
download.py

탱크옥션(tankauction.com) 경매 사건 서류를 자동으로 다운로드하는 스크립트.
URL 또는 tid를 입력 받아 로그인 후 서류를 docs/{사건번호}_{물건번호}/ 폴더에 저장합니다.
"""

import re
import sys
import json
import time
import random
import logging
import argparse
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))
from session import create_session, login, load_cookies, check_session_expired

BASE_URL = "https://www.tankauction.com"

# (저장 접두사, 저장 확장자)
# json 카테고리: fileShow.php 렌더링 결과를 .html 로 저장
# pdf  카테고리: 파일경로 직접 다운로드
CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "사건내역":   ("AA-사건내역",   "html"),
    "기일내역":   ("AB-기일내역",   "html"),
    "문건/송달":  ("AC-문건송달",   "html"),
    "현황조사서": ("AD-현황조사서", "html"),
    "부동산표시": ("AE-부동산표시", "html"),
    "감정평가서": ("AF-감정평가서", "pdf"),
    "매물명세서": ("AG-매물명세서", "pdf"),
    "토지등기":   ("DA-토지등기",   "pdf"),
    "건물등기":   ("DB-건물등기",   "pdf"),
    "세대열람":   ("EA-세대열람",   "pdf"),
    "건축물대장": ("EC-건축물대장", "pdf"),
}


def extract_tid(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    tid_list = params.get("tid", [])
    if not tid_list:
        logger.error(f"URL에서 tid를 찾을 수 없습니다: {url}")
        sys.exit(1)
    return tid_list[0]


def parse_case_info(html: str, tid: str) -> tuple[str, str]:
    sa_no_match = re.search(r"(\d{4}타경\d+)", html)
    maemul_match = re.search(r"물건번호\s*[:\s]+(\d+)", html)
    sa_no = sa_no_match.group(1) if sa_no_match else f"tid{tid}"
    maemul_no = maemul_match.group(1) if maemul_match else "1"
    return sa_no, maemul_no


def fetch_dt_data(session: requests.Session, tid: str) -> dict:
    """caFile.php 에서 var dtData = {...}; 를 파싱해 반환합니다."""
    url = f"{BASE_URL}/ca/caFile.php?tid={tid}&tp=AA&idx=0&free="
    logger.info(f"dtData 페이지 요청: {url}")

    resp = session.get(url, timeout=15)

    if check_session_expired(resp.text):
        sys.exit(1)

    match = re.search(r"var\s+dtData\s*=\s*(\{.*?\});", resp.text, re.DOTALL)
    if not match:
        logger.warning("dtData를 찾을 수 없습니다. 빈 딕셔너리로 계속 진행합니다.")
        return {}

    try:
        dt_data = json.loads(match.group(1))
        logger.info(f"dtData 파싱 완료. 카테고리 키 수: {len(dt_data)}")
        return dt_data
    except json.JSONDecodeError as e:
        logger.warning(f"dtData JSON 파싱 실패: {e}. 빈 딕셔너리로 계속 진행합니다.")
        return {}


def _resolve_category_entries(dt_data: dict, category: str, tp_code: str) -> list[dict]:
    """
    dtData에서 해당 카테고리의 항목 리스트를 반환합니다.
    키가 한글(사건내역)인 경우와 tp코드(AA)인 경우를 모두 시도합니다.
    """
    raw = dt_data.get(category) or dt_data.get(tp_code)
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = raw.get("list") or raw.get("files") or [raw]
    if not isinstance(raw, list):
        raw = [raw]
    return [item if isinstance(item, dict) else {"idx": item} for item in raw]


def _get_download_url(entry: dict, tid: str) -> tuple[str, bool] | tuple[None, None]:
    """
    dtData 항목에서 다운로드 URL과 텍스트 저장 여부를 반환합니다.

    - 확장자가 json: fileShow.php 렌더링 URL → (url, as_text=True)
    - 그 외(pdf 등): 파일경로 직접 URL     → (url, as_text=False)
    """
    path = entry.get("파일경로") or entry.get("filePath") or ""
    path = path.replace("\\/", "/")
    if not path:
        return None, None

    ext = entry.get("확장자", "")

    if ext == "json":
        idx  = entry.get("idx", "")
        sn   = entry.get("사건번호", "")
        wdt  = entry.get("수집일", "")
        url  = (
            f"{BASE_URL}/inc/fileShow.php"
            f"?idx={idx}&tid={tid}&sn={sn}&wdt={wdt}&filePath={path}"
        )
        return url, True

    # PDF 등 바이너리 직접 다운로드
    if path.startswith("http"):
        return path, False
    return (f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"), False


def download_file(
    session: requests.Session, url: str, dest: Path, as_text: bool = False
) -> bool:
    """파일을 다운로드해 저장합니다. as_text=True 이면 UTF-8 텍스트로, False 이면 바이너리로 저장합니다."""
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"다운로드 실패 (HTTP {resp.status_code}): {url}")
            return False

        content_type = resp.headers.get("Content-Type", "")

        if not as_text and "text/html" in content_type:
            if check_session_expired(resp.text):
                logger.error("세션 만료 — 재실행 필요")
                sys.exit(1)
            logger.warning(f"바이너리 URL이 HTML을 반환했습니다 (건너뜀): {url}")
            return False

        if as_text:
            dest.write_text(resp.text, encoding="utf-8")
        else:
            dest.write_bytes(resp.content)

        logger.info(f"저장: {dest.name} ({len(resp.content)} bytes)")
        return True
    except requests.RequestException as e:
        logger.warning(f"다운로드 오류 ({url}): {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="탱크옥션 서류 다운로드")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="탱크옥션 caView.php URL")
    group.add_argument("--tid", help="탱크옥션 tid")
    args = parser.parse_args()

    tid = extract_tid(args.url) if args.url else args.tid
    logger.info(f"대상 tid: {tid}")

    # 세션 준비: 브라우저 쿠키 우선, 없으면 로그인
    session = create_session()
    if not load_cookies(session):
        login(session)

    # 상세페이지 가져오기
    detail_url = f"{BASE_URL}/ca/caView.php?tid={tid}"
    logger.info(f"상세페이지 요청: {detail_url}")
    resp = session.get(detail_url, timeout=15)

    if check_session_expired(resp.text):
        sys.exit(1)

    detail_html = resp.text

    # 사건번호·물건번호 추출
    sa_no, maemul_no = parse_case_info(detail_html, tid)
    logger.info(f"사건번호: {sa_no} / 물건번호: {maemul_no}")

    # 저장 폴더 준비
    docs_root = Path(__file__).parent.parent / "docs"
    folder_name = f"{sa_no}_{maemul_no}"
    save_dir = docs_root / folder_name
    meta_path = save_dir / "meta.json"

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("completed"):
                print(f"이미 수집 완료: {save_dir}")
                return
        except (json.JSONDecodeError, OSError):
            pass

    save_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"저장 폴더: {save_dir}")

    saved_files: list[str] = []

    # dtData 파싱
    time.sleep(random.uniform(1.0, 2.0))
    dt_data = fetch_dt_data(session, tid)

    # 카테고리별 다운로드
    for category, (prefix, save_ext) in CATEGORY_MAP.items():
        entries = _resolve_category_entries(dt_data, category, prefix[:2])

        if not entries:
            logger.info(f"카테고리 없음 (건너뜀): {category}")
            continue

        for seq, entry in enumerate(entries, start=1):
            file_url, as_text = _get_download_url(entry, tid)
            if not file_url:
                logger.warning(f"URL 구성 실패 ({category} #{seq}): {entry}")
                continue

            filename = f"{prefix}.{save_ext}" if len(entries) == 1 else f"{prefix}-{seq}.{save_ext}"
            dest = save_dir / filename
            time.sleep(random.uniform(1.0, 2.0))
            if download_file(session, file_url, dest, as_text=as_text):
                saved_files.append(filename)

    # meta.json 저장
    meta_data = {
        "tid": tid,
        "sa_no": sa_no,
        "maemul_no": maemul_no,
        "saved_files": saved_files,
        "completed": True,
        "crawled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료: docs/{folder_name}/ - 총 {len(saved_files)}개 파일 저장")


if __name__ == "__main__":
    main()
