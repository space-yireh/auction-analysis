"""
session.py

탱크옥션(tankauction.com) 서비스 로그인 세션을 생성 및 유지하고,
로그인 여부, 장치 제한, 추가 휴대폰 인증 요구 상태를 철저히 검사하여 관리하는 모듈입니다.
"""

import os
import sys
import logging
import requests
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# .env 로드
load_dotenv()


def create_session() -> requests.Session:
    """
    User-Agent 및 XMLHttpRequest 헤더가 기본 탑재된 requests.Session 객체를 생성합니다.

    Returns:
        requests.Session: 설정이 완료된 세션 객체
    """
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.tankauction.com",
        "Referer": "https://www.tankauction.com/ca/caList.php?page=1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    })
    return session


def login(session: requests.Session) -> bool:
    """
    .env 파일의 TANK_ID, TANK_PW 환경 변수를 사용하여 탱크옥션에 로그인을 수행합니다.
    추가 인증(cert_chk) 요구 상황이나 로그인 실패가 감지되면 계정 차단을 방지하기 위해 프로세스를 안전하게 종료합니다.

    Args:
        session (requests.Session): 로그인 요청을 보낼 세션 객체

    Returns:
        bool: 로그인 성공 여부 (성공 시 True 반환, 실패 시 프로세스 종료)
    """
    tank_id = os.environ.get("TANK_ID")
    tank_pw = os.environ.get("TANK_PW")

    if not tank_id or not tank_pw:
        logger.error("환경 변수에 TANK_ID 또는 TANK_PW가 정의되지 않았습니다. .env 파일을 확인해 주세요.")
        sys.exit(1)

    login_url = "https://www.tankauction.com/res/logIn.php"
    payload = {
        "mode": "3",
        "client_id": tank_id,
        "passwd": tank_pw
    }

    try:
        logger.info("탱크옥션 로그인 시도 중...")
        response = session.post(login_url, data=payload, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"로그인 요청 실패 (HTTP 상태 코드: {response.status_code})")
            sys.exit(1)

        try:
            data = response.json()
        except ValueError:
            logger.error("로그인 응답이 JSON 형식이 아닙니다.")
            sys.exit(1)

        res_suc = data.get("resSuc")
        cert_chk = data.get("cert_chk")
        res_msg = data.get("resMsg", "")

        if res_suc == 1:
            # cert_chk 가 1 이외의 값(0, 2, 3 등)이면 휴대폰 추가 인증이 필요함을 의미
            if cert_chk != 1:
                logger.error(
                    f"로그인은 성공했으나 추가 휴대폰 인증이 요구됩니다. "
                    f"(cert_chk: {cert_chk}, 모바일: {data.get('mobile')}). "
                    f"계정 차단을 예방하기 위해 프로세스를 즉시 종료합니다. 웹브라우저에서 인증을 마쳐주세요."
                )
                sys.exit(1)
            
            logger.info(f"로그인 성공 (ID: {tank_id})")
            return True
        else:
            logger.error(f"로그인 실패: {res_msg} (resSuc: {res_suc}, cert_chk: {cert_chk})")
            sys.exit(1)

    except requests.RequestException as e:
        logger.error(f"로그인 요청 중 네트워크 오류가 발생했습니다: {e}")
        sys.exit(1)


def check_session_expired(html_content: str) -> bool:
    """
    조회된 HTML 내용에 로그인 요구 스크립트가 포함되어 있는지 검사하여 로그인 만료를 감지합니다.

    Args:
        html_content (str): 상세 페이지 등에서 받은 HTML 텍스트

    Returns:
        bool: 로그인 만료 상태인 경우 True, 정상 세션인 경우 False
    """
    # 탱크옥션은 로그인 세션 만료 시 "로그인 후 이용하세요." 등의 스크립트 얼럿을 띄움
    if "로그인 후 이용하세요" in html_content or "logIn.php" in html_content:
        logger.warning("로그인 세션 만료 또는 로그아웃 상태 전이가 감지되었습니다.")
        return True
    return False
