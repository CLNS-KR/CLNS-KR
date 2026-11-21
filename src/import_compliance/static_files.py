"""검색·AI 크롤러용 정적 파일과 MCP 서버 카드.

- `GET /robots.txt`   → ROBOTS_TXT
- `GET /llms.txt`     → LLMS_TXT (AI 크롤러 진입점)
- `GET /sitemap.xml`  → SITEMAP_XML
- `GET /.well-known/mcp/server-card.json` → server_card() (api.TOOL_DEFS 에서 생성)
- `GET /static/og.png` → load_og_image() (1200×630 공유 미리보기 이미지)

툴 목록은 `api.py` 의 TOOL_DEFS 한 곳에서만 고치면 되도록 여기서 생성한다.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional

from .api import mcp_tools
from .corpus import load_corpus
from .version import __version__

DEFAULT_BASE_URL = "https://clns-kr.onrender.com"


def base_url(value: Optional[str] = None) -> str:
    """공개 주소(환경변수 PUBLIC_BASE_URL 로 덮어쓸 수 있다)."""
    raw = (value or os.environ.get("PUBLIC_BASE_URL") or "").strip()
    return (raw or DEFAULT_BASE_URL).rstrip("/")


def robots_txt(base: Optional[str] = None) -> str:
    root = base_url(base)
    return f"""# CLNS — robots.txt
# 검색 로봇·AI 크롤러 공개 범위. API 경로(/v1/)는 색인 대상이 아니다.

User-agent: *
Allow: /
Disallow: /v1/

# 검색 로봇
User-agent: Yeti
Allow: /

User-agent: Googlebot
Allow: /

# AI 크롤러 — 인용·요약은 허용하고 학습 전용 수집만 막는 절충안.
# 전부 허용하려면 아래 블록을 지우고 "User-agent: * / Allow: /" 만 남긴다.
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

Sitemap: {root}/sitemap.xml
"""


def llms_txt(base: Optional[str] = None) -> str:
    root = base_url(base)
    from . import guides, pseo  # 순환 import 방지(지연 로드)

    try:
        pseo_count = len(pseo.items())
    except Exception:  # noqa: BLE001 - 카탈로그가 없어도 llms.txt 는 나가야 한다
        pseo_count = 0
    try:
        guide_count = len(guides.items())
    except Exception:  # noqa: BLE001
        guide_count = 0
    return f"""# CLNS — Korea Import Compliance

> 한국 수입 규제(세관장확인 요건·식약처 수입 이력·국내 리콜·근거 법령)를 3단계로 판정하는 무료 사전 점검 서비스.
> 확정 판정이 아니라 "확인해야 할 항목의 목록"을 제시하며, 모든 응답에 근거 조항·시행일·원문 URL·국/영문 면책이 함께 온다.
> 데이터: 관세청 세관장확인대상물품(15101589), 식약처 수입식품 계열(15058273·15073949), 식약처 행정처분결과(15124560·15124559), 법제처 국가법령정보, 국표원 리콜 파일데이터(15040696), 국립전파연구원 적합성평가 DB정보(3034183, 인증·등록번호 조회·키 불필요), 마약류 관리에 관한 법률 시행령 별표 1~8에서 생성한 의약품 성분 사전.
> 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않으며, 품목분류(HS) 확정·인증 대행·통관 대리를 하지 않는다.

