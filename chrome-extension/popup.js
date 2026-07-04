// Set up PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = 'libs/pdf.worker.min.js';

// DOM elements
const tabStatusEl = document.getElementById('tab-status');
const caseDetailsEl = document.getElementById('case-details');
const caseNoEl = document.getElementById('case-no');
const itemNoEl = document.getElementById('item-no');
const alertBoxEl = document.getElementById('alert-box');
const btnDownloadEl = document.getElementById('btn-download');
const statusContainerEl = document.getElementById('status-container');
const progressBarEl = document.getElementById('progress-bar');
const currentActionEl = document.getElementById('current-action');
const progressPctEl = document.getElementById('progress-pct');
const consoleLogEl = document.getElementById('console-log');

const ORIGIN = 'https://www.tankauction.com';
// 신규 상세 데이터 API (2026 개편). fileInfo/baseInfo/등기/임차인 전부 이 하나로 조회.
const AUCT_VIEW_API = (tid) => `${ORIGIN}/api/proxy/api1.php/ca/AuctView.php?tid=${encodeURIComponent(tid)}`;

let activeTid = null;
let auctData = null;      // AuctView.php 응답 원본
let parsedCaseNo = null;
let parsedItemNo = null;

// 카테고리코드(ctgrCd) → 저장 파일 접두사
const CTGR_MAP = {
  AA: "AA-사건내역",
  AB: "AB-기일내역",
  AC: "AC-문건송달",
  AD: "AD-현황조사서",
  AE: "AE-부동산표시",
  AF: "AF-감정평가서",
  AG: "AG-매물명세서",
  DA: "DA-토지등기",
  DB: "DB-건물등기",
  EA: "EA-세대열람",
  EC: "EC-건축물대장",
};
// PDF 계열 (filePath 직접 다운로드 → 텍스트 추출)
const PDF_CTGR = new Set(["AF", "AG", "DA", "DB", "EA", "EC"]);

// Start initialization
chrome.tabs.query({ active: true, currentWindow: true }, async function (tabs) {
  const tab = tabs[0];
  if (!tab || !tab.url) {
    showError("활성화된 탭을 조회할 수 없습니다.");
    return;
  }

  let tid = null;
  try {
    const urlObj = new URL(tab.url);
    if (urlObj.hostname.includes("tankauction.com")) {
      tid = urlObj.searchParams.get("tid");
    }
  } catch (e) { /* invalid url */ }

  if (!tid) {
    showError("탱크옥션 사건상세 페이지(tid 포함)에서만 동작합니다.");
    return;
  }

  activeTid = tid;
  tabStatusEl.textContent = "탱크옥션 상세 페이지 확인됨";
  tabStatusEl.style.color = "#10b981";
  await fetchCaseDetails(activeTid);
});

function showError(msg) {
  alertBoxEl.textContent = msg;
  alertBoxEl.style.display = "block";
  btnDownloadEl.disabled = true;
}

