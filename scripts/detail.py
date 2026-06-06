"""
detail.py

낙찰된 경매 물건의 상세 페이지(참고자료 포함)에 접근하여
감정평가서/매각명세서(PDF), 사건/기일내역(JSON/HTML), 현장 사진 원본 등을 
안전하게 일괄 다운로드하고 로컬 스토리지에 인덱싱하는 상세 수집 모듈입니다.
"""

import re
import json
import time
import random
import logging
from urllib.parse import urljoin
import requests
from parser import AuctionItem
from storage import AuctionStorage
from session import check_session_expired

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tankauction.com"


def _extract_dt_data(html_content: str) -> Optional[dict]:
    """
    참고자료 HTML 소스코드 내 자바스크립트 변수 'dtData'를 정규표현식으로 추출하여
    파이썬 딕셔너리로 변환합니다.

    Args:
        html_content (str): caFile.php 호출로 반환받은 HTML 소스

    Returns:
        Optional[dict]: 파싱된 파일 데이터 딕셔너리, 실패 시 None
    """
    # var dtData = { ... }; 패턴 매칭
    pattern = r"var\s+dtData\s*=\s*(\{.*?\});"
    match = re.search(pattern, html_content, re.DOTALL)
    
    if not match:
        logger.warning("HTML 소스에서 dtData 자바스크립트 객체를 찾을 수 없습니다.")
        return None
        
    json_str = match.group(1)
    try:
        # JSON 파싱 진행
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"dtData JSON 디코딩 실패: {e}")
        return None


def download_file_with_delay(session: requests.Session, url: str) -> Optional[bytes]:
    """
    공통 대기 시간을 적용하여 파일을 다운로드합니다.
    (AGENTS.md 규칙: 개별 서류 다운로드 및 사진 조회 간 1.0 ~ 2.0초 무작위 대기)

    Args:
        session (requests.Session): 세션 객체
        url (str): 다운로드할 절대 URL

    Returns:
        Optional[bytes]: 다운로드된 파일 바이너리 데이터, 실패 시 None
    """
    # 다운로드 대기 시간
    delay = random.uniform(1.0, 2.0)
    logger.info(f"다운로드 대기 중 ({delay:.2f}초)... -> URL: {url}")
    time.sleep(delay)

    try:
        response = session.get(url, timeout=20)
        if response.status_code == 200:
            return response.content
        else:
            logger.warning(f"파일 다운로드 실패 (상태 코드: {response.status_code}) -> URL: {url}")
            return None
    except requests.RequestException as e:
        logger.error(f"파일 다운로드 중 네트워크 오류 발생: {e} -> URL: {url}")
        return None


