# Tank Report (탱크옥션 경매 데이터 수집 프로젝트)

이 프로젝트는 부동산 경매 정보 포털인 **탱크옥션(tankauction.com)**으로부터 매각 예정 및 진행 물건의 목록을 수집하고, 낙찰 물건의 상세 메타데이터와 관련 법원 서류(사건내역, 감정평가서, 매각명세서, 등기 등) 및 현장 사진을 로컬에 체계적으로 저장하는 자동화 크롤러입니다.

---

## 1. 주요 기능
*   **세션 로그인 자동화:** 탱크옥션 로그인 API `/res/logIn.php` 연동 및 세션 쿠키 상시 유지.
*   **경매 물건 목록 수집:** 날짜별 기일 물건 검색 API `/ca/AuctList.php` (POST)를 호출하여 데이터 파싱 및 가공.
*   **상세 서류 및 사진 저장:** 각 낙찰 물건의 상세 팝업 `/ca/caView.php` 구조를 크롤링하여 첨부 서류(PDF, HTML) 및 현장 사진 자동 다운로드.
*   **통합 DB 및 파일 인덱싱:** 가공된 메타데이터를 로컬 SQLite DB(`auctions.db`)에 업데이트하고 날짜별 JSON 인덱스 저장.

---

## 2. 프로젝트 구성 파일 설명

*   **[crawler.py](file:///C:/Users/MichelleBerger/Projects/tank-report/crawler.py):** 수집 날짜 범위, 상세 서류 수집 여부, 병렬 스레드 수 등을 제어하는 통합 CLI 진입점 파일.
*   **[session.py](file:///C:/Users/MichelleBerger/Projects/tank-report/session.py):** 탱크옥션 로그인 세션을 생성 및 유지하며, 로그인 성공 여부 및 장치 제한을 체크하는 세션 관리 모듈.
*   **[parser.py](file:///C:/Users/MichelleBerger/Projects/tank-report/parser.py):** 탱크옥션의 검색 조건 양식에 따라 목록 API 요청을 가공 및 호출하고, 수신된 JSON 목록 데이터를 파이썬 데이터 객체로 매핑하는 파서.
*   **[detail.py](file:///C:/Users/MichelleBerger/Projects/tank-report/detail.py):** 로그인 세션을 활용해 개별 사건의 상세 페이지에 접근 후 감정평가서/매각명세서(PDF), 사건/기일내역(HTML), 물건 사진 등을 다운로드하는 상세 수집 모듈.
*   **[storage.py](file:///C:/Users/MichelleBerger/Projects/tank-report/storage.py):** 수집된 서류 파일 및 이미지 저장 폴더 구조(`data/cases/{case_id}/`)를 조율하고, 수집 완료 사건에 대한 중복 방지 플래그(`meta.json`의 `completed` 값)를 검사하는 저장소 인터페이스.
*   **[db.py](file:///C:/Users/MichelleBerger/Projects/tank-report/db.py):** 로컬 SQLite DB(`auctions.db`) 생성, 마이그레이션 및 목록 데이터의 Upsert 연산을 수행하는 데이터베이스 관리 모듈.

---

## 3. 시작 가이드

### 의존성 설치
```bash
pip install requests beautifulsoup4 pandas openpyxl python-dotenv pypdf
```

### 환경 변수 설정
루트 디렉토리에 `.env` 파일을 생성하고 탱크옥션 계정 정보를 입력합니다.
```env
TANK_ID=본인_아이디
TANK_PW=본인_비밀번호
```

### 실행 방법
```bash
# 특정 날짜 하루치 목록만 수집하여 DB 적재
python crawler.py --date 2026-05-22

# 이번 주 월요일부터 오늘까지의 목록 수집
python crawler.py --week

# 날짜 범위 지정 목록 수집 + 낙찰 물건의 상세 서류 및 이미지 동시 다운로드 (병렬 스레드 2개 사용)
python crawler.py --range 2026-05-19 2026-05-23 --detail --workers 2
```
