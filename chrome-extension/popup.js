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
// 신규 상세 데이터 API (2026 개편)
const CA_API = (tid) => `${ORIGIN}/api/proxy/api1.php/ca/AuctView.php?tid=${encodeURIComponent(tid)}`;       // 경매(법원)
const PA_API = (cltrNo) => `${ORIGIN}/api/proxy/api1.php/pa/PubAuctView.php?cltrNo=${encodeURIComponent(cltrNo)}`; // 공매(온비드)

let mode = null;          // "ca"(경매) | "pa"(공매)
let activeId = null;      // tid 또는 cltrNo
let auctData = null;      // API 응답 원본
let plan = null;          // { caseId, itemNo, tasks: [...] }

// 경매(ca) 카테고리코드(ctgrCd) → 저장 파일 접두사
const CA_CTGR_MAP = {
  AA: "AA-사건내역", AB: "AB-기일내역", AC: "AC-문건송달",
  AD: "AD-현황조사서", AE: "AE-부동산표시",
  AF: "AF-감정평가서", AG: "AG-매물명세서",
  DA: "DA-토지등기", DB: "DB-건물등기",
  EA: "EA-세대열람", EC: "EC-건축물대장",
};
const CA_PDF_CTGR = new Set(["AF", "AG", "DA", "DB", "EA", "EC"]);

