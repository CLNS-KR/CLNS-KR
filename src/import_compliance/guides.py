"""질문형·규제별 가이드 페이지(`/guides/{slug}`) — AI 인용·검색 유입용 정적 렌더러.

무엇이 다른가
-------------
`/p/{slug}` 가 "품목"으로 들어오는 사람을 위한 페이지라면, 이 모듈은 **실제로 검색창과
AI 챗봇에 입력되는 질문 문장**으로 들어오는 유입을 받는다. 제목·H1 이 질문이고, 첫
문단이 그 질문에 대한 답이며, `FAQPage` 구조화 데이터가 같은 질문·답변을 그대로 담는다.

원칙(pSEO 와 동일)
------------------
1. **JS 없이 읽힌다** — 본문 전체를 서버에서 렌더한다(실행 스크립트 0줄).
2. **익명** — 저작·운영 주체는 `CLNS` 하나뿐이다. 개인 이름·연락처를 넣지 않는다.
3. **단정 금지** — "대상입니다·면제됩니다·필요 없습니다" 대신 "확인해야 할 항목"으로 쓴다.
4. **근거는 검증된 조문만** — 답변에 인용하는 법령 조문은 이 저장소에서 이미 법제처
   현행본으로 검증한 문안만 쓴다(`traps_20.json`, `advertising.py`, `labeling.py`,
   `drugs.py`). 카탈로그는 조문을 직접 들고 있지 않고 **키로 참조**하며, 로딩 시
   모든 키가 실제로 해석되는지 검증한다(해석 안 되면 서버가 뜨지 않는다).
5. **얇은 페이지는 색인하지 않는다** — 답변이나 체크포인트가 부족하면 `noindex`.

데이터
------
`src/guides_items.json` — 질문 65종(기본 50종 + 롱테일 15종, 카탈로그 1.2.0). 문안은 위
모듈들의 검증된 사실(6병 기준, $150/$200, KC 유형 구분, 광고 금지 표현 16종 등)을 근거로
작성했고, `cases` 는 함정 코퍼스(`traps_20.json`)의 케이스 ID, `basis_keys` 는 이 저장소에서
검증한 조문 상수 키다. 새 질문을 넣을 때도 둘 중 하나는 반드시 실제로 해석되어야 한다
(근거 없는 페이지는 서버가 뜨지 않는다).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from . import pseo, static_files
from .corpus import load_corpus
from .models import Trap
from .standards import REGULATION_TAGS

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "guides_items.json")

# 얇은 페이지 판정: 답변 길이·체크포인트 수·근거 수.
THIN_MIN_ANSWER = 80
THIN_MIN_CHECKPOINTS = 3
MAX_LIST_ITEMS = 8

REQUIRED_FIELDS = ("question_ko", "title_ko", "category", "summary_ko", "answer_ko",
                   "checkpoints_ko", "tags", "tool")


class GuideCatalogError(RuntimeError):
    pass


# --- 근거 조문 레지스트리 ------------------------------------------------------
# 카탈로그는 조문 문안을 직접 갖지 않는다. 이 저장소에서 법제처 현행본으로 검증한
# 상수만 키로 참조한다(오탈자·구법 인용이 페이지에 새어 나가지 않게).
def _basis_registry() -> Dict[str, Dict[str, Any]]:
    from . import advertising, ecommerce, drugs, feed, labeling

    registry: Dict[str, Dict[str, Any]] = {}
    for module_name, module in (("advertising", advertising), ("labeling", labeling),
                                ("ecommerce", ecommerce), ("feed", feed)):
        for name in dir(module):
            if not name.startswith("B_"):
                continue
            value = getattr(module, name)
            if isinstance(value, dict) and value.get("law") and value.get("article"):
                registry[f"{module_name}:{name}"] = dict(value)
    for list_name in ("BASIS_NARCOTIC", "BASIS_PRECURSOR", "BASIS_SELF_USE"):
        for index, row in enumerate(getattr(drugs, list_name)):
            registry[f"drugs:{list_name}:{index}"] = dict(row)
    return registry


@lru_cache(maxsize=1)
def basis_registry() -> Dict[str, Dict[str, Any]]:
    return _basis_registry()


@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    """가이드 카탈로그를 읽고(슬러그·필수 필드·참조 무결성) 검증한다."""
    with open(CATALOG_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)
    items = raw.get("items") or []
    if not isinstance(items, list) or not items:
        raise GuideCatalogError("empty guide catalog")
    corpus_ids = set()
    try:
        corpus_ids = {trap.id for trap in load_corpus().traps}
    except (OSError, ValueError):
        corpus_ids = set()
    registry = basis_registry()
    seen = set()
    for item in items:
        slug = str(item.get("slug") or "")
        if not slug or not slug.replace("-", "").isalnum():
            raise GuideCatalogError(f"invalid slug: {slug!r}")
        if slug in seen:
            raise GuideCatalogError(f"duplicate slug: {slug}")
        seen.add(slug)
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                raise GuideCatalogError(f"{slug}: missing {field}")
        if len(item.get("checkpoints_ko") or []) < THIN_MIN_CHECKPOINTS:
            raise GuideCatalogError(f"{slug}: too few checkpoints")
        for tag in item.get("tags") or []:
            if tag not in REGULATION_TAGS:
                raise GuideCatalogError(f"{slug}: unknown regulation tag {tag}")
        for key in item.get("basis_keys") or []:
            if key not in registry:
                raise GuideCatalogError(f"{slug}: unknown basis key {key}")
        for case_id in item.get("cases") or []:
            if corpus_ids and case_id not in corpus_ids:
                raise GuideCatalogError(f"{slug}: unknown case {case_id}")
    return raw


def items() -> List[Dict[str, Any]]:
    return list(load_catalog()["items"])


@lru_cache(maxsize=1)
def item_index() -> Dict[str, Dict[str, Any]]:
    return {item["slug"]: item for item in load_catalog()["items"]}


def get_item(slug: str) -> Optional[Dict[str, Any]]:
    return item_index().get(str(slug or "").strip())


def slugs() -> List[str]:
    return [item["slug"] for item in load_catalog()["items"]]


def catalog_meta() -> Dict[str, Any]:
    raw = load_catalog()
    return {
        "version": raw.get("catalog_version", ""),
        "verified_on": raw.get("verified_on", ""),
        "count": len(raw.get("items") or []),
    }


def page_path(slug: str) -> str:
    return f"/guides/{slug}"


def index_path() -> str:
    return "/guides/"


def is_indexable(item: Dict[str, Any]) -> bool:
    """답변·체크포인트·근거가 충분한 페이지만 색인 대상으로 둔다."""
    if len(str(item.get("answer_ko") or "")) < THIN_MIN_ANSWER:
        return False
    if len(item.get("checkpoints_ko") or []) < THIN_MIN_CHECKPOINTS:
        return False
    return bool(item.get("cases") or item.get("basis_keys"))


def indexable_paths() -> List[str]:
    return [index_path()] + [page_path(slug) for slug, item in item_index().items()
                             if is_indexable(item)]


# --- 근거 조문 ----------------------------------------------------------------
def _trap_map() -> Dict[str, Trap]:
    try:
        return {trap.id: trap for trap in load_corpus().traps}
    except (OSError, ValueError):
        return {}


def legal_basis(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """케이스 근거 + 카탈로그가 참조한 검증 조문을 중복 없이 순서 유지로 모은다."""
    out: List[Dict[str, Any]] = []
    seen: set = set()
    registry = basis_registry()
    for key in item.get("basis_keys") or []:
        row = dict(registry.get(key) or {})
        if not row:
            continue
        row["ref"] = key
        dedupe = (row.get("law"), row.get("article"))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        out.append(row)
    traps = _trap_map()
    for case_id in item.get("cases") or []:
        trap = traps.get(str(case_id))
        if trap is None:
            continue
        for basis in trap.legal_basis:
            dedupe = (basis.law, basis.article)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            row = basis.to_dict()
            row["case_id"] = trap.id
            out.append(row)
    return out


def _case_traps(item: Dict[str, Any]) -> List[Trap]:
    traps = _trap_map()
    out: List[Trap] = []
    for case_id in item.get("cases") or []:
        trap = traps.get(str(case_id))
        if trap is not None:
            out.append(trap)
    return out


# 0.2.0 이후 추가된 규제 태그의 소관 기관·확인 툴(pSEO 표에 없는 것만 여기서 채운다).
AUTHORITY_KO: Dict[str, str] = {
    "FOOD_AD_CLAIM": "식품의약품안전처",
    "HFF_CLAIM_MISREPRESENTATION": "식품의약품안전처",
    "COSMETICS_AD_CLAIM": "식품의약품안전처",
    "COSMETICS_FUNCTIONAL_CLAIM": "식품의약품안전처",
    "NARCOTIC_IMPORT_BAN": "식품의약품안전처·관세청",
    "DRUG_INGREDIENT_RESTRICTION": "식품의약품안전처·관세청",
    "MFDS_DISPOSITION": "식품의약품안전처",
    "PRICE_AD_CLAIM": "공정거래위원회",
    "REVIEW_MARKETING": "공정거래위원회",
    "WITHDRAWAL_REFUND": "공정거래위원회",
    "DELIVERY_FULFILLMENT": "공정거래위원회",
    "CERTIFICATION_AWARD": "공정거래위원회",
    "RANKING_CLAIM": "공정거래위원회",
    "SUBSCRIPTION_AUTO_RENEWAL": "공정거래위원회",
    "DARK_PATTERN_UI": "공정거래위원회",
    "SELLER_DISCLOSURE": "공정거래위원회",
    "FEED_IMPORT_DECLARATION": "농림축산식품부·관세청",
    "FEED_INGREDIENT_REGISTRATION": "농림축산식품부·시·도지사",
    "FEED_BUSINESS_REGISTRATION": "농림축산식품부·시·도지사",
    "FEED_LABELING": "농림축산식품부",
    "FEED_HAZARD_STANDARD": "농림축산식품부",
    "FEED_SELF_QUALITY_INSPECTION": "농림축산식품부",
    "ANIMAL_PRODUCT_QUARANTINE": "농림축산검역본부",
    "PET_FOOD_QUARANTINE": "농림축산검역본부",
}

TOOL_BY_TAG: Dict[str, str] = {
    "FOOD_AD_CLAIM": "check_ad_labeling",
    "HFF_CLAIM_MISREPRESENTATION": "check_ad_labeling",
    "COSMETICS_AD_CLAIM": "check_ad_labeling",
    "COSMETICS_FUNCTIONAL_CLAIM": "check_ad_labeling",
    "NARCOTIC_IMPORT_BAN": "check_drug_import",
    "DRUG_INGREDIENT_RESTRICTION": "check_drug_import",
    "MFDS_DISPOSITION": "lookup_mfds_disposition",
    "PRICE_AD_CLAIM": "check_ecommerce_compliance",
    "REVIEW_MARKETING": "check_ecommerce_compliance",
    "WITHDRAWAL_REFUND": "check_ecommerce_compliance",
    "DELIVERY_FULFILLMENT": "check_ecommerce_compliance",
    "CERTIFICATION_AWARD": "check_ecommerce_compliance",
    "RANKING_CLAIM": "check_ecommerce_compliance",
    "SUBSCRIPTION_AUTO_RENEWAL": "check_ecommerce_compliance",
    "DARK_PATTERN_UI": "check_ecommerce_compliance",
    "SELLER_DISCLOSURE": "check_ecommerce_compliance",
    "FEED_IMPORT_DECLARATION": "check_feed_import",
    "FEED_INGREDIENT_REGISTRATION": "check_feed_import",
    "FEED_BUSINESS_REGISTRATION": "check_feed_import",
    "FEED_LABELING": "check_feed_import",
    "FEED_HAZARD_STANDARD": "check_feed_import",
    "FEED_SELF_QUALITY_INSPECTION": "check_feed_import",
    "ANIMAL_PRODUCT_QUARANTINE": "check_feed_import",
    "PET_FOOD_QUARANTINE": "check_feed_import",
}


def authority_for(tag: str) -> str:
    return (pseo.TAG_AUTHORITY_KO.get(tag) or AUTHORITY_KO.get(tag) or "소관 기관 확인")


def tool_for_tag(tag: str) -> str:
    return pseo.TAG_TOOL.get(tag) or TOOL_BY_TAG.get(tag) or "assess_import_case"


# --- 렌더링 -------------------------------------------------------------------
_esc = pseo._esc
_clamp = pseo._clamp


def _head(title: str, description: str, canonical: str, base: str, noindex: bool,
          json_ld: Optional[Dict[str, Any]] = None) -> str:
    return pseo._head(title, description, canonical, base, noindex, json_ld)


def _footer(base: str) -> str:
    """가이드 공통 푸터 — pSEO 와 같은 문구·같은 면책, 카탈로그 표기만 가이드 기준."""
    meta = catalog_meta()
    return f"""<footer>
    <p><strong>CLNS</strong> — Clearance, simplified. 한국 수입 규제 사전 점검(무료 베타).</p>
    <p><strong>면책:</strong> 본 페이지는 사전 참고용이며 법적 효력이 없습니다. 최종 법적 판단과 통관·인증 가능 여부는 관세사, 관세청, 국가기술표준원·인증기관, 식품의약품안전처 등 소관 기관의 확인이 필요합니다. 본 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않습니다.</p>
    <p><strong>데이터:</strong> 인용한 법령 조문은 법제처 국가법령정보센터 현행본으로 확인한 문안이며, 시행일과 원문 링크를 함께 표시합니다. 개정으로 내용이 바뀔 수 있으니 통관·판매 전 다시 확인해야 합니다. 원본 API 응답을 그대로 중계하지 않고 결합·정규화한 판정만 제공합니다.</p>
    <p><strong>개인정보:</strong> 이름·연락처·이메일을 받지 않으며, 접속 IP·User-Agent·쿠키를 저장하지 않습니다. 일별 호출 수만 익명으로 집계합니다.</p>
    <p>© 2026 CLNS · 익명 운영 무료 베타 · 가이드 v{_esc(meta['version'])} · 근거 확인 {_esc(meta['verified_on'])} · <a href="/p/">품목별 요건</a> · <a href="/privacy">개인정보</a> · <a href="/terms">약관</a> · <a href="/about">소개</a> · <a href="{_esc(base)}/llms.txt">llms.txt</a> · <a href="{_esc(base)}/sitemap.xml">sitemap</a></p>
  </footer>
