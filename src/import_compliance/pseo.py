"""품목별 무료 체크 페이지(pSEO) — 서버가 완성된 HTML을 내려주는 정적 렌더러.

원칙
----
1. **JS 없이 읽힌다**: 크롤러가 H1·요약·요건·근거·면책을 그대로 파싱할 수 있게
   본문을 모두 서버에서 렌더한다(스크립트 0줄).
2. **익명**: 저작·운영 주체는 `CLNS` 하나뿐이다. 개인 이름·연락처를 넣지 않는다.
3. **단정 금지**: 요건은 "확인해야 할 항목"으로 쓰고, 세관장확인 0건은
   "요건 없음이 아니라 조회되지 않음"으로 밝힌다.
4. **얇은 페이지는 색인하지 않는다**: 내용이 부족한 항목은 `noindex`를 붙이고
   사이트맵에서도 뺀다(`is_indexable`).

데이터
------
`src/pseo_items.json` — 2026-11-18 관세청 세관장확인대상물품(15101589) 실조회 결과를
기관별로 정규화한 요건 표 + 큐레이션 문안. 갱신은 `tools/refresh_pseo_hs.py`.
법적 근거 인용은 함정 코퍼스(`traps_20.json`)의 조항을 그대로 재사용한다.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from html import escape
from typing import Any, Dict, List, Optional

from . import site_verification, static_files
from .corpus import load_corpus
from .models import Trap
from .standards import CASE_REGULATION_TAGS, REGULATION_TAGS

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "pseo_items.json")

# 얇은 페이지 판정 기준: 핵심 포인트+요건+인증 문장이 이보다 적거나 요약이 짧으면 색인 제외.
THIN_MIN_BLOCKS = 4
THIN_MIN_SUMMARY = 60
MAX_QUOTE = 240
MAX_TRAP_ANSWER = 320

ZERO_NOTE_KO = (
    "조회 결과 0건은 '요건 없음'이 아니라 '조회되지 않음'입니다. HS 10자리 품목코드, "
    "수입/수출 구분, 고시 개정 시점에 따라 결과가 달라집니다."
)


class CatalogError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    """pSEO 카탈로그를 읽는다(슬러그 중복·필수 필드 검증)."""
    with open(CATALOG_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)
    items = raw.get("items") or []
    if not isinstance(items, list) or not items:
        raise CatalogError("empty pseo catalog")
    seen = set()
    for item in items:
        slug = str(item.get("slug") or "")
        if not slug or not slug.replace("-", "").isalnum():
            raise CatalogError(f"invalid slug: {slug!r}")
        if slug in seen:
            raise CatalogError(f"duplicate slug: {slug}")
        seen.add(slug)
        for field in ("name_ko", "hs_code", "summary_ko", "requirements_ko"):
            if not item.get(field):
                raise CatalogError(f"{slug}: missing {field}")
    return raw


def items() -> List[Dict[str, Any]]:
    return list(load_catalog()["items"])


@lru_cache(maxsize=1)
def item_index() -> Dict[str, Dict[str, Any]]:
    return {item["slug"]: item for item in load_catalog()["items"]}


def get_item(slug: str) -> Optional[Dict[str, Any]]:
    """슬러그로 항목을 찾는다. 없으면 None(서버가 404)."""
    return item_index().get(str(slug or "").strip())


def slugs() -> List[str]:
    return [item["slug"] for item in load_catalog()["items"]]


def catalog_meta() -> Dict[str, Any]:
    raw = load_catalog()
    return {
        "version": raw.get("catalog_version", ""),
        "verified_on": raw.get("verified_on", ""),
        "hs_checked_at": raw.get("hs_checked_at", ""),
        "count": len(raw.get("items") or []),
    }


def is_indexable(item: Dict[str, Any]) -> bool:
    """색인 가능한(=충분히 두꺼운) 페이지만 True. 얇으면 noindex."""
    blocks = (len(item.get("key_points_ko") or [])
              + len(item.get("requirements_ko") or [])
              + len(item.get("certifications_ko") or [])
              + len(item.get("traps") or []))
    summary_len = len(str(item.get("summary_ko") or ""))
    return blocks >= THIN_MIN_BLOCKS and summary_len >= THIN_MIN_SUMMARY


def page_path(slug: str) -> str:
    return f"/p/{slug}"


def index_path() -> str:
    return "/p/"


def indexable_paths() -> List[str]:
    """사이트맵에 넣을 경로(홈 제외). 얇은 페이지는 빠진다."""
    return [index_path()] + [page_path(slug) for slug, item in item_index().items()
                             if is_indexable(item)]


# --- 렌더링 헬퍼 -------------------------------------------------------------

def _esc(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _clamp(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _json_ld(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("</", "<\\/")


def _trap_map() -> Dict[str, Trap]:
    try:
        corpus = load_corpus()
    except (OSError, ValueError):
        return {}
    return {trap.id: trap for trap in corpus.traps}


def _item_traps(item: Dict[str, Any]) -> List[Trap]:
    traps = _trap_map()
    out: List[Trap] = []
    for case_id in item.get("traps") or []:
        trap = traps.get(str(case_id))
        if trap is not None:
            out.append(trap)
    return out


def _legal_basis(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """항목에 연결된 함정 케이스들의 근거 조항을 중복 없이 모은다."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for trap in _item_traps(item):
        for basis in trap.legal_basis:
            key = (basis.law, basis.article)
            if key in seen:
                continue
            seen.add(key)
            entry = basis.to_dict()
            entry["case_id"] = trap.id
            out.append(entry)
    return out


