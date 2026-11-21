"""정적 고지 페이지 — `/privacy` · `/terms` · `/about`.

왜 서버 렌더 정적 HTML 인가
--------------------------
- 사람·검색 크롤러·AI 크롤러가 같은 내용을 본다(JS 없음, 외부 CDN 없음 → CSP 그대로).
- 무료 베타에 필요한 최소 고지(무엇을 받지 않는지·무엇이 남는지·어디로 삭제를 요청하는지)를
  한 곳에 둔다. 문구를 바꿀 때 이 파일만 고치면 세 주소가 함께 바뀐다.

익명 운영 원칙
--------------
실명·직업·개인 연락처·상대 서비스 핸들을 쓰지 않는다. 문의·삭제 요청 경로는 서비스 자체
접수(`POST /v1/inquiry`)와 공개 저장소 Issues 만 쓴다. 운영자 개인정보를 페이지에 남기지
않는 것이 이 서비스의 약속이므로, 고지 문구도 그 선을 넘지 않는다.
"""
from __future__ import annotations

from typing import Dict, Optional

from . import static_files
from .version import __version__

SERVICE = "CLNS"
TAGLINE = "Clearance, simplified."
REPO_URL = "https://github.com/CLNS-KR/CLNS-KR"
REPO_ISSUES = REPO_URL + "/issues"
SIBLINGS = (
    ("https://grnt-kr.onrender.com/", "GRNT", "개인·창업 통합 지원금 판정기"),
    ("https://frnc.onrender.com/", "FRNC", "프랜차이즈 창업 전 리스크 체크"),
)

# 고지 문구의 기준일. 내용을 실제로 바꿀 때만 올린다.
EFFECTIVE_DATE = "2026-11-21"

TITLES: Dict[str, str] = {
    "privacy": "개인정보 처리방침",
    "terms": "이용약관",
    "about": "서비스 소개",
}
DESCRIPTIONS: Dict[str, str] = {
    "privacy": "CLNS가 받지 않는 정보, 남기는 익명 통계, 문의 연락처 보관 기간(180일), 삭제 요청 경로를 정리했습니다.",
    "terms": "CLNS는 무료 정보 제공 서비스입니다. 확정 판정·전문가 자문이 아니며, 근거 조문과 한계를 밝힙니다.",
    "about": "한국 수입 규제 사전 점검 서비스 CLNS의 대상·데이터 출처·판정 3단계와, 같이 운영하는 서비스 2종을 소개합니다.",
}

_CSS = """
:root{--bg:#0b1019;--card:#121a2b;--line:#243252;--ink:#e8edf5;--soft:#9fb3d9;--brand:#7ea6ff}
@media (prefers-color-scheme:light){:root{--bg:#f6f8fc;--card:#fff;--line:#dbe3f2;--ink:#16213a;--soft:#4c5f80;--brand:#1a4fd6}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.wrap{max-width:780px;margin:0 auto;padding:32px 20px 64px}
.top{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.top a.brand{color:var(--ink);text-decoration:none;font-weight:800;font-size:20px;letter-spacing:.02em}
.top span{color:var(--soft);font-size:13px}
h1{font-size:26px;line-height:1.35;margin:18px 0 6px}
h2{font-size:18px;margin:30px 0 8px}
p,li{color:var(--ink)}
.meta{color:var(--soft);font-size:13px;margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:16px 0}
ul{padding-left:20px;margin:8px 0}
li{margin:6px 0}
a{color:var(--brand)}
code{font-size:13px;background:rgba(126,166,255,.12);padding:1px 5px;border-radius:5px}
.nav{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);font-size:13px;color:var(--soft)}
.nav a{margin-right:10px}
footer{margin-top:28px;font-size:12px;color:var(--soft)}
"""

_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {service}</title>
<meta name="description" content="{description}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{service}">
<meta property="og:title" content="{title} · {service}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:locale" content="ko_KR">
<meta property="og:image" content="{root}/static/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <a class="brand" href="/">{service}</a>
    <span>{tagline} · 수입 규제 사전 점검</span>
  </div>
  <h1>{title}</h1>
  <p class="meta">시행일 {effective} · 버전 {version} · 무료 베타</p>
  {body}
  <div class="nav">{nav}</div>
  <footer>© 2026 {service} · 익명 운영 무료 베타 · 이 페이지는 사전 점검 서비스의 고지이며 법률 자문이 아닙니다.</footer>