</div>
</body>
</html>
"""


def _answer_block(item: Dict[str, Any]) -> str:
    return (
        '<div class="card">'
        '<p style="margin:0 0 6px"><strong>한 줄 답변</strong></p>'
        f'<p style="margin:0; font-size:16.5px">{_esc(item["answer_ko"])}</p>'
        "</div>"
    )


def _bullet_block(title: str, rows: List[str], *, anchor: str = "") -> str:
    if not rows:
        return ""
    lis = "".join(f"<li>{_esc(row)}</li>" for row in rows[:MAX_LIST_ITEMS])
    anchor_html = f' id="{_esc(anchor)}"' if anchor else ""
    return f"<h2{anchor_html}>{_esc(title)}</h2><div class=\"card\"><ul class=\"clean\">{lis}</ul></div>"


def _axes_block(item: Dict[str, Any]) -> str:
    rows = []
    for tag in item.get("tags") or []:
        meta = REGULATION_TAGS.get(tag) or {}
        tool = tool_for_tag(tag)
        rows.append(
            "<tr>"
            f"<td>{_esc(meta.get('label_ko') or tag)}</td>"
            f"<td>{_esc(authority_for(tag))}</td>"
            f"<td><code>{_esc(tool)}</code></td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<div class="tablewrap"><table><thead><tr><th>규제 축</th><th>소관 기관</th>'
        "<th>확인 툴</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        + '<p class="brand-sub" style="margin-top:8px">같은 품목이라도 용도·수량·표시 문구에 따라 '
        "걸리는 축이 달라집니다. 아래 '자주 틀리는 답'에서 결론이 갈리는 지점을 먼저 확인하세요.</p>"
    )


def _traps_block(item: Dict[str, Any]) -> str:
    traps = _case_traps(item)
    if not traps:
        return ('<div class="card"><p style="margin:0">이 질문에 연결된 함정 케이스가 없습니다. '
                "근거 조문과 체크포인트를 기준으로 확인하세요.</p></div>")
    out = []
    for trap in traps:
        out.append(
            '<div class="trap">'
            f"<strong>{_esc(trap.id)} · {_esc(trap.title)}</strong>"
            f"<p><b>흔한 오답:</b> {_esc(_clamp(trap.common_ai_wrong, pseo.MAX_TRAP_ANSWER))}</p>"
            f"<p><b>확인해야 할 점:</b> {_esc(_clamp(trap.correct_answer, pseo.MAX_TRAP_ANSWER))}</p>"
            "</div>"
        )
    return "".join(out)


def _basis_block(item: Dict[str, Any]) -> str:
    rows = legal_basis(item)
    if not rows:
        return '<div class="card"><p style="margin:0">근거 조문은 실시간 조회 응답의 evidence 로 제공됩니다.</p></div>'
    out = []
    for entry in rows:
        quote = _clamp(entry.get("quote") or "", pseo.MAX_QUOTE)
        url = entry.get("url") or ""
        link = (f'<a href="{_esc(url)}" rel="noopener nofollow" target="_blank">원문</a>'
                if str(url).startswith("http") else "")
        out.append(
            "<h3>"
            f"{_esc(entry.get('law') or '')} {_esc(entry.get('article') or '')}"
            f' <span class="pill ghost">시행 {_esc(entry.get("effective_date") or "-")}</span></h3>'
            f'<p style="font-size:14px; margin:4px 0">{_esc(quote)} {link}</p>'
        )
    return "".join(out)


def _tool_block(item: Dict[str, Any], base: str) -> str:
    """이 질문에 바로 쓸 수 있는 툴·MCP 연결 — 모든 페이지 같은 형식."""
    tool = str(item.get("tool") or "assess_import_case")
    example_args = item.get("tool_example") or {"query": item["question_ko"]}
    example = json.dumps(example_args, ensure_ascii=False)
    other = [name for name in ("assess_import_case", "check_ad_labeling", "lookup_hs_requirements",
                               "lookup_recall", "get_legal_basis") if name != tool][:3]
    extra = "".join(
        f"<li><code>{_esc(name)}</code> — {_esc(pseo.TOOL_ONE_LINE_KO.get(name, ''))}</li>"
        for name in other
    )
    return (
        "<h2>API·MCP로 같은 질문 자동 확인</h2>"
        '<div class="card">'
        f'<p style="margin-top:0"><strong>이 질문의 1차 툴</strong> '
        f"<code>{_esc(tool)}</code> — {_esc(pseo.TOOL_ONE_LINE_KO.get(tool, ''))}</p>"
        f'<p style="margin-bottom:4px"><strong>HTTP</strong> <code>POST /v1/tools/{_esc(tool)}</code></p>'
        f'<p style="font-size:13.5px; color:var(--ink-soft); margin-top:0"><code>{_esc(_clamp(example, 220))}</code></p>'
        f'<ul class="clean">{extra}</ul>'
        f'<p style="margin-bottom:0"><strong>MCP</strong> <code>POST /mcp</code> · 매니페스트 '
        f'<a href="{_esc(base)}/v1/mcp">/v1/mcp</a> · 로컬 실행 '
        '<code>python -m import_compliance.mcp_stdio</code></p>'
        '<p class="brand-sub" style="margin-bottom:0">응답에는 근거 조항·시행일·원문 URL과 국·영문 면책이 함께 옵니다. '
        "원본 API 응답은 재전송하지 않고 결합·정규화한 판정만 돌려줍니다.</p>"
        "</div>"
    )


def _related_blocks(item: Dict[str, Any]) -> str:
    blocks = []
    guide_links = []
    for slug in item.get("related_guides") or []:
        other = get_item(slug)
        if other is None:
            continue
        guide_links.append(
            f'<a href="{_esc(page_path(other["slug"]))}">{_esc(other["question_ko"])}'
            f'<span>{_esc(other["category"])}</span></a>'
        )
    if guide_links:
        blocks.append('<h2>이어서 많이 보는 질문</h2><div class="grid">'
                      + "".join(guide_links) + "</div>")
    item_links = []
    for slug in item.get("related_items") or []:
        other = pseo.get_item(slug)
        if other is None:
            continue
        item_links.append(
            f'<a href="{_esc(pseo.page_path(other["slug"]))}">{_esc(other["name_ko"])}'
            f'<span>HS {_esc(other["hs_code"])} · {_esc(other.get("category") or "")}</span></a>'
        )
    if item_links:
        blocks.append('<h2>관련 품목 페이지</h2><div class="grid">'
                      + "".join(item_links) + "</div>")
    return "".join(blocks)


def _breadcrumb_ld(canonical: str, root: str, name: str) -> Dict[str, Any]:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "CLNS", "item": f"{root}/"},
            {"@type": "ListItem", "position": 2, "name": "질문형 가이드", "item": f"{root}{index_path()}"},
            {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
        ],
    }


def render_guide(slug: str, base: Optional[str] = None) -> Optional[str]:
    """`/guides/{slug}` HTML. 없는 슬러그면 None(서버가 404)."""
    item = get_item(slug)
    if item is None:
        return None
    root = static_files.base_url(base)
    canonical = f"{root}{page_path(item['slug'])}"
    meta = catalog_meta()
    noindex = not is_indexable(item)
    question = item["question_ko"]
    title = f"{question} | CLNS"
    description = _clamp(item["summary_ko"], 180)

    json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FAQPage",
                "inLanguage": "ko-KR",
                "url": canonical,
                "mainEntity": [{
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": item["answer_ko"]},
                }],
            },
            {
                "@type": "WebPage",
                "name": item["title_ko"],
                "description": item["summary_ko"],
                "url": canonical,
                "inLanguage": "ko-KR",
                "dateModified": item.get("updated_on") or meta["verified_on"],
                "isAccessibleForFree": True,
                "author": {"@type": "Organization", "name": "CLNS"},
                "publisher": {"@type": "Organization", "name": "CLNS", "url": root},
                "isPartOf": {"@type": "WebSite", "name": "CLNS", "url": root},
            },
            _breadcrumb_ld(canonical, root, item["title_ko"]),
        ],
    }

    keywords = ", ".join(str(word) for word in item.get("keywords") or [])
    search_query = question.replace("?", "").replace("？", "").strip()
    tool = str(item.get("tool") or "assess_import_case")

    return "".join([
        _head(title, description, canonical, root, noindex, json_ld),
        f"""<nav class="crumb"><a href="/">CLNS 홈</a> › <a href="{index_path()}">질문형 가이드</a> › {_esc(item["title_ko"])}</nav>