function log(msg, type = "info") {
  consoleLogEl.style.display = "flex";
  const line = document.createElement('div');
  line.className = `console-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  consoleLogEl.appendChild(line);
  consoleLogEl.scrollTop = consoleLogEl.scrollHeight;
}

function updateProgress(pct, actionText) {
  progressBarEl.style.width = `${pct}%`;
  progressPctEl.textContent = `${Math.round(pct)}%`;
  if (actionText) {
    currentActionEl.textContent = actionText;
  }
}

// AuctView API 호출 → 사건번호/물건번호 표시 + 데이터 캐시
async function fetchCaseDetails(tid) {
  try {
    const response = await fetch(AUCT_VIEW_API(tid), {
      headers: { accept: "application/json" },
      credentials: "include",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const ct = response.headers.get("content-type") || "";
    const raw = await response.text();

    // 세션 만료 시 로그인 HTML이 반환됨
    if (!ct.includes("json") || raw.trim().startsWith("<")) {
      throw new Error("SESSION");
    }

    auctData = JSON.parse(raw);
    const base = auctData.baseInfo || {};

    const sn1 = String(base.sn1 || "").trim();
    const sn2 = String(base.sn2 || "").trim();
    parsedCaseNo = (sn1 && sn2) ? `${sn1}타경${sn2}` : `tid_${tid}`;
    parsedItemNo = (base.pn && Number(base.pn) > 0) ? String(base.pn) : "1";

    caseNoEl.textContent = parsedCaseNo;
    itemNoEl.textContent = parsedItemNo;
    caseDetailsEl.style.display = "flex";
    btnDownloadEl.disabled = false;
  } catch (err) {
    if (err.message === "SESSION") {
      log("세션이 만료된 것으로 보입니다.", "error");
      showError("탱크옥션 로그인이 필요합니다. 크롬 탭에서 로그인 후 다시 시도하세요.");
    } else {
      log(`사건 정보 로드 실패: ${err.message}`, "error");
      showError("상세 정보를 불러오지 못했습니다. 세션 만료 또는 페이지 변경을 확인하세요.");
    }
  }
}

// Button Click Listener
btnDownloadEl.addEventListener('click', async () => {
  btnDownloadEl.disabled = true;
  statusContainerEl.style.display = "flex";
  consoleLogEl.innerHTML = "";

  // 클립보드에 사건번호 + 물건번호 복사 (AI 도구용)
  try {
    const textToCopy = `${parsedCaseNo} (${parsedItemNo})`;
    await navigator.clipboard.writeText(textToCopy);
    log(`클립보드 복사 성공: "${textToCopy}" (AI 도구용)`, "success");
  } catch (clipErr) {
    log(`클립보드 복사 실패: ${clipErr.message}`, "error");
  }

  log("문서 다운로드 및 AI 최적화 변환 프로세스 시작...");
  log("⚠️ 완료될 때까지 이 팝업 창을 닫지 마세요.", "success");

  try {
    updateProgress(5, "상세 데이터 확인 중...");

    // 최신 데이터로 재조회 (팝업이 오래 떠 있었을 경우 대비)
    if (!auctData) {
      const resp = await fetch(AUCT_VIEW_API(activeTid), {
        headers: { accept: "application/json" },
        credentials: "include",
      });
      if (!resp.ok) throw new Error(`상세 조회 실패: HTTP ${resp.status}`);
      auctData = await resp.json();
    }

    const items = (auctData.fileInfo && Array.isArray(auctData.fileInfo.items))
      ? auctData.fileInfo.items
      : [];
    if (items.length === 0) {
      throw new Error("문서 목록(fileInfo)이 비어 있습니다.");
    }

    const zip = new JSZip();

    // 0. 사건 개요 JSON (baseInfo·등기·임차인 등 분석용 요약)
    updateProgress(8, "사건 개요 정리 중...");
    try {
      const summary = { ...auctData };
      delete summary.fileInfo; // 문서 본문은 개별 파일로 저장
      if (summary.bldgInfo && summary.bldgInfo.flrMap) {
        summary.bldgInfo = { ...summary.bldgInfo };
        delete summary.bldgInfo.flrMap; // 층 코드표(노이즈) 제거
      }
      zip.file("00-사건개요.json", JSON.stringify(summary, null, 2));
      log("사건 개요 저장: 00-사건개요.json (물건정보·등기·임차인)", "success");
    } catch (sumErr) {
      log(`사건 개요 정리 실패: ${sumErr.message}`, "error");
    }

    // 1. 대상 문서 그룹화 (카테고리별)
    const groups = {};
    for (const it of items) {
      const code = String(it.ctgrCd || "").trim();
      if (!CTGR_MAP[code]) continue; // 사진(BA~BE) 등 제외
      (groups[code] = groups[code] || []).push(it);
    }

    // 2. 태스크 구성
    const tasks = [];
    for (const code of Object.keys(groups)) {
      const prefix = CTGR_MAP[code];
      const entries = groups[code];
      entries.forEach((entry, seq) => {
        const isSingle = entries.length === 1;
        const baseName = isSingle ? prefix : `${prefix}-${seq + 1}`;
        tasks.push({ code, prefix, baseName, entry });
      });
    }

    if (tasks.length === 0) {
      throw new Error("다운로드할 수 있는 문서가 존재하지 않습니다.");
    }
    log(`총 ${tasks.length}개의 분석 대상 문서 확인 완료.`, "info");

    // 3. 태스크 처리
    let completedCount = 0;
    for (const task of tasks) {
      const pct = 10 + (completedCount / tasks.length) * 80;

      try {
        if (PDF_CTGR.has(task.code)) {
          // PDF 계열: filePath 직접 다운로드 → 텍스트 추출
          const filePath = String(task.entry.filePath || "").trim();
          if (!filePath) {
            log(`파일경로 없음: ${task.baseName}`, "error");
            completedCount++;
            continue;
          }
          const fileUrl = ORIGIN + (filePath.startsWith("/") ? filePath : "/" + filePath);
          updateProgress(pct, `${task.baseName}.pdf 다운로드 중...`);
          log(`PDF 다운로드 시도: ${task.baseName}.pdf`);

          const fileResp = await fetch(encodeURI(fileUrl), { credentials: "include" });
          if (!fileResp.ok) {
            log(`다운로드 실패 (${task.baseName}): HTTP ${fileResp.status}`, "error");
            completedCount++;
            continue;
          }
          const arrayBuffer = await fileResp.arrayBuffer();

          let textContent = "";
          try {
            textContent = await extractTextFromPdf(arrayBuffer);
          } catch (pdfErr) {
            log(`PDF 텍스트 추출 에러: ${pdfErr.message}. 원본 저장으로 대체.`, "error");
          }

          if (textContent.trim().length > 100) {
            zip.file(`${task.baseName}.txt`, textContent);
            log(`PDF 텍스트 추출 완료: ${task.baseName}.txt (${textContent.length}자)`, "success");
          } else {
            zip.file(`${task.baseName}.pdf`, arrayBuffer);
            log(`[스캔본 대체] 텍스트 없음 → PDF 원본 저장: ${task.baseName}.pdf`, "info");
          }

          completedCount++;
          await new Promise(r => setTimeout(r, 400 + Math.random() * 400));
        } else {
          // AA~AE: content 필드에 법원 API JSON이 이미 포함됨 → 그대로 저장 (다운로드 불필요)
          updateProgress(pct, `${task.baseName}.json 정리 중...`);
          const content = String(task.entry.content || "").trim();
          if (!content) {
            log(`내용 없음(content 비어있음): ${task.baseName}`, "error");
            completedCount++;
            continue;
          }
          let out = content;
          try {
            const parsed = JSON.parse(content);
            // 법원 응답은 {status, message, data, token} 형태 → data만 저장
            const body = (parsed && parsed.data !== undefined) ? parsed.data : parsed;
            out = JSON.stringify(body, null, 2);
          } catch (e) {
            log(`${task.baseName} JSON 파싱 실패 → 원문 저장`, "info");
          }
          zip.file(`${task.baseName}.json`, out);
          log(`문서 저장 완료: ${task.baseName}.json (${out.length}자)`, "success");
          completedCount++;
        }
      } catch (taskErr) {
        log(`문서 처리 오류 (${task.baseName}): ${taskErr.message}`, "error");
        completedCount++;
      }
    }

    // 4. ZIP 생성 및 다운로드
    updateProgress(90, "ZIP 압축 생성 중...");
    log("수집된 문서 ZIP 압축 파일 생성 중...");

    const zipContent = await zip.generateAsync({ type: "blob" });
    const zipUrl = URL.createObjectURL(zipContent);
    const zipName = `${parsedCaseNo}_${parsedItemNo}.zip`;

    updateProgress(95, "다운로드 요청 중...");
    chrome.downloads.download({
      url: zipUrl,
      filename: zipName,
      saveAs: true
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        log(`다운로드 요청 실패: ${chrome.runtime.lastError.message}`, "error");
        btnDownloadEl.disabled = false;
      } else {
        log(`압축 파일 다운로드 완료! 저장명: ${zipName}`, "success");
        updateProgress(100, "완료!");
        btnDownloadEl.disabled = false;
      }
    });

  } catch (err) {
    log(`치명적 오류 발생: ${err.message}`, "error");
    updateProgress(0, "오류 발생");
    btnDownloadEl.disabled = false;
  }
});

// Helper: Extract text page-by-page from PDF using pdf.js
async function extractTextFromPdf(pdfArrayBuffer) {
  // Use a copy to prevent pdf.js from detaching the original ArrayBuffer
  const loadingTask = pdfjsLib.getDocument({ data: pdfArrayBuffer.slice(0) });
  const pdf = await loadingTask.promise;
  let fullText = "";

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const textContent = await page.getTextContent();
    const pageText = textContent.items.map(item => item.str).join(" ");
    fullText += `--- Page ${i} ---\n${pageText}\n\n`;
  }

  return fullText;
}
