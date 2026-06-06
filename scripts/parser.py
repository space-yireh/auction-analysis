"""
parser.py

탱크옥션(tankauction.com) 목록 API(/ca/AuctList.php)를 호출하여 
사건 목록 데이터를 수집하고 이를 정규화된 AuctionItem 데이터 구조로 변환하는 파서 모듈입니다.
"""

import re
import time
import random
import logging
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


@dataclass
class AuctionItem:
    """
    정규화된 개별 경매 물건의 데이터 구조 클래스입니다.
    """
    tid: str                # 탱크옥션 고유 키
    sa_no: str              # 법원 사건번호 (예: '2025타경1004')
    maemul_no: str          # 물건번호 (예: '1', '2' 등)
    ctgr: str               # 물건 용도
    dpsl: str               # 매각 구분
    spl_cdtn: str           # 특수 조건
    addr: str               # 물건 소재지
    apsl_amt: int           # 감정가격 (원)
    minb_amt: int           # 최저입찰가격 (원)
    minb_pct: int           # 감정가 대비 최저가 비율 (%)
    deal_amt: Optional[int] # 낙찰가격 (원, 미낙찰 시 None)
    status: str             # 매각 진행상태
    bid_dt: str             # 매각 기일 (YYYY-MM-DD)
    court: str              # 관할 법원 담당 계
    crawled_at: str         # 수집 동기화 일시 (ISO 8601 UTC)


def _parse_sa_no(raw_sa_no: str) -> tuple:
    """
    탱크옥션의 사건번호 표기법(예: '2019-50471' 또는 '2022-30449(6)')을
    법원 정식 사건번호('2019타경50471')와 물건번호('1' 또는 '6')의 튜플로 분리 및 정규화합니다.

    Args:
        raw_sa_no (str): 탱크옥션 원본 사건번호

    Returns:
        tuple: (sa_no, maemul_no)
    """
    # 패턴 예: 2022-30449(6) 또는 2019-50471
    pattern = r"^(\d{4})-(\d+)(?:\((\d+)\))?$"
    match = re.match(pattern, raw_sa_no.strip())
    
    if match:
        year = match.group(1)
        num = match.group(2)
        maemul = match.group(3)
        
        sa_no = f"{year}타경{num}"
        maemul_no = maemul if maemul else "1"
        return sa_no, maemul_no
    else:
        # 매칭이 실패한 경우 원본을 최대한 보존
        return raw_sa_no, "1"


def _parse_bid_dt(raw_bid_dt: str) -> str:
    """
    탱크옥션 날짜 표기법(예: '26.06.01')을 표준 YYYY-MM-DD 형식('2026-06-01')으로 변환합니다.

    Args:
        raw_bid_dt (str): 원본 날짜 문자열

    Returns:
        str: YYYY-MM-DD 날짜 문자열
    """
    clean_dt = raw_bid_dt.strip().replace('.', '-')
    # '26-06-01' -> '2026-06-01'
    if len(clean_dt) == 8:
        return f"20{clean_dt}"
    return clean_dt


def _item_from_json(raw: dict) -> AuctionItem:
    """
    탱크옥션 응답 JSON 항목을 정규화된 AuctionItem 데이터 모델로 매핑합니다.

    Args:
        raw (dict): 응답 JSON 내 개별 아이템 딕셔너리

    Returns:
        AuctionItem: 데이터가 정제된 파이썬 객체
    """
    raw_sa_no = raw.get("saNo", "")
    sa_no, maemul_no = _parse_sa_no(raw_sa_no)
    
    # 낙찰금액 sucbAmt 가 0인 경우 미낙찰이므로 None 매핑
    sucb_amt = raw.get("sucbAmt", 0)
    deal_amt = int(sucb_amt) if sucb_amt and int(sucb_amt) > 0 else None
    
    # 기일 날짜 정제
    raw_bid_dt = raw.get("bidDt", "")
    bid_dt = _parse_bid_dt(raw_bid_dt)
    
    # 주소 정제 (HTML 태그 제거)
    raw_addr = raw.get("regnAdrs", raw.get("adrsInfo", ""))
    addr = re.sub(r"<[^>]+>", " ", raw_addr).strip()
    
    # 현재 수집 시각
    crawled_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 상태값 정제 (HTML 태그 제거)
    raw_status = raw.get("statNm", "")
    status = re.sub(r"<[^>]+>", "", raw_status).strip()

    return AuctionItem(
        tid=str(raw.get("tid")),
        sa_no=sa_no,
        maemul_no=maemul_no,
        ctgr=str(raw.get("ctgr", "")),
        dpsl=str(raw.get("dpsl", "")),
        spl_cdtn=str(raw.get("splCdtn", "")),
        addr=addr,
        apsl_amt=int(raw.get("apslAmt", 0)),
        minb_amt=int(raw.get("minbAmt", 0)),
        minb_pct=int(raw.get("minbPct", 0)),
        deal_amt=deal_amt,
        status=status,
        bid_dt=bid_dt,
        court=str(raw.get("crtDpt", "")),
        crawled_at=crawled_at
    )