<main>
<h1>{_esc(question)}</h1>
<p class="lede">{_esc(item["summary_ko"])}</p>
<div class="pills">
  <span class="pill">{_esc(item["category"])}</span>
  <span class="pill ghost">근거 확인 {_esc(item.get("updated_on") or meta["verified_on"])}</span>
  <span class="pill ghost">무료 · 회원가입 없음</span>
</div>
{_answer_block(item)}

<h2>대표 체크포인트</h2>
<div class="card"><ul class="clean">{"".join(f"<li>{_esc(row)}</li>" for row in item["checkpoints_ko"])}</ul></div>

{_bullet_block("왜 이렇게 갈리나요", item.get("key_points_ko") or [])}

<h2>이 질문에 걸리는 규제 축</h2>
<div class="card">{_axes_block(item)}</div>

<h2>자주 틀리는 답 — 이렇게 답하면 틀립니다</h2>
{_traps_block(item)}

<h2>근거 법령</h2>
<div class="card">{_basis_block(item)}</div>

<h2>지금 내 건으로 확인하기</h2>
<div class="card">
  <p style="margin-top:0">이 페이지는 공개된 기준을 정리한 <strong>사전 점검</strong>입니다. 실제 건은 품목명·수량·경로(휴대 반입/직구/판매)·표시 문구를 넣어 확인하세요.</p>
  <div class="cta">
    <a href="/?q={_esc(search_query)}">웹에서 바로 체크</a>
    <a class="ghost" href="/v1/tools/{_esc(tool)}">이 질문의 API 툴</a>
    <a class="ghost" href="/mcp">MCP로 붙이기</a>
  </div>
