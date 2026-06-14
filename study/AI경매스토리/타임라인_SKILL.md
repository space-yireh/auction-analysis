# 경매스토리 타임라인 생성 SKILL

경매 서류 업로드 시 타임라인 HTML을 생성하는 규칙과 코드 기준을 정의합니다.
이 파일을 읽은 뒤에만 타임라인 아티팩트를 생성하세요.

---

## 1. 출력 방식

- `create_file`로 `/mnt/user-data/outputs/타임라인_[사건번호].html` 저장
- `present_files`로 사용자에게 제공
- CSS·JS 모두 포함한 **단일 HTML 파일** (외부 의존성 없음)
- `show_widget(Visualizer)` 사용 금지

---

## 2. 데이터 구조

```js
const tlData = [
  {
    date: 'YYYY.MM.DD',   // 필수
    type: 'reg',          // 필수: reg | doc | send | key | risk
    label: '...',         // 필수: 카드 제목
    note: '...',          // 선택: 부가 설명
    result: '...',        // 선택: 송달 결과 텍스트 (send 타입)
    ok: true,             // 선택: true=초록, false=빨강 (result와 쌍으로)
    card: 'is-key',       // 선택: is-key | is-risk | is-reg (카드 테두리 강조)
  },
];
```

**type 기준:**
| type | 색상 | 용도 |
|------|------|------|
| reg  | 파랑 | 등기부 기재 사항 (소유권·근저당·압류·경매개시 등) |
| doc  | 초록 | 법원 제출 문건 (감정평가서·교부청구·보정서 등) |
| send | 보라 | 발송 문서 및 도달 결과 |
| key  | 주황 | 절차상 중요 이벤트 (매각기일·배당요구종기·개시결정 등) |
| risk | 빨강 | 투자자 주의 항목 (직접 type으로도, card:'is-risk'로도 표현 가능) |

---

## 3. ⚠️ 날짜 정렬 — 반드시 지켜야 할 핵심 규칙

`tlData` 배열의 선언 순서와 무관하게, **렌더링 시 반드시 날짜 오름차순으로 정렬**해야 합니다.
이를 빠뜨리면 등기·문건·송달이 유형별로 뭉쳐서 출력되어 시간 흐름이 깨집니다.

```js
// ✅ 올바른 렌더 함수 — sorted 사용
function tlRender() {
  const tl = document.getElementById('tl2');
  tl.innerHTML = '';

  // 반드시 날짜 기준 정렬
  const sorted = [...tlData].sort((a, b) =>
    a.date.replace(/\./g, '').localeCompare(b.date.replace(/\./g, ''))
  );

  // 이후 sorted.forEach(...) 로 렌더링
  sorted.forEach(item => { ... });
}

// ❌ 잘못된 예 — tlData를 직접 forEach
tlData.forEach(item => { ... }); // 선언 순서대로 출력되어 시간 역전 발생
```

---

## 4. 완성 코드 템플릿

