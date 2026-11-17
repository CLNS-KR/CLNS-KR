"""사람용 단일 페이지 웹 UI (`GET /`).

원칙
----
1. **외부 의존 0**: CSS·JS·이미지를 모두 인라인으로 넣는다(CDN·폰트·트래커 없음).
   서버 CSP가 외부 로드를 아예 막으므로, 페이지가 스스로 완결되어야 한다.
2. **익명**: 실명·이메일·사업자 정보·연락처를 페이지 어디에도 넣지 않는다.
3. **단정 금지**: 판정 문구는 전부 "가능성·확인 필요"로 표기하고, 면책을 하단에 고정한다.
4. **입력값만 전송**: 폼은 품목명·HS·원산지·무선 여부·어린이 대상·품목군·수입 목적만 보낸다.
"""
from __future__ import annotations

SERVICE_NAME = "CLNS"
SERVICE_SUBTITLE_EN = "PRODUCT COMPLIANCE INTELLIGENCE · KOREA"
SERVICE_SUBTITLE_KO = "복잡한 한국 수입 규제를 10초 만에 확인"
SERVICE_TAGLINE = "Clearance, simplified."
SERVICE_VERSION = "0.1.0"

PAGE_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>CLNS · PRODUCT COMPLIANCE INTELLIGENCE · KOREA</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231a4fd6'/%3E%3Ctext x='16' y='23' font-size='19' font-weight='700' fill='white' text-anchor='middle' font-family='sans-serif'%3EC%3C/text%3E%3C/svg%3E">
<meta name="description" content="CLNS — Korea Import Compliance MCP &amp; API. PRODUCT COMPLIANCE INTELLIGENCE · KOREA. Clearance, simplified. 품목명·HS 코드·원산지만으로 세관장확인 요건, 식약처 수입 이력, 국내 리콜 이력, 근거 법령을 한 번에 확인하는 무료 사전 점검. 관세사·법률 자문이 아닌 참고용입니다.">
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
input[type=text], select{
  width:100%; font:inherit; font-size:15px; color:var(--ink); background:var(--bg);
  border:1px solid var(--line); border-radius:10px; padding:11px 12px; appearance:none;
}
select{background-image:none; cursor:pointer}
input[type=text]:focus, select:focus{outline:2px solid var(--brand); outline-offset:1px; border-color:transparent}
.hint{display:block; margin-top:5px; font-size:11.5px; color:var(--ink-soft)}
.seg{display:flex; gap:6px; flex-wrap:wrap}
.seg label{position:relative; flex:1 1 0; min-width:74px}
.seg input{position:absolute; opacity:0; width:1px; height:1px}
.seg span{display:block; text-align:center; cursor:pointer; font-size:13.5px; font-weight:600;
  padding:10px 6px; border:1px solid var(--line); border-radius:10px; background:var(--bg);
  color:var(--ink-soft); user-select:none}