## 사람용
- [리스크 체크]({root}/): 품목명(+HS 10자리)으로 확인 항목·요건·리콜·근거 조문을 한 화면에서 본다.
- [품목별 수입 요건]({root}/p/): {pseo_count}개 품목(선풍기·보조배터리·오메가3·선크림·반려동물 사료 등)의 세관장확인 요건·KC·전파·식약처 확인 항목·함정·근거를 정적 HTML로 정리. 개별 페이지는 `{root}/p/<slug>`.
- [질문형 가이드]({root}/guides/): {guide_count}개 질문(영양제 6병, 면세 한도 150/200달러, KC·전파 인증, 한글표시사항, 과대광고 금지 표현, 단순변심 환불 불가 문구, 체험단 대가성 표시, 반려동물 사료·간식 수입과 동물검역, 스마트스토어 상표권·지재권, 어린이제품 KC 안전확인, 직구 전자제품 1인 1대 전파인증 예외, 화장품 미백·주름 문구, 목록통관 배제대상물품, '100% 천연' 실증 의무, 향수 60mL·와인 직구, 콘택트렌즈·유모차·카시트 KC, 원두·차 수입신고, 구매대행 청약철회 등)에 한 줄 답변·체크포인트·근거 조문으로 답하는 정적 HTML. `FAQPage` 구조화 데이터 포함, 개별 페이지는 `{root}/guides/<slug>`.
- [시계열 추이]({root}/v1/trends): 일일 리콜·행정처분 스냅샷 기반 신규/변경 건수와 최근 7·30일 급증 품목·유형 요약(읽기 전용 GET).
- [서비스 메타]({root}/v1/meta): 코퍼스 버전, 판정 등급, 무료 한도, 이용 범위.
- [익명 사용 통계]({root}/v1/stats): IP·User-Agent·쿠키를 저장하지 않고 일별 호출 수·툴·판정 분포만 집계한 JSON.

## 기계용 (MCP · JSON-RPC 2.0)
- [MCP 엔드포인트]({root}/mcp): POST. `initialize` → `tools/list` → `tools/call` 순서로 쓰는 JSON-RPC 2.0 서버. 인증 불필요, 응답은 `application/json` 한 덩어리(SSE 스트리밍 없음).
- [MCP 서버 카드]({root}/.well-known/mcp/server-card.json): 서버 정보·인증 방식·툴 15종 스키마.
- [툴 매니페스트]({root}/v1/mcp): GET. 툴 15종의 이름·설명·inputSchema(사람이 읽는 JSON).

## 기계용 (REST JSON)
- [종합 판정]({root}/v1/tools/assess_import_case): POST. `{{"query": "...", "facts": {{"purpose": "resale", "hs_code": "8414519000", "rf_tx": "no"}}}}`
- [HS 10자리 세관장확인 요건]({root}/v1/tools/lookup_hs_requirements): POST. `{{"hs_code": "8414519000"}}`
- [식품·화장품·기구용기 요건]({root}/v1/tools/check_food_cosmetics): POST. `{{"product_name": "오메가3", "kind": "health_functional"}}`
- [KC·전파 적합성평가]({root}/v1/tools/check_kc_certification): POST. `{{"product_name": "블루투스 스피커", "rf_tx": "yes", "rra_cert_no": "R-LARN-00-0210"}}`
- [국내 리콜 이력]({root}/v1/tools/lookup_recall): POST. `{{"product_name": "전지"}}`
- [의약품·영양제 금지성분]({root}/v1/tools/check_drug_import): POST. `{{"product_name": "졸피뎀", "channel": "online", "quantity": 30}}` — 마약류·원료물질·국내 전용 성분과 자가사용 인정기준(6병·3개월분)을 대조
- [한글표시사항(라벨) 체크]({root}/v1/tools/check_korean_labeling): POST. `{{"product_type": "kc_electronics", "label_text": "KC 마크 / 안전확인신고번호 XU12345-20001"}}` — 화장품·식품/건기식·전기/생활용품 KC·반려동물 사료·일반 공산품 5개 품목군의 법정 표시항목 체크리스트와 라벨 문구 누락, 흔한 과태료 사례(한글 스티커 훼손·전성분 누락·소비기한/제조일자 혼동·KC 표시 누락·원산지 미표시)를 근거 조문과 함께 반환
- [과대광고·한글표시사항 검수]({root}/v1/tools/check_ad_labeling): POST. `{{"product_type": "general_food", "ad_copy": "먹기만 하면 100% 다이어트, 항암 효과", "label_text": "제품명 … 소비기한 …"}}` — 유형별 금지 표현과 필수 표시항목 누락을 대조
- [반려동물 사료·간식 사료관리법·동물검역]({root}/v1/tools/check_feed_import): POST. `{{"product_name": "강아지 동결건조 간식", "product_type": "treat", "animal": "dog", "purpose": "resale", "animal_origin": "yes"}}` — 성분등록·사료 수입신고·표시·유해물질·제조업 등록과 지정검역물·반려동물 사료 수입위생조건 확인 항목(사료관리법에 수입업 등록은 없음)
- [국내 판매페이지 공정위·전자상거래법 검수]({root}/v1/tools/check_ecommerce_compliance): POST. `{{"detail_copy": "정가 39,000원 → 오늘만 19,900원! 단순변심 환불 불가", "channel": "smartstore"}}` — 허위 정가·마감임박·체험단 대가성 미표기·청약철회 제한·배송 회피·최저가/1위·구독 자동결제·가격/해지 다크패턴과 판매자 정보 고지 누락을 근거 조문(시행일·원문 URL)·수정 전→후 문구와 함께 반환
- [식약처 행정처분 이력]({root}/v1/tools/lookup_mfds_disposition): POST. `{{"industry": "manufacturing", "keyword": "표시"}}` — 식품제조가공업·식품판매업 처분 이력(개인정보 필드는 폐기)
- [근거 조항]({root}/v1/tools/get_legal_basis): POST. `{{"law": "관세법", "article": "제226조"}}`
- [리콜·행정처분 시계열 추이]({root}/v1/tools/get_compliance_trends): POST. `{{"days": 30}}` — 일일 스냅샷의 신규/변동 건수와 급증 품목·유형