</div>
</body>
</html>
"""


def _page(slug: str, body: str, base: Optional[str] = None) -> str:
    root = static_files.base_url(base)
    canonical = f"{root}/{slug}"
    nav_items = [f'<a href="/">리스크 체크</a>', f'<a href="/p/">품목별 요건</a>',
                 f'<a href="/guides/">질문형 가이드</a>']
    for other, title in TITLES.items():
        if other != slug:
            nav_items.append(f'<a href="/{other}">{title}</a>')
    return _PAGE.format(title=TITLES[slug], description=DESCRIPTIONS[slug], canonical=canonical,
                        service=SERVICE, tagline=TAGLINE, css=_CSS, version=__version__,
                        effective=EFFECTIVE_DATE, body=body, nav="".join(nav_items), root=root)


def _privacy(base: Optional[str] = None) -> str:
    body = f"""
<p>CLNS는 회원가입·로그인이 없고, 결제도 받지 않습니다. 아래는 이 서비스가 <strong>받지 않는 것</strong>과
<strong>남기는 것</strong>, 그리고 남긴 것을 지우는 방법입니다.</p>

<h2>받지 않는 정보</h2>
<ul>
  <li>이름·주민등록번호·전화번호·이메일·주소: 조회·판정 화면에서는 받지 않습니다.</li>
  <li>회원 계정·비밀번호·소셜 로그인: 만들지 않습니다.</li>
  <li>브라우저 쿠키·광고 식별자·추적 스크립트: 쓰지 않습니다. 외부 CDN·폰트도 불러오지 않습니다.</li>
</ul>

<h2>조회할 때 남는 것</h2>
<ul>
  <li><strong>판정 이력</strong> — 입력한 품목명·HS 코드·문구와 그 결과가 익명 식별자와 함께 서버 DB에
  저장될 수 있습니다. 이 식별자는 브라우저가 보내는 임의 문자열(<code>X-Client-Id</code>) 또는
  <code>anonymous</code> 이며, 사람을 특정하는 값이 아닙니다. 상호·연락처 같은 식별 정보는 넣지 마세요.</li>
  <li><strong>익명 일별 카운터</strong> — 날짜·경로·툴 이름·판정 등급의 <em>호출 횟수</em>만 남깁니다.
  IP 주소·User-Agent 원문·쿠키·Referer·세션 ID는 저장하지 않습니다. 요청 제한을 위해 쓰는 IP는
  프로세스마다 새로 만드는 salt로 해시해 메모리에만 두고, 저장하지 않습니다.</li>
  <li><strong>요청 종류</strong> — 브라우저인지 봇인지의 구분(브라우저·봇·기타 3종)만 셉니다. User-Agent 원문은 남기지 않습니다(봇 판별은 문자열 표식 기준의 참고 수치).</li>
  <li><strong>시계열 스냅샷</strong> — 리콜·행정처분 같은 제도 정보의 날짜별 요약입니다. 사용자 입력은 들어가지 않습니다.</li>
</ul>

<h2>문의할 때 남기는 연락처</h2>
<ul>
  <li>'CLNS Pro 사전 신청·도입 문의'(<code>POST /v1/inquiry</code>)에 적은 연락처는 <strong>그 문의에 회신하는 용도로만</strong> 씁니다.</li>
  <li>보관 기간은 접수일로부터 <strong>180일</strong>이며, 기간이 지나면 지웁니다. 통계·공개 화면에는 넣지 않습니다.</li>
  <li>문의 본문은 회신에 필요한 범위에서만 확인하고, 다른 목적으로 쓰지 않습니다.</li>
</ul>

<h2>삭제 요청</h2>
<ul>
  <li>판정 이력·문의로 남긴 연락처의 삭제를 원하시면 서비스 내 문의(<code>POST /v1/inquiry</code>)에
  <strong>삭제 요청</strong>이라고 적어 보내 주세요. 확인 후 지체 없이 지우고 회신합니다.</li>
  <li>공개 저장소 <a href="{REPO_ISSUES}" target="_blank" rel="noopener noreferrer">이슈</a>로도 요청할 수 있습니다.
  이슈는 공개되므로 개인정보는 적지 말고, 삭제 대상(대략적인 조회 시점·품목)만 알려 주세요.</li>
</ul>