def fetch_by_date(session: requests.Session, bid_dt: str, data_size: int = 100, limit: Optional[int] = None) -> List[AuctionItem]:
    """
    지정된 날짜(bid_dt)에 해당하는 경매 물건 목록을 탱크옥션 API로부터 수집합니다.
    페이지네이션 및 크롤링 딜레이 제약을 준수합니다.

    Args:
        session (requests.Session): 로그인 상태가 유지된 세션 객체
        bid_dt (str): 검색할 기일 날짜 (형식: YYYY-MM-DD)
        data_size (int, optional): 한 페이지당 가져올 사건 수. Defaults to 100.
        limit (int, optional): 최대 수집할 사건 개수 제한. Defaults to None.

    Returns:
        List[AuctionItem]: 파싱이 완료된 사건 객체 리스트
    """
    logger.info(f"기일별 경매 물건 목록 수집 시작: {bid_dt} (페이지당 {data_size}건, 제한: {limit}건)")
    
    # limit이 data_size보다 작으면 한 번의 요청으로 충분하도록 data_size 축소
    if limit and limit < data_size:
        data_size = limit

    items: List[AuctionItem] = []
    page_no = 1
    total_cnt = -1

    # 검색 폼 기본 페이로드 구성 (수동 연동 캡처본 기준)
    payload_template = (
        "siCd=0&guCd=0&dnCd=0&dptCd=0&addr_cs_key=0&adrPlural=&adrPlural_cnt=0&"
        "adrsEtcSelect=0&adrsEtc=&ctgr=0&sn1=0&sn2=&pn=&chkAllCtgr=0&stat=0&"
        "fbCntBgn=0&fbCntEnd=0&bgnDt={date}&endDt={date}&apslAmtBgn=0&apslAmtEnd=0&"
        "landSqmBgn=&landSqmEnd=&minbAmtBgn=0&minbAmtEnd=0&bldgSqmBgn=&bldgSqmEnd=&"
        "totFlrBgn=0&totFlrEnd=0&prsvBgn=0&prsvEnd=0&flrBgn=0&flrEnd=0&"
        "preBgnDt=&preEndDt=&dpslDvsn=0&auctType=0&minbPctBgn=0&minbPctEnd=0&"
        "maxPnBgn=0&maxPnEnd=0&local=0&line=0&station=0&distance=0&splSrchType=0&"
        "powerCtgrs=0&chkCtgrsCd=&chkSplCdtn=&chkPrpsCdtn=&dataSize={data_size}&"
        "lsType=0&odrCol=14&odrAds=1&srchFR=0&idxFR=0&ck_photo=0"
    )

    while True:
        # 날짜와 데이터 사이즈를 동적으로 바인딩
        payload_str = payload_template.format(date=bid_dt, data_size=data_size)
        
        # 쿼리 파라미터가 포함된 URL
        url = (
            f"https://www.tankauction.com/ca/AuctList.php?"
            f"srchCase=srchAll&pageNo={page_no}&dataSize={data_size}&pageSize=10"
        )
        
        try:
            logger.info(f"목록 API 요청 중: Page {page_no} (URL: {url})")
            response = session.post(
                url,
                data=payload_str.encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                timeout=15
            )

            if response.status_code != 200:
                logger.error(f"목록 API 요청 실패 (상태 코드: {response.status_code})")
                break

            try:
                response.encoding = 'utf-8'
                data = response.json()
            except ValueError:
                logger.error("목록 API 응답이 JSON 형식이 아닙니다.")
                break

            # 로그인 상태가 해제되었는지 HTML 등이 반환되었을 경우 검증
            if "login" in response.text.lower() and not data:
                logger.error("API 요청 중 세션 만료 감지 (로그인 필요)")
                break

            total_cnt = data.get("totalCnt", 0)
            raw_items = data.get("item", [])
            
            logger.info(f"수집 현황: 검색 전체 {total_cnt}건 중 현재 페이지에서 {len(raw_items)}건 수신")

            for raw in raw_items:
                try:
                    item = _item_from_json(raw)
                    items.append(item)
                except Exception as ex:
                    logger.error(f"개별 사건 데이터 파싱 오류: {ex}. 사건 정보: {raw}")
            
            # limit에 도달한 경우 조기 브레이크
            if limit and len(items) >= limit:
                items = items[:limit]
                logger.info(f"수집 제한 개수({limit}건)에 도달하여 목록 수집을 조기 종료합니다.")
                break

            # 페이지네이션 종료 조건 확인
            if len(items) >= total_cnt or not raw_items:
                break
                
            page_no += 1
            
            # 크롤링 페이지 전환 간 딜레이 대기 (AGENTS.md 제약: 2.0초 ~ 4.0초)
            delay = random.uniform(2.0, 4.0)
            logger.info(f"목록 페이지 전환 대기 중 ({delay:.2f}초)...")
            time.sleep(delay)

        except requests.RequestException as e:
            logger.error(f"목록 API 요청 중 오류 발생: {e}")
            break

    logger.info(f"기일별 목록 수집 완료. 총 {len(items)}건의 사건 데이터 파싱 완료.")
    return items