## 읽는 법
- 판정 등급은 `check_likely`(확인 가능성 높음) / `info_needed`(추가 정보 필요) / `low_risk`(현재 정보상 가능성 낮음) 세 가지이며 확정 판단이 아니다.
- 조회 0건은 "요건 없음"이 아니라 "조회되지 않음"이다. HS 10자리·입력 표기 차이로도 0건이 나온다.
- 전파 적합성평가는 인증·등록번호로만 실시간 조회되며(`rra_conformity`), 번호가 없으면 국립전파연구원 조회 화면에서 모델명으로 확인해야 한다.
- 리콜 데이터는 2023-08-09 배포본(등록일 2019-10~2022-07) 정적 스냅샷이라 최신 리콜은 반영되지 않는다.
- 실시간 조회 결과가 7일 TTL 캐시에서 나온 경우 `state: "cached_fallback"` 과 `age_hours` 로 캐시 시점을 밝힌다.
- 의약품 성분은 마약류 관리에 관한 법률 시행령 별표 1~8에서 생성한 로컬 사전으로 대조한다. 시행령 별표에 없다고 마약류가 아니라고 단정할 수 없으며(임시마약류 지정·개정 시차), 2026-11-21 활용승인된 식약처 의약품 허가정보·e약은요·DUR·마약류 오남용 정보 API 결과를 함께 보여 준다(조회 실패은 상태로 밝힌다).
- 한글표시사항 체크는 입력한 라벨 문구에서 항목의 존재만 대조한다. 항목을 찾지 못한 것은 입력에 없다는 뜻이며, 전항목 확인이 라벨의 적법성을 확정하지 않는다(라벨 사진 인식은 하지 않는다).
- 과대광고·표시 검수는 문구 패턴 대조이며, 근거는 식품등의 표시·광고에 관한 법률 제8조·시행령 제3조·화장품법 제13조와 식약처 고시(식품등의 부당한 표시 또는 광고의 내용 기준)다. 같은 단어도 문맥에 따라 판단이 달라진다.
- 국내 판매페이지 검수는 공정위 표시·광고의 공정화에 관한 법률 제3조·제5조·시행령 제3조, 전자상거래 등에서의 소비자보호에 관한 법률 제13조·제17조·제18조·제21조·제21조의2·시행령 제20조의2와 공정위 고시(부당한 표시·광고행위의 유형 및 기준, 상품 등의 정보제공, 소비자보호 지침)ㆍ예규(추천·보증 심사지침)를 근거로 쓴다. 실제 판매 이력·화면 구성은 반영하지 않으므로 확정 판정이 아니다.
- 행정처분 이력은 과거 처분 사실이며 현재 영업 상태를 뜻하지 않는다. 원본의 업소명·연락처·주소·인허가번호는 읽지 않고 버린다. 데이터셋 승인 전파 전이면 내장 대표 적발 패턴으로 안내한다.
"""


def sitemap_xml(base: Optional[str] = None) -> str:
    """`/` + `/p/` + 품목별 페이지 + `/guides/` + 질문형 가이드를 동적으로 반환한다."""
    root = base_url(base)
    try:
        lastmod = load_corpus().verified_on or "2026-11-18"
    except (OSError, ValueError):
        lastmod = "2026-11-18"
    from . import guides, pseo  # 순환 import 방지(지연 로드)

    try:
        paths = pseo.indexable_paths()
    except Exception:  # noqa: BLE001 - 카탈로그 문제가 사이트맵을 막지 않게
        paths = []
    try:
        guide_paths = guides.indexable_paths()
    except Exception:  # noqa: BLE001
        guide_paths = []
    entries = [f"""  <url>
    <loc>{root}/</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>"""]
    for path in paths:
        priority = "0.9" if path == "/p/" else "0.7"
        freq = "weekly" if path == "/p/" else "monthly"
        entries.append(f"""  <url>
    <loc>{root}{path}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>""")
    try:
        guide_lastmod = guides.catalog_meta()["verified_on"] or lastmod
    except Exception:  # noqa: BLE001
        guide_lastmod = lastmod
    for path in guide_paths:
        priority = "0.9" if path == "/guides/" else "0.8"
        freq = "weekly" if path == "/guides/" else "monthly"
        entries.append(f"""  <url>
    <loc>{root}{path}</loc>
    <lastmod>{guide_lastmod}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>""")
    body = "\n".join(entries + [
        f"""  <url>
    <loc>{root}/about</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>""",
        f"""  <url>
    <loc>{root}/privacy</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>yearly</changefreq>
    <priority>0.3</priority>
  </url>""",
        f"""  <url>
    <loc>{root}/terms</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>yearly</changefreq>
    <priority>0.3</priority>
  </url>""",
    ])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
"""


