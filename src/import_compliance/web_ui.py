"""사람용 단일 페이지 웹 UI (`GET /`).

원칙
----
1. **외부 의존 0**: CSS·JS·이미지를 모두 인라인으로 넣는다(CDN·폰트·트래커 없음).
   서버 CSP가 외부 로드를 아예 막으므로, 페이지가 스스로 완결되어야 한다.
2. **익명**: 운영 주체의 실명·이메일·사업자 정보·연락처를 페이지 어디에도 넣지 않는다.
   예외는 하단 'CLNS Pro 사전 신청·도입 문의' 폼뿐이며, 여기서 받는 연락처는 회신 목적으로만
   저장하고 화면·통계에 다시 노출하지 않는다.
3. **단정 금지**: 판정 문구는 전부 "가능성·확인 필요"로 표기하고, 면책을 하단에 고정한다.
4. **입력값만 전송**: 조회 폼은 품목명·HS·원산지·무선 여부·어린이 대상·품목군·수입 목적만 보낸다.
   문의 폼은 관심 항목·회신 연락처·선택 메모만 보낸다.
5. **공유는 요약만**: 결과 공유 링크에는 품목명·품목군·원산지 같은 안전한 파라미터만 담고,
   상세페이지 전문·성분표·연락처 같은 입력 본문은 담지 않는다.
"""
from __future__ import annotations

from . import site_verification
from .version import __version__

SERVICE_NAME = "CLNS"
SERVICE_SUBTITLE_EN = "PRODUCT COMPLIANCE INTELLIGENCE · KOREA"
SERVICE_SUBTITLE_KO = "복잡한 한국 수입 규제를 10초 만에 확인"
SERVICE_TAGLINE = "Clearance, simplified."
SERVICE_VERSION = __version__

PAGE_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>CLNS · PRODUCT COMPLIANCE INTELLIGENCE · KOREA</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231a4fd6'/%3E%3Ctext x='16' y='23' font-size='19' font-weight='700' fill='white' text-anchor='middle' font-family='sans-serif'%3EC%3C/text%3E%3C/svg%3E">
<meta name="description" content="CLNS — Korea Import Compliance MCP &amp; API. PRODUCT COMPLIANCE INTELLIGENCE · KOREA. Clearance, simplified. 품목명·HS 코드·원산지만으로 세관장확인 요건, 식약처 수입 이력, 국내 리콜 이력, 근거 법령을 한 번에 확인하는 무료 사전 점검. 관세사·법률 자문이 아닌 참고용입니다.">
<link rel="canonical" href="https://clns-kr.onrender.com/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="CLNS">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="CLNS — 수입 요건 10초 확인 (한국 수입 규제 사전 점검)">
<meta property="og:description" content="품목명과 HS 10자리만 넣으면 세관장확인 요건·식약처 수입 이력·국내 리콜·근거 법령을 한 번에. 무료, 회원가입 없음.">
<meta property="og:url" content="https://clns-kr.onrender.com/">
<meta property="og:image" content="https://clns-kr.onrender.com/static/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="CLNS — 한국 수입 규제 10초 점검">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="CLNS — 수입 요건 10초 확인">
<meta name="twitter:description" content="세관장확인 요건·식약처 수입 이력·국내 리콜·근거 법령을 한 화면에서. 무료 베타.">
<meta name="twitter:image" content="https://clns-kr.onrender.com/static/og.png">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "CLNS",
  "alternateName": "Korea Import Compliance MCP & API",
  "url": "https://clns-kr.onrender.com/",
  "applicationCategory": "BusinessApplication",
  "operatingSystem": "Web",
  "inLanguage": "ko-KR",
  "description": "한국 수입 규제(세관장확인 요건·식약처 수입 이력·국내 리콜·근거 법령)를 3단계로 판정하는 무료 사전 점검 서비스. 관세사·법률 자문이 아닌 참고용.",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "KRW" },
  "isAccessibleForFree": true
}
</script>
<style>
:root{
  --bg:#f4f6fa; --card:#ffffff; --ink:#12161f; --ink-soft:#4c5566; --line:#dde3ec;
  --brand:#1a4fd6; --brand-soft:#e8eefc;
  --ok:#0f7a4a; --ok-soft:#e4f6ec;
  --warn:#9a5b00; --warn-soft:#fdf1dc;
  --info:#1f5f9e; --info-soft:#e7f1fb;
  --danger:#a4231f; --danger-soft:#fbe9e8;
  --radius:14px;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#0e1116; --card:#161b22; --ink:#e8edf5; --ink-soft:#a7b1c2; --line:#2a3240;
    --brand:#7ea6ff; --brand-soft:#18233c;
    --ok:#5fd39a; --ok-soft:#12291f;
    --warn:#f0bb63; --warn-soft:#2a2113;
    --info:#82b6ea; --info-soft:#132436;
    --danger:#f09a95; --danger-soft:#2c1615;
  }
}
*{box-sizing:border-box}
[hidden]{display:none !important}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
  line-height:1.55; font-size:16px;
}
a{color:var(--brand); text-underline-offset:2px}
.wrap{max-width:1000px; margin:0 auto; padding:0 16px 64px}
header.top{display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
  padding:22px 0 14px; border-bottom:1px solid var(--line)}
.brand{display:flex; gap:12px; align-items:center; min-width:0}
.mark{width:38px;height:38px;border-radius:11px;background:var(--brand);color:#fff;
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:19px;flex:0 0 auto}
.brand h1{margin:0; font-size:20px; letter-spacing:.14em; text-transform:uppercase}
.brand p{margin:1px 0 0; font-size:12.5px; color:var(--ink-soft)}
.brand p.sub-en{font-size:10.5px; letter-spacing:.1em; text-transform:uppercase}
.brand p.slogan{font-size:12.5px; font-weight:600; color:var(--brand)}
.badges{display:flex; gap:6px; flex-wrap:wrap}
.pill{font-size:11.5px; font-weight:600; padding:4px 9px; border-radius:999px;
  background:var(--brand-soft); color:var(--brand); border:1px solid transparent; white-space:nowrap}
.pill.ghost{background:transparent; color:var(--ink-soft); border-color:var(--line)}
nav.tabs{display:flex; gap:6px; padding:14px 0 0; overflow-x:auto; -webkit-overflow-scrolling:touch}
nav.tabs button{
  flex:0 0 auto; font:inherit; font-size:14px; font-weight:600; padding:9px 14px; cursor:pointer;
  background:transparent; color:var(--ink-soft); border:1px solid transparent; border-radius:999px;
}
nav.tabs button[aria-selected="true"]{background:var(--card); color:var(--ink); border-color:var(--line);
  box-shadow:0 1px 2px rgba(16,24,40,.06)}
nav.tabs button .tab-ko{display:block; margin-top:1px; font-size:10.5px; font-weight:500;
  color:var(--ink-soft); letter-spacing:0; text-transform:none}
@media (max-width:680px){
  nav.tabs button{font-size:12.5px; padding:8px 11px}
  nav.tabs button .tab-ko{font-size:9.5px}
}
/* 390px 폭에서 3개 탭이 잘리지 않게 3열로 정렬한다. */
@media (max-width:430px){
  nav.tabs{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px;
    overflow:visible; padding-top:12px}
  nav.tabs button{width:100%; font-size:11.5px; padding:8px 6px; line-height:1.25;
    white-space:normal; word-break:keep-all; text-align:center}
  nav.tabs button .tab-ko{font-size:9.5px}
}
nav.tabs button:focus-visible{outline:2px solid var(--brand); outline-offset:2px}
main{padding-top:18px}
section[hidden]{display:none}
.card{background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:20px; box-shadow:0 1px 2px rgba(16,24,40,.04)}
.card + .card{margin-top:14px}
h2{font-size:16px; margin:0 0 4px; letter-spacing:-.2px}
h3{font-size:14.5px; margin:18px 0 8px}
.sub{margin:0 0 16px; color:var(--ink-soft); font-size:13px}
.lead{margin:8px 0 4px; font-size:14px; font-weight:700; color:var(--ink)}
.grid{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px}
.grid .full{grid-column:1 / -1}
@media (max-width:680px){ .grid{grid-template-columns:1fr} }
label.field, .field{display:block}
.field > .lab{display:block; font-size:13px; font-weight:600; margin-bottom:5px}
.field > .lab .req{color:var(--danger); margin-left:2px}
.field > .lab .opt{color:var(--ink-soft); font-weight:500; margin-left:4px; font-size:11.5px}
input[type=text], select, textarea{
  width:100%; font:inherit; font-size:15px; color:var(--ink); background:var(--bg);
  border:1px solid var(--line); border-radius:10px; padding:11px 12px; appearance:none;
}
textarea{resize:vertical; min-height:84px; line-height:1.5}
select{background-image:none; cursor:pointer}
input[type=text]:focus, select:focus, textarea:focus{outline:2px solid var(--brand); outline-offset:1px; border-color:transparent}
.hint{display:block; margin-top:5px; font-size:11.5px; color:var(--ink-soft)}
.seg{display:flex; gap:6px; flex-wrap:wrap}
.seg label{position:relative; flex:1 1 0; min-width:74px}
.seg input{position:absolute; opacity:0; width:1px; height:1px}
.seg span{display:block; text-align:center; cursor:pointer; font-size:13.5px; font-weight:600;
  padding:10px 6px; border:1px solid var(--line); border-radius:10px; background:var(--bg);
  color:var(--ink-soft); user-select:none}
.seg input:checked + span{background:var(--brand-soft); border-color:var(--brand); color:var(--brand)}
.seg input:focus-visible + span{outline:2px solid var(--brand); outline-offset:2px}
.presets{display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:0 0 14px}
.presets .plabel{font-size:12px; font-weight:600; color:var(--ink-soft); margin-right:2px}
.presets button{font:inherit; font-size:13px; font-weight:600; color:var(--brand);
  background:var(--brand-soft); border:1px solid transparent; border-radius:999px;
  padding:9px 13px; cursor:pointer; min-height:38px; white-space:nowrap}
.presets button:hover{border-color:var(--brand)}
.presets button:focus-visible{outline:2px solid var(--brand); outline-offset:2px}
@media (max-width:430px){ .presets button{font-size:12.5px; padding:9px 11px} }
.actions{display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:18px}
button.primary{
  font:inherit; font-size:15px; font-weight:700; color:#fff; background:var(--brand);
  border:0; border-radius:11px; padding:13px 22px; cursor:pointer; min-height:46px;
}
button.primary:disabled{opacity:.6; cursor:progress}
button.ghost{font:inherit; font-size:13.5px; font-weight:600; color:var(--ink-soft); background:transparent;
  border:1px solid var(--line); border-radius:10px; padding:10px 14px; cursor:pointer}
.note-inline{font-size:12px; color:var(--ink-soft)}
#result, #hs-result{margin-top:16px}
.verdict{border-radius:12px; padding:14px 16px; border:1px solid var(--line); background:var(--info-soft)}
.verdict .code{font-size:12px; font-weight:700; letter-spacing:.02em; text-transform:uppercase; opacity:.85}
.verdict .lab{font-size:19px; font-weight:800; letter-spacing:-.3px; margin:2px 0 2px; color:var(--ink)}
.verdict .en{font-size:12px; font-weight:600; color:var(--ink-soft); margin-left:6px}
.verdict p{margin:6px 0 0; font-size:12.5px; color:var(--ink-soft)}
.statusrow{margin-top:9px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; font-size:12.5px; color:var(--ink-soft)}
.statusrow code{font-size:11.5px; font-weight:700; background:var(--info-soft); color:var(--info); padding:2px 6px; border-radius:6px}
.missrow{margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; font-size:12px; color:var(--ink-soft)}
.v-check_likely{background:var(--warn-soft); border-color:var(--warn)}
.v-check_likely .lab{color:var(--warn)}
.v-info_needed{background:var(--info-soft); border-color:var(--info)}
.v-info_needed .lab{color:var(--info)}
.v-low_risk{background:var(--ok-soft); border-color:var(--ok)}
.v-low_risk .lab{color:var(--ok)}
.meta-line{display:flex; gap:10px; flex-wrap:wrap; font-size:11.5px; color:var(--ink-soft); margin:10px 0 0}
.meta-line code{font-size:11.5px}
.tbl-wrap{overflow-x:auto; border:1px solid var(--line); border-radius:10px; margin-top:8px}
table{width:100%; border-collapse:collapse; font-size:13px; min-width:520px}
th,td{text-align:left; padding:9px 11px; border-bottom:1px solid var(--line); vertical-align:top}
th{background:var(--bg); font-size:12px; font-weight:700; color:var(--ink-soft); white-space:nowrap}
tr:last-child td{border-bottom:0}
ul.check{list-style:none; margin:8px 0 0; padding:0}
ul.check li{position:relative; padding:7px 0 7px 28px; font-size:13.5px; border-bottom:1px dashed var(--line)}
ul.check li:last-child{border-bottom:0}
ul.check li::before{content:""; position:absolute; left:2px; top:12px; width:14px; height:14px;
  border:1.6px solid var(--brand); border-radius:4px}
ol.steps{margin:8px 0 0; padding-left:20px; font-size:13.5px}
ol.steps li{margin:4px 0}
ul.plain{margin:6px 0 0; padding-left:18px; font-size:13.5px}
ul.plain li{margin:4px 0}
details{border:1px solid var(--line); border-radius:10px; padding:0; margin:8px 0 0; background:var(--bg)}
details summary{cursor:pointer; padding:11px 13px; font-size:13.5px; font-weight:600; list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"+"; display:inline-block; width:16px; color:var(--brand); font-weight:800}
details[open] summary::before{content:"-" }
details .body{padding:0 13px 13px; font-size:13px; color:var(--ink-soft)}
details .body p{margin:6px 0}
details.card{background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:0; margin-top:14px; box-shadow:0 1px 2px rgba(16,24,40,.04)}
details.card > summary{padding:16px 20px; font-size:15px; font-weight:700; color:var(--ink)}
details.card > summary .sum-sub{display:block; margin-top:3px; padding-left:16px; font-size:12.5px; font-weight:400; color:var(--ink-soft)}
details.card .card-body{padding:0 20px 20px}
.tag{display:inline-block; font-size:11px; font-weight:700; padding:2px 7px; border-radius:6px;
  background:var(--brand-soft); color:var(--brand); margin-right:5px}