def fetch_all_files(session: requests.Session, item: AuctionItem, storage: AuctionStorage) -> bool:
    """
    개별 사건의 메타데이터 요약을 저장하고, 관련된 상세 파일(PDF, JSON 등) 및 사진을 일괄 수집하여 저장합니다.
    도중에 파일 누락이나 다운로드 에러가 나더라도 건너뛰며 프로세스가 끊기지 않도록 설계되었습니다.

    Args:
        session (requests.Session): 로그인 세션 객체
        item (AuctionItem): 목록 수집을 통해 획득한 사건 정보 객체
        storage (AuctionStorage): 로컬 파일 저장소 인터페이스

    Returns:
        bool: 수집 프로세스가 정상 완료되어 meta.json에 완료 등록된 경우 True, 실패 시 False
    """
    case_id = f"{item.sa_no}_{item.maemul_no}"
    logger.info(f"사건 {case_id} (TID: {item.tid}) 상세 파일 수집 시작...")

    # 1. 참고자료 HTML 호출 (어떤 tp 값이든 전체 dtData가 수신되므로 tp=AA로 고정 호출)
    ca_file_url = f"{BASE_URL}/ca/caFile.php?tid={item.tid}&tp=AA&idx=0&free="
    
    # 딜레이 대기 후 호출
    time.sleep(random.uniform(1.0, 2.0))
    try:
        response = session.get(ca_file_url, timeout=15)
        if response.status_code != 200:
            logger.error(f"참고자료 HTML 조회 실패 (TID: {item.tid}, 상태: {response.status_code})")
            return False
            
        html = response.text
        
        # 세션 만료 여부 검증
        if check_session_expired(html):
            logger.error("세션이 유효하지 않습니다. 크롤링을 중단합니다.")
            return False
            
    except requests.RequestException as e:
        logger.error(f"참고자료 페이지 요청 중 오류 발생 (TID: {item.tid}): {e}")
        return False

    # 2. 자바스크립트 dtData 추출
    dt_data = _extract_dt_data(html)
    if not dt_data:
        logger.warning(f"사건 {case_id}의 파일 목록(dtData)을 추출할 수 없습니다. 수집을 건너뜁니다.")
        return False

    # 수집할 메타 정보 구성 (기본 딕셔너리로 저장)
    metadata = {
        "tid": item.tid,
        "sa_no": item.sa_no,
        "maemul_no": item.maemul_no,
        "ctgr": item.ctgr,
        "addr": item.addr,
        "apsl_amt": item.apsl_amt,
        "minb_amt": item.minb_amt,
        "deal_amt": item.deal_amt,
        "status": item.status,
        "bid_dt": item.bid_dt,
        "court": item.court,
        "files_downloaded": []
    }

    # 3. 문서 및 데이터 파일 다운로드 (감정평가서, 매물명세서, 등기, 현황조사서 등)
    # 다운로드할 수 있는 카테고리 리스트
    document_categories = [
        "사건내역", "기일내역", "문건/송달", "감정평가서", 
        "매물명세서", "토지등기", "건물등기", "세대열람", "건축물대장",
        "현황조사서", "부동산표시"
    ]

    for category in document_categories:
        file_list = dt_data.get(category, [])
        if not file_list:
            continue
            
        logger.info(f"카테고리 [{category}] 파일 {len(file_list)}건 다운로드 시도...")
        for f_idx, file_info in enumerate(file_list):
            file_path = file_info.get("파일경로")
            if not file_path:
                continue
                
            # 절대 URL 생성 (예: /FILE/CA/... -> https://www.tankauction.com/FILE/CA/...)
            absolute_url = urljoin(BASE_URL, file_path)
            
            # 저장할 파일명 설정
            # 예: 감정평가서_1.pdf, 사건내역_1.json 등
            ext = file_info.get("확장자", "pdf").lower()
            save_name = f"{category}_{f_idx + 1}.{ext}"
            
            # 다운로드 실행
            content_bytes = download_file_with_delay(session, absolute_url)
            if content_bytes:
                success = storage.save_file(case_id, save_name, content_bytes)
                if success:
                    metadata["files_downloaded"].append({
                        "category": category,
                        "file_name": save_name,
                        "url": absolute_url
                    })

    # 4. 현장 사진 원본 다운로드
    photo_list = dt_data.get("사진보기", [])
    if photo_list:
        logger.info(f"현장 사진 {len(photo_list)}건 다운로드 시도...")
        for p_idx, photo_info in enumerate(photo_list):
            thumb_path = photo_info.get("파일경로", "")
            if not thumb_path:
                continue
                
            # 썸네일 파일명에서 'T_'를 제거하여 원본 이미지 경로 획득
            # 예: /FILE/CA/BA/.../T_BA-xxxx.jpg -> /FILE/CA/BA/.../BA-xxxx.jpg
            original_path = thumb_path.replace("T_", "")
            absolute_photo_url = urljoin(BASE_URL, original_path)
            
            save_photo_name = f"photo_{p_idx + 1}.jpg"
            
            # 다운로드 실행
            photo_bytes = download_file_with_delay(session, absolute_photo_url)
            if photo_bytes:
                success = storage.save_file(case_id, save_photo_name, photo_bytes)
                if success:
                    metadata["files_downloaded"].append({
                        "category": "사진",
                        "file_name": save_photo_name,
                        "url": absolute_photo_url
                    })

    # 5. 메타데이터 최종 기록 및 completed=True 저장
    storage.save_meta(case_id, metadata, completed=True)
    logger.info(f"사건 {case_id}에 대한 상세 서류 및 현장 사진 일괄 수집 완료.")
    return True