def server_card() -> Dict[str, Any]:
    """`/.well-known/mcp/server-card.json` — 정적 서버 카드(툴 정의는 TOOL_DEFS 에서 생성)."""
    corpus = None
    try:
        corpus = load_corpus()
    except (OSError, ValueError):
        corpus = None
    card: Dict[str, Any] = {
        "serverInfo": {"name": "CLNS", "version": __version__},
        "description": (
            "한국 수입 규제 사전 점검 MCP 서버 — 세관장확인 요건·식약처 수입 이력·국내 리콜·근거 법령을 "
            "3단계로 판정한다. 확정 판정이 아니며 근거 조항·면책을 함께 돌려준다."
        ),
        "authentication": {"required": False, "schemes": []},
        "transport": {
            "type": "streamable-http",
            "endpoint": "/mcp",
            "protocolVersion": "2025-06-18",
            "contentType": "application/json",
        },
        "transports": {
            "http": {"endpoint": "/mcp", "protocolVersion": "2025-06-18"},
            "stdio": {
                "command": "python",
                "args": ["-m", "import_compliance.mcp_stdio"],
                "note_ko": "로쇠 실행형 MCP 디렉터리(Glama·mcp.so 등)용. 한 줄에 JSON-RPC 2.0 한 건을 stdin 으로 받고 stdout 으로 응답한다.",
            },
        },
        "tools": mcp_tools(),
        "resources": [],
        "prompts": [],
        "attribution_ko": "출처: 관세청 / 식품의약품안전처 / 산업통상부 국가기술표준원 / 법제처 국가법령정보센터",
    }
    if corpus is not None:
        card["corpus"] = {"version": corpus.version, "verified_on": corpus.verified_on,
                          "cases": len(corpus.traps)}
    return card


def og_image_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "static", "og.png")


@lru_cache(maxsize=1)
def load_og_image() -> Optional[bytes]:
    """공유 미리보기 PNG(1200×630). 파일이 없으면 None → 서버가 404 로 응답한다."""
    path = og_image_path()
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None