<h2>제3자 제공·처리 위탁</h2>
<ul>
  <li>수집한 정보를 제3자에게 판매·제공하지 않습니다. 국외 이전도 하지 않습니다.</li>
  <li>서비스는 호스팅 사업자 위에서 동작합니다. 호스팅 사업자의 플랫폼 접속 로그는 이 서비스 코드가
  저장하는 정보와 별개로 그 사업자 정책을 따릅니다.</li>
</ul>

<h2>공공데이터에 포함된 정보</h2>
<p>관세청·식약처 등 공개 데이터에 기관 담당 부서·연락처가 포함된 경우가 있습니다. CLNS는 이를
판정 근거로만 보여 주며, 별도로 수집·가공해 제공하지 않습니다.</p>

<h2>문의</h2>
<p>개인정보 처리에 관한 문의는 서비스 내 문의 접수 또는 공개 저장소
<a href="{REPO_ISSUES}" target="_blank" rel="noopener noreferrer">이슈</a>로 받습니다. 운영자 개인 연락처는
공개하지 않습니다(익명 운영 원칙).</p>
"""
    return _page("privacy", body, base)


def _terms(base: Optional[str] = None) -> str:
    body = f"""
<p>CLNS는 한국 수입·유통 규제를 <strong>미리 확인해 보는 무료 사전 점검 도구</strong>입니다.
이용 전에 아래 범위와 한계를 확인해 주세요.</p>

<h2>서비스가 하는 일</h2>
<ul>
  <li>품목명·HS 코드 등으로 세관장확인 요건, 식약처 수입 이력, 국내 리콜, 근거 법령을 조회해
  <strong>확인해야 할 항목의 목록</strong>을 제시합니다.</li>
  <li>모든 응답에 근거 조항·시행일·원문 주소와 국·영문 면책을 함께 표시합니다.</li>
</ul>

<h2>서비스가 하지 않는 일</h2>
<ul>
  <li>확정 판정이 아닙니다. 판정 등급은 '확인 가능성 높음 / 추가 정보 필요 / 현재 정보상 낮음'이며
  통관·인증 가능 여부를 확정하지 않습니다.</li>
  <li>관세사법상 관세 상담·대리 업무를 하지 않습니다. 품목분류(HS) 확정, 인증 대행, 통관 대리도 하지 않습니다.</li>
  <li>법률·세무·의료 자문을 대신하지 않습니다. 최종 판단은 관세사, 관세청, 국가기술표준원·인증기관,
  식품의약품안전처 등 소관 기관의 확인으로 하세요.</li>
</ul>

<h2>데이터와 정확성</h2>
<ul>
  <li>관세청·식약처·국가기술표준원·국립전파연구원·법제처 공공데이터와 공개 법령을 활용합니다.
  원본을 그대로 중계하지 않고 결합·정규화한 판정을 제공합니다.</li>
  <li>공공데이터는 갱신이 늦거나 개편될 수 있습니다. 리콜 데이터처럼 배포 시점이 오래된 자료도 있습니다.
  조회 0건은 '요건 없음'이 아니라 '조회되지 않음'입니다.</li>
  <li>실시간 조회가 실패하거나 캐시로 답한 경우, 그 사실과 캐시 시점을 응답에 표시합니다.</li>
</ul>

<h2>이용자의 책임</h2>
<ul>
  <li>입력한 정보의 정확성은 이용자에게 있습니다. 상호·연락처 등 식별 정보는 입력하지 마세요.</li>
  <li>자동화된 과도한 호출, 서비스 우회·부하 유발, 결과를 확정 판정처럼 재판매·재게시하는 행위는
  제한될 수 있습니다(요청 제한은 분당 호출 수로 적용됩니다).</li>
</ul>

<h2>책임의 한계</h2>
<ul>
  <li>서비스는 '있는 그대로' 제공됩니다. 무료 베타이며, 중단·변경·오류가 있을 수 있습니다.</li>
  <li>서비스 이용으로 발생한 통관 지연·과태료·거래 손실 등 결과에 대해, 고의 또는 중대한 과실이 없는 한
  책임지지 않습니다. 서비스는 법적 조언이나 보증을 제공하지 않습니다.</li>
</ul>

<h2>약관의 변경</h2>
<p>내용이 바뀌면 이 페이지의 시행일과 버전을 갱신합니다. 중요한 변경은 서비스 화면에서 알립니다.</p>