def _requirement_rows(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = item.get("hs_requirements") or []
    return [row for row in rows if isinstance(row, dict)]


# --- 공통 레이아웃 -----------------------------------------------------------

STYLE = """
:root{
  --bg:#f4f6fa; --card:#ffffff; --ink:#12161f; --ink-soft:#4c5566; --line:#dde3ec;
  --brand:#1a4fd6; --brand-soft:#e8eefc; --ok:#0f7a4a; --ok-soft:#e4f6ec;
  --warn:#9a5b00; --warn-soft:#fdf1dc; --radius:14px;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#0e1116; --card:#161b22; --ink:#e8edf5; --ink-soft:#a7b1c2; --line:#2a3240;
    --brand:#7ea6ff; --brand-soft:#18233c; --ok:#5fd39a; --ok-soft:#12291f;
    --warn:#f0bb63; --warn-soft:#2a2113;}
}
*{box-sizing:border-box}
body{margin:0; background:var(--bg); color:var(--ink); line-height:1.6; font-size:16px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif}
a{color:var(--brand); text-underline-offset:2px}
.wrap{max-width:920px; margin:0 auto; padding:0 18px 56px}
header.top{display:flex; gap:12px; align-items:center; justify-content:space-between;
  flex-wrap:wrap; padding:20px 0 14px; border-bottom:1px solid var(--line)}
header.top a.brand{display:flex; gap:11px; align-items:center; text-decoration:none; color:inherit}
.mark{width:36px;height:36px;border-radius:10px;background:var(--brand);color:#fff;
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px}
.brand-name{font-size:18px; letter-spacing:.14em; text-transform:uppercase; font-weight:700}
.brand-sub{margin:0; font-size:11.5px; color:var(--ink-soft)}
nav.crumb{margin:18px 0 0; font-size:12.5px; color:var(--ink-soft)}
nav.crumb a{color:var(--ink-soft)}
h1{font-size:27px; line-height:1.3; margin:14px 0 8px; letter-spacing:-.01em}
h2{font-size:18.5px; margin:26px 0 10px}
h3{font-size:15px; margin:16px 0 6px}
p.lede{font-size:16px; color:var(--ink); margin:0 0 14px}
.pills{display:flex; gap:6px; flex-wrap:wrap; margin:10px 0 6px}
.pill{font-size:11.5px; font-weight:600; padding:4px 10px; border-radius:999px;
  background:var(--brand-soft); color:var(--brand)}
.pill.ghost{background:transparent; color:var(--ink-soft); border:1px solid var(--line)}
.card{background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:16px 18px; margin:12px 0}
ul.clean{margin:8px 0 0; padding-left:18px}
ul.clean li{margin:5px 0}
table{width:100%; border-collapse:collapse; font-size:14px; margin-top:8px}
.tablewrap{overflow-x:auto; -webkit-overflow-scrolling:touch}
th,td{text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top}
th{font-size:12.5px; color:var(--ink-soft); font-weight:600; white-space:nowrap}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13.5px;
  background:var(--brand-soft); padding:1px 5px; border-radius:5px}
.kv{display:grid; grid-template-columns:minmax(90px,140px) 1fr; gap:6px 14px; font-size:14px}
.kv dt{color:var(--ink-soft); margin:0}
.kv dd{margin:0}
.trap{border-left:3px solid var(--warn); background:var(--warn-soft); padding:12px 14px;
  border-radius:10px; margin:10px 0}
.trap strong{display:block; margin-bottom:4px}
.trap p{margin:5px 0; font-size:14px}
.cta{display:flex; gap:10px; flex-wrap:wrap; margin:16px 0 4px}
.cta a{display:inline-block; padding:11px 16px; border-radius:10px; text-decoration:none;
  font-weight:700; font-size:15px; background:var(--brand); color:#fff}
.cta a.ghost{background:transparent; color:var(--brand); border:1px solid var(--line)}
.zero{background:var(--warn-soft); border-radius:10px; padding:12px 14px; font-size:14px; color:var(--ink)}
.grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; margin-top:12px}
.grid a{display:block; padding:12px 14px; border:1px solid var(--line); border-radius:12px;
  background:var(--card); text-decoration:none; color:var(--ink); font-weight:600; font-size:14.5px}
.grid a span{display:block; font-weight:400; font-size:12px; color:var(--ink-soft); margin-top:3px}
footer{margin-top:34px; padding-top:16px; border-top:1px solid var(--line); font-size:12.5px; color:var(--ink-soft)}
footer p{margin:6px 0}
footer strong{color:var(--ink)}
@media (max-width:560px){
  h1{font-size:22px} .wrap{padding:0 14px 44px}
  table{font-size:13px} th,td{padding:7px 6px}
}
"""


def _head(title: str, description: str, canonical: str, base: str,
          noindex: bool, json_ld: Optional[Dict[str, Any]] = None) -> str:
    robots = '<meta name="robots" content="noindex,follow">\n' if noindex else ""
    ld = ""
    if json_ld is not None:
        ld = f'<script type="application/ld+json">{_json_ld(json_ld)}</script>\n'
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
{robots}{site_verification.meta_tags()}<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231a4fd6'/%3E%3Ctext x='16' y='23' font-size='19' font-weight='700' fill='white' text-anchor='middle' font-family='sans-serif'%3EC%3C/text%3E%3C/svg%3E">
<link rel="canonical" href="{_esc(canonical)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="CLNS">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{_esc(canonical)}">
<meta property="og:image" content="{_esc(base)}/static/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(description)}">
{ld}<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <a class="brand" href="/">
    <span class="mark" aria-hidden="true">C</span>
    <span><span class="brand-name">CLNS</span>
    <p class="brand-sub">PRODUCT COMPLIANCE INTELLIGENCE · KOREA</p></span>
  </a>
  <span class="pill ghost">무료 베타 · 결제 없음 · 회원가입 없음</span>
</header>
"""


def _footer(base: str) -> str:
    meta = catalog_meta()
    return f"""<footer>
    <p><strong>CLNS</strong> — Clearance, simplified. 한국 수입 규제 사전 점검(무료 베타).</p>
    <p><strong>면책:</strong> 본 페이지는 사전 참고용이며 법적 효력이 없습니다. 최종 법적 판단과 통관·인증 가능 여부는 관세사, 관세청, 국가기술표준원·인증기관, 식품의약품안전처 등 소관 기관의 확인이 필요합니다. 본 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않습니다.</p>
    <p><strong>데이터:</strong> 세관장확인 요건은 관세청 세관장확인대상물품(15101589) 실조회 결과를 기관별로 정규화한 것이며, 근거 조항은 법제처 국가법령정보센터 기준입니다. 원본 응답을 그대로 중계하지 않고 결합·정규화한 판정만 제공합니다. 조회 실패·개정 지연 시 조회 시점을 밝힙니다.</p>
    <p><strong>개인정보:</strong> 이름·연락처·이메일을 받지 않으며, 접속 IP·User-Agent·쿠키를 저장하지 않습니다. 일별 호출 수만 익명으로 집계합니다.</p>
    <p>© 2026 CLNS · 익명 운영 무료 베타 · 카탈로그 v{_esc(meta['version'])} · 최종 확인 {_esc(meta['verified_on'])} · <a href="/p/">품목 전체 보기</a> · <a href="/guides/">질문형 가이드</a> · <a href="/llms.txt">llms.txt</a> · <a href="/sitemap.xml">sitemap</a></p>
  </footer>
</div>
</body>
</html>
"""


def _requirements_table(item: Dict[str, Any]) -> str:
    rows = _requirement_rows(item)
    checked = _esc(item.get("hs_checked_at") or catalog_meta()["hs_checked_at"])
    if not rows:
        return (
            '<div class="zero"><strong>세관장확인 요건 조회 결과 0건</strong><br>'
            f'{_esc(ZERO_NOTE_KO)}<br>'
            f'<span class="pill ghost">조회 시점 {checked}</span></div>'
        )
    body = []
    for row in rows:
        agencies = row.get("agencies") or []
        agency = ", ".join(str(a) for a in agencies[:2])
        if len(agencies) > 2:
            agency += f" 외 {len(agencies) - 2}곳"
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('requirement_document') or '-')}</td>"
            f"<td>{_esc(row.get('requirement_law') or '-')}</td>"
            f"<td>{_esc(agency or '-')}</td>"
            f"<td>{_esc(row.get('timing') or '-')}</td>"
            f"<td>{_esc(row.get('applies_from') or '-')}</td>"
            "</tr>"
        )
    return (
        '<div class="tablewrap"><table><thead><tr><th>요건확인서</th><th>근거 법령</th><th>확인 기관</th>'
        "<th>확인 시점</th><th>적용 시작</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
        + f'<p class="brand-sub" style="margin-top:8px">관세청 실조회 시점 {checked} · 기관별 중복 응답은 하나로 묶었습니다. '
        + "요건은 고시 개정으로 바뀌므로 통관 전 관세청 고시 원문과 실시간 조회를 다시 확인하세요.</p>"
    )


def _traps_block(item: Dict[str, Any]) -> str:
    traps = _item_traps(item)
    if not traps:
        return ""
    out = []
    for trap in traps:
        out.append(
            '<div class="trap">'
            f"<strong>{_esc(trap.id)} · {_esc(trap.title)}</strong>"
            f"<p>{_esc(trap.issue_ko)}</p>"
            f"<p><b>흔한 오답:</b> {_esc(_clamp(trap.common_ai_wrong, MAX_TRAP_ANSWER))}</p>"
            f"<p><b>확인해야 할 점:</b> {_esc(_clamp(trap.correct_answer, MAX_TRAP_ANSWER))}</p>"
            "</div>"
        )
    return "".join(out)


def _basis_block(item: Dict[str, Any]) -> str:
    basis = _legal_basis(item)
    if not basis:
        return ""
    out = []
    for entry in basis:
        quote = _clamp(entry.get("quote") or "", MAX_QUOTE)
        url = entry.get("url") or ""
        link = (f'<a href="{_esc(url)}" rel="noopener nofollow" target="_blank">원문</a>'
                if url.startswith("http") else "")
        out.append(
            "<h3>"
            f"{_esc(entry.get('law') or '')} {_esc(entry.get('article') or '')}"
            f' <span class="pill ghost">시행 {_esc(entry.get("effective_date") or "-")}</span></h3>'
            f'<p style="font-size:14px; margin:4px 0">{_esc(quote)} {link}</p>'
        )
    return "".join(out)


# 규제 태그 → 소관 기관(페이지의 '규제 축' 표에 쓰는 공통 어휘).
TAG_AUTHORITY_KO: Dict[str, str] = {
    "FOOD_IMPORT_DECLARATION": "식품의약품안전처",
    "FOOD_BUSINESS_REGISTRATION": "식품의약품안전처",
    "FOOD_ADDITIVE": "식품의약품안전처",
    "HEALTH_FUNCTIONAL_FOOD": "식품의약품안전처",
    "FOOD_CONTACT_MATERIAL": "식품의약품안전처",
    "KOREAN_LABELING": "식품의약품안전처·관세청",
    "COSMETICS_RESPONSIBLE_SALES": "식품의약품안전처",
    "CHILDREN_PRODUCT_SAFETY": "산업통상부 국가기술표준원",
    "ELECTRICAL_KC": "산업통상부 국가기술표준원",
    "BATTERY_SAFETY": "산업통상부 국가기술표준원",
    "RF_CONFORMITY": "과학기술정보통신부 국립전파연구원",
    "HOUSEHOLD_CHEMICAL": "환경부·산업통상부",
    "CUSTOMS_CHECKPOINT": "관세청",
    "CUSTOMS_LOW_VALUE": "관세청",
    "CUSTOMS_PERSONAL_ID": "관세청",
    "DRUG_IMPORT": "식품의약품안전처",
    "TOBACCO_VAPE": "보건복지부·기획재정부",
    "ORIGIN_FTA": "관세청",
    "ORIGIN_MARKING": "관세청·산업통상부",
    "IP_PARALLEL_IMPORT": "관세청·특허청",
    "MEDICAL_DEVICE_IMPORT": "식품의약품안전처",
    "HYGIENE_PRODUCT_IMPORT": "식품의약품안전처",
}

# 태그 → 이 페이지에서 "어떤 툴로 확인하는지"(MCP 연결 안내를 일관되게 만든다).
TAG_TOOL: Dict[str, str] = {
    "CUSTOMS_CHECKPOINT": "lookup_hs_requirements",
    "CUSTOMS_LOW_VALUE": "lookup_hs_requirements",
    "CUSTOMS_PERSONAL_ID": "lookup_hs_requirements",
    "ELECTRICAL_KC": "check_kc_certification",
    "BATTERY_SAFETY": "check_kc_certification",
    "CHILDREN_PRODUCT_SAFETY": "check_kc_certification",
    "RF_CONFORMITY": "check_kc_certification",
    "FOOD_IMPORT_DECLARATION": "check_food_cosmetics",
    "FOOD_BUSINESS_REGISTRATION": "check_food_cosmetics",
    "FOOD_ADDITIVE": "check_food_cosmetics",
    "HEALTH_FUNCTIONAL_FOOD": "check_food_cosmetics",
    "FOOD_CONTACT_MATERIAL": "check_food_cosmetics",
    "COSMETICS_RESPONSIBLE_SALES": "check_food_cosmetics",
    "MEDICAL_DEVICE_IMPORT": "assess_import_case",
    "HYGIENE_PRODUCT_IMPORT": "assess_import_case",
    "KOREAN_LABELING": "assess_import_case",
    "HOUSEHOLD_CHEMICAL": "assess_import_case",
    "DRUG_IMPORT": "assess_import_case",
    "TOBACCO_VAPE": "assess_import_case",
    "ORIGIN_FTA": "assess_import_case",
    "ORIGIN_MARKING": "assess_import_case",
    "IP_PARALLEL_IMPORT": "assess_import_case",
}

TOOL_ONE_LINE_KO: Dict[str, str] = {
    "assess_import_case": "품목·상황을 자연어로 넣어 쟁점·근거·면책을 한 번에 판정",
    "lookup_hs_requirements": "HS 10자리로 세관장확인 요건·기관·확인시점 조회",
    "check_kc_certification": "전기용품 KC·전지·전파 적합성평가 중 무엇이 걸리는지 판정",
    "check_food_cosmetics": "식품·건강기능식품·화장품·기구용기 요건 판정(위생용품은 assess_import_case)",
    "lookup_recall": "브랜드·모델·품목군으로 국내 리콜 이력 조회",
    "get_legal_basis": "근거 법령 조문 요지·시행일·원문 URL 조회",
    "explain_trap": "이 페이지의 함정 케이스 해설(오답·정답·근거)",
}


def _item_tags(item: Dict[str, Any]) -> List[str]:
    """항목에 연결된 함정 케이스들의 규제 태그를 순서 유지·중복 제거로 뽑는다."""
    out: List[str] = []
    for trap in _item_traps(item):
        for tag in CASE_REGULATION_TAGS.get(trap.id, []):
            if tag not in out:
                out.append(tag)
    return out


def _axes_block(item: Dict[str, Any]) -> str:
    """'이 품목에 걸리는 규제 축' — 태그·소관 기관·확인 카드·조회 툴을 한 표로 보여준다."""
    tags = _item_tags(item)
    if not tags:
        return ""
    traps = {trap.id: trap for trap in _item_traps(item)}
    rows = []
    for tag in tags:
        meta = REGULATION_TAGS.get(tag) or {}
        cards = [trap_id for trap_id, trap in traps.items()
                 if tag in CASE_REGULATION_TAGS.get(trap_id, [])]
        rows.append(
            "<tr>"
            f"<td>{_esc(meta.get('label_ko') or tag)}</td>"
            f"<td>{_esc(TAG_AUTHORITY_KO.get(tag) or '소관 기관 확인')}</td>"
            f"<td>{_esc(', '.join(cards) or '-')}</td>"
            f"<td><code>{_esc(TAG_TOOL.get(tag, 'assess_import_case'))}</code></td>"
            "</tr>"
        )
    return (
        '<div class="tablewrap"><table><thead><tr><th>규제 축</th><th>소관 기관</th>'
        "<th>확인 카드</th><th>MCP 툴</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        + '<p class="brand-sub" style="margin-top:8px">축은 품목 유형·표시 문구에 따라 갈립니다. '
        "아래 '핵심 함정'에서 어떤 말 한마디로 결론이 바뀌는지 먼저 보세요.</p>"
    )


def _classification_block(item: Dict[str, Any]) -> str:
    """HS 요건 표와 법령상 품목 분류는 다르다는 것을 모든 페이지에 같은 문장으로 밝힌다."""
    tags = set(_item_tags(item))
    extra = ""
    if tags & {"MEDICAL_DEVICE_IMPORT", "HYGIENE_PRODUCT_IMPORT"}:
        extra = (
            " <strong>의료기기·위생용품·의약외품 경계:</strong> 의료기기는 의료기기법(수입업 허가·품목 허가), "
            "위생용품은 위생용품 관리법(수입업 신고·수입신고·검사·기준규격), 생리대·탐폰·생리컵과 "
            "KF·비말차단·수술용 마스크는 의약외품(약사법)으로 법이 다릅니다."
        )
    return (
        '<div class="card"><p style="margin-top:0"><strong>HS 요건과 법령상 품목 분류는 다릅니다.</strong> '
        "위 세관장확인 표는 <strong>HS 10자리 단위</strong>의 요건이라, 같은 HS에 묶인 다른 품목의 요건이 "
        "함께 나올 수 있습니다. 반대로 표에 없다고 그 법의 적용이 없는 것도 아닙니다. "
        "품목이 그 법의 정의에 들어가는지는 품목명·용도·표시로 따로 판단해야 합니다."
        + extra
        + "</p></div>"
    )


def _mcp_block(item: Dict[str, Any], base: str) -> str:
    """MCP·API 연결 안내 — 이 품목에 실제로 쓸 툴만 골라 보여준다(모든 페이지 공통 형식)."""
    tags = _item_tags(item)
    tools = ["assess_import_case"]
    for tag in tags:
        tool = TAG_TOOL.get(tag)
        if tool and tool not in tools:
            tools.append(tool)
    for extra in ("lookup_recall", "get_legal_basis"):
        if extra not in tools:
            tools.append(extra)
    items_html = "".join(
        f"<li><code>{_esc(tool)}</code> — {_esc(TOOL_ONE_LINE_KO.get(tool, ''))}</li>"
        for tool in tools
    )
    example = json.dumps({"query": f"{item['name_ko']} 수입 판매",
                          "facts": {"hs_code": item["hs_code"], "purpose": "resale"}},
                         ensure_ascii=False)
    return (
        '<h2>API·MCP로 이 품목 자동 조회</h2>'
        '<div class="card">'
        f'<ul class="clean">{items_html}</ul>'
        '<p style="margin-bottom:4px"><strong>HTTP</strong> <code>POST /v1/tools/assess_import_case</code></p>'
        f'<p style="font-size:13.5px; color:var(--ink-soft); margin-top:0"><code>{_esc(_clamp(example, 220))}</code></p>'
        '<p style="margin-bottom:0"><strong>MCP</strong> <code>POST /mcp</code> · 매니페스트 '
        f'<a href="{_esc(base)}/v1/mcp">/v1/mcp</a> · 로컬 실행 '
        '<code>python -m import_compliance.mcp_stdio</code></p>'
        '<p class="brand-sub" style="margin-bottom:0">응답에는 항상 근거 조항·시행일·원문 URL과 국·영문 면책이 함께 옵니다. '
        "원본 API 응답은 재전송하지 않고 결합·정규화한 판정만 돌려줍니다.</p>"
        "</div>"
    )


def _channel_block() -> str:
    """모든 페이지 공통: 직구·목록통관 축은 품목별 카드와 별도로 항상 같은 문장으로 안내한다."""
    traps = _trap_map()
    out = []
    for trap_id in ("TRAP-12", "TRAP-13"):
        trap = traps.get(trap_id)
        if trap is None:
            continue
        out.append(
            f"<li><strong>{_esc(trap.id)} · {_esc(trap.title)}</strong> — "
            f"{_esc(_clamp(trap.correct_answer, MAX_TRAP_ANSWER))}</li>"
        )
    if not out:
        return ""
    return (
        '<h2>해외직구·목록통관으로 들여올 때</h2>'
        f'<div class="card"><ul class="clean">{"".join(out)}</ul>'
        '<p class="brand-sub" style="margin-bottom:0">판매 목적·금액·품목에 따라 목록통관 배제와 개인통관고유부호 요구가 달라집니다. '
        "금액이 낮아도 면세·목록통관이 자동으로 되지 않습니다.</p></div>"
    )


def _related_block(item: Dict[str, Any]) -> str:
    same = [other for other in items()
            if other["slug"] != item["slug"] and other.get("category") == item.get("category")]
    if not same:
        return ""
    links = "".join(
        f'<a href="{_esc(page_path(other["slug"]))}">{_esc(other["name_ko"])}'
        f'<span>HS {_esc(other["hs_code"])} · {_esc(other.get("category") or "")}</span></a>'
        for other in same[:6]
    )
    return f'<h2>같은 분류의 다른 품목</h2><div class="grid">{links}</div>'


def _guides_block(item: Dict[str, Any]) -> str:
    """이 품목의 규제 축과 겹치는 질문형 가이드로 내부 링크를 건다(색인·발견성)."""
    try:
        from . import guides
    except Exception:  # noqa: BLE001 - 가이드 카탈로그 문제가 품목 페이지를 막지 않게
        return ""
    tags = set(_item_tags(item))
    if not tags:
        return ""
    try:
        matches = [guide for guide in guides.items()
                   if set(guide.get("tags") or []) & tags][:4]
    except Exception:  # noqa: BLE001
        return ""
    if not matches:
        return ""
    links = "".join(
        f'<a href="{_esc("/guides/" + guide["slug"])}">{_esc(guide["question_ko"])}'
        f'<span>{_esc(guide.get("category") or "")}</span></a>'
        for guide in matches
    )
    return f'<h2>이 품목과 함께 보는 질문</h2><div class="grid">{links}</div>'


def _requirement_summary(item: Dict[str, Any]) -> str:
    rows = _requirement_rows(item)
    if not rows:
        return "0건 조회 (아래 '0건은 요건 없음이 아닙니다' 설명 참고)"
    return f"{len(rows)}종 확인 (관세청 실조회)"


def render_item(slug: str, base: Optional[str] = None) -> Optional[str]:
    """`/p/{slug}` HTML. 없는 슬러그면 None(서버가 404 처리)."""
    item = get_item(slug)
    if item is None:
        return None
    root = static_files.base_url(base)
    name = item["name_ko"]
    hs_code = item["hs_code"]
    canonical = f"{root}{page_path(item['slug'])}"
    noindex = not is_indexable(item)
    meta = catalog_meta()
    title = f"{name} 수입 요건 — 세관장확인·KC·전파 확인 | CLNS"
    description = _clamp(
        f"{name}(HS {hs_code}) 수입 시 세관장확인 요건, KC·전파·식약처 확인 항목, "
        f"자주 틀리는 함정과 근거 법령을 한 화면에 정리했습니다. 무료 사전 점검.", 180)

    key_points = "".join(f"<li>{_esc(point)}</li>" for point in item.get("key_points_ko") or [])
    requirements = "".join(f"<li>{_esc(req)}</li>" for req in item.get("requirements_ko") or [])
    certifications = "".join(f"<li>{_esc(cert)}</li>" for cert in item.get("certifications_ko") or [])
    keywords = ", ".join(str(word) for word in item.get("keywords") or [])
    search_query = f"{name} 수입 요건"

    json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": f"{name} 수입 요건 — 세관장확인·인증 확인 항목",
                "inLanguage": "ko-KR",
                "url": canonical,
                "dateModified": meta["verified_on"],
                "author": {"@type": "Organization", "name": "CLNS"},
                "publisher": {"@type": "Organization", "name": "CLNS", "url": root},
                "about": {"@type": "Product", "name": name, "description": item["summary_ko"]},
                "isAccessibleForFree": True,
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f"{name} 수입 시 세관장확인 요건이 있나요?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                f"HS {hs_code} 기준으로 관세청 세관장확인대상물품 조회 결과 "
                                f"{len(_requirement_rows(item))}종의 요건확인서가 확인됩니다. "
                                "0건은 '요건 없음'이 아니라 '조회되지 않음'이므로 HS 10자리를 다시 확인해야 합니다."
                                if _requirement_rows(item) else
                                f"HS {hs_code} 기준 조회에서 세관장확인 요건이 0건으로 나왔습니다. "
                                "0건은 '요건 없음'이 아니라 '조회되지 않음'이며, HS 10자리·수입 구분을 다시 확인해야 합니다."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": f"{name}에 어떤 인증이 필요한가요?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": " / ".join(item.get("certifications_ko") or []) or "확인 항목 없음",
                        },
                    },
                ],
            },
        ],
    }

    return "".join([
        _head(title, description, canonical, root, noindex, json_ld),
        f"""<nav class="crumb"><a href="/">CLNS 홈</a> › <a href="/p/">품목별 수입 요건</a> › {_esc(name)}</nav>
<main>
<h1>{_esc(name)} 수입 요건</h1>
<p class="lede">{_esc(item["summary_ko"])}</p>
<div class="pills">
  <span class="pill">{_esc(item.get("category") or "")}</span>
  <span class="pill ghost">대표 HS {_esc(hs_code)}</span>
  <span class="pill ghost">최종 확인 {_esc(meta["verified_on"])}</span>
</div>
<div class="cta">
  <a href="/?q={_esc(name)}">실시간으로 내 품목 조회하기</a>
  <a class="ghost" href="/#hs">HS 10자리로 요건 조회</a>
</div>

<h2>대표 HS 코드</h2>
<div class="card">
  <dl class="kv">
    <dt>HS 10자리</dt><dd><code>{_esc(hs_code)}</code></dd>
    <dt>품목분류</dt><dd>{_esc(item.get("hs_name_ko") or "-")}</dd>
    <dt>요건 조회</dt><dd>{_esc(_requirement_summary(item))}</dd>
    <dt>조회 시점</dt><dd>{_esc(item.get("hs_checked_at") or meta["hs_checked_at"])}</dd>
  </dl>
  <p class="brand-sub" style="margin-top:10px">HS 6자리와 10자리는 요건 판정이 갈립니다. 같은 6자리에서도 10자리에 따라 0건/여러 건이 나뉘므로, 실제 수입 신고 전 품목분류(HS) 확정이 먼저입니다.</p>
</div>

<h2>세관장확인 요건 (관세청)</h2>
<div class="card">{_requirements_table(item)}</div>

<h2>이 품목에 걸리는 규제 축</h2>
<div class="card">{_axes_block(item)}</div>

{_classification_block(item)}

<h2>인증·허가 요건</h2>
<div class="card"><ul class="clean">{certifications or "<li>확인 항목 없음</li>"}</ul></div>

<h2>수입 전 확인할 항목</h2>
<div class="card"><ul class="clean">{requirements or "<li>확인 항목 없음</li>"}</ul></div>

<h2>핵심 함정 — 이렇게 답하면 틀립니다</h2>
{_traps_block(item) or '<div class="card">이 품목에 연결된 함정 케이스가 없습니다. HS 요건 표와 인증 항목을 기준으로 확인하세요.</div>'}

<h2>법적 근거</h2>
<div class="card">{_basis_block(item) or "<p>근거 조항은 실시간 조회 응답의 evidence 로 제공됩니다.</p>"}</div>

{_channel_block()}

<h2>이 페이지에서 다룬 검색어</h2>
<p style="font-size:14px; color:var(--ink-soft)">{_esc(keywords)}</p>

{_related_block(item)}

{_guides_block(item)}

{_mcp_block(item, root)}

<h2>정확히 확인하려면</h2>
<div class="card">
  <p style="margin-top:0">이 페이지는 공개된 요건을 정리한 <strong>사전 점검</strong>입니다. 실제 수입 건의 판정은 품목명·HS·원산지·수입 목적을 넣어 실시간 조회로 확인하세요.</p>
  <div class="cta">
    <a href="/?q={_esc(search_query)}">내 품목으로 실시간 조회</a>
    <a class="ghost" href="/p/">품목 전체 {len(items())}개 보기</a>
    <a class="ghost" href="/v1/mcp">MCP·API로 붙이기</a>
  </div>
</div>
</main>
""",
        _footer(root),
    ])


def render_index(base: Optional[str] = None) -> str:
    """`/p/` 인덱스 — 크롤러와 사람이 30여 개 품목 페이지로 들어오는 입구."""
    root = static_files.base_url(base)
    meta = catalog_meta()
    canonical = f"{root}{index_path()}"
    title = "품목별 수입 요건 무료 체크 — 세관장확인·KC·전파 | CLNS"
    description = _clamp(
        "무선 미니 선풍기·보조배터리·오메가3·선크림·반려동물 사료 등 수입 수요가 많은 "
        f"{meta['count']}개 품목의 세관장확인 요건, KC·전파·식약처 확인 항목, 자주 틀리는 함정을 정리했습니다.", 180)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in items():
        grouped.setdefault(item.get("category") or "기타", []).append(item)

    sections = []
    for category, group in grouped.items():
        links = "".join(
            f'<a href="{_esc(page_path(item["slug"]))}">{_esc(item["name_ko"])}'
            f'<span>HS {_esc(item["hs_code"])} · 요건 {len(_requirement_rows(item))}종</span></a>'
            for item in group
        )
        sections.append(f"<h2>{_esc(category)}</h2><div class=\"grid\">{links}</div>")

    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "품목별 수입 요건 무료 체크",
        "url": canonical,
        "inLanguage": "ko-KR",
        "isPartOf": {"@type": "WebSite", "name": "CLNS", "url": root},
        "dateModified": meta["verified_on"],
    }

    return "".join([
        _head(title, description, canonical, root, False, json_ld),
        f"""<nav class="crumb"><a href="/">CLNS 홈</a> › 품목별 수입 요건</nav>
<main>
<h1>품목별 수입 요건 무료 체크</h1>
<p class="lede">한국으로 수입해 판매할 때 자주 막히는 {meta['count']}개 품목을 골라, 세관장확인 요건·KC 인증·전파 적합성평가·식약처 요건과 <strong>흔히 틀리는 함정</strong>을 한 페이지씩 정리했습니다. JS 없이 읽히는 정적 문서이며, 모든 페이지에 근거 법령과 면책이 함께 있습니다.</p>
<div class="pills">
  <span class="pill">{meta['count']}개 품목</span>
  <span class="pill ghost">관세청 실조회 {_esc(meta['verified_on'])}</span>
  <span class="pill ghost">무료 · 회원가입 없음</span>
</div>
<div class="cta">
  <a href="/">실시간 품목 조회</a>
  <a class="ghost" href="/v1/mcp">MCP·API</a>
</div>
{''.join(sections)}
<h2>읽는 법</h2>
<div class="card">
  <ul class="clean">
    <li>요건 표는 <strong>관세청 세관장확인대상물품</strong>을 HS 10자리로 실조회해 기관별로 묶은 것입니다. 고시 개정으로 바뀔 수 있습니다.</li>
    <li>조회 결과 <strong>0건은 '요건 없음'이 아니라 '조회되지 않음'</strong>입니다. HS 10자리·수입/수출 구분을 다시 확인하세요.</li>
    <li>KC·전파·식약처 요건은 제품 유형·표시 문구에 따라 갈립니다. 페이지의 '핵심 함정'을 먼저 읽는 편이 빠릅니다.</li>
    <li>이 페이지는 사전 참고용이며, 확정 판정은 소관 기관 확인이 필요합니다.</li>
  </ul>
</div>
</main>
""",
        _footer(root),
    ])