아래를 기반으로 `tlData`만 교체하여 사용합니다.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>타임라인 — [사건번호]</title>
<style>
:root{
  --color-background-primary:#fff;
  --color-background-secondary:#f7f7f8;
  --color-text-primary:#1a1a1a;
  --color-text-secondary:#555;
  --color-text-tertiary:#999;
  --color-border-primary:#aaa;
  --color-border-secondary:#ccc;
  --color-border-tertiary:#e5e5e5;
  --border-radius-md:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#fff;color:#1a1a1a;padding:20px 24px 40px}
h2{font-size:15px;font-weight:600;margin-bottom:4px}
.sub{font-size:12px;color:#888;margin-bottom:18px}
.tl-wrap{padding:12px 0 24px;font-size:14px}
.tl-filter{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:18px}
.tl-filter button{padding:4px 12px;border-radius:20px;border:1px solid #ccc;background:#f7f7f8;color:#555;cursor:pointer;font-size:12px;transition:all .15s}
.tl-filter button.active{background:#1a1a1a;color:#fff;border-color:#1a1a1a;font-weight:500}
.tl-list{position:relative;padding-left:28px}
.tl-list::before{content:'';position:absolute;left:8px;top:6px;bottom:6px;width:1.5px;background:#e5e5e5}
.tl-item{position:relative;margin-bottom:3px;display:flex;align-items:flex-start;gap:10px}
.tl-item.hidden{display:none}
.tl-dot{position:absolute;left:-24px;top:11px;width:8px;height:8px;border-radius:50%;border:1.5px solid;flex-shrink:0}
.tl-dot.reg{background:#E6F1FB;border-color:#185FA5}
.tl-dot.doc{background:#EAF3DE;border-color:#3B6D11}
.tl-dot.send{background:#EEEDFE;border-color:#534AB7}
.tl-dot.key{background:#FAEEDA;border-color:#854F0B;width:10px;height:10px;left:-25px;top:10px}
.tl-dot.risk{background:#FCEBEB;border-color:#A32D2D;width:10px;height:10px;left:-25px;top:10px}
.tl-card{width:100%;padding:8px 12px;border-radius:8px;background:#f7f7f8;border:1px solid #e5e5e5;margin-bottom:4px}
.tl-card:hover{border-color:#ccc}
.tl-card.is-key{border-color:#BA7517}
.tl-card.is-risk{border-color:#A32D2D;background:#fff9f9}
.tl-card.is-reg{border-color:#185FA5}
.tl-date{font-size:11px;color:#999;margin-bottom:2px}
.tl-main{color:#1a1a1a;font-size:13px;line-height:1.5}
.tl-note{font-size:11px;color:#555;margin-top:3px;line-height:1.5}
.tl-result{font-size:11px;margin-top:2px}
.tl-result.ok{color:#3B6D11}
.tl-result.warn{color:#A32D2D}
.tl-badge{display:inline-block;font-size:10px;padding:1px 6px;border-radius:10px;margin-right:5px;font-weight:500;vertical-align:middle;white-space:nowrap}
.b-reg{background:#B5D4F4;color:#0C447C}
.b-doc{background:#C0DD97;color:#27500A}
.b-send{background:#CECBF6;color:#26215C}
.b-key{background:#FAC775;color:#633806}
.b-risk{background:#F7C1C1;color:#501313}
.month-sep{font-size:11px;font-weight:500;color:#999;padding:14px 0 4px;letter-spacing:.05em;border-top:1px solid #e5e5e5;margin-top:8px}
.month-sep:first-child{border-top:none;margin-top:0;padding-top:4px}
</style>
</head>
<body>
<h2>[사건번호] · [사건명]</h2>
<div class="sub">[소재지] · [담당법원]</div>

<div class="tl-wrap">
<div class="tl-filter">
  <button class="active" onclick="tlFilter('all',this)">전체</button>
  <button onclick="tlFilter('reg',this)">등기</button>
  <button onclick="tlFilter('doc',this)">문건</button>
  <button onclick="tlFilter('send',this)">송달</button>
  <button onclick="tlFilter('key',this)">주요 이벤트</button>
  <button onclick="tlFilter('risk',this)">⚠ 리스크</button>
</div>
<div class="tl-list" id="tl2"></div>
</div>

<script>
const tlData=[
  // ← 여기에 데이터 입력
];

let curFilter='all';
function tlGetMonth(d){return d.slice(0,7)}

function tlRender(){
  const tl=document.getElementById('tl2');
  tl.innerHTML='';

  // ★ 날짜 오름차순 정렬 (선언 순서 무관)
  const sorted=[...tlData].sort((a,b)=>
    a.date.replace(/\./g,'').localeCompare(b.date.replace(/\./g,''))
  );

  const typeFilter={
    all:()=>true,
    reg:i=>i.type==='reg',
    doc:i=>i.type==='doc',
    send:i=>i.type==='send',
    key:i=>['key','risk'].includes(i.type),
    risk:i=>i.card==='is-risk'||i.type==='risk'
  };
  const badgeMap={reg:'등기',doc:'문건',send:'송달',key:'이벤트',risk:'리스크'};
  const badgeClass={reg:'b-reg',doc:'b-doc',send:'b-send',key:'b-key',risk:'b-risk'};
  const dotClass={reg:'reg',doc:'doc',send:'send',key:'key',risk:'risk'};
  let lastMonth='';

  sorted.forEach(item=>{
    const show=typeFilter[curFilter](item);
    const m=tlGetMonth(item.date);
    if(show&&m!==lastMonth){
      const sep=document.createElement('div');
      sep.className='month-sep';
      sep.textContent=m.replace('-','년 ')+'월';
      tl.appendChild(sep);
      lastMonth=m;
    }
    const wrap=document.createElement('div');
    wrap.className='tl-item'+(show?'':' hidden');
    const dot=document.createElement('div');
    const dc=dotClass[item.type]||'doc';
    dot.className='tl-dot '+(item.card==='is-risk'?'risk':item.card==='is-key'?'key':dc);
    const card=document.createElement('div');
    const cardCls=item.card||'';
    card.className='tl-card'+(cardCls?' '+cardCls:'');
    const bt=item.type==='risk'?'risk':item.type;
    const badge=`<span class="tl-badge ${badgeClass[bt]||'b-doc'}">${badgeMap[bt]||'문건'}</span>`;
    let html=`<div class="tl-date">${item.date}</div><div class="tl-main">${badge}${item.label}</div>`;
    if(item.note)html+=`<div class="tl-note">${item.note}</div>`;
    if(item.result)html+=`<div class="tl-result ${item.ok?'ok':'warn'}">${item.result}</div>`;
    card.innerHTML=html;
    wrap.appendChild(dot);
    wrap.appendChild(card);
    tl.appendChild(wrap);
  });
}

function tlFilter(type,btn){
  curFilter=type;
  document.querySelectorAll('.tl-filter button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  tlRender();
}
tlRender();
</script>
</body>
</html>
```

---

## 5. 자주 하는 실수 체크리스트

- [ ] `sorted.forEach` 대신 `tlData.forEach` 쓰지 않았는가?
- [ ] `tlData` 선언 순서를 날짜 순으로 맞췄다고 정렬 생략하지 않았는가?
- [ ] `send` 타입 항목에 `result` + `ok` 필드를 함께 입력했는가?
- [ ] 말소된 등기는 제외했는가?
- [ ] 주요 이벤트(매각기일·배당요구종기)에 `type:'key'` 또는 `card:'is-key'` 붙였는가?
- [ ] 리스크 항목에 `card:'is-risk'` 붙였는가?