.tag.ok{background:var(--ok-soft); color:var(--ok)}
.tag.warn{background:var(--warn-soft); color:var(--warn)}
.tag.info{background:var(--info-soft); color:var(--info)}
.tag.bad{background:var(--danger-soft); color:var(--danger)}
.ev{border-left:3px solid var(--brand); padding:8px 0 8px 12px; margin:10px 0 0}
.ev .law{font-weight:700; font-size:13.5px; color:var(--ink)}
.ev .date{font-size:11.5px; color:var(--ink-soft); margin-left:6px}
.ev blockquote{margin:6px 0; font-size:12.5px; color:var(--ink-soft); border:0; padding:0}
.ev a{font-size:11.5px; word-break:break-all}
.empty{font-size:13px; color:var(--ink-soft); padding:12px; border:1px dashed var(--line); border-radius:10px}
.spinner{display:inline-block; width:14px; height:14px; border:2px solid var(--line);
  border-top-color:var(--brand); border-radius:50%; animation:spin .8s linear infinite; vertical-align:-2px}
@keyframes spin{to{transform:rotate(360deg)}}
pre{background:var(--bg); border:1px solid var(--line); border-radius:10px; padding:12px;
  overflow-x:auto; font-size:12.5px; line-height:1.5; margin:8px 0 0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
footer{margin-top:30px; padding-top:16px; border-top:1px solid var(--line); font-size:12px; color:var(--ink-soft)}
footer p{margin:6px 0}
footer strong{color:var(--ink)}
.sharebar{display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:12px}
.sharebar button{
  font:inherit; font-size:13px; font-weight:700; color:var(--brand); background:var(--brand-soft);
  border:1px solid transparent; border-radius:10px; padding:9px 13px; cursor:pointer;
}
.sharebar button:hover{border-color:var(--brand)}
.sharebar button:focus-visible{outline:2px solid var(--brand); outline-offset:2px}
.sharebar .copied{font-size:12.5px; font-weight:700; color:var(--ok)}
.card.inquiry{margin-top:14px; padding:16px 18px; background:var(--card)}
.card.inquiry h2{font-size:15px}
.card.inquiry .sub{margin:0 0 12px; font-size:12.5px}
.card.inquiry .hint{font-size:11.5px}
.sr{position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden;
  clip:rect(0,0,0,0); white-space:nowrap; border:0}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="mark" aria-hidden="true">C</div>
      <div>
        <h1>CLNS</h1>
        <p class="sub-en">PRODUCT COMPLIANCE INTELLIGENCE · KOREA</p>
        <p class="slogan">Clearance, simplified.</p>
      </div>
    </div>
    <div class="badges">
      <span class="pill">결제 없음</span>
      <span class="pill ghost">회원가입 없음</span>
      <span class="pill ghost" id="quota-pill">무료 한도 확인 중</span>
    </div>
  </header>

  <nav class="tabs" role="tablist" aria-label="화면 선택">
    <button type="button" role="tab" id="tabbtn-check" aria-controls="tab-check" aria-selected="true" data-tab="check">CLNS Check<span class="tab-ko">통합 리스크 체크</span></button>
    <button type="button" role="tab" id="tabbtn-hs" aria-controls="tab-hs" aria-selected="false" data-tab="hs">CLNS Intelligence<span class="tab-ko">HS·법령·리콜</span></button>
    <button type="button" role="tab" id="tabbtn-api" aria-controls="tab-api" aria-selected="false" data-tab="api">CLNS API &amp; MCP<span class="tab-ko">개발자 연결</span></button>
  </nav>

  <main>
    <!-- ================= 리스크 체크 ================= -->
    <section id="tab-check" role="tabpanel" aria-labelledby="tabbtn-check">
      <div class="card">
        <h2>CLNS Check</h2>
        <p class="sub">수입·반입 전 10초 통합 체크 · 품목명만 넣어도 규제·의약품·리콜을 한 번에 확인합니다. 결과는 확정 판정이 아니라 <strong>확인할 항목의 목록</strong>입니다.</p>
        <form id="check-form" novalidate>
          <div class="presets" role="group" aria-label="대표 품목으로 바로 체험">
            <span class="plabel">대표 품목으로 1초 체험</span>
            <button type="button" class="preset" id="preset-supplement" data-preset="supplement">영양제 직구</button>
            <button type="button" class="preset" id="preset-dog-treat" data-preset="dog-treat">강아지 간식</button>
            <button type="button" class="preset" id="preset-cosmetics" data-preset="cosmetics">수입 화장품</button>
            <button type="button" class="preset" id="preset-earbuds" data-preset="earbuds">블루투스 이어폰</button>
            <button type="button" class="preset" id="preset-kids-clothes" data-preset="kids-clothes">유아용 의류</button>
          </div>
          <div class="grid">
            <label class="field full" for="product">
              <span class="lab">품목명<span class="req">*</span></span>
              <input type="text" id="product" name="product" maxlength="80" autocomplete="off"
                     placeholder="예: 중국산 블루투스 스피커, 비타민 D3, 멜라토닌, 유아용 원목 완구">
              <span class="hint">제품명·성분명·용도를 적으면 관련 규제(전파·식약처·의약품·어린이제품)를 자동으로 찾아 판정합니다.</span>
            </label>

            <label class="field" for="hs">
              <span class="lab">HS 코드<span class="opt">선택</span></span>
              <input type="text" id="hs" name="hs" maxlength="10" inputmode="numeric" autocomplete="off"
                     placeholder="10자리 (예: 8518220000)">
              <span class="hint">10자리를 넣으면 관세청 세관장확인대상물품을 실시간 조회합니다(6자리는 요건 판정에 부족).</span>
            </label>

            <label class="field" id="rra-wrap" for="rra" hidden>
              <span class="lab">적합성평가 번호<span class="opt">선택</span></span>
              <input type="text" id="rra" name="rra" maxlength="40" autocomplete="off"
                     placeholder="예: R-LARN-00-0210">
              <span class="hint">전파 적합성평가는 번호가 있어야 실시간 조회됩니다(국립전파연구원, 키 불필요).</span>
            </label>

            <label class="field" for="origin">
              <span class="lab">원산지<span class="opt">선택</span></span>
              <select id="origin" name="origin">
                <option value="">선택 안 함</option>
                <option value="중국">중국</option>
                <option value="미국">미국</option>
                <option value="일본">일본</option>
                <option value="베트남">베트남</option>
                <option value="대만">대만</option>
                <option value="태국">태국</option>
                <option value="인도네시아">인도네시아</option>
                <option value="인도">인도</option>
                <option value="독일">독일</option>
                <option value="멕시코">멕시코</option>
                <option value="기타">기타</option>
              </select>
            </label>

            <div class="field">
              <span class="lab">무선·블루투스 송신 기능</span>
              <div class="seg" role="radiogroup" aria-label="무선·블루투스 송신 기능">
                <label><input type="radio" name="wire" value="unknown" checked><span>모름</span></label>
                <label><input type="radio" name="wire" value="yes"><span>있음</span></label>
                <label><input type="radio" name="wire" value="no"><span>없음</span></label>
              </div>
              <span class="hint">있음이면 전파법 적합성평가(적합인증·적합등록) 쟁점이 붙습니다.</span>
            </div>

            <div class="field">
              <span class="lab">어린이 대상 제품</span>
              <div class="seg" role="radiogroup" aria-label="어린이 대상 제품">
                <label><input type="radio" name="child" value="no" checked><span>아니오</span></label>
                <label><input type="radio" name="child" value="yes"><span>예</span></label>
              </div>
              <span class="hint">만 13세 이하 사용 제품이면 어린이제품 안전관리 쟁점을 함께 봅니다.</span>
            </div>

            <label class="field" for="kind">
              <span class="lab">품목군<span class="opt">선택</span></span>
              <select id="kind" name="kind">
                <option value="">자동 판단</option>
                <option value="food">식품</option>
                <option value="health_functional">건강기능식품</option>
                <option value="cosmetics">화장품</option>
                <option value="drug">의약품·영양제</option>
                <option value="food_contact">식품용 기구·용기·포장</option>
                <option value="electronics">전자·생활용품</option>
                <option value="feed">반려동물 사료·간식</option>
              </select>
              <span class="hint">화장품·의약품·식품을 고르거나 품목명에 적으면 추가 대조 항목이 자동으로 열립니다.</span>
            </label>

            <div class="field full">
              <span class="lab">수입 목적</span>
              <div class="seg" role="radiogroup" aria-label="수입 목적">
                <label><input type="radio" name="purpose" value="resale" checked><span>판매·유통</span></label>
                <label><input type="radio" name="purpose" value="self_use"><span>자가소비·휴대 반입</span></label>
              </div>
              <span class="hint">판매 목적이면 표시·인증·영업등록 요건이 함께 걸립니다. 자가소비는 개인 반입 면제 범위(6병 기준 등)를 따집니다.</span>
            </div>

            <div class="field full" id="drug-fields-wrap" hidden>
              <div class="grid">
                <div class="field">
                  <span class="lab">반입 경로</span>
                  <div class="seg" role="radiogroup" aria-label="반입 경로">
                    <label><input type="radio" name="drug-channel" value="carry" checked><span>휴대 반입</span></label>
                    <label><input type="radio" name="drug-channel" value="online"><span>해외직구</span></label>
                    <label><input type="radio" name="drug-channel" value="unknown"><span>모름</span></label>
                  </div>
                  <span class="hint">직구는 6병 기준 자가사용 반입이 허용되지 않는 경로입니다.</span>
                </div>
                <label class="field" for="drug-qty">
                  <span class="lab">수량·단위<span class="opt">선택</span></span>
                  <div style="display:flex;gap:8px">
                    <input type="text" id="drug-qty" name="drug-qty" maxlength="3" inputmode="numeric" autocomplete="off" placeholder="예: 2" style="flex:1">
                    <select id="drug-unit" name="drug-unit" style="width:92px">
                      <option value="병">병</option>
                      <option value="정">정</option>
                      <option value="캡슐">캡슐</option>
                      <option value="개">개</option>
                    </select>
                  </div>
                  <span class="hint">자가사용 인정기준(6병·3개월 복용량)과 대조합니다.</span>
                </label>
                <label class="field" for="drug-rx">
                  <span class="lab">처방전 유무<span class="opt">선택</span></span>
                  <select id="drug-rx" name="drug-rx">
                    <option value="unknown">모름</option>
                    <option value="yes">있음</option>
                    <option value="no">없음</option>
                  </select>
                </label>
              </div>
            </div>

            <div class="field full">
              <details id="ad-onestop-wrap">
                <summary>상세페이지·광고·라벨 문구 함께 검수하기 <span class="opt" style="font-weight:500;color:var(--ink-soft)">(선택 · 원스톱)</span></summary>
                <div class="body" style="padding-top:10px">
                  <div class="grid">
                    <div class="field full">
                      <span class="lab">기능성 여부</span>
                      <div class="seg" role="radiogroup" aria-label="기능성 여부">
                        <label><input type="radio" name="ad-functional" value="unknown" checked><span>모름</span></label>
                        <label><input type="radio" name="ad-functional" value="yes"><span>기능성(심사·보고 완료)</span></label>
                        <label><input type="radio" name="ad-functional" value="no"><span>일반 제품</span></label>
                      </div>
                    </div>
                    <label class="field full" for="ad-copy-onestop">
                      <span class="lab">상세페이지·광고 문구<span class="opt">선택</span></span>
                      <textarea id="ad-copy-onestop" name="ad-copy-onestop" rows="3" maxlength="4000"
                                placeholder="예: 먹기만 하면 100% 다이어트! 면역력 강화·암 예방"></textarea>
                      <span class="hint">식약처 과대광고 검수와 함께, 공정거래위원회 표시광고법·전자상거래법 기준(허위 정가·마감임박, 체험단 대가성 미표기, 청약철회 제한, 배송·품절 책임 회피, 최저가·1위, 구독·자동결제, 가격·해지 다크패턴)도 같이 봅니다. 국내 셀러는 상세페이지 문구만 붙여넣어도 됩니다.</span>
                    </label>
                    <label class="field full" for="ad-label-onestop">
                      <span class="lab">라벨·한글표시사항 문구<span class="opt">선택</span></span>
                      <textarea id="ad-label-onestop" name="ad-label-onestop" rows="2" maxlength="4000"
                                placeholder="예: 제품명 비타민D3 / 내용량 60정 / 원료명 … / 소비기한 2027.03.15"></textarea>
                      <span class="hint">포장에 적힌 항목을 옮기면 필수 한글표시사항 누락을 대조합니다.</span>
                    </label>
                  </div>
                </div>
              </details>
            </div>

            <label class="field full" id="cosmetic-ingredients-wrap" for="cosmetic-ingredients-onestop" hidden>
              <span class="lab">화장품 전성분<span class="opt">선택 · 배합금지/한도 대조</span></span>
              <textarea id="cosmetic-ingredients-onestop" name="cosmetic-ingredients-onestop" rows="2" maxlength="4000"
                        placeholder="예: Water, Hydroquinone, Salicylic Acid, Phenoxyethanol (쉼표 또는 줄바꿈 구분)"></textarea>
              <span class="hint">화장품·속눈썹영양제·스킨케어라면 전성분(한글·INCI)을 넣어 배합금지·한도 성분을 함께 확인하세요.</span>
            </label>
          </div>

          <div class="actions">
            <button type="submit" class="primary" id="check-submit">리스크 체크</button>
            <button type="button" class="ghost" id="check-demo">예시로 채워 보기</button>
            <button type="button" class="ghost" id="check-demo-shop">국내 판매페이지 예시</button>
            <button type="button" class="ghost" id="check-demo-feed">반려동물 사료 예시</button>
            <button type="button" class="ghost" id="check-reset">입력 지우기</button>
            <span class="note-inline" id="form-note" aria-live="polite"></span>
          </div>
        </form>
      </div>

      <div class="card" id="ec-only-card">
        <h2>국내 판매페이지 문구만 빠르게 검수</h2>
        <p class="sub">수입 요건 없이 상세페이지 문구만 넣어도 됩니다. 공정거래위원회 표시광고법·전자상거래법 기준으로 위험 문구와 빠진 고지를 확인합니다. 입력한 문구는 저장하지 않습니다.</p>
        <label class="field full" for="ec-copy">
          <span class="lab">상세페이지 문구<span class="req">*</span></span>
          <textarea id="ec-copy" rows="3" maxlength="8000"
                    placeholder="예: 정가 39,000원 → 오늘만 19,900원! 단순변심 환불 불가 / 체험단으로 선정되어 직접 써봤어요"></textarea>
          <span class="hint">가격·후기·청약철회·배송·구독 안내를 페이지에 적힌 그대로 붙여넣으세요. 고지 항목(상호·연락처·판매자 신고번호·청약철회·배송)까지 함께 대조합니다.</span>
        </label>
        <div class="grid">
          <label class="field" for="ec-channel">
            <span class="lab">판매 채널<span class="opt">선택</span></span>
            <select id="ec-channel">
              <option value="own">자사몰</option>
              <option value="smartstore">네이버 스마트스토어</option>
              <option value="coupang">쿠팡</option>
              <option value="other">기타(오픈마켓·SNS 커머스)</option>
            </select>
          </label>
        </div>
        <div class="actions">
          <button type="button" class="primary" id="ec-submit">판매페이지 검수</button>
          <button type="button" class="ghost" id="ec-demo">예시로 채워 보기</button>
          <span class="note-inline" id="ec-note" aria-live="polite"></span>
        </div>
        <div id="ec-result" aria-live="polite"></div>
        <div class="sharebar" id="ec-share" hidden>
          <button type="button" id="ec-copy-summary">결과 요약 복사</button>
          <button type="button" id="ec-copy-link">공유 링크 복사</button>
          <span class="copied" id="ec-share-note" role="status" aria-live="polite"></span>
        </div>
      </div>

      <div id="result" aria-live="polite"></div>
      <div class="sharebar" id="result-share" hidden>
        <button type="button" id="result-copy-summary">결과 요약 복사</button>
        <button type="button" id="result-copy-link">공유 링크 복사</button>
        <span class="copied" id="result-share-note" role="status" aria-live="polite"></span>
      </div>
    </section>

    <!-- ================= HS 조회 ================= -->
    <section id="tab-hs" role="tabpanel" aria-labelledby="tabbtn-hs" hidden>
      <div class="card">
        <h2>CLNS Intelligence</h2>
        <p class="sub">HS·법령·리콜 위험 분석 · HS 10자리(품목코드)로 세관장확인대상물품을 조회합니다. 조회 0건은 "요건 없음"이 아니라 "조회되지 않음"입니다.</p>
        <form id="hs-form" novalidate>
          <div class="grid">
            <label class="field" for="hs-code">
              <span class="lab">HS 10자리<span class="req">*</span></span>
              <input type="text" id="hs-code" name="hs-code" maxlength="10" inputmode="numeric"
                     autocomplete="off" placeholder="예: 8518220000">
              <span class="hint">숫자 10자리만 입력하세요. 6·8자리는 요건 판정에 부족합니다.</span>
            </label>
            <label class="field" for="hs-direction">
              <span class="lab">구분</span>
              <select id="hs-direction" name="hs-direction">
                <option value="import">수입</option>
                <option value="export">수출</option>
              </select>
            </label>
          </div>
          <div class="actions">
            <button type="submit" class="primary" id="hs-submit">요건 조회</button>
            <button type="button" class="ghost" id="hs-demo">예시로 채워 보기</button>
            <span class="note-inline" id="hs-note" aria-live="polite"></span>
          </div>
        </form>
      </div>
      <div id="hs-result" aria-live="polite"></div>
    </section>

    <!-- ================= 개발자 ================= -->
    <section id="tab-api" role="tabpanel" aria-labelledby="tabbtn-api" hidden>
      <div class="card">
        <h2>CLNS API &amp; MCP</h2>
        <p class="sub">외부 AI·서비스 연결용 한국 규제 API &amp; MCP · 같은 엔진을 JSON API와 MCP 툴 목록으로 노출합니다. 인증키·결제 없이 무료 베타로 운영합니다.</p>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>메서드</th><th>경로</th><th>설명</th></tr></thead>
            <tbody>
              <tr><td>GET</td><td><code>/</code></td><td>이 화면(사람용 웹 UI)</td></tr>
              <tr><td>GET</td><td><code>/healthz</code></td><td>헬스체크</td></tr>
              <tr><td>GET</td><td><code>/v1/meta</code></td><td>코퍼스 버전·판정 등급·무료 한도</td></tr>
              <tr><td>POST</td><td><code>/mcp</code> · <code>/v1/mcp</code></td><td>MCP JSON-RPC 2.0 (initialize·tools/list·tools/call·ping)</td></tr>
              <tr><td>GET</td><td><code>/.well-known/mcp/server-card.json</code></td><td>MCP 서버 카드(인증 없음·툴 14종 스키마)</td></tr>
              <tr><td>GET</td><td><code>/v1/mcp</code></td><td>MCP 툴 매니페스트(툴 14종, 사람이 읽는 JSON)</td></tr>
              <tr><td>GET</td><td><code>/guides/</code> · <code>/guides/{slug}</code></td><td>질문형·규제별 가이드(서버 렌더 HTML)</td></tr>
              <tr><td>GET</td><td><code>/v1/trends</code></td><td>일일 스냅샷 기반 리콜·행정처분 시계열 추이</td></tr>
              <tr><td>GET</td><td><code>/robots.txt</code> · <code>/llms.txt</code> · <code>/sitemap.xml</code></td><td>검색·AI 크롤러용 공개 파일</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/assess_import_case</code></td><td>종합 판정(웹 UI가 호출)</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/assess_import_risk</code></td><td>종합 판정(동일 툴 별칭)</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/lookup_hs_requirements</code></td><td>HS 10자리 세관장확인 요건</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_kc_certification</code></td><td>KC 인증 유형</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_food_cosmetics</code></td><td>식품·화장품·건기식 요건</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_drug_import</code></td><td>의약품·영양제 금지성분·반입 제한</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_ad_labeling</code></td><td>과대광고·한글표시사항 검수</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_ecommerce_compliance</code></td><td>국내 판매페이지 공정위·전자상거래법 검수</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/lookup_mfds_disposition</code></td><td>식약처 행정처분 이력</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/lookup_recall</code></td><td>국내 리콜 이력</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/get_legal_basis</code></td><td>근거 조항</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/get_compliance_trends</code></td><td>리콜·행정처분 시계열 추이</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/explain_trap</code></td><td>함정 케이스 해설</td></tr>
              <tr><td>POST</td><td><code>/v1/inquiry</code></td><td>CLNS Pro 사전 신청·도입 문의(비쿼터, 회신용 연락처만 보관)</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/get_service_meta</code></td><td>서비스·티어 정보</td></tr>
            </tbody>
          </table>
        </div>
        <h3>호출 예시</h3>
        <pre><code>curl -s -X POST <span class="base-slot">https://&lt;your-host&gt;</span>/v1/tools/assess_import_case \\
  -H 'Content-Type: application/json' \\
  -d '{"query":"중국산 블루투스 스피커를 수입해 판매","facts":{"rf_tx":"yes","purpose":"resale"}}'</code></pre>
        <p class="sub" style="margin-top:10px">응답에는 판정(<code>verdict</code>), 확인 항목(<code>answer.guidance</code>), 근거 법령·시행일·원문 URL(<code>evidence</code>), 면책(<code>disclaimer</code>)이 항상 함께 들어갑니다. 원본 공공 API 응답은 재전송하지 않고 결합·정규화한 결과만 돌려줍니다.</p>
        <h3>MCP 연결</h3>
        <p class="sub">MCP 클라이언트는 <code><span class="base-slot">https://&lt;your-host&gt;</span>/mcp</code>에 JSON-RPC 2.0으로 붙습니다(같은 경로가 <code>/v1/mcp</code>에도 있습니다). <code>initialize</code> → <code>notifications/initialized</code> → <code>tools/list</code> → <code>tools/call</code> 순서로 동작하며, 응답은 <code>application/json</code> 한 덩어리입니다(SSE 스트리밍은 제공하지 않습니다). 인증은 필요 없고, 서버 카드는 <code>/.well-known/mcp/server-card.json</code>에 있습니다.</p>
        <div class="actions">
          <a class="ghost" href="/v1/mcp" target="_blank" rel="noopener" style="text-decoration:none;padding:10px 14px">툴 매니페스트 열기</a>
          <a class="ghost" href="/.well-known/mcp/server-card.json" target="_blank" rel="noopener" style="text-decoration:none;padding:10px 14px">서버 카드 열기</a>
          <a class="ghost" href="/v1/meta" target="_blank" rel="noopener" style="text-decoration:none;padding:10px 14px">/v1/meta 열기</a>
        </div>
      </div>
    </section>
  </main>

  <!-- ================= CLNS Pro 사전 신청 · 도입 문의 ================= -->
  <section class="card inquiry" id="inquiry" aria-labelledby="inquiry-title">
    <h2 id="inquiry-title">CLNS Pro 사전 신청 · 도입 문의</h2>
    <p class="sub">엑셀/CSV 일괄 검수와 API·MCP 연동은 준비 중입니다. 필요하시면 남겨 주세요. 확인 후 남기신 연락처로만 회신드리며, 며칠 걸릴 수 있습니다.</p>
    <form id="inquiry-form" novalidate>
      <div class="grid">
        <label class="field" for="inquiry-topic">
          <span class="lab">관심 항목</span>
          <select id="inquiry-topic" name="inquiry-topic">
            <option value="clns_pro_batch">CLNS Pro · 엑셀/CSV 일괄 검수</option>
            <option value="api_mcp">API · MCP 연동</option>
            <option value="other">그 외 문의</option>
          </select>
        </label>
        <label class="field" for="inquiry-contact">
          <span class="lab">이메일 또는 연락처 <span class="req">*</span></span>
          <input type="text" id="inquiry-contact" name="inquiry-contact" maxlength="120"
                 autocomplete="off" placeholder="회신받을 이메일이나 연락처"
                 aria-describedby="inquiry-contact-hint">
          <span class="hint" id="inquiry-contact-hint">회신 목적으로만 저장합니다.</span>
        </label>
        <label class="field full" for="inquiry-message">
          <span class="lab">메모 <span class="opt">선택</span></span>
          <textarea id="inquiry-message" name="inquiry-message" rows="2" maxlength="500"
                    placeholder="다루는 품목 수, 연동하려는 서비스 등 편하게 적어 주세요."></textarea>
        </label>
      </div>
      <div class="actions">
        <button type="submit" class="primary" id="inquiry-submit">사전 신청 보내기</button>
        <span class="note-inline" id="inquiry-note" role="status" aria-live="polite"></span>
      </div>
      <p class="hint">이 폼에서 받은 연락처는 이 문의에 회신하는 데만 쓰고, 통계·공개 화면에는 넣지 않습니다.</p>
    </form>
  </section>

  <footer>
    <p><strong>CLNS</strong></p>
    <p>PRODUCT COMPLIANCE INTELLIGENCE · KOREA</p>
    <p>Clearance, simplified.</p>
    <p>무료 베타 · 결제 없음 · 회원가입 없음</p>
    <p><strong>품목별 수입 요건:</strong> <a href="/p/">선풍기·보조배터리·오메가3·선크림 등 35개 품목의 요건·인증·함정을 정리한 무료 체크 페이지</a></p>
    <p><strong>질문형 가이드:</strong> <a href="/guides/">영양제 6병, 면세 한도 150/200달러, KC·전파 인증, 한글표시사항, 과대광고 금지 표현, 단순변심 환불 불가 문구, 체험단 대가성 표시, 스마트스토어 상표권, 어린이제품 KC, 직구 전자제품 1인 1대 전파 예생, 화장품 미백·주름 문구, 목록통관 배제 품목, 향수 60mL·와인 직구, 콘택트렌즈·유모차 KC, 원두·차 수입신고, 구매대행 청약철회 등 자주 묻는 질문 __GUIDE_COUNT__개에 근거 법령으로 답한 페이지</a></p>
    <p><strong>면책:</strong> 본 결과는 사전 참고용입니다. 법적 효력이 없으며, 최종 법적 판단과 통관·인증 가능 여부는 관세사, 관세청, 국가기술표준원·인증기관, 식품의약품안전처 등 소관 기관의 확인이 필요합니다. 본 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않습니다.</p>
    <p><strong>데이터:</strong> 관세청·식품의약품안전처·산업통상부 국가기술표준원·과학기술정보통신부 국립전파연구원·법제처 공공데이터를 활용합니다. 의약품 성분은 마약류 관리에 관한 법률 시행령 별표 1~8을 로컬 사전으로 만들어 대조하며, 식약처 의약품 허가정보·e약은요·DUR API는 활용승인 전이라 실시간 전수 대조를 제공하지 않습니다. 원본을 그대로 중계하지 않고 결합·정규화한 판정만 제공하며, 조회 실패나 개정 지연 시 캐시 시점을 밝히고 판정을 "추가 정보 필요"로 낮춥니다.</p>
    <p><strong>개인정보:</strong> 품목 조회에는 이름·연락처·이메일·사업자 정보를 받지 않습니다. 위 'CLNS Pro 사전 신청·도입 문의'에 남긴 연락처는 회신하는 용도로만 저장하고, 통계·공개 화면에는 쓰지 않습니다. 입력한 품목 정보(품목명·HS·원산지 등)는 판정 이력에 익명으로 저장될 수 있습니다. 상호·주소 등 식별 정보는 입력하지 마세요.</p>
    <p>© 2026 CLNS · 익명 운영 무료 베타 · <span id="version">v__VERSION__</span></p>
  </footer>
</div>

<script>
(function(){
  "use strict";
  var BASE = location.origin;

  function esc(v){
    return String(v === null || v === undefined ? "" : v)
      .split("&").join("&amp;").split("<").join("&lt;").split(">").join("&gt;")
      .split('"').join("&quot;").split("'").join("&#39;");
  }
  function text(v){ return String(v === null || v === undefined ? "" : v); }
  function join(arr, sep){ return (arr || []).filter(function(x){ return x; }).join(sep || " "); }
  function clientId(){
    var id = "";
    try { id = localStorage.getItem("clns_cid") || ""; } catch(e){ id = ""; }
    if (!/^[a-z0-9]{8,40}$/.test(id)){
      id = "web-" + Math.random().toString(36).slice(2, 12);
      try { localStorage.setItem("clns_cid", id); } catch(e){}
    }
    return id;
  }
  var CID = clientId();

  function request(method, path, payload){
    var opts = { method: method, headers: { "X-Client-Id": CID, "X-Tier": "free" } };
    if (payload !== undefined){
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(payload);
    }
    return fetch(path, opts).then(function(res){
      return res.text().then(function(raw){
        var data = null;
       try { data = raw ? JSON.parse(raw) : null; } catch(e) { data = null; }
        if (!res.ok || !data){
          throw new Error("요청이 처리되지 않았습니다 (HTTP " + res.status + ")");
        }
        if (data.ok === false){
          if (data.error === "quota_exceeded"){
            throw new Error("이번 달 무료 점검 한도를 넘었습니다. 다음 달에 다시 이용할 수 있습니다.");
          }
          throw new Error(data.message || data.error || "요청이 처리되지 않았습니다");
        }
        return data.result !== undefined ? data.result : data;
      });
    });
  }
  function postTool(name, payload){ return request("POST", "/v1/tools/" + name, payload || {}); }
  function soft(promise){
    return promise.then(function(v){ return v; }, function(err){ return { __error: err && err.message ? err.message : "조회 실패" }; });
  }

  var FIELD_LABELS_KO = {
    claim_type: "표시·광고 문구 유형",
    ingredient: "주요 원료·성분명",
    import_channel: "수입 경로(판매/자가소비)",
    label_text: "라벨·한글표시사항 문구",
    hs_code: "HS 10자리 코드",
    origin: "원산지",
    rf_tx: "무선·블루투스 여부",
    target_age: "어린이 대상 여부",
    purpose: "수입 목적",
    quantity: "수량",
    prescription: "처방전 유무",
    product_name: "제품명",
    rra_cert_no: "적합성평가 번호"
  };
  function fieldKo(key){ return FIELD_LABELS_KO[key] || key; }

  // ---------- 조각 렌더 ----------
  function verdictBlock(v, result){
    if (!v) return "";
    var extra = "";
    result = result || {};
    var geo = [];
    if (result.destination) geo.push("목적지 " + result.destination);
    if (result.jurisdiction) geo.push("법령 " + result.jurisdiction);
    if (result.origin) geo.push("원산지 " + result.origin);
    if (result.assessment_status){
      extra += '<div class="statusrow"><span class="tag">상태</span>' +
        esc(result.assessment_status_label_ko || result.assessment_status) +
        (geo.length ? '<span class="note-inline">' + esc(geo.join(" · ")) + '</span>' : '') + '</div>';
    }
    if ((result.missing_information || []).length){
      extra += '<div class="missrow"><span class="tag info">추가 확인 항목</span>' +
        result.missing_information.map(function(m){ return '<code>' + esc(fieldKo(m)) + '</code>'; }).join(" ") + '</div>';
    }
    return '<div class="verdict v-' + esc(v.code) + '">' +
      '<div class="code">종합 판정</div>' +
      '<div class="lab">' + esc(v.label_ko) + '</div>' +
      '<p>' + esc(v.note_ko) + '</p>' + extra + '</div>';
  }
  function section(title, inner, sub){
    return '<div class="card"><h2>' + esc(title) + '</h2>' +
      (sub ? '<p class="sub">' + esc(sub) + '</p>' : '') + inner + '</div>';
  }
  function sectionCollapsible(title, inner, summaryText, sub){
    return '<div class="card"><details><summary>' + esc(title) + (summaryText ? ' · ' + esc(summaryText) : '') + '</summary>' +
      '<div class="body">' + (sub ? '<p class="sub">' + esc(sub) + '</p>' : '') + inner + '</div></details></div>';
  }
  function emptyBox(msg){ return '<div class="empty">' + esc(msg) + '</div>'; }
  function table(headers, rows){
    if (!rows || !rows.length) return "";
    var head = headers.map(function(h){ return "<th>" + esc(h[0]) + "</th>"; }).join("");
    var body = rows.map(function(row){
      return "<tr>" + headers.map(function(h){
        var cell = row[h[1]];
        return "<td>" + (cell === null || cell === undefined || cell === "" ? "—" : esc(cell)) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<div class="tbl-wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function checklist(result){
    var items = [];
    (result.next_actions || []).forEach(function(a){ items.push(a); });
    (result.findings || []).forEach(function(f){
      (f.missing_inputs || []).forEach(function(m){
        items.push("추가 확인 필요: " + (m.prompt || m.field));
      });
    });
    var uniq = [];
    items.forEach(function(x){ if (x && uniq.indexOf(x) === -1) uniq.push(x); });
    if (!uniq.length) return emptyBox("따로 확인할 항목이 제시되지 않았습니다. 다만 이 결과는 사전 참고용입니다.");
    return '<ul class="check">' + uniq.map(function(x){ return "<li>" + esc(x) + "</li>"; }).join("") + '</ul>';
  }

  function guidanceBlock(result){
    var answer = result.answer || {};
    var items = answer.guidance || [];
    var html = "";
    if (answer.headline) html += '<p class="lead">' + esc(answer.headline) + "</p>";
    if (items.length) html += '<ul class="plain">' + items.map(function(g){ return "<li>" + esc(g) + "</li>"; }).join("") + "</ul>";
    return html || emptyBox("표시할 판정 요지가 없습니다.");
  }

  function findingsTable(findings){
    if (!findings || !findings.length) return emptyBox("입력에서 규정 신호를 찾지 못했습니다. 품목명·HS 10자리·수입 목적을 보강해 다시 조회해 보세요.");
    var rows = findings.map(function(f){
      var chips = '<span class="tag ' + (f.verdict === "check_likely" ? "warn" : (f.verdict === "low_risk" ? "ok" : "info")) + '">' + esc(f.verdict_label_ko) + '</span>';
      return "<tr><td><strong>" + esc(f.issue_ko || f.title) + "</strong><br><span class='note-inline'>" + esc(f.title) + "</span></td><td>" + chips + "</td><td>" + esc(String(Math.round((f.confidence || 0) * 100)) + "%") + "</td></tr>";
    }).join("");
    return '<div class="tbl-wrap"><table><thead><tr><th>쟁점</th><th>판정</th><th>신뢰도</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function findingsDetail(findings){
    if (!findings || !findings.length) return "";
    return findings.map(function(f){
      var body = '<div class="body">' +
        (f.explanation ? "<p>" + esc(f.explanation) + "</p>" : "") +
        (f.misconception ? '<p><span class="tag bad">흔한 오해</span>' + esc(f.misconception) + "</p>" : "") +
        (f.notes ? '<p><span class="tag">주의</span>' + esc(f.notes) + "</p>" : "") +
        (f.reason ? '<p class="note-inline">판정 사유: ' + esc(f.reason) + "</p>" : "") +
        "</div>";
      return '<details><summary>' + esc(f.issue_ko || f.title) + '</summary>' + body + '</details>';
    }).join("");
  }

  function evidenceBlock(evidence){
    if (!evidence || !evidence.length) return emptyBox("표시할 근거 조항이 없습니다.");
    return evidence.map(function(e){
      return '<div class="ev"><div class="law">' + esc(e.law) + " " + esc(e.article) +
        '<span class="date">시행 ' + esc(e.effective_date || "-") + '</span></div>' +
        (e.quote ? "<blockquote>" + esc(e.quote) + "</blockquote>" : "") +
        (e.url ? '<a href="' + esc(e.url) + '" target="_blank" rel="noopener noreferrer">원문 보기 · ' + esc(e.url) + "</a>" : "") +
        "</div>";
    }).join("");
  }

  function customsBlock(block, hsDigits){
    if (!block){
      if (hsDigits && hsDigits !== 10){
        return emptyBox("HS 10자리를 입력하면 관세청 세관장확인대상물품을 실시간으로 조회합니다(현재 " + esc(String(hsDigits)) + "자리).");
      }
      return emptyBox("실시간 세관장확인 조회는 이 배포에서 꺼져 있거나 HS 10자리가 없어 실행되지 않았습니다. 판정은 코퍼스·법령 근거로만 이루어졌습니다.");
    }
    if (block.state !== "live"){
      return emptyBox("관세청 실시간 조회에 실패했습니다(코드 " + esc(text(block.code) || "n/a") + "). " + esc(block.note_ko || "") + " 판정을 요건 없음으로 해석하지 마세요.");
    }
    var grouped = {};
    var order = [];
    (block.requirements || []).forEach(function(r){
      var key = [r.requirement_law || "", r.requirement_document || "", r.applies_from || "", r.timing || ""].join("||");
      if (!grouped[key]){
        grouped[key] = { law: r.requirement_law, agencies: [], doc: r.requirement_document, from: r.applies_from, timing: r.timing };
        order.push(key);
      }
      if (r.requirement_agency && grouped[key].agencies.indexOf(r.requirement_agency) === -1){
        grouped[key].agencies.push(r.requirement_agency);
      }
    });
    var rows = order.map(function(k){
      var g = grouped[k];
      return { law: g.law, agency: g.agencies.join(", "), doc: g.doc, from: g.from, timing: g.timing };
    });
    var inner = '<p class="sub">' + esc(block.hs_code) + " · 조회 " + esc(block.checked_at) + " · 요건 " + esc(String(block.requirement_count)) + "건</p>";
    inner += table([["요건 법령", "law"], ["확인 기관", "agency"], ["확인 서류", "doc"], ["적용 시작", "from"], ["시점", "timing"]], rows);
    if (!rows.length) inner += emptyBox(block.zero_note_ko || "0건은 요건 없음을 뜻하지 않습니다.");
    return inner + '<p class="note-inline" style="margin-top:8px">' + esc(block.note_ko || "") + "</p>";
  }

  function rraBlock(block){
    if (!block) return emptyBox("적합성평가 번호를 넣으면 국립전파연구원 적합성평가 DB를 실시간으로 조회합니다(키 불필요). 번호가 없으면 모델명으로 직접 확인해야 합니다.");
    if (block.state === "cached_fallback") {
      var cachedRows = (block.matches || []).map(function(m){
        return { equip: m.equipment_name, model: m.base_model, cert: m.cert_no, date: m.certified_on, country: m.manufacture_country };
      });
      var cachedHead = '<p class="sub">' + esc(block.cert_no) + " · 캐시 " + esc(String(block.age_hours)) + "시간 경과 · 일치 " + esc(String(block.match_count)) + "건</p>";
      cachedHead += table([["기자재명", "equip"], ["기본모델", "model"], ["인증·등록번호", "cert"], ["인증일", "date"], ["제조국", "country"]], cachedRows);
      if (!cachedRows.length) cachedHead += emptyBox(block.note_ko || "조회 결과가 없습니다.");
      return cachedHead + '<p class="note-inline" style="margin-top:8px">' + esc(block.cache_note_ko || "") + "</p>";
    }
    if (block.state === "not_found") {
      return emptyBox(block.note_ko || "이 번호로 조회된 적합성평가 기록이 없습니다.") +
        '<p class="note-inline" style="margin-top:8px"><a href="' + esc(block.official_url || "") + '" target="_blank" rel="noopener noreferrer">국립전파연구원에서 직접 확인</a></p>';
    }
    if (block.state !== "live") {
      return emptyBox("적합성평가 조회가 정상 처리되지 않았습니다(코드 " + esc(text(block.code) || text(block.result_code) || "n/a") + "). " + esc(block.note_ko || ""));
    }
    var rows = (block.matches || []).map(function(m){
      return { equip: m.equipment_name, model: m.base_model, cert: m.cert_no, date: m.certified_on, country: m.manufacture_country };
    });
    var inner = '<p class="sub">' + esc(block.cert_no) + " · " + esc(block.cert_type_estimate || "") + " · 조회 " + esc(block.checked_at) + " · 일치 " + esc(String(block.match_count)) + "건</p>";
    inner += table([["기자재명", "equip"], ["기본모델", "model"], ["인증·등록번호", "cert"], ["인증일", "date"], ["제조국", "country"]], rows);
    if (!rows.length) inner += emptyBox(block.note_ko || "조회 결과가 없습니다.");
    return inner + '<p class="note-inline" style="margin-top:8px">' + esc(block.type_note_ko || "") + " " + esc(block.note_ko || "") + "</p>";
  }

  function mfdsBlock(block){
    if (!block) return "";
    var parts = [];
    function one(title, node, mapper, headers){
      if (!node) return;
      if (node.state === "error"){
        parts.push("<h3>" + esc(title) + '</h3>' + emptyBox("조회 실패: " + text(node.note_ko || node.message || "")));
        return;
      }
      var rows = (node.samples || []).map(mapper);
      parts.push("<h3>" + esc(title) + " <span class='tag info'>일치 " + esc(String(node.match_count === null || node.match_count === undefined ? rows.length : node.match_count)) + "건</span></h3>");
      if (rows.length) parts.push(table(headers, rows));
      else parts.push(emptyBox("표시할 표본이 없습니다. 0건은 이 제품의 요건 미적용을 뜻하지 않습니다."));
    }
    one("제품DB", block.product_db, function(s){
      return { name: s.product_name, category: s.product_category, country: s.manufacture_country, item: s.item_name };
    }, [["제품명", "name"], ["구분", "category"], ["제조국", "country"], ["품목", "item"]]);
    one("수입신고 이력", block.import_permit_history, function(s){
      return { name: s.product_name_ko, type: s.product_type, maker: s.manufacturer, country: s.manufacture_country, date: s.accepted_on };
    }, [["제품명", "name"], ["유형", "type"], ["제조사", "maker"], ["제조국", "country"], ["수리일", "date"]]);
    one("검사부적합 이력", block.improper_history, function(s){
      return { name: s.product_name_ko, type: s.product_type, reason: s.fail_reason, date: s.accepted_on };
    }, [["제품명", "name"], ["유형", "type"], ["부적합 사유", "reason"], ["처리일", "date"]]);
    if (block.state === "error") parts.unshift(emptyBox("식약처 실시간 조회에 실패했습니다."));
    if (block.improper_history && block.improper_history.note_ko) parts.push('<p class="note-inline" style="margin-top:8px">' + esc(block.improper_history.note_ko) + "</p>");
    if (block.zero_note_ko) parts.push('<p class="note-inline">' + esc(block.zero_note_ko) + "</p>");
    return parts.join("");
  }

  function recallBlock(recall){
    if (!recall) return "";
    var head = "";
    if (recall.state === "source_unavailable"){
      return emptyBox(recall.note_ko || "리콜 데이터 소스가 연결되지 않았습니다.") +
        (recall.official_url ? '<p class="note-inline" style="margin-top:8px"><a href="' + esc(recall.official_url) + '" target="_blank" rel="noopener noreferrer">제품안전정보센터에서 직접 확인</a></p>' : "");
    }
    var rows = (recall.matches || []).map(function(m){
      return { name: m.product_name, model: m.model, brand: m.brand, type: m.recall_type, hazard: m.hazard_type, date: m.registered_on };
    });
    head = table([["제품명", "name"], ["모델명", "model"], ["브랜드", "brand"], ["리콜종류", "type"], ["위해유형", "hazard"], ["등록일", "date"]], rows);
    if (!rows.length) head += emptyBox("이 키워드로 일치한 리콜 이력이 없습니다. 0건은 리콜 이력 없음을 뜻하지 않습니다.");
    var cov = recall.coverage || {};
    if (recall.note_ko) head += '<p class="note-inline" style="margin-top:8px">' + esc(recall.note_ko) + "</p>";
    if (cov.items) head += '<p class="note-inline">적재 범위 ' + esc(String(cov.items)) + "건 · " + esc(cov.first_registered_on || "") + " ~ " + esc(cov.last_registered_on || "") + "</p>";
    if (recall.official_url) head += '<p class="note-inline"><a href="' + esc(recall.official_url) + '" target="_blank" rel="noopener noreferrer">제품안전정보센터 최신 리콜 확인</a></p>';
    return head;
  }

  function tariffFtaBlock(tf){
    tf = tf || {};
    var fta = tf.fta || {};
    var ags = (fta.agreements && fta.agreements.length) ? fta.agreements.join(", ") : "해당 없음 / 미지정";
    var rows = [
      { k: "품목군 기준", v: tf.category_label || "-" },
      { k: "예상 기본관세", v: tf.base_rate_hint || "-" },
      { k: "부가가치세", v: tf.vat_rate || "10%" },
      { k: "원산지·협정", v: (tf.origin || "미지정") + " · " + ags },
      { k: "원산지증명서(CO)", v: fta.co_type || "-" },
      { k: "면세·과세 기준", v: tf.duty_free_note || "-" }
    ];
    var out = table([["항목", "k"], ["내용", "v"]], rows);
    if (fta.tip) out += '<p class="note-inline" style="margin-top:8px">실무 팁: ' + esc(fta.tip) + "</p>";
    if (tf.unipass_url) out += '<p class="note-inline"><a href="' + esc(tf.unipass_url) + '" target="_blank" rel="noopener noreferrer">관세법령정보포털(UNIPASS)에서 10자리 세율 직접 조회</a></p>';
    return out;
  }

  function cosmeticScreenBlock(cs){
    cs = cs || {};
    var proh = cs.prohibited || [];
    var rest = cs.restricted || [];
    var html = '<p class="sub">' + esc(cs.summary || "") + "</p>";
    if (proh.length){
      html += '<h3 style="color:#b91c1c;margin-top:10px">배합금지 의심 성분 (' + proh.length + '건)</h3>';
      html += table([["입력 성분", "m"], ["규정 원료명", "k"], ["사유·근거", "r"]], proh.map(function(p){
        return { m: p.matched_input, k: p.ingredient_ko, r: p.reason + " (" + p.basis + ")" };
      }));
    }
    if (rest.length){
      html += '<h3 style="margin-top:10px">배합한도 지정 성분 (' + rest.length + '건)</h3>';
      html += table([["입력 성분", "m"], ["규정 원료명", "k"], ["허용 한도·근거", "l"]], rest.map(function(r){
        return { m: r.matched_input, k: r.ingredient_ko, l: r.limit + " (" + r.basis + ")" };
      }));
    }
    return html;
  }

  function drugScreenBlock(screen, check){
    screen = screen || {};
    check = check || {};
    var matches = screen.matches || [];
    var inner = "";
    if (matches.length){
      var rows = matches.map(function(m){
        return { name: m.name_ko + (m.name_en ? " (" + m.name_en + ")" : ""),
                 cls: m.class_ko, ref: (m.schedule_table_ko || m.reference_ko || "-"),
                 note: m.note_ko || "" };
      });
      inner += table([["성분", "name"], ["분류", "cls"], ["근거 별표·조문", "ref"], ["비고", "note"]], rows);
    } else {
      inner += emptyBox("마약류·원료물질·국내 전용 성분 사전에서 일치하는 성분을 찾지 못했습니다. 성분표 표기를 그대로 넣어 다시 시도해 보세요. 0건은 '제한 없음' 확정이 아닙니다.");
    }
    var rule = screen.self_use_rule || check.self_use_rule || {};
    var qty = screen.quantity || check.quantity;
    if (Object.keys(rule).length){
      inner += '<p class="note-inline" style="margin-top:10px">자가사용 인정기준: 총 ' + esc(text(rule.limit_bottles)) + '병(초과 시 용법상 ' + esc(text(rule.limit_months)) + '개월 복용량) · 반입 경로 ' + esc(text(screen.channel || check.channel || "unknown")) + ' · 수량 ' + esc(qty && qty.value ? qty.value + (qty.unit || "") : "미입력") + '</p>';
      if (rule.scope_note_ko) inner += '<p class="note-inline">' + esc(rule.scope_note_ko) + '</p>';
    }
    if (screen.coverage_ko || check.coverage_ko) inner += '<p class="note-inline">' + esc(screen.coverage_ko || check.coverage_ko) + '</p>';
    var candidates = check.api_candidates || screen.api_candidates || [];
    if (candidates.length){
      var pending = [];
      candidates.forEach(function(c){ if (c.state !== "live") pending.push(c.name_ko + "(" + c.dataset_id + ")"); });
      if (pending.length) inner += '<p class="note-inline">활용신청 전이라 실시간 전수 대조가 어려운 데이터: ' + esc(pending.join(", ")) + '</p>';
    }
    return inner;
  }

  function riskTag(risk){
    var cls = risk === "high" ? "bad" : (risk === "caution" ? "warn" : "ok");
    var label = risk === "high" ? "높음" : (risk === "caution" ? "주의" : "낮음");
    return '<span class="tag ' + cls + '">' + label + '</span>';
  }

  function adFindingsBlock(review){
    var findings = (review && review.findings) || [];
    if (!findings.length) return emptyBox("탐지된 위험 표현이 없습니다. 그래도 광고 근거자료는 보관해야 합니다(실증 의무).");
    var body = findings.map(function(f){
      return "<tr><td>" + riskTag(f.risk) + "</td><td><strong>" + esc(f.name_ko) + "</strong><br><span class='note-inline'>" +
        esc((f.matched_phrases || []).join(", ")) + "</span></td><td>" + esc(f.why_ko) +
        (f.category_note_ko ? "<br><span class='note-inline'>" + esc(f.category_note_ko) + "</span>" : "") +
        "</td><td>" + esc(f.safer_ko) + "</td></tr>";
    }).join("");
    return '<div class="tbl-wrap"><table><thead><tr><th>위험도</th><th>유형·탐지 표현</th><th>판단 이유</th><th>대체 표현</th></tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function categoryCompareBlock(rows){
    if (!rows || !rows.length) return "";
    var body = rows.map(function(r){
      var tag = r.highest_risk === "high" ? '<span class="tag bad">금지 위험</span>' :
        (r.highest_risk === "caution" ? '<span class="tag warn">주의</span>' : '<span class="tag ok">탐지 없음</span>');
      var notes = (r.findings || []).map(function(f){ return f.name_ko + (f.note_ko ? " (" + f.note_ko + ")" : ""); }).join(" · ");
      return "<tr><td>" + esc(r.label_ko) + "</td><td>" + tag + "</td><td>" + esc(String(r.finding_count)) + "건</td><td>" + esc(notes) + "</td></tr>";
    }).join("");
    return '<div class="tbl-wrap"><table><thead><tr><th>품목 유형</th><th>판단</th><th>탐지</th><th>설명</th></tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function labelChecklistBlock(check){
    if (!check) return "";
    var rows = (check.checklist || []).map(function(r){
      var tag = r.status === "present" ? '<span class="tag ok">확인</span>' :
        (r.status === "missing" ? '<span class="tag ' + (r.required ? "bad" : "warn") + '">' + (r.required ? "누락" : "확인 필요") + '</span>' :
          (r.status === "not_applicable" ? '<span class="tag">해당 없음</span>' : '<span class="tag info">미확인</span>'));
      var basis = r.legal_basis ? (r.legal_basis.law + " " + r.legal_basis.article) : "";
      return "<tr><td>" + (r.required ? "<strong>필수</strong>" : "조건부") + "</td><td>" + esc(r.label_ko) +
        (r.applies_when_ko ? "<br><span class='note-inline'>" + esc(r.applies_when_ko) + "</span>" : "") +
        "</td><td>" + tag + "</td><td>" + esc(basis) + "</td></tr>";
    }).join("");
    var head = '<p class="sub">' + esc(check.product_type_label_ko) + " · 필수 " + esc(String(check.required_count)) +
      "항목 중 " + esc(String(check.present_count)) + "항목 확인 (완료율 " + esc(String(Math.round((check.completion_rate || 0) * 100))) + "%)</p>";
    return head + '<div class="tbl-wrap"><table><thead><tr><th>구분</th><th>표시항목</th><th>상태</th><th>근거</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<p class="note-inline" style="margin-top:8px">' + esc(check.coverage_ko || "") + '</p>';
  }

  function ecommerceFindingsBlock(review){
    if (!review) return emptyBox("국내 판매페이지 검수 결과가 없습니다.");
    var findings = review.findings || [];
    if (!findings.length) return emptyBox("탐지된 공정위ㆍ전자상거래법 위험 문구가 없습니다. 근거 자료는 계속 보관해야 합니다(실증 의무).");
    var body = findings.map(function(f){
      return "<tr><td>" + riskTag(f.risk) + "</td><td><strong>" + esc(f.name_ko) + "</strong><br><span class='note-inline'>" +
        esc((f.matched_phrases || []).join(", ")) + "</span></td><td>" + esc(f.why_ko) +
        "</td><td>" + esc(f.safer_ko) +
        (f.fix_example_ko ? "<br><span class='note-inline'>" + esc(f.fix_example_ko) + "</span>" : "") + "</td></tr>";
    }).join("");
    return '<div class="tbl-wrap"><table><thead><tr><th>위험도</th><th>유형·탐지 표현</th><th>판단 이유</th><th>수정 권고 문구</th></tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function feedCheckBlock(block){
    if (!block) return emptyBox("반려동물 사료·간식 검수 결과가 없습니다.");
    var rows = (block.findings || []);
    if (!rows.length) return emptyBox("입력한 범위에서 확인이 남은 사료관리법·동물검역 항목이 없습니다.");
    var body = rows.map(function(f){
      var tag = f.status === "missing" ? '<span class="tag bad">갖추지 못함</span>' : '<span class="tag info">확인 필요</span>';
      var basis = (f.legal_basis && f.legal_basis[0]) ? (f.legal_basis[0].law + " " + f.legal_basis[0].article) : "";
      return "<tr><td>" + tag + "</td><td><strong>" + esc(f.name_ko) + "</strong><br><span class='note-inline'>" +
        esc(f.axis_ko || "") + " · " + esc(basis) + "</span></td><td>" + esc(f.safer_ko || "") + "</td></tr>";
    }).join("");
    var head = '<p class="sub">' + esc(block.input ? block.input.product_type_label_ko : "") + " · " +
      esc(block.input ? block.input.purpose_label_ko : "") + " · " + esc(block.risk_summary_ko || "") +
      " · 근거 확인 " + esc(block.checked_on || "") + "</p>";
    return head + '<div class="tbl-wrap"><table><thead><tr><th>상태</th><th>확인 항목</th><th>무엇을 하면 되나</th></tr></thead><tbody>' +
      body + '</tbody></table></div>';
  }

  function ecommerceDisclosureBlock(check){
    if (!check || !(check.checklist || []).length) return "";
    var rows = (check.checklist || []).map(function(r){
      var tag = r.status === "present" ? '<span class="tag ok">확인</span>' :
        (r.status === "missing" ? '<span class="tag ' + (r.required ? "bad" : "warn") + '">' + (r.required ? "누락" : "확인 필요") + '</span>' :
          (r.status === "not_applicable" ? '<span class="tag">해당 없음</span>' : '<span class="tag info">미확인</span>'));
      var basis = (r.legal_basis && r.legal_basis[0]) ? (r.legal_basis[0].law + " " + r.legal_basis[0].article) : "";
      return "<tr><td>" + (r.required ? "<strong>필수</strong>" : "조건부") + "</td><td>" + esc(r.label_ko) +
        (r.example_ko ? "<br><span class='note-inline'>" + esc(r.example_ko) + "</span>" : "") +
        "</td><td>" + tag + "</td><td>" + esc(basis) + "</td></tr>";
    }).join("");
    var head = '<p class="sub">필수 고지 ' + esc(String(check.required_count)) + "항목 중 " + esc(String(check.present_count)) +
      "항목 확인 (완료율 " + esc(String(Math.round((check.completion_rate || 0) * 100))) + "%) — 입력한 문구에서 찾지 못한 결과이며, 실제 페이지에 없다는 단정은 아닙니다.</p>";
    return head + '<div class="tbl-wrap"><table><thead><tr><th>구분</th><th>고지 항목</th><th>상태</th><th>근거</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function disclaimerBlock(result){
    var ko = result.disclaimer ? result.disclaimer.ko : "";
    var limits = result.scope_limits_ko || [];
    var inner = "<p>" + esc(ko) + "</p>";
    if (limits.length) inner += '<ul class="plain">' + limits.map(function(l){ return "<li>" + esc(l) + "</li>"; }).join("") + "</ul>";
    return inner;
  }

  function provenanceLine(result){
    var prov = result.data_provenance || {};
    var bits = [];
    if (prov.checked_at) bits.push("조회 " + prov.checked_at);
    if (result.assessment_id) bits.push("ID " + result.assessment_id);
    if (result.engine && result.engine.version) bits.push("코퍼스 " + result.engine.version);
    if (!bits.length) return "";
    return '<div class="meta-line">' + bits.map(function(b){ return "<span>" + esc(b) + "</span>"; }).join("") + "</div>";
  }

  // ---------- 결과 공유·복사 ----------
  // 판정 요약과 공유 링크만 클립보드로 내보낸다. 요약에는 품목명·판정·주요 항목·근거 법령·
  // 출처 링크만 담고, 원문 상세 문구나 입력한 긴 텍스트는 넣지 않는다.
  var SOURCE_URL = "https://clns-kr.onrender.com";
  var NL = String.fromCharCode(10);
  var shareState = { check: null, ec: null };

  function flashNote(el, message){
    if (!el) return;
    el.textContent = message;
    window.setTimeout(function(){
      if (el.textContent === message) el.textContent = "";
    }, 2600);
  }
  function copyText(value, done){
    var payload = String(value === null || value === undefined ? "" : value);
    function fallback(){
      var area = document.createElement("textarea");
      area.value = payload;
      area.setAttribute("readonly", "readonly");
      area.style.position = "fixed";
      area.style.top = "-1000px";
      area.style.left = "-1000px";
      document.body.appendChild(area);
      var ok = false;
      try {
        area.select();
        ok = document.execCommand("copy");
      } catch (e) {
        ok = false;
      }
      document.body.removeChild(area);
      done(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(payload).then(function(){ done(true); }, function(){ fallback(); });
      return;
    }
    fallback();
  }
  function uniqueLabels(values, limit){
    var out = [];
    (values || []).forEach(function(value){
      var label = String(value === null || value === undefined ? "" : value).trim();
      if (label && out.indexOf(label) === -1) out.push(label);
    });
    return out.slice(0, limit || 5);
  }
  function basisLabels(rows, limit){
    return uniqueLabels((rows || []).map(function(row){
      if (!row || !row.law) return "";
      return (row.law + " " + (row.article || "")).trim();
    }), limit);
  }
  function checkSummaryText(productName, result){
    result = result || {};
    var verdict = result.verdict || {};
    var lines = ["[CLNS 사전 점검] " + (productName || "입력 품목")];
    lines.push("판정: " + (verdict.label_ko || "-") + " (" + (verdict.code || "-") + ")");
    var needCheck = [];
    var lowRisk = [];
    (result.findings || []).forEach(function(f){
      var label = f.issue_ko || f.title || "";
      if (!label) return;
      if (f.verdict === "low_risk") lowRisk.push(label);
      else needCheck.push(label);
    });
    if (needCheck.length) lines.push("주요 위험·확인 항목: " + uniqueLabels(needCheck, 5).join(", "));
    if (lowRisk.length) lines.push("현재 정보상 가능성 낮음: " + uniqueLabels(lowRisk, 3).join(", "));
    var basis = basisLabels(result.evidence, 5);
    if (basis.length) lines.push("근거 법령: " + basis.join(" / "));
    var rules = uniqueLabels((result.findings || []).map(function(f){ return f.case_id; }), 6);
    if (rules.length) lines.push("규칙·케이스 ID: " + rules.join(", "));
    lines.push("사전 참고용이며 확정 판정이 아닙니다. " + SOURCE_URL);
    return lines.join(NL);
  }
  function ecSummaryText(result){
    result = result || {};
    var verdict = result.verdict || {};
    var review = result.ecommerce_review || {};
    var lines = ["[CLNS 판매페이지 사전 점검] " + (result.channel_label_ko || "채널 미지정")];
    lines.push("판정: " + (verdict.label_ko || "-") + " (" + (verdict.code || "-") + ")");
    var high = [];
    var caution = [];
    (review.findings || []).forEach(function(f){
      var label = f.name_ko || f.rule_id || "";
      if (!label) return;
      if (f.risk === "high") high.push(label);
      else caution.push(label);
    });
    if (high.length) lines.push("금지 위험 문구: " + uniqueLabels(high, 5).join(", "));
    if (caution.length) lines.push("주의·확인 문구: " + uniqueLabels(caution, 5).join(", "));
    var basis = basisLabels(result.evidence, 5);
    if (basis.length) lines.push("근거 법령: " + basis.join(" / "));
    lines.push("사전 참고용이며 확정 판정이 아닙니다. " + SOURCE_URL);
    return lines.join(NL);
  }
  function shareUrl(kind){
    var parts = [];
    if (kind === "check" && shareState.check){
      if (shareState.check.product) parts.push("item=" + encodeURIComponent(shareState.check.product));
      if (shareState.check.cat) parts.push("cat=" + encodeURIComponent(shareState.check.cat));
      if (shareState.check.origin) parts.push("origin=" + encodeURIComponent(shareState.check.origin));
    }
    if (kind === "ec") parts.push("cat=ec");
    return SOURCE_URL + "/" + (parts.length ? "?" + parts.join("&") : "") + "#check";
  }
  function setShareBar(barId, visible){
    var bar = document.getElementById(barId);
    if (bar) bar.hidden = !visible;
  }
  function bindShare(barId, noteId, copyId, linkId, kind){
    var note = document.getElementById(noteId);
    var copyBtn = document.getElementById(copyId);
    var linkBtn = document.getElementById(linkId);
    if (copyBtn) copyBtn.addEventListener("click", function(){
      var state = shareState[kind];
      if (!state || !state.summary){
        flashNote(note, "먼저 점검을 실행해 주세요.");
        return;
      }
      copyText(state.summary, function(ok){
        flashNote(note, ok ? "복사됨 ✓" : "복사 권한이 없어 클립보드에 넣지 못했습니다. 브라우저 설정에서 클립보드 접근을 허용해 주세요.");
      });
    });
    if (linkBtn) linkBtn.addEventListener("click", function(){
      copyText(shareUrl(kind), function(ok){
        flashNote(note, ok ? "복사됨 ✓" : "복사 권한이 없어 클립보드에 넣지 못했습니다. 브라우저 설정에서 클립보드 접근을 허용해 주세요.");
      });
    });
  }
  bindShare("result-share", "result-share-note", "result-copy-summary", "result-copy-link", "check");
  bindShare("ec-share", "ec-share-note", "ec-copy-summary", "ec-copy-link", "ec");

  // ---------- 리스크 체크 ----------
  var form = document.getElementById("check-form");
  var resultEl = document.getElementById("result");
  var submitBtn = document.getElementById("check-submit");
  var formNote = document.getElementById("form-note");

  function radio(name){
    var el = form.querySelector('input[name=' + name + ']:checked');
    return el ? el.value : "";
  }

  function buildQuery(data){
    var parts = [];
    if (data.origin && data.origin !== "기타" && data.product.indexOf(data.origin) === -1) parts.push(data.origin + "산");
    parts.push(data.product);
    if (data.wire === "yes") parts.push("블루투스 무선 송신");
    if (data.child === "yes") parts.push("어린이 대상");
    parts.push(data.purpose === "self_use" ? "수입해서 자가소비" : "수입해서 판매");
    return parts.join(" ");
  }

  function readForm(){
    return {
      product: document.getElementById("product").value.trim(),
      hs: document.getElementById("hs").value.replace(/[^0-9]/g, ""),
      origin: document.getElementById("origin").value,
      wire: radio("wire") || "unknown",
      child: radio("child") || "no",
      rra: (document.getElementById("rra").value || "").trim(),
      kind: document.getElementById("kind").value,
      purpose: radio("purpose") || "resale"
    };
  }

  form.addEventListener("submit", function(ev){
    ev.preventDefault();
    var data = readForm();
    if (data.product.length < 2){
      formNote.textContent = "품목명을 2자 이상 입력해 주세요.";
      document.getElementById("product").focus();
      return;
    }
    if (data.hs && data.hs.length !== 10){
      formNote.textContent = "HS는 10자리만 조회에 쓰입니다. 지금은 " + data.hs.length + "자리라 요건 조회에서 제외합니다.";
    } else {
      formNote.textContent = "";
    }

    var facts = { purpose: data.purpose, rf_tx: data.wire, target_age: data.child === "yes" ? "어린이" : "성인" };
    if (data.hs.length === 10) facts.hs_code = data.hs;
    if (data.wire === "yes" && data.rra) facts.rra_cert_no = data.rra;
    if (data.origin) facts.origin = data.origin;
    var cosIng = (data.kind === "cosmetics" && document.getElementById("cosmetic-ingredients-onestop") && document.getElementById("cosmetic-ingredients-onestop").value || "").trim();
    if (cosIng) facts.cosmetic_ingredients = cosIng;
    var query = buildQuery(data);

    submitBtn.disabled = true;
    submitBtn.textContent = "확인 중…";
    resultEl.innerHTML = '<div class="card"><p class="sub"><span class="spinner"></span> 판정과 공공데이터를 조회하고 있습니다…</p></div>';

    var adCopy = (document.getElementById("ad-copy-onestop") && document.getElementById("ad-copy-onestop").value || "").trim();
    var adLabel = (document.getElementById("ad-label-onestop") && document.getElementById("ad-label-onestop").value || "").trim();
    var adFunctional = radio("ad-functional") || "unknown";
    var drugMode = (data.kind === "drug") || isDrugHint(data.product);
    function inferAdType(kindVal, prodName){
      if (kindVal === "health_functional") return "health_functional_food";
      if (kindVal === "cosmetics") return adFunctional === "yes" ? "functional_cosmetics" : "cosmetics";
      if (kindVal === "food") return "general_food";
      if (/(비타민|영양제|루테인|오메가|유산균|프로바이오|콜라겐|홍삼|밀크씨슬|마그네슘|아연)/.test(prodName)) return "health_functional_food";
      if (/(화장품|크림|세럼|로션|선크림|토너|에센스|마스크팩|립|파운데이션|샴푸)/.test(prodName)) return adFunctional === "yes" ? "functional_cosmetics" : "cosmetics";
      return "general_food";
    }

    var mainP = postTool("assess_import_case", { query: query, facts: facts, limit: 5 });
    var hsP = data.hs.length === 10 ? soft(postTool("lookup_hs_requirements", { hs_code: data.hs, direction: "import" })) : Promise.resolve(null);
    var recallP = soft(postTool("lookup_recall", { product_name: data.product, brand: "", limit: 5 }));
    var adPayload = {
      product_name: data.product,
      product_type: inferAdType(data.kind, data.product),
      imported: "yes",
      functional: adFunctional,
      purpose: data.purpose,
      limit: 8
    };
    if (adCopy) adPayload.ad_copy = adCopy;
    if (adLabel) adPayload.label_text = adLabel;
    var adP = (adCopy || adLabel) ? soft(postTool("check_ad_labeling", adPayload)) : Promise.resolve(null);

    var drugPayload = null;
    if (drugMode){
      var dCh = (form.querySelector('input[name="drug-channel"]:checked') || {}).value || (data.purpose === "self_use" ? "carry" : "unknown");
      var rawQty = (document.getElementById("drug-qty") && document.getElementById("drug-qty").value || "").replace(/[^0-9]/g, "");
      drugPayload = {
        product_name: data.product,
        channel: dCh,
        unit: (document.getElementById("drug-unit") && document.getElementById("drug-unit").value) || "병",
        prescription: (document.getElementById("drug-rx") && document.getElementById("drug-rx").value) || "unknown",
        limit: 3
      };
      if (rawQty) drugPayload.quantity = parseInt(rawQty, 10);
    }
    var drugP = drugPayload ? soft(postTool("check_drug_import", drugPayload)) : Promise.resolve(null);

    Promise.all([mainP, hsP, recallP, adP, drugP]).then(function(res){
      var result = res[0], hsResult = res[1], recall = res[2], adResult = res[3], drugResult = res[4];
      var kind = (data.kind && data.kind !== "drug" && data.kind !== "feed") ? data.kind : "";
      if (!kind){
        var cats = (result.findings || []).map(function(f){ return f.category; });
        if (cats.indexOf("cosmetics") !== -1) kind = "cosmetics";
        else if (cats.indexOf("food") !== -1 || cats.indexOf("label") !== -1) kind = "food";
      }
      var mfdsP = kind ? soft(postTool("check_food_cosmetics", { product_name: data.product, kind: kind, purpose: data.purpose })) : Promise.resolve(null);
      return Promise.all([Promise.resolve(result), Promise.resolve(hsResult), Promise.resolve(recall), mfdsP, Promise.resolve(adResult), Promise.resolve(drugResult)]);
    }).then(function(res){
      var result = res[0], hsResult = res[1], recall = res[2], mfds = res[3], adResult = res[4], drugResult = res[5];
      var html = "";
      html += '<div class="card">' +
        '<h2>판정 결과</h2>' +
        '<p class="sub">입력한 품목: ' + esc(data.product) + '</p>' +
        verdictBlock(result.verdict, result) +
        provenanceLine(result) +
        '<h3>판정 요지</h3>' + guidanceBlock(result) +
        '<h3>확인 필요 체크리스트</h3>' + checklist(result) +
        '</div>';

      var fCount = (result.findings || []).length;
      html += section("쟁점 요약 " + String(fCount) + "건", findingsTable(result.findings),
        "각 쟁점의 상세 설명과 오해 포인트는 아래에서 눌러 펼쳐 볼 수 있습니다.");
      if (fCount > 0) {
        html += sectionCollapsible("쟁점 상세 설명", findingsDetail(result.findings), String(fCount) + "건 상세 펼쳐 보기");
      }

      if (result.cosmetic_screening) {
        var prohCnt = (result.cosmetic_screening.prohibited || []).length;
        var restCnt = (result.cosmetic_screening.restricted || []).length;
        if (prohCnt > 0 || restCnt > 0) {
          html += section("화장품 배합금지·한도 대조", cosmeticScreenBlock(result.cosmetic_screening),
            "식약처 「화장품 안전기준 등에 관한 규정」 별표 1·2 핵심 성분 기준입니다.");
        } else {
          html += sectionCollapsible("화장품 배합금지·한도 대조", cosmeticScreenBlock(result.cosmetic_screening),
            "주요 금지·한도 성분 0건");
        }
      }

      if (result.tariff_fta) {
        html += section("관세율·FTA 원산지 가이드", tariffFtaBlock(result.tariff_fta),
          result.tariff_fta.disclaimer || "");
      }

      var drugScreen = (drugResult && !drugResult.__error && drugResult.drug_screening) || result.drug_screening;
      var drugCheck = (drugResult && !drugResult.__error && drugResult.drug_import_check) || result.drug_import_check;
      if (drugScreen) {
        var drugMatches = (drugScreen.matches || []).length;
        if (drugMatches > 0 || drugMode) {
          html += section("의약품·성분 및 반입 기준 대조", drugScreenBlock(drugScreen, drugCheck),
            "마약류·원료물질 목록은 마약류 관리에 관한 법률 시행령 별표 1~8, 자가사용 기준은 수입통관 사무처리에 관한 고시 별표 11 기준입니다.");
        }
      }

      var hsDigits = data.hs ? data.hs.length : 0;
      var customs = (hsResult && !hsResult.__error && hsResult.hs_requirements_live) || null;
      var customsInner = (hsResult && hsResult.__error)
        ? emptyBox("세관장확인 조회 실패: " + hsResult.__error)
        : customsBlock(customs, hsDigits);
      var customsSub = hsDigits !== 10
        ? "HS 10자리를 넣으면 이 항목이 실시간 조회로 채워집니다."
        : (customs && customs.state === "live"
            ? "HS " + data.hs + " 실시간 조회 결과입니다."
            : "HS " + data.hs + " 기준입니다. 아래에 실시간 조회 결과 또는 실패 사유가 표시됩니다.");
      if (hsDigits === 10 || (customs && customs.state === "live")) {
        html += section("세관장확인 요건 (관세청)", customsInner, customsSub);
      } else {
        html += sectionCollapsible("세관장확인 요건 (관세청)", customsInner, "HS 10자리 미입력");
      }

      if (result.rra_conformity_live){
        html += section("전파 적합성평가 (국립전파연구원)", rraBlock(result.rra_conformity_live),
          "인증·등록번호 1건 단위 조회 결과입니다. 모델명 일치는 별도로 대조해야 합니다.");
      }

      if (mfds){
        var fi = mfds.food_import_live || {};
        var mfdsTotal = ((fi.product_db && fi.product_db.match_count) || 0) +
          ((fi.import_history && fi.import_history.match_count) || 0) +
          ((fi.non_compliant && fi.non_compliant.match_count) || 0);
        if (mfdsTotal > 0 || mfds.__error) {
          html += section("식약처 수입 이력", mfds.__error ? emptyBox("식약처 조회 실패: " + mfds.__error) : mfdsBlock(mfds.food_import_live),
            "제품DB·수입신고·검사부적합 이력을 참고용으로 보여줍니다.");
        } else {
          html += sectionCollapsible("식약처 수입 이력", mfdsBlock(mfds.food_import_live), "조회 일치 0건");
        }
      }

      var recallInner = (recall && recall.__error)
        ? emptyBox("리콜 조회 실패: " + recall.__error)
        : recallBlock(recall && recall.recall);
      var recallCount = (recall && recall.recall && recall.recall.match_count) || 0;
      if (recallCount > 0) {
        html += section("로컬 리콜 참고 (국표원)", recallInner,
          "2023-08-09 배포본 기준 과거 이력입니다. 최신 리콜은 제품안전정보센터에서 확인하세요.");
      } else {
        html += sectionCollapsible("로컬 리콜 참고 (국표원)", recallInner, "일치 0건 (과거 스냅샷)");
      }

      if (result.feed_check && result.feed_check.is_feed) {
        html += section("반려동물 사료·간식 검수 (사료관리법·농림축산검역본부)",
          feedCheckBlock(result.feed_check),
          "반려동물이 먹는 사료·간식은 식품이 아니라 사료관리법이 적용됩니다. 판매 목적이면 성분등록·사료 수입신고·한글 표시가 붙고, " +
          "동물성 원료가 있으면 지정검역물로 수입검역이 따로 필요합니다. 사료관리법에 '수입업 등록' 제도는 없습니다.");
      }

      if (adResult) {
        if (adResult.__error) {
          html += section("원스톱 광고·라벨 검수", emptyBox("광고·라벨 검수 실패: " + adResult.__error));
        } else {
          var adRev = adResult.ad_review || {};
          var adLbl = adResult.labeling_check || {};
          if (adCopy) {
            html += section("원스톱 광고 문구 검수", adFindingsBlock(adRev),
              "위험도 ‘높음’은 문구 수정 없이는 금지 유형에 해당할 수 있는 표현, ‘주의’는 실증·심의 확인이 필요한 표현입니다.");
            html += sectionCollapsible("같은 문구의 유형별 판단", categoryCompareBlock(adRev.category_comparison),
              "유형별 허용 범위 비교 펼쳐 보기");
          }
          if (adCopy && adResult.ecommerce_review) {
            var ecRev = adResult.ecommerce_review;
            html += section("국내 판매페이지 검수 (공정거래위원회)",
              '<p class="sub">쿠팡·스마트스토어·자사몰에 올릴 때 걸리는 표시광고법·전자상거래법 위험 문구입니다. ' +
              esc(ecRev.risk_summary_ko || "") + ' · 근거 확인 ' + esc(ecRev.checked_on || "") + '</p>' +
              ecommerceFindingsBlock(ecRev),
              "가격(허위 정가·마감임박), 후기(뒷광고), 청약철회·환불 제한, 배송·품절 책임 회피, 인증·수상, 최저가·1위, " +
              "구독·자동결제, 가격·해지 다크패턴, 위약금, 보장 문구를 공정위 기준으로 대조합니다. " +
              "판매자 정보·거래조건 고지 항목까지 보려면 상세페이지 전체를 check_ecommerce_compliance 로 넣으세요.");
            if (ecRev.disclosure_check) {
              html += sectionCollapsible("판매자 정보·거래조건 고지 체크",
                ecommerceDisclosureBlock(ecRev.disclosure_check), "상세페이지 하단 고지 항목 펼쳐 보기");
            }
          }
          if (adLabel) {
            html += section("한글표시사항 라벨 체크", labelChecklistBlock(adLbl),
              "누락은 입력한 텍스트에서 항목을 찾지 못했다는 뜻입니다. 세부 서식은 고시를 확인하세요.");
          }
        }
      }

      var evCount = (result.evidence || []).length;
      html += sectionCollapsible("근거 법령·조항", evidenceBlock(result.evidence), String(evCount) + "건 펼쳐 보기",
        "인용문은 요지 발췌입니다. 조문 전체는 원문에서 확인해야 하며, 출처 표시 없이 재배포할 수 없습니다.");

      html += sectionCollapsible("면책·이용 범위", disclaimerBlock(result), "안내 보기");

      resultEl.innerHTML = html;
      shareState.check = {
        product: data.product,
        cat: data.kind || "",
        origin: data.origin || "",
        summary: checkSummaryText(data.product, result)
      };
      setShareBar("result-share", true);
      var resultShareNote = document.getElementById("result-share-note");
      if (resultShareNote) resultShareNote.textContent = "";
      resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }).catch(function(err){
      shareState.check = null;
      setShareBar("result-share", false);
      resultEl.innerHTML = '<div class="card"><div class="empty">' + esc(err.message || "조회에 실패했습니다.") + "</div>" +
        '<p class="note-inline" style="margin-top:10px">잠시 후 다시 시도해 주세요. 계속 실패하면 HS 10자리 조회 탭만 따로 이용해 보세요.</p></div>';
    }).then(function(){
      submitBtn.disabled = false;
      submitBtn.textContent = "리스크 체크";
    });
  });

  var kindSelect = document.getElementById("kind");
  var productInput = document.getElementById("product");
  var cosWrap = document.getElementById("cosmetic-ingredients-wrap");
  var rraWrap = document.getElementById("rra-wrap");
  var drugWrap = document.getElementById("drug-fields-wrap");
  var adOnestopWrap = document.getElementById("ad-onestop-wrap");
  function isDrugHint(prodName){
    return /(멜라토닌|melatonin|졸피뎀|zolpidem|애더럴|adderall|리탈린|cbd|칸나비디올|의약품|처방약|수면제|진통제|타이레놀|이부프로펜|아스피린|항생제|스테로이드)/i.test(prodName || "");
  }
  function syncConditionalFields(){
    if (cosWrap && kindSelect){
      cosWrap.hidden = (kindSelect.value !== "cosmetics");
    }
    if (rraWrap){
      rraWrap.hidden = (radio("wire") !== "yes");
    }
    if (drugWrap){
      var pVal = (productInput && productInput.value || "").trim();
      drugWrap.hidden = !((kindSelect && kindSelect.value === "drug") || isDrugHint(pVal));
    }
  }
  if (kindSelect){
    kindSelect.addEventListener("change", syncConditionalFields);
  }
  if (productInput){
    productInput.addEventListener("input", syncConditionalFields);
  }
  Array.prototype.slice.call(form.querySelectorAll('input[name="wire"]')).forEach(function(el){
    el.addEventListener("change", syncConditionalFields);
  });
  syncConditionalFields();

  // 대표 품목 원클릭 체험 — 품목명·품목군·원산지를 채우고 바로 점검을 실행한다.
  var PRESETS = {
    "supplement": {product: "미국산 멜라토닌 영양제", kind: "health_functional", origin: "미국",
                   wire: "no", child: "no", purpose: "self_use", hs: ""},
    "dog-treat": {product: "미국산 강아지 동결건조 간식", kind: "feed", origin: "미국",
                  wire: "no", child: "no", purpose: "resale", hs: "2309101000"},
    "cosmetics": {product: "미국산 수딩 크림", kind: "cosmetics", origin: "미국",
                  wire: "no", child: "no", purpose: "resale", hs: "3304992000"},
    "earbuds": {product: "중국산 블루투스 이어폰", kind: "electronics", origin: "중국",
                wire: "yes", child: "no", purpose: "resale", hs: "8518309000"},
    "kids-clothes": {product: "베트남산 유아용 의류", kind: "", origin: "베트남",
                     wire: "no", child: "yes", purpose: "resale", hs: ""}
  };
  function pickRadio(name, value){
    var el = form.querySelector('input[name="' + name + '"][value="' + value + '"]');
    if (el) el.checked = true;
  }
  function applyPreset(key){
    var preset = PRESETS[key];
    if (!preset) return;
    document.getElementById("product").value = preset.product;
    document.getElementById("hs").value = preset.hs || "";
    document.getElementById("origin").value = preset.origin;
    document.getElementById("kind").value = preset.kind;
    pickRadio("wire", preset.wire);
    pickRadio("child", preset.child);
    pickRadio("purpose", preset.purpose);
    var adPreset = document.getElementById("ad-copy-onestop");
    if (adPreset) adPreset.value = "";
    syncConditionalFields();
    formNote.textContent = "대표 품목을 채우고 점검을 시작했습니다.";
    if (form.requestSubmit) form.requestSubmit();
    else form.dispatchEvent(new Event("submit", {cancelable: true}));
  }
  Array.prototype.slice.call(document.querySelectorAll(".preset[data-preset]")).forEach(function(btn){
    btn.addEventListener("click", function(){ applyPreset(btn.getAttribute("data-preset")); });
  });

  document.getElementById("check-demo").addEventListener("click", function(){
    document.getElementById("product").value = "중국산 블루투스 스피커";
    document.getElementById("hs").value = "8518220000";
    document.getElementById("origin").value = "중국";
    var wy = form.querySelector('input[name="wire"][value="yes"]'); if (wy) wy.checked = true;
    var cn = form.querySelector('input[name="child"][value="no"]'); if (cn) cn.checked = true;
    document.getElementById("kind").value = "electronics";
    var pr = form.querySelector('input[name="purpose"][value="resale"]'); if (pr) pr.checked = true;
    var adOnestop = document.getElementById("ad-copy-onestop");
    if (adOnestop) adOnestop.value = "KC 인증 완료, 초저지연 완벽 호환 — 무료 체험 이벤트!";
    if (adOnestopWrap) adOnestopWrap.open = true;
    syncConditionalFields();
    formNote.textContent = "예시를 채웠습니다. '리스크 체크'를 눌러 원스톱 검수를 확인해 보세요.";
  });

  var demoShop = document.getElementById("check-demo-shop");
  if (demoShop){
    demoShop.addEventListener("click", function(){
      document.getElementById("product").value = "국산 보습 핸드크림";
      document.getElementById("hs").value = "";
      document.getElementById("origin").value = "한국";
      var wno = form.querySelector('input[name="wire"][value="no"]'); if (wno) wno.checked = true;
      var cn2 = form.querySelector('input[name="child"][value="no"]'); if (cn2) cn2.checked = true;
      document.getElementById("kind").value = "cosmetics";
      var pr2 = form.querySelector('input[name="purpose"][value="resale"]'); if (pr2) pr2.checked = true;
      var adShop = document.getElementById("ad-copy-onestop");
      if (adShop) adShop.value = "정가 39,000원 → 오늘만 19,900원 (49% 할인)! 마감 임박! | 체험단으로 선정되어 직접 써봤어요. 국내 최저가! | 단순변심 환불 불가, 포장 개봉 시 교환·반품 불가";
      if (adOnestopWrap) adOnestopWrap.open = true;
      syncConditionalFields();
      formNote.textContent = "국내 셀러 상세페이지 예시를 채웠습니다. '리스크 체크'를 누르면 식약처 광고 검수와 공정위·전자상거래법 검수를 함께 봅니다.";
    });
  }

  var demoFeed = document.getElementById("check-demo-feed");
  if (demoFeed){
    demoFeed.addEventListener("click", function(){
      document.getElementById("product").value = "미국산 강아지 동결건조 간식 수입 판매";
      document.getElementById("hs").value = "2309101000";
      document.getElementById("origin").value = "미국";
      var wno2 = form.querySelector('input[name="wire"][value="no"]'); if (wno2) wno2.checked = true;
      var cn3 = form.querySelector('input[name="child"][value="no"]'); if (cn3) cn3.checked = true;
      document.getElementById("kind").value = "feed";
      var pr3 = form.querySelector('input[name="purpose"][value="resale"]'); if (pr3) pr3.checked = true;
      syncConditionalFields();
      formNote.textContent = "반려동물 사료 예시를 채웠습니다. '리스크 체크'를 누르면 사료관리법·동물검역 확인 항목과 세관장확인 요건을 함께 봅니다.";
    });
  }

  var ecCopy = document.getElementById("ec-copy");
  var ecChannel = document.getElementById("ec-channel");
  var ecSubmit = document.getElementById("ec-submit");
  var ecNote = document.getElementById("ec-note");
  var ecResult = document.getElementById("ec-result");

  function renderEcommerce(result){
    var rev = result.ecommerce_review || {};
    var disc = result.disclosure_check || rev.disclosure_check;
    var html = '<div class="card"><h2>판매페이지 검수 결과</h2>' +
      '<p class="sub">판매 채널: ' + esc(result.channel_label_ko || "") + ' · 근거 확인 ' + esc(rev.checked_on || "") +
      ' · ' + esc(rev.risk_summary_ko || "") + '</p>' +
      verdictBlock(result.verdict, result) +
      '<h3>판정 요지</h3>' + guidanceBlock(result);
    if (disc) {
      html += '<h3>판매자 정보·거래조건 고지</h3>' + ecommerceDisclosureBlock(disc);
    }
    html += '</div>';
    html += section("위험 문구 " + String((rev.findings || []).length) + "건", ecommerceFindingsBlock(rev),
      "가격(허위 정가·마감임박), 후기 대비책, 청약철회·환불 제한, 배송·품절 회피, 인증·수상, 최저가·1위, 구독·자동결제, 가격·해지 다크패턴, 위약금, 보장 문구를 공정위 기준으로 대조합니다.");
    html += sectionCollapsible("근거 법령·조항", evidenceBlock(result.evidence), String((result.evidence || []).length) + "건 펼쳐 보기",
      "인용문은 요지 발췌입니다. 조문 전체는 원문에서 확인해야 하며, 출처 표시 없이 재배포할 수 없습니다.");
    html += sectionCollapsible("면책·이용 범위", disclaimerBlock(result), "안내 보기");
    return html;
  }

  if (ecSubmit){
    ecSubmit.addEventListener("click", function(){
      var text = (ecCopy && ecCopy.value || "").trim();
      if (text.length < 2){
        if (ecNote) ecNote.textContent = "상세페이지 문구를 2자 이상 입력해 주세요.";
        return;
      }
      ecSubmit.disabled = true;
      ecResult.innerHTML = '<div class="card"><p class="sub"><span class="spinner"></span> 공정위 기준으로 대조하고 있습니다…</p></div>';
      postTool("check_ecommerce_compliance", {detail_copy: text, channel: (ecChannel && ecChannel.value) || "own", limit: 12})
        .then(function(result){
          ecResult.innerHTML = renderEcommerce(result);
          shareState.ec = { summary: ecSummaryText(result) };
          setShareBar("ec-share", true);
          var ecShareNote = document.getElementById("ec-share-note");
          if (ecShareNote) ecShareNote.textContent = "";
          ecResult.scrollIntoView({behavior: "smooth", block: "start"});
        })
        .catch(function(err){
          shareState.ec = null;
          setShareBar("ec-share", false);
          ecResult.innerHTML = '<div class="card"><div class="empty">' + esc(err.message || "검수에 실패했습니다.") + '</div></div>';
        })
        .then(function(){
          ecSubmit.disabled = false;
          if (ecNote) ecNote.textContent = "";
        });
    });
  }
  var ecDemo = document.getElementById("ec-demo");
  if (ecDemo){
    ecDemo.addEventListener("click", function(){
      if (ecCopy) ecCopy.value = "정가 39,000원 → 오늘만 19,900원 (49% 할인)! 마감 임박! 체험단으로 선정되어 직접 써봤어요. 국내 최저가! 단순변심 환불 불가, 포장 개봉 시 교환·반품 불가. 배송 지연 시 책임지지 않습니다.";
      if (ecChannel) ecChannel.value = "smartstore";
      if (ecNote) ecNote.textContent = "예시를 채웠습니다. '판매페이지 검수'를 눌러 보세요.";
    });
  }

  document.getElementById("check-reset").addEventListener("click", function(){
    form.reset();
    if (adOnestopWrap) adOnestopWrap.open = false;
    syncConditionalFields();
    resultEl.innerHTML = "";
    shareState.check = null;
    setShareBar("result-share", false);
    formNote.textContent = "";
  });

  // ---------- HS 조회 ----------
  var hsForm = document.getElementById("hs-form");
  var hsResultEl = document.getElementById("hs-result");
  var hsSubmit = document.getElementById("hs-submit");
  var hsNote = document.getElementById("hs-note");

  hsForm.addEventListener("submit", function(ev){
    ev.preventDefault();
    var code = document.getElementById("hs-code").value.replace(/[^0-9]/g, "");
    if (code.length !== 10){
      hsNote.textContent = "HS 10자리 숫자를 입력해 주세요(현재 " + code.length + "자리).";
      return;
    }
    hsNote.textContent = "";
    hsSubmit.disabled = true;
    hsSubmit.textContent = "조회 중…";
    hsResultEl.innerHTML = '<div class="card"><p class="sub"><span class="spinner"></span> 세관장확인대상물품을 조회하고 있습니다…</p></div>';
    postTool("lookup_hs_requirements", { hs_code: code, direction: document.getElementById("hs-direction").value })
      .then(function(result){
        var html = '<div class="card"><h2>HS ' + esc(code) + '</h2>' +
          '<p class="sub">' + esc((result.hs_lookup && result.hs_lookup.note_ko) || "") + '</p>' +
          verdictBlock(result.verdict, result) + provenanceLine(result) +
          '<h3>세관장확인 요건</h3>' + customsBlock(result.hs_requirements_live, 10) +
          '</div>';
        html += sectionCollapsible("근거 법령·조항", evidenceBlock(result.evidence), String((result.evidence || []).length) + "건 펼쳐 보기");
        html += sectionCollapsible("면책·이용 범위", disclaimerBlock(result), "안내 보기");
        hsResultEl.innerHTML = html;
      })
      .catch(function(err){
        hsResultEl.innerHTML = '<div class="card"><div class="empty">' + esc(err.message || "조회에 실패했습니다.") + '</div></div>';
      })
      .then(function(){
        hsSubmit.disabled = false;
        hsSubmit.textContent = "요건 조회";
      });
  });

  document.getElementById("hs-demo").addEventListener("click", function(){
    document.getElementById("hs-code").value = "8518220000";
    document.getElementById("hs-direction").value = "import";
    hsNote.textContent = "예시를 채웠습니다. '요건 조회'를 눌러 확인해 보세요.";
  });

  // ---------- 탭 전환 ----------
  var buttons = Array.prototype.slice.call(document.querySelectorAll("nav.tabs button[data-tab]"));
  var panels = { check: "tab-check", hs: "tab-hs", api: "tab-api" };
  function showTab(key){
    buttons.forEach(function(btn){
      var on = btn.getAttribute("data-tab") === key;
      btn.setAttribute("aria-selected", on ? "true" : "false");
      document.getElementById(panels[btn.getAttribute("data-tab")]).hidden = !on;
    });
    if (location.hash !== "#" + key){
      try { history.replaceState(null, "", "#" + key); } catch(e){}
    }
  }
  buttons.forEach(function(btn){
    btn.addEventListener("click", function(){ showTab(btn.getAttribute("data-tab")); });
  });
  var initial = (location.hash || "").replace("#", "");
  if (panels[initial]) showTab(initial);

  // ---------- /?q= 프리필 (품목별 페이지에서 넘어온 품목) ----------
  try {
    var preset = new URLSearchParams(location.search).get("q");
    var presetInput = document.getElementById("product");
    if (preset && presetInput){
      presetInput.value = preset.slice(0, 80);
      showTab("check");
      if (form.requestSubmit) form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  } catch (e) {}

  // ---------- /?item=&cat=&origin= 프리필 (공유 링크로 들어온 경우) ----------
  // 공유 링크에는 품목명·품목군·원산지만 담는다. 상세 문구나 개인정보는 받지 않으므로
  // 여기서도 입력란에 그대로 채우지 않고, 허용된 선택지 값일 때만 반영한다.
  try {
    var shared = new URLSearchParams(location.search);
    var sharedItem = shared.get("item");
    var sharedCat = shared.get("cat");
    var sharedOrigin = shared.get("origin");
    var filled = false;
    var optionValue = function(selectEl, wanted){
      var found = null;
      if (!selectEl) return null;
      Array.prototype.forEach.call(selectEl.options, function(opt){
        if (opt.value === wanted) found = opt.value;
      });
      return found;
    };
    if (sharedItem && !shared.get("q")){
      var itemInput = document.getElementById("product");
      if (itemInput && !itemInput.value){
        itemInput.value = sharedItem.slice(0, 80);
        filled = true;
      }
    }
    if (sharedCat){
      var catSelect = document.getElementById("kind");
      var catValue = optionValue(catSelect, sharedCat);
      if (catValue !== null){
        catSelect.value = catValue;
        filled = true;
      }
    }
    if (sharedOrigin){
      var originSelect = document.getElementById("origin");
      var originValue = optionValue(originSelect, sharedOrigin);
      if (originValue !== null){
        originSelect.value = originValue;
        filled = true;
      }
    }
    if (filled){
      showTab("check");
      syncConditionalFields();
      formNote.textContent = "공유 링크의 품목·구분·원산지를 채웠습니다. 내용을 확인하고 '리스크 체크'를 눌러 주세요.";
    }
  } catch (e) {}

  Array.prototype.forEach.call(document.querySelectorAll(".base-slot"), function(el){ el.textContent = BASE; });

  // ---------- CLNS Pro 사전 신청 · 도입 문의 ----------
  var inquiryForm = document.getElementById("inquiry-form");
  if (inquiryForm){
    var inquiryNote = document.getElementById("inquiry-note");
    var inquirySubmit = document.getElementById("inquiry-submit");
    var inquiryContact = document.getElementById("inquiry-contact");
    var inquiryButtonText = inquirySubmit.textContent;
    inquiryForm.addEventListener("submit", function(ev){
      ev.preventDefault();
      var contact = (inquiryContact.value || "").trim();
      if (contact.length < 3){
        inquiryNote.textContent = "회신받을 이메일이나 연락처를 3자 이상 적어 주세요.";
        inquiryContact.focus();
        return;
      }
      var topicEl = document.getElementById("inquiry-topic");
      var messageEl = document.getElementById("inquiry-message");
      inquirySubmit.disabled = true;
      inquirySubmit.textContent = "보내는 중";
      inquiryNote.textContent = "";
      request("POST", "/v1/inquiry", {
        contact: contact,
        topic: topicEl ? topicEl.value : "other",
        message: messageEl ? (messageEl.value || "").trim() : ""
      }).then(function(res){
        inquiryForm.reset();
        inquiryNote.textContent = "접수되었습니다 (접수번호 " + text(res && res.id) +
          "). 확인 후 남기신 연락처로 회신드리겠습니다.";
      }).catch(function(err){
        inquiryNote.textContent = (err && err.message) ? err.message : "접수되지 않았습니다. 잠시 후 다시 시도해 주세요.";
      }).then(function(){
        inquirySubmit.disabled = false;
        inquirySubmit.textContent = inquiryButtonText;
      });
    });
  }

  // ---------- 무료 한도 ----------
  var quotaPill = document.getElementById("quota-pill");
  request("GET", "/v1/meta").then(function(meta){
    var free = meta.free_tier || {};
    if (typeof free.used === "number" && typeof free.monthly_calls === "number"){
      var left = Math.max(0, free.monthly_calls - free.used);
      quotaPill.textContent = "이번 달 무료 호출 " + String(left) + "회 남음";
    } else {
      quotaPill.textContent = "무료 베타";
    }
  }).catch(function(){ quotaPill.textContent = "무료 베타"; });
})();
</script>
<noscript><div class="wrap"><p>이 화면은 자바스크립트가 필요합니다. API는 <code>/v1/mcp</code>에서 확인할 수 있습니다.</p></div></noscript>
</body>
</html>
"""


def render_page(service_name: str = SERVICE_NAME, version: str = SERVICE_VERSION) -> str:
    """웹 UI HTML을 돌려준다(외부 자원 없음, 익명 서비스명만 사용)."""
    page = PAGE_HTML.replace("__VERSION__", version)
    # 가이드 수는 카탈로그에서 읽는다(하드코딩하면 가이드를 추가할 때마다 어긋난다).
    try:
        from . import guides

        guide_count = str(len(guides.items()))
    except Exception:  # noqa: BLE001 - 카탈로그 문제가 첫 화면을 막지 않게
        guide_count = ""
    page = page.replace("__GUIDE_COUNT__", guide_count)
    if service_name != SERVICE_NAME:
        page = page.replace(SERVICE_NAME, service_name)
    verification = site_verification.meta_tags()
    if verification:
        page = page.replace("</head>", verification + "</head>", 1)
    return page
