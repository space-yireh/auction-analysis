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

let activeTid = null;
let activeUrl = null;
let parsedCaseNo = null;
let parsedItemNo = null;

// Categories map matching download.py
const CATEGORY_MAP = {
  "사건내역":   ["AA-사건내역",   "html"],
  "기일내역":   ["AB-기일내역",   "html"],
  "문건/송달":  ["AC-문건송달",   "html"],
  "현황조사서": ["AD-현황조사서", "html"],
  "부동산표시": ["AE-부동산표시", "html"],
  "감정평가서": ["AF-감정평가서", "pdf"],
  "매물명세서": ["AG-매물명세서", "pdf"],
  "토지등기":   ["DA-토지등기",   "pdf"],
  "건물등기":   ["DB-건물등기",   "pdf"],
  "세대열람":   ["EA-세대열람",   "pdf"],
  "건축물대장": ["EC-건축물대장", "pdf"],
};

// Start initialization
chrome.tabs.query({ active: true, currentWindow: true }, async function (tabs) {
  const tab = tabs[0];
  if (tab && tab.url) {
    activeUrl = tab.url;
    if (activeUrl.includes("tankauction.com/ca/caView.php")) {
      const urlObj = new URL(activeUrl);
      activeTid = urlObj.searchParams.get("tid");
      if (activeTid) {
        tabStatusEl.textContent = "탱크옥션 상세 페이지 확인됨";
        tabStatusEl.style.color = "#10b981";
        await fetchCaseDetails(activeTid);
      } else {
        showError("URL에서 tid 파라미터를 찾을 수 없습니다.");
      }
    } else {
      showError("탱크옥션 사건상세 페이지(caView.php)에서만 동작합니다.");
    }
  } else {
    showError("활성화된 탭을 조회할 수 없습니다.");
  }
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

// Fetch case details to show 사건번호 / 물건번호 in popup
async function fetchCaseDetails(tid) {
  try {
    const response = await fetch(`https://www.tankauction.com/ca/caView.php?tid=${tid}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const htmlText = await response.text();

    const saNoMatch = htmlText.match(/(\d{4}타경\d+)/);
    const maemulMatch = htmlText.match(/물건번호\s*[:\s]+(\d+)/);

    parsedCaseNo = saNoMatch ? saNoMatch[1] : `tid_${tid}`;
    parsedItemNo = maemulMatch ? maemulMatch[1] : "1";

    caseNoEl.textContent = parsedCaseNo;
    itemNoEl.textContent = parsedItemNo;
    caseDetailsEl.style.display = "flex";
    btnDownloadEl.disabled = false;
  } catch (err) {
    log(`사건 정보 로드 실패: ${err.message}`, "error");
    showError("상세 정보를 파싱하는 데 실패했습니다. 세션 만료를 확인하세요.");
  }
}

// Button Click Listener
btnDownloadEl.addEventListener('click', async () => {
  btnDownloadEl.disabled = true;
  statusContainerEl.style.display = "flex";
  consoleLogEl.innerHTML = "";
  log("문서 다운로드 및 AI 최적화 변환 프로세스 시작...");
  log("⚠️ 완료될 때까지 이 팝업 창을 닫지 마세요.", "success");

  try {
    // 1. Fetch dtData
    updateProgress(10, "문서 목록(dtData) 요청 중...");
    const filePageUrl = `https://www.tankauction.com/ca/caFile.php?tid=${activeTid}&tp=AA&idx=0&free=`;
    const response = await fetch(filePageUrl);
    if (!response.ok) throw new Error(`목록 조회 실패: HTTP ${response.status}`);
    const fileHtml = await response.text();

    // Verify Session Expiry
    if (fileHtml.includes("로그인 후 이용하세요") || fileHtml.includes("logIn.php")) {
      throw new Error("탱크옥션 세션이 만료되었습니다. 크롬 탭에서 다시 로그인해 주세요.");
    }

    const dtDataMatch = fileHtml.match(/var\s+dtData\s*=\s*(\{.*?\});/s);
    if (!dtDataMatch) {
      throw new Error("문서 목록 데이터(dtData)를 찾을 수 없습니다.");
    }

    let dtData = {};
    try {
      dtData = JSON.parse(dtDataMatch[1]);
    } catch (e) {
      throw new Error(`dtData JSON 파싱 에러: ${e.message}`);
    }

    // 2. Prepare download tasks
    const tasks = [];
    for (const [category, [prefix, saveExt]] of Object.entries(CATEGORY_MAP)) {
      const entries = resolveCategoryEntries(dtData, category, prefix.substring(0, 2));
      if (entries.length === 0) continue;

      entries.forEach((entry, seq) => {
        const fileUrl = resolveDownloadUrl(entry, activeTid);
        if (fileUrl) {
          const isSingle = entries.length === 1;
          const filename = isSingle ? `${prefix}.${saveExt}` : `${prefix}-${seq + 1}.${saveExt}`;
          tasks.push({ category, fileUrl, filename, saveExt, entry });
        }
      });
    }

    if (tasks.length === 0) {
      throw new Error("다운로드할 수 있는 문서가 존재하지 않습니다.");
    }

    log(`총 ${tasks.length}개의 분석 대상 문서 확인 완료.`, "info");

    // 3. Process each task
    const zip = new JSZip();
    let completedCount = 0;

    for (const task of tasks) {
      const pct = 10 + (completedCount / tasks.length) * 80;
      updateProgress(pct, `${task.filename} 처리 중...`);
      log(`다운로드 시도: ${task.filename}`);

      try {
        const fileResp = await fetch(task.fileUrl);
        if (!fileResp.ok) {
          log(`다운로드 실패 (${task.filename}): HTTP ${fileResp.status}`, "error");
          continue;
        }

        if (task.saveExt === "html") {
          // HTML 카테고리 (JSON 확장자로 된 fileShow.php 렌더링 결과) -> 마크다운 변환
          const htmlText = await fileResp.text();
          const mdContent = htmlToCleanMarkdown(htmlText);
          const mdFilename = task.filename.replace(".html", ".md");
          zip.file(mdFilename, mdContent);
          log(` 마크다운 표 변환 성공: ${mdFilename} (크기: ${mdContent.length}자)`, "success");
        } else if (task.saveExt === "pdf") {
          // PDF 카테고리 -> 텍스트 추출 시도
          const arrayBuffer = await fileResp.arrayBuffer();
          log(` PDF 텍스트 추출 시도: ${task.filename}`);
          
          let textContent = "";
          try {
            textContent = await extractTextFromPdf(arrayBuffer);
          } catch (pdfErr) {
            log(` PDF 텍스트 추출 중 에러 발생: ${pdfErr.message}. 원본 포함 처리 진행.`, "error");
          }

          // Check if we successfully extracted a meaningful amount of text
          if (textContent.trim().length > 100) {
            const txtFilename = task.filename.replace(".pdf", ".txt");
            zip.file(txtFilename, textContent);
            log(` PDF 텍스트 추출 완료: ${txtFilename} (크기: ${textContent.length}자)`, "success");
          } else {
            // Scanned image PDF fallback -> Add original PDF
            zip.file(task.filename, arrayBuffer);
            log(` [스캔본 대체] 텍스트가 없어 PDF 원본을 저장합니다: ${task.filename}`, "info");
          }
        }
      } catch (taskErr) {
        log(`문서 처리 오류 (${task.filename}): ${taskErr.message}`, "error");
      }

      completedCount++;
      // Random delay to avoid overloading (500ms - 1000ms)
      await new Promise(resolve => setTimeout(resolve, 500 + Math.random() * 500));
    }

    // 4. Generate and download ZIP
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

// Helper: resolve category entries from dtData
function resolveCategoryEntries(dtData, category, tpCode) {
  let raw = dtData[category] || dtData[tpCode];
  if (raw === undefined || raw === null) {
    return [];
  }
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    raw = raw.list || raw.files || [raw];
  }
  if (!Array.isArray(raw)) {
    raw = [raw];
  }
  return raw.map(item => (typeof item === 'object' ? item : { idx: item }));
}

// Helper: resolve final download URL
function resolveDownloadUrl(entry, tid) {
  let path = entry.파일경로 || entry.filePath || "";
  path = path.replace(/\\/g, "/");
  if (!path) return null;

  const ext = entry.확장자 || "";
  if (ext === "json") {
    const idx = entry.idx || "";
    const sn = entry.사건번호 || "";
    const wdt = entry.수집일 || "";
    return `https://www.tankauction.com/inc/fileShow.php?idx=${idx}&tid=${tid}&sn=${sn}&wdt=${wdt}&filePath=${path}`;
  }

  if (path.startsWith("http")) {
    return path;
  }
  return path.startsWith("/") ? `https://www.tankauction.com${path}` : `https://www.tankauction.com/${path}`;
}

// Helper: Convert Tankauction Table HTML to clean Markdown format
function htmlToCleanMarkdown(htmlString) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlString, 'text/html');
  
  // Remove script, style, link, head, meta tags
  doc.querySelectorAll('script, style, link, head, meta').forEach(el => el.remove());
  
  let mdText = "";
  
  const pageTitle = doc.querySelector('.center.bold')?.textContent?.trim();
  if (pageTitle) {
    mdText += `# ${pageTitle}\n\n`;
  }
  
  const tables = doc.querySelectorAll('table');
  if (tables.length > 0) {
    tables.forEach(table => {
      let title = "세부 항목 정보";
      let prev = table.previousElementSibling;
      while (prev) {
        if (prev.tagName === 'H3') {
          title = prev.textContent.trim();
          break;
        }
        if (prev.classList.contains('table_title')) {
          const h3 = prev.querySelector('h3');
          if (h3) title = h3.textContent.trim();
          break;
        }
        prev = prev.previousElementSibling;
      }
      
      mdText += `## ${title}\n\n`;
      
      const rows = Array.from(table.querySelectorAll('tr'));
      rows.forEach((row, rowIndex) => {
        const cells = Array.from(row.querySelectorAll('th, td')).map(cell => {
          return cell.textContent.replace(/\s+/g, ' ').trim();
        });
        
        if (cells.length > 0) {
          mdText += "| " + cells.join(" | ") + " |\n";
          // Add table divider header if it is index 0 or has <th> elements
          if (rowIndex === 0 || row.querySelector('th')) {
            mdText += "| " + cells.map(() => "---").join(" | ") + " |\n";
          }
        }
      });
      mdText += "\n";
    });
  } else {
    mdText = doc.body.innerText.replace(/\n\s*\n/g, '\n').trim();
  }
  
  return mdText;
}

// Helper: Extract text page-by-page from PDF using pdf.js
async function extractTextFromPdf(pdfArrayBuffer) {
  const loadingTask = pdfjsLib.getDocument({ data: pdfArrayBuffer });
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
