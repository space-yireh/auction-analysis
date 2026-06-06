"""
storage.py

수집된 경매 사건 서류 파일(PDF, HTML) 및 현장 사진 이미지들을 로컬 디렉토리 구조
(data/cases/{사건번호_물건번호}/)에 저장하고 관리하는 파일 스토리지 인터페이스 모듈입니다.
"""

import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

BASE_DATA_DIR = os.path.join("data", "cases")


class AuctionStorage:
    """
    로컬 파일 스토리지에 데이터를 저장하고, 개별 사건 수집 완료 상태를 추적하는 클래스입니다.
    """
    def __init__(self, base_dir: str = BASE_DATA_DIR):
        """
        AuctionStorage 클래스를 초기화합니다.

        Args:
            base_dir (str, optional): 기본 데이터 디렉토리 경로. Defaults to "data/cases".
        """
        self.base_dir = base_dir
        # 기본 디렉토리가 존재하지 않을 경우 생성
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_case_dir(self, case_id: str) -> str:
        """
        사건 ID(예: '2025타경1004_1')에 따른 사건별 로컬 저장 디렉토리 절대경로를 반환합니다.

        Args:
            case_id (str): 사건번호_물건번호 형태의 식별자

        Returns:
            str: 사건 저장용 디렉토리 경로
        """
        # 폴더명에 한글 및 영숫자 조합이 있으므로 안전하게 처리
        # 파일시스템 문자열 인코딩 문제 등을 방지하기 위해 파일 경로 정제
        safe_case_id = "".join([c for c in case_id if c.isalnum() or c in ['_', '-']]).strip()
        if not safe_case_id:
            safe_case_id = "unknown_case"
        return os.path.join(self.base_dir, safe_case_id)

    def already_crawled(self, case_id: str) -> bool:
        """
        해당 사건의 상세 파일 수집이 완료되었는지 확인합니다.
        사건 폴더 내의 meta.json 파일의 completed 값이 True인지 검사합니다.

        Args:
            case_id (str): 사건번호_물건번호 형태의 식별자

        Returns:
            bool: 이미 수집이 완료된 경우 True, 수집 전이거나 미완료된 경우 False
        """
        case_dir = self._get_case_dir(case_id)
        meta_file = os.path.join(case_dir, "meta.json")
        
        if not os.path.exists(meta_file):
            return False

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
                return meta.get("completed", False) is True
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"사건 {case_id}의 meta.json 파일을 읽을 수 없습니다: {e}")
            return False

    def save_meta(self, case_id: str, metadata: Dict[str, Any], completed: bool = True) -> None:
        """
        사건의 요약 메타데이터를 meta.json 파일로 저장하고 완료 플래그를 설정합니다.

        Args:
            case_id (str): 사건번호_물건번호 형태의 식별자
            metadata (Dict[str, Any]): 저장할 메타데이터 딕셔너리
            completed (bool, optional): 수집 완료 여부 플래그. Defaults to True.
        """
        case_dir = self._get_case_dir(case_id)
        os.makedirs(case_dir, exist_ok=True)
        
        meta_file = os.path.join(case_dir, "meta.json")
        
        # 완료 플래그 추가
        meta_data = dict(metadata)
        meta_data["completed"] = completed
        meta_data["updated_at"] = os.path.getmtime(case_dir) if os.path.exists(case_dir) else None

        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)
            logger.info(f"사건 {case_id}의 메타 요약 정보 저장 완료 (completed: {completed})")
        except IOError as e:
            logger.error(f"사건 {case_id}의 메타 정보 저장 실패: {e}")

    def save_file(self, case_id: str, file_name: str, content: bytes) -> bool:
        """
        사건 폴더 내부에 임의의 파일(PDF, HTML, JPG 등)을 바이너리 형식으로 저장합니다.

        Args:
            case_id (str): 사건번호_물건번호 형태의 식별자
            file_name (str): 저장할 파일 이름 (예: 'appraisal.pdf', 'photo_1.jpg')
            content (bytes): 파일 바이너리 내용

        Returns:
            bool: 저장 성공 시 True, 실패 시 False
        """
        case_dir = self._get_case_dir(case_id)
        os.makedirs(case_dir, exist_ok=True)
        
        file_path = os.path.join(case_dir, file_name)
        
        try:
            with open(file_path, "wb") as f:
                f.write(content)
            logger.info(f"파일 저장 완료: {file_path} ({len(content)} bytes)")
            return True
        except IOError as e:
            logger.error(f"사건 {case_id}의 파일 {file_name} 저장 실패: {e}")
            return False