<h2>준거법</h2>
<p>이 약관은 대한민국 법에 따릅니다.</p>
"""
    return _page("terms", body, base)


def _about(base: Optional[str] = None) -> str:
    root = static_files.base_url(base)
    siblings = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener noreferrer"><strong>{name}</strong></a> — {desc}</li>'
        for url, name, desc in SIBLINGS
    )
    body = f"""
<p><strong>CLNS</strong>는 한국으로 물건을 들여오기 전에 "무엇을 확인해야 하는지"를 한 화면에서
정리해 주는 무료 사전 점검 서비스입니다. {TAGLINE}</p>

<h2>누구를 위한 서비스인가</h2>
<ul>
  <li>해외 직구·구매대행으로 판매를 시작하려는 소규모 셀러</li>
  <li>수입 품목의 인증·표시·광고 문구를 미리 점검하려는 운영자</li>
  <li>수입 규제를 조사하는 개발자·기획자(AI·MCP 클라이언트 포함)</li>
</ul>

<h2>무엇을 답하나</h2>
<ul>
  <li>세관장확인 요건(관세청 HS 10자리), 식약처 수입 이력, 국내 리콜, KC·전파 적합성평가</li>
  <li>의약품·영양제 금지성분, 한글표시사항, 과대광고 금지 표현, 반려동물 사료·동물검역</li>
  <li>국내 판매페이지의 공정위·전자상거래법 표시 위험, 관세율·FTA, 화장품 배합 금지·한도</li>
</ul>

<h2>판정 3단계</h2>
<p><code>check_likely</code> 확인 가능성 높음 · <code>info_needed</code> 추가 정보 필요 ·
<code>low_risk</code> 현재 정보상 가능성 낮음. 셋 다 확정 판단이 아니며, 근거 조문과 함께 표시합니다.</p>

<h2>데이터 출처</h2>
<p>관세청 세관장확인대상물품, 식품의약품안전처 수입식품·행정처분·의약품 허가정보, 산업통상부
국가기술표준원 리콜 파일데이터, 과학기술정보통신부 국립전파연구원 적합성평가 정보, 법제처 국가법령정보,
그리고 마약류 관리에 관한 법률 시행령 별표 1~8에서 만든 성분 사전을 씁니다.</p>

<h2>쓰는 방법</h2>
<ul>
  <li>사람: <a href="/">리스크 체크</a>에서 품목명을 넣고 확인 항목을 봅니다.</li>
  <li>검색·AI: <a href="/p/">품목별 요건</a>·<a href="/guides/">질문형 가이드</a>가 정적 HTML로 열려 있습니다.</li>
  <li>개발자: MCP(<code>POST /mcp</code>) · REST(<code>POST /v1/tools/&lt;tool&gt;</code>)로 같은 판정을 받습니다.
  키 없이 쓸 수 있고, 무료 월 호출 한도가 있습니다.</li>
</ul>

<h2>같이 쓰는 서비스</h2>
<ul>{siblings}</ul>
<p>세 서비스는 같은 원칙으로 운영합니다 — 무료, 로그인 없음, 익명 운영, 근거 조문 표시,
확정 판정 대신 확인 항목 제시.</p>

<h2>만든 방식과 한계</h2>
<p>표준 라이브러리만으로 동작하고, 페이지는 외부 CDN 없이 인라인 자원만 씁니다. 무료 베타라
지자체·기관 데이터 커버리지에 빈 곳이 있을 수 있고, 그런 경우 응답에 사실대로 표시합니다.</p>
"""
    return _page("about", body, base)


_RENDERERS = {"privacy": _privacy, "terms": _terms, "about": _about}


def is_page(path: str) -> bool:
    """`/privacy`·`/privacy/` 처럼 이 모듈이 답하는 주소인지."""
    slug = str(path or "").strip("/").lower()
    return slug in _RENDERERS


def render(path: str, base: Optional[str] = None) -> Optional[str]:
    """슬러그(`privacy`·`terms`·`about`) 또는 경로로 HTML 을 만든다. 모르는 주소면 None."""
    slug = str(path or "").strip("/").lower()
    renderer = _RENDERERS.get(slug)
    return renderer(base) if renderer else None


def footer_links_html() -> str:
    """홈·가이드 푸터에 붙는 고지 링크 묶음(모든 화면에서 같은 자리)."""
    items = " · ".join(f'<a href="/{slug}">{title}</a>' for slug, title in TITLES.items())
    return f'<span class="legal-links">{items}</span>'
