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
    return f"""# CLNS — Korea Import Compliance

> 한국 수입 규제(세관장확인 요건·식약처 수입 이력·국내 리콜·근거 법령)를 3단계로 판정하는 무료 사전 점검 서비스.
> 확정 판정이 아니라 "확인해야 할 항목의 목록"을 제시하며, 모든 응답에 근거 조항·시행일·원문 URL·국/영문 면책이 함께 온다.
> 데이터: 관세청 세관장확인대상물품(15101589), 식약처 수입식품 계열(15058273·15073949), 법제처 국가법령정보, 국표원 리콜 파일데이터(15040696).
> 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않으며, 품목분류(HS) 확정·인증 대행·통관 대리를 하지 않는다.

## 사람용
- [리스크 체크]({root}/): 품목명(+HS 10자리)으로 확인 항목·요건·리콜·근거 조문을 한 화면에서 본다.
- [서비스 메타]({root}/v1/meta): 코퍼스 버전, 판정 등급, 무료 한도, 이용 범위.

## 기계용 (MCP · JSON-RPC 2.0)
- [MCP 엔드포인트]({root}/mcp): POST. `initialize` → `tools/list` → `tools/call` 순서로 쓰는 JSON-RPC 2.0 서버. 인증 불필요, 응답은 `application/json` 한 덩어리(SSE 스트리밍 없음).
- [MCP 서버 카드]({root}/.well-known/mcp/server-card.json): 서버 정보·인증 방식·툴 8종 스키마.
- [툴 매니페스트]({root}/v1/mcp): GET. 툴 8종의 이름·설명·inputSchema(사람이 읽는 JSON).

## 기계용 (REST JSON)
- [종합 판정]({root}/v1/tools/assess_import_case): POST. `{{"query": "...", "facts": {{"purpose": "resale", "hs_code": "8414519000", "rf_tx": "no"}}}}`
- [HS 10자리 세관장확인 요건]({root}/v1/tools/lookup_hs_requirements): POST. `{{"hs_code": "8414519000"}}`
- [식품·화장품 요건]({root}/v1/tools/check_food_cosmetics): POST. `{{"product_name": "오메가3", "kind": "health_functional"}}`
- [국내 리콜 이력]({root}/v1/tools/lookup_recall): POST. `{{"product_name": "전지"}}`
- [근거 조항]({root}/v1/tools/get_legal_basis): POST. `{{"law": "관세법", "article": "제226조"}}`

## 읽는 법
- 판정 등급은 `check_likely`(확인 가능성 높음) / `info_needed`(추가 정보 필요) / `low_risk`(현재 정보상 가능성 낮음) 세 가지이며 확정 판단이 아니다.
- 조회 0건은 "요건 없음"이 아니라 "조회되지 않음"이다. HS 10자리·입력 표기 차이로도 0건이 나온다.
- 리콜 데이터는 2023-08-09 배포본(등록일 2019-10~2022-07) 정적 스냅샷이라 최신 리콜은 반영되지 않는다.
- 실시간 조회 결과가 7일 TTL 캐시에서 나온 경우 `state: "cached_fallback"` 과 `age_hours` 로 캐시 시점을 밝힌다.
"""


def sitemap_xml(base: Optional[str] = None) -> str:
    root = base_url(base)
    try:
        lastmod = load_corpus().verified_on or "2026-11-18"
    except (OSError, ValueError):
        lastmod = "2026-11-18"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{root}/</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
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