</div>

<h2>이 페이지에서 다룬 검색어</h2>
<p style="font-size:14px; color:var(--ink-soft)">{_esc(keywords)}</p>

{_related_blocks(item)}

{_tool_block(item, root)}
</main>
""",
        _footer(root),
    ])


def render_index(base: Optional[str] = None) -> str:
    """`/guides/` 인덱스 — 카탈로그 전체 질문으로 들어오는 입구."""
    root = static_files.base_url(base)
    meta = catalog_meta()
    canonical = f"{root}{index_path()}"
    title = f"수입 규제 질문 {meta['count']}선 — 자주 묻는 기준을 한 페이지씩 | CLNS"
    description = _clamp(
        "해외직구 영양제 6병, 자가사용 면세 한도 150/200달러, KC·전파 인증, 한글표시사항, "
        f"과대광고 금지 표현 등 셀러와 소비자가 가장 많이 묻는 {meta['count']}개 질문에 "
        "근거 법령과 확인 체크포인트로 답합니다.", 180)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in items():
        grouped.setdefault(item["category"], []).append(item)
    sections = []
    for category, group in grouped.items():
        links = "".join(
            f'<a href="{_esc(page_path(item["slug"]))}">{_esc(item["question_ko"])}'
            f'<span>{_esc(item["title_ko"])}</span></a>'
            for item in group
        )
        sections.append(f"<h2>{_esc(category)}</h2><div class=\"grid\">{links}</div>")

    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "수입 규제 질문 가이드",
        "url": canonical,
        "inLanguage": "ko-KR",
        "isPartOf": {"@type": "WebSite", "name": "CLNS", "url": root},
        "dateModified": meta["verified_on"],
        "numberOfItems": meta["count"],
    }

    return "".join([
        _head(title, description, canonical, root, False, json_ld),
        f"""<nav class="crumb"><a href="/">CLNS 홈</a> › 질문형 가이드</nav>