.seg input:checked + span{background:var(--brand-soft); border-color:var(--brand); color:var(--brand)}
.seg input:focus-visible + span{outline:2px solid var(--brand); outline-offset:2px}
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
    <button type="button" role="tab" id="tabbtn-check" aria-controls="tab-check" aria-selected="true" data-tab="check">CLNS Check<span class="tab-ko">리스크 체크</span></button>
    <button type="button" role="tab" id="tabbtn-hs" aria-controls="tab-hs" aria-selected="false" data-tab="hs">CLNS Intelligence<span class="tab-ko">HS·법령·리콜</span></button>
    <button type="button" role="tab" id="tabbtn-api" aria-controls="tab-api" aria-selected="false" data-tab="api">CLNS API &amp; MCP<span class="tab-ko">개발자 연결</span></button>
  </nav>

  <main>
    <!-- ================= 리스크 체크 ================= -->
    <section id="tab-check" role="tabpanel" aria-labelledby="tabbtn-check">
      <div class="card">
        <h2>CLNS Check</h2>
        <p class="sub">수입 전 10초 리스크 체크 · 품목명만 넣어도 됩니다. HS 10자리를 넣으면 세관장확인 요건까지 함께 조회합니다. 결과는 확정 판정이 아니라 <strong>확인할 항목의 목록</strong>입니다.</p>
        <form id="check-form" novalidate>
          <div class="grid">
            <label class="field full" for="product">
              <span class="lab">품목명<span class="req">*</span></span>
              <input type="text" id="product" name="product" maxlength="80" autocomplete="off"
                     placeholder="예: 중국산 블루투스 스피커, 비타민 D3 영양제, 유아용 원목 완구">
              <span class="hint">제품명·용도가 함께 들어가면 판정이 좁혀집니다. 상호·개인정보는 넣지 마세요.</span>
            </label>

            <label class="field" for="hs">
              <span class="lab">HS 코드<span class="opt">선택</span></span>
              <input type="text" id="hs" name="hs" maxlength="10" inputmode="numeric" autocomplete="off"
                     placeholder="10자리 (예: 8518220000)">
              <span class="hint">10자리를 넣으면 관세청 세관장확인대상물품을 실시간 조회합니다(6자리는 요건 판정에 부족).</span>
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
                <option value="food_contact">식품용 기구·용기·포장</option>
                <option value="electronics">전자·생활용품</option>
              </select>
              <span class="hint">식품·화장품을 고르면 식약처 수입신고·부적합 이력을 함께 조회합니다.</span>
            </label>

            <div class="field full">
              <span class="lab">수입 목적</span>
              <div class="seg" role="radiogroup" aria-label="수입 목적">
                <label><input type="radio" name="purpose" value="resale" checked><span>판매·유통</span></label>
                <label><input type="radio" name="purpose" value="self_use"><span>자가소비</span></label>
              </div>
              <span class="hint">판매 목적이면 표시·인증·영업등록 요건이 함께 걸립니다. 자가소비는 개인 반입 면제 범위를 따집니다.</span>
            </div>
          </div>

          <div class="actions">
            <button type="submit" class="primary" id="check-submit">리스크 체크</button>
            <button type="button" class="ghost" id="check-reset">입력 지우기</button>
            <span class="note-inline" id="form-note" aria-live="polite"></span>
          </div>
        </form>
      </div>
      <div id="result" aria-live="polite"></div>
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
              <tr><td>GET</td><td><code>/v1/mcp</code></td><td>MCP 툴 매니페스트(툴 8종)</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/assess_import_case</code></td><td>종합 판정(웹 UI가 호출)</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/assess_import_risk</code></td><td>종합 판정(동일 툴 별칭)</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/lookup_hs_requirements</code></td><td>HS 10자리 세관장확인 요건</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_kc_certification</code></td><td>KC 인증 유형</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/check_food_cosmetics</code></td><td>식품·화장품·건기식 요건</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/lookup_recall</code></td><td>국내 리콜 이력</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/get_legal_basis</code></td><td>근거 조항</td></tr>
              <tr><td>POST</td><td><code>/v1/tools/explain_trap</code></td><td>함정 케이스 해설</td></tr>
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
        <p class="sub">MCP 클라이언트에는 <code><span class="base-slot">https://&lt;your-host&gt;</span>/v1/mcp</code>의 툴 목록을 그대로 등록할 수 있습니다. 아래 링크에서 실제 JSON을 확인하세요.</p>
        <div class="actions">
          <a class="ghost" href="/v1/mcp" target="_blank" rel="noopener" style="text-decoration:none;padding:10px 14px">/v1/mcp 열기</a>
          <a class="ghost" href="/v1/meta" target="_blank" rel="noopener" style="text-decoration:none;padding:10px 14px">/v1/meta 열기</a>
        </div>
      </div>
    </section>
  </main>

  <footer>
    <p><strong>CLNS</strong></p>
    <p>PRODUCT COMPLIANCE INTELLIGENCE · KOREA</p>
    <p>Clearance, simplified.</p>
    <p>무료 베타 · 결제 없음 · 회원가입 없음</p>
    <p><strong>면책:</strong> 본 결과는 사전 참고용입니다. 법적 효력이 없으며, 최종 법적 판단과 통관·인증 가능 여부는 관세사, 관세청, 국가기술표준원·인증기관, 식품의약품안전처 등 소관 기관의 확인이 필요합니다. 본 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않습니다.</p>
    <p><strong>데이터:</strong> 관세청·식품의약품안전처·산업통상부 국가기술표준원·법제처 공공데이터를 활용합니다. 원본을 그대로 중계하지 않고 결합·정규화한 판정만 제공하며, 조회 실패나 개정 지연 시 캐시 시점을 밝히고 판정을 "추가 정보 필요"로 낮춥니다.</p>
    <p><strong>개인정보:</strong> 이름·연락처·이메일·사업자 정보를 받지 않습니다. 입력한 품목 정보(품목명·HS·원산지 등)는 판정 이력에 익명으로 저장될 수 있습니다. 상호·주소 등 식별 정보는 입력하지 마세요.</p>
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

  // ---------- 조각 렌더 ----------
  function verdictBlock(v){
    if (!v) return "";
    return '<div class="verdict v-' + esc(v.code) + '">' +
      '<div class="code">종합 판정</div>' +
      '<div class="lab">' + esc(v.label_ko) + '<span class="en">' + esc(v.label_en) + '</span></div>' +
      '<p>' + esc(v.note_ko) + '</p></div>';
  }
  function section(title, inner, sub){
    return '<div class="card"><h2>' + esc(title) + '</h2>' +
      (sub ? '<p class="sub">' + esc(sub) + '</p>' : '') + inner + '</div>';
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
      return "<tr><td><strong>" + esc(f.case_id) + "</strong></td><td>" + esc(f.title) + "<br><span class='note-inline'>" + esc(f.issue_ko) + "</span></td><td>" + chips + "</td><td>" + esc(String(Math.round((f.confidence || 0) * 100)) + "%") + "</td></tr>";
    }).join("");
    return '<div class="tbl-wrap"><table><thead><tr><th>케이스</th><th>쟁점</th><th>판정</th><th>신뢰도</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function findingsDetail(findings){
    if (!findings || !findings.length) return "";
    return findings.map(function(f){
      var body = '<div class="body">' +
        (f.explanation ? "<p>" + esc(f.explanation) + "</p>" : "") +
        (f.misconception ? '<p><span class="tag bad">흔한 오답</span>' + esc(f.misconception) + "</p>" : "") +
        (f.notes ? '<p><span class="tag">주의</span>' + esc(f.notes) + "</p>" : "") +
        (f.reason ? '<p class="note-inline">판정 사유: ' + esc(f.reason) + "</p>" : "") +
        "</div>";
      return '<details><summary>' + esc(f.case_id) + " · " + esc(f.title) + '</summary>' + body + '</details>';
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
    var rows = (block.requirements || []).map(function(r){
      return { law: r.requirement_law, agency: r.requirement_agency, doc: r.requirement_document, from: r.applies_from, timing: r.timing };
    });
    var inner = '<p class="sub">' + esc(block.hs_code) + " · 조회 " + esc(block.checked_at) + " · 요건 " + esc(String(block.requirement_count)) + "건</p>";
    inner += table([["요건 법령", "law"], ["확인 기관", "agency"], ["확인 서류", "doc"], ["적용 시작", "from"], ["시점", "timing"]], rows);
    if (!rows.length) inner += emptyBox(block.zero_note_ko || "0건은 요건 없음을 뜻하지 않습니다.");
    return inner + '<p class="note-inline" style="margin-top:8px">' + esc(block.note_ko || "") + "</p>";
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
    var query = buildQuery(data);

    submitBtn.disabled = true;
    submitBtn.textContent = "확인 중…";
    resultEl.innerHTML = '<div class="card"><p class="sub"><span class="spinner"></span> 판정과 공공데이터를 조회하고 있습니다…</p></div>';

    var mainP = postTool("assess_import_case", { query: query, facts: facts, limit: 3 });
    var hsP = data.hs.length === 10 ? soft(postTool("lookup_hs_requirements", { hs_code: data.hs, direction: "import" })) : Promise.resolve(null);
    var recallP = soft(postTool("lookup_recall", { product_name: data.product, brand: "", limit: 5 }));

    Promise.all([mainP, hsP, recallP]).then(function(res){
      var result = res[0], hsResult = res[1], recall = res[2];
      var kind = data.kind;
      if (!kind){
        var cats = (result.findings || []).map(function(f){ return f.category; });
        if (cats.indexOf("cosmetics") !== -1) kind = "cosmetics";
        else if (cats.indexOf("food") !== -1 || cats.indexOf("label") !== -1) kind = "food";
      }
      var mfdsP = kind ? soft(postTool("check_food_cosmetics", { product_name: data.product, kind: kind, purpose: data.purpose })) : Promise.resolve(null);
      return Promise.all([Promise.resolve(result), Promise.resolve(hsResult), Promise.resolve(recall), mfdsP]);
    }).then(function(res){
      var result = res[0], hsResult = res[1], recall = res[2], mfds = res[3];
      var html = "";
      html += '<div class="card">' +
        '<h2>판정 결과</h2>' +
        '<p class="sub">입력한 품목: ' + esc(result.query ? result.query.text : data.product) + '</p>' +
        verdictBlock(result.verdict) +
        provenanceLine(result) +
        '<h3>판정 요지</h3>' + guidanceBlock(result) +
        '<h3>확인 필요 체크리스트</h3>' + checklist(result) +
        '</div>';

      html += section("쟁점 " + String((result.findings || []).length) + "건", findingsTable(result.findings) + findingsDetail(result.findings),
        "신뢰도는 입력 정보의 충족 정도를 반영합니다. 100% 확정 판정이 아닙니다.");

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
      html += section("세관장확인 요건 (관세청)", customsInner, customsSub);

      if (mfds){
        html += section("식약처 수입 이력", mfds.__error ? emptyBox("식약처 조회 실패: " + mfds.__error) : mfdsBlock(mfds.food_import_live),
          "제품DB·수입신고·검사부적합 이력을 참고용으로 보여줍니다.");
      }

      var recallInner = (recall && recall.__error)
        ? emptyBox("리콜 조회 실패: " + recall.__error)
        : recallBlock(recall && recall.recall);
      html += section("로컬 리콜 참고 (국표원)", recallInner,
        "2023-08-09 배포본 기준 과거 이력입니다. 최신 리콜은 제품안전정보센터에서 확인하세요.");

      html += section("근거 법령·조항", evidenceBlock(result.evidence),
        "인용문은 요지 발췌입니다. 조문 전체는 원문에서 확인해야 하며, 출처 표시 없이 재배포할 수 없습니다.");

      html += section("면책·이용 범위", disclaimerBlock(result));

      resultEl.innerHTML = html;
      resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }).catch(function(err){
      resultEl.innerHTML = '<div class="card"><div class="empty">' + esc(err.message || "조회에 실패했습니다.") + "</div>" +
        '<p class="note-inline" style="margin-top:10px">잠시 후 다시 시도해 주세요. 계속 실패하면 HS 10자리 조회 탭만 따로 이용해 보세요.</p></div>';
    }).then(function(){
      submitBtn.disabled = false;
      submitBtn.textContent = "리스크 체크";
    });
  });

  document.getElementById("check-reset").addEventListener("click", function(){
    form.reset();
    resultEl.innerHTML = "";
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
          verdictBlock(result.verdict) + provenanceLine(result) +
          '<h3>세관장확인 요건</h3>' + customsBlock(result.hs_requirements_live, 10) +
          '</div>';
        html += section("쟁점", findingsTable(result.findings));
        html += section("근거 법령·조항", evidenceBlock(result.evidence));
        html += section("면책·이용 범위", disclaimerBlock(result));
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

  Array.prototype.forEach.call(document.querySelectorAll(".base-slot"), function(el){ el.textContent = BASE; });

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
    if service_name != SERVICE_NAME:
        page = page.replace(SERVICE_NAME, service_name)
    return page