// Start initialization
chrome.tabs.query({ active: true, currentWindow: true }, async function (tabs) {
  const tab = tabs[0];
  if (!tab || !tab.url) {
    showError("활성화된 탭을 조회할 수 없습니다.");
    return;
  }

  try {
    const u = new URL(tab.url);
    if (u.hostname.includes("tankauction.com")) {
      const tid = u.searchParams.get("tid");
      const cltrNo = u.searchParams.get("cltrNo");
      if (tid) { mode = "ca"; activeId = tid; }
      else if (cltrNo) { mode = "pa"; activeId = cltrNo; }
    }
  } catch (e) { /* invalid url */ }

  if (!mode) {
    showError("탱크옥션 상세 페이지(경매 tid / 공매 cltrNo)에서만 동작합니다.");
    return;
  }

  tabStatusEl.textContent = mode === "ca" ? "탱크옥션 경매 상세 확인됨" : "탱크옥션 공매 상세 확인됨";
  tabStatusEl.style.color = "#10b981";
  await fetchCaseDetails();
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
  if (actionText) currentActionEl.textContent = actionText;
}

// API 호출 → 식별정보 표시 + 데이터 캐시
async function fetchCaseDetails() {
  try {
    const response = await fetch(mode === "ca" ? CA_API(activeId) : PA_API(activeId), {
      headers: { accept: "application/json" },
      credentials: "include",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const ct = response.headers.get("content-type") || "";
    const raw = await response.text();
    if (!ct.includes("json") || raw.trim().startsWith("<")) throw new Error("SESSION");

    auctData = JSON.parse(raw);
    plan = planFiles();

    // 라벨/값 표시 (경매 vs 공매)
    const rows = caseDetailsEl.querySelectorAll('.info-row .info-label');
    if (mode === "ca") {
      if (rows[0]) rows[0].textContent = "사건번호:";
      if (rows[1]) rows[1].textContent = "물건번호:";
      caseNoEl.textContent = plan.caseId;
      itemNoEl.textContent = plan.itemNo || "1";
    } else {
      if (rows[0]) rows[0].textContent = "물건관리번호:";
      if (rows[1]) rows[1].textContent = "처분기관:";
      caseNoEl.textContent = plan.caseId;
      itemNoEl.textContent = String((auctData.baseInfo || {}).org_nm || "-");
    }
    caseDetailsEl.style.display = "flex";
    btnDownloadEl.disabled = false;
  } catch (err) {
    if (err.message === "SESSION") {
      log("세션이 만료된 것으로 보입니다.", "error");
      showError("탱크옥션 로그인이 필요합니다. 크롬 탭에서 로그인 후 다시 시도하세요.");
    } else {
      log(`상세 정보 로드 실패: ${err.message}`, "error");
      showError("상세 정보를 불러오지 못했습니다. 세션 만료 또는 페이지 변경을 확인하세요.");
    }
  }
}

// content(JSON 문자열) 묶음 → 저장용 문자열. 법원/온비드 응답의 data만 추출.
function combineContents(group) {
  const arr = group.map(it => {
    const c = String(it.content || "").trim();
    try {
      const p = JSON.parse(c);
      return (p && p.data !== undefined) ? p.data : p;
    } catch (e) {
      return c;
    }
  });
  return JSON.stringify(arr.length === 1 ? arr[0] : arr, null, 2);
}

// 다운로드 계획 수립 (경매/공매 공통 태스크 목록으로 정규화)
function planFiles() {
  const tasks = [];
  const b = auctData.baseInfo || {};

  if (mode === "ca") {
    const items = (auctData.fileInfo && Array.isArray(auctData.fileInfo.items)) ? auctData.fileInfo.items : [];
    const groups = {};
    items.forEach(it => {
      const c = String(it.ctgrCd || "").trim();
      if (CA_CTGR_MAP[c]) (groups[c] = groups[c] || []).push(it);
    });
    for (const code of Object.keys(groups)) {
      const g = groups[code], prefix = CA_CTGR_MAP[code];
      if (CA_PDF_CTGR.has(code)) {
        g.forEach((it, i) => {
          const fp = String(it.filePath || "").trim();
          if (!fp) return;
          const url = ORIGIN + (fp.startsWith("/") ? fp : "/" + fp);
          tasks.push({ name: g.length === 1 ? prefix : `${prefix}-${i + 1}`, kind: "pdf", url });
        });
      } else {
        // AA~AE: content 박제 → 그대로 저장
        tasks.push({ name: prefix, kind: "content", output: combineContents(g) });
      }
    }
    const caseId = (b.sn1 && b.sn2) ? `${b.sn1}타경${b.sn2}` : `tid_${activeId}`;
    const itemNo = (b.pn && Number(b.pn) > 0) ? String(b.pn) : "1";
    return { caseId, itemNo, tasks };
  }

  // 공매(pa)
  const items = Array.isArray(auctData.fileInfo) ? auctData.fileInfo : [];
  const nameMap = (auctData.codes && auctData.codes.fileCtgr) || {};
  const groups = {};
  items.forEach(it => {
    const c = String(it.ctgr || "").trim();
    if (c) (groups[c] = groups[c] || []).push(it);
  });
  for (const code of Object.keys(groups)) {
    const g = groups[code];
    const prefix = `${code}-${nameMap[code] || code}`;
    const isPdf = String(g[0].file || "").toLowerCase().endsWith(".pdf");
    const hasContent = !!String(g[0].content || "").trim();
    if (isPdf) {
      g.forEach((it, i) => {
        const url = ORIGIN + "/FILEPA/PA/" + String(it.file || "").trim();
        tasks.push({ name: g.length === 1 ? prefix : `${prefix}-${i + 1}`, kind: "pdf", url });
      });
    } else if (hasContent) {
      // L(물건상세) 등: content 박제 → 저장
      tasks.push({ name: prefix, kind: "content", output: combineContents(g) });
    }
    // 그 외(사진 A / 지적도 B / 위치도 C 등 이미지)는 제외
  }
  const caseId = String(b.cmgmt_no || "").trim() || `cltr_${b.cltr_no || activeId}`;
  return { caseId, itemNo: "", tasks };
}

// Button Click Listener
btnDownloadEl.addEventListener('click', async () => {
  btnDownloadEl.disabled = true;
  statusContainerEl.style.display = "flex";
  consoleLogEl.innerHTML = "";

  // 클립보드에 식별자 복사 (AI 도구용)
  try {
    const textToCopy = mode === "ca" ? `${plan.caseId} (${plan.itemNo})` : plan.caseId;
    await navigator.clipboard.writeText(textToCopy);
    log(`클립보드 복사 성공: "${textToCopy}" (AI 도구용)`, "success");
  } catch (clipErr) {
    log(`클립보드 복사 실패: ${clipErr.message}`, "error");
  }

  log(`${mode === "ca" ? "경매" : "공매"} 문서 다운로드 및 AI 최적화 변환 시작...`);
  log("⚠️ 완료될 때까지 이 팝업 창을 닫지 마세요.", "success");

  try {
    updateProgress(5, "상세 데이터 확인 중...");
    if (!auctData || !plan) {
      const resp = await fetch(mode === "ca" ? CA_API(activeId) : PA_API(activeId), {
        headers: { accept: "application/json" }, credentials: "include",
      });
      if (!resp.ok) throw new Error(`상세 조회 실패: HTTP ${resp.status}`);
      auctData = await resp.json();
      plan = planFiles();
    }

    const zip = new JSZip();

    // 0. 사건 개요 JSON (물건정보·등기·임차인 등 분석용 요약)
    updateProgress(8, "사건 개요 정리 중...");
    try {
      const summary = { ...auctData };
      delete summary.fileInfo;   // 문서 본문은 개별 파일로 저장
      delete summary.codes;      // 코드 매핑표(노이즈)
      if (summary.bldgInfo && summary.bldgInfo.flrMap) {
        summary.bldgInfo = { ...summary.bldgInfo };
        delete summary.bldgInfo.flrMap;
      }
      zip.file("00-사건개요.json", JSON.stringify(summary, null, 2));
      log("사건 개요 저장: 00-사건개요.json", "success");
    } catch (sumErr) {
      log(`사건 개요 정리 실패: ${sumErr.message}`, "error");
    }

    const tasks = plan.tasks;
    if (tasks.length === 0) throw new Error("다운로드할 수 있는 문서가 존재하지 않습니다.");
    log(`총 ${tasks.length}개의 분석 대상 문서 확인 완료.`, "info");

    let done = 0;
    for (const task of tasks) {
      const pct = 10 + (done / tasks.length) * 80;
      try {
        if (task.kind === "pdf") {
          updateProgress(pct, `${task.name}.pdf 다운로드 중...`);
          log(`PDF 다운로드 시도: ${task.name}.pdf`);
          const resp = await fetch(encodeURI(task.url), { credentials: "include" });
          if (!resp.ok) {
            log(`다운로드 실패 (${task.name}): HTTP ${resp.status}`, "error");
            done++; continue;
          }
          const buf = await resp.arrayBuffer();
          let text = "";
          try { text = await extractTextFromPdf(buf); }
          catch (e) { log(`PDF 텍스트 추출 에러: ${e.message}. 원본 저장으로 대체.`, "error"); }

          if (text.trim().length > 100) {
            zip.file(`${task.name}.txt`, text);
            log(`PDF 텍스트 추출 완료: ${task.name}.txt (${text.length}자)`, "success");
          } else {
            zip.file(`${task.name}.pdf`, buf);
            log(`[스캔본 대체] 텍스트 없음 → PDF 원본 저장: ${task.name}.pdf`, "info");
          }
          done++;
          await new Promise(r => setTimeout(r, 400 + Math.random() * 400));
        } else {
          // content 저장
          updateProgress(pct, `${task.name}.json 정리 중...`);
          if (!task.output || !task.output.trim()) {
            log(`내용 없음: ${task.name}`, "error");
            done++; continue;
          }
          zip.file(`${task.name}.json`, task.output);
          log(`문서 저장 완료: ${task.name}.json (${task.output.length}자)`, "success");
          done++;
        }
      } catch (taskErr) {
        log(`문서 처리 오류 (${task.name}): ${taskErr.message}`, "error");
        done++;
      }
    }

    // ZIP 생성 및 다운로드
    updateProgress(90, "ZIP 압축 생성 중...");
    log("수집된 문서 ZIP 압축 파일 생성 중...");
    const zipContent = await zip.generateAsync({ type: "blob" });
    const zipUrl = URL.createObjectURL(zipContent);
    const zipName = plan.itemNo ? `${plan.caseId}_${plan.itemNo}.zip` : `${plan.caseId}.zip`;

    updateProgress(95, "다운로드 요청 중...");
    chrome.downloads.download({ url: zipUrl, filename: zipName, saveAs: true }, (downloadId) => {
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