<main>
<h1>수입 규제 질문 가이드</h1>
<p class="lede">검색창과 AI 챗봇에 실제로 입력되는 {meta['count']}개 질문을 골라, 한 줄 답변과 확인 체크포인트, 근거 법령을 한 페이지씩 정리했습니다. 품목으로 찾고 싶으면 <a href="/p/">품목별 수입 요건</a>에서 {len(pseo.items())}개 품목을 보세요.</p>
<div class="pills">
  <span class="pill">{meta['count']}개 질문</span>
  <span class="pill ghost">근거 확인 {_esc(meta['verified_on'])}</span>
  <span class="pill ghost">JS 없음 · 무료</span>
</div>
<div class="cta">
  <a href="/">실시간으로 내 건 체크</a>
  <a class="ghost" href="/p/">품목별 요건</a>
  <a class="ghost" href="/mcp">MCP·API</a>
</div>
{''.join(sections)}
<h2>읽는 법</h2>
<div class="card">
  <ul class="clean">
    <li>각 페이지의 첫 문단이 그 질문에 대한 답입니다. 답이 갈리는 조건(수량·경로·용도·표시)은 '대표 체크포인트'에 적었습니다.</li>
    <li>근거 조문은 법제처 현행본으로 확인한 문안과 시행일을 그대로 싣고, 원문 링크를 붙였습니다. 개정으로 바뀔 수 있으니 통관 전 다시 확인하세요.</li>
    <li>조회 결과 0건은 '요건 없음'이 아니라 '조회되지 않음'입니다. HS 10자리와 입력 표기를 함께 확인하세요.</li>
    <li>이 페이지는 사전 참고용이며, 확정 판정은 관세사·관세청·식약처·국가기술표준원 등 소관 기관 확인이 필요합니다.</li>
  </ul>
</div>
</main>
""",
        _footer(root),
    ])
