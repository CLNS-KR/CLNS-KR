"""API / MCP 툴 12종."""
from __future__ import annotations

import json
import os

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from . import usage
from .corpus import load_corpus, normalize
from .standards import (
    ASSESSMENT_STATUS_ORDER,
    DEFAULT_DESTINATION,
    DEFAULT_JURISDICTION,
    REGULATION_TAGS,
    SCHEMA_VERSION,
    apply_geography,
    apply_status,
    tags_for_findings,
    testset_meta,
)
from .engine import assess
from .models import VERDICT_LABEL_EN, VERDICT_LABEL_KO, VERDICT_SEVERITY
from .policy import PAID_TIER_NOTICE_KO, SCOPE_LIMITS_KO, TIER_BOUNDARIES
from .version import __version__ as PACKAGE_VERSION
from .store import (
    FREE_MONTHLY_CALLS,
    QuotaExceeded,
    SourceGateway,
    Store,
    iso,
    now_kst,
    snapshot_age_hours,
)

# 공공데이터 스냅샷 TTL(문서 03 설계값: 7일). 이 시간 안의 캐시는 'cached_fallback'으로 정직하게 표시한다.
CACHE_TTL_HOURS = 24 * 7


def _envelope(tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    # 모든 툴 응답에 같은 표준 필드(schema_version·destination·jurisdiction·origin)를
    # 보장한다. 이미 계산된 값(assess 결과 등)은 덮어쓰지 않는다.
    apply_geography(payload)
    return {"tool": tool, "ok": True, "result": payload}


LIVE_NOTES = {
    "usage_ko": (
        "실API 조회 결과는 참고 정보이며, 요건 적용 여부의 최종 확인은 관세청·요건승인기관·"
        "식품의약품안전처 등 소관 기관에 문의해야 합니다."
    ),
    "zero_ko": (
        "조회 결과 0건은 '요건·이력 없음'을 뜻하지 않습니다. 입력값 표기 차이, HS 10자리 불일치, "
        "데이터 갱신 지연으로도 0건이 나올 수 있습니다."
    ),
    "passthrough_ko": "원본 응답은 내부 캐시에만 보관하며 그대로 재전송하지 않습니다.",
}


def _cache_key(*parts: Any) -> str:
    """캐시 조회 키(정규화·길이 제한). 원본 입력은 남기지 않는다."""
    return normalize("|".join("" if part is None else str(part) for part in parts))[:120]


def _cached_block(store: Any, source_id: str, key: str,
                  ttl_hours: float = CACHE_TTL_HOURS) -> Optional[Dict[str, Any]]:
    """TTL 안의 스냅샷을 블록으로 되살린다. 캐시 히트는 state로 숨기지 않고 표시한다."""
    if store is None:
        return None
    hit = store.get_cached_snapshot(source_id, key, ttl_hours)
    if hit is None:
        return None
    payload, age_hours = hit
    block = dict(payload)
    block["state"] = "cached_fallback"
    block["fresh"] = age_hours <= ttl_hours
    block["age_hours"] = round(age_hours, 2)
    block["cache_ttl_hours"] = ttl_hours
    block["cache_note_ko"] = (
        f"{ttl_hours / 24:.0f}일 TTL 캐시에서 응답했습니다(원 조회 후 {age_hours:.1f}시간 경과). "
        "소스별 갱신 주기가 다르므로 최신 값은 소관 기관 원문에서 확인해야 합니다."
    )
    return block


def _store_block(store: Any, source_id: str, key: str, block: Dict[str, Any]) -> None:
    if store is None:
        return
    store.put_snapshot(source_id, key, block)


def _mark_live_provenance(result: Dict[str, Any], source_id: str, *, state: str = "live",
                          fetched_at: str = "", fresh: bool = True,
                          age_hours: Optional[float] = None, **extra: Any) -> None:
    """data_provenance.sources 의 해당 소스 상태를 실호출 결과로 덮어쓴다.

    `engine.assess()` 는 게이트웨이가 아는 소스(세관장확인)만 상태를 만들 수 있어서,
    assess 이후에 따로 실호출하는 식약처·법령 경로는 '연결 실패'로 남는 모순이 있었다.
    """
    provenance = result.get("data_provenance")
    if not isinstance(provenance, dict):
        return
    entry: Dict[str, Any] = {"source_id": source_id, "state": state, "fresh": fresh}
    if fetched_at:
        entry["fetched_at"] = fetched_at
    if age_hours is not None:
        entry["age_hours"] = age_hours
    entry.update({key: value for key, value in extra.items() if value is not None})
    sources = [src for src in (provenance.get("sources") or [])
               if src.get("source_id") != source_id and src.get("state") != "corpus_only"]
    sources.append(entry)
    provenance["sources"] = sources


def _raise_verdict(result: Dict[str, Any], code: str) -> None:
    """판정을 낮추지 않고 최소 등급만 올린다(세관장확인 요건이 조회된 경우)."""
    verdict = result.get("verdict")
    if not isinstance(verdict, dict) or code not in VERDICT_SEVERITY:
        return
    current = str(verdict.get("code") or "")
    if VERDICT_SEVERITY[code] > VERDICT_SEVERITY.get(current, 0):
        verdict["code"] = code
        verdict["label_ko"] = VERDICT_LABEL_KO[code]
        verdict["label_en"] = VERDICT_LABEL_EN[code]


def _live_error(exc: Exception) -> Dict[str, Any]:
    return {
        "state": "error",
        "code": getattr(exc, "code", None),
        "http_status": getattr(exc, "http_status", None),
        "retryable": getattr(exc, "retryable", False),
        "message": getattr(exc, "message", str(exc)),
        "note_ko": "실시간 조회가 되지 않았습니다. 오래된 캐시로 대신하지 않고 '조회 실패'로 표시합니다.",
    }


def _customs_live(live: Any, hs_code: str, direction: str, limit: int = 10) -> Optional[Dict[str, Any]]:
    if live is None or not getattr(live, "has_customs", False):
        return None
    from .live_api import LiveApiError, normalize_customs_item

    try:
        fetch = live.customs_checkpoint(hs_code, direction)
    except LiveApiError as exc:
        return _live_error(exc)
    rows = [normalize_customs_item(item) for item in fetch.items]
    return {
        "state": "live",
        "fresh": True,
        "checked_at": fetch.fetched_at,
        "hs_code": hs_code,
        "direction": direction,
        "requirement_count": len(rows),
        "requirements": rows[:limit],
        "source": "관세청_세관장확인대상물품(data.go.kr 15101589, 이용허락범위 제한 없음)",
        "note_ko": LIVE_NOTES["usage_ko"],
        "zero_note_ko": LIVE_NOTES["zero_ko"],
        "passthrough_ko": LIVE_NOTES["passthrough_ko"],
    }


def _mfds_live(live: Any, product_name: str, *, store: Any = None,
               rows: int = 3) -> Optional[Dict[str, Any]]:
    """식약처 3개 오퍼레이션(제품DB·수입신고·부적합)을 병렬 호출하고 7일 TTL 캐시를 쓴다.

    - 순차 호출 시 9~13초 → 병렬화로 3~4초(실측 근거: 05 문서 1-5절).
    - 같은 품목 재호출은 스냅샷 캐시로 즉시 응답하되 state='cached_fallback'으로 표시한다.
    - 게이트는 `has_mfds`(data.go.kr 키 존재)다. 세관장확인 키와 같은 키를 쓰지만 의미를 분리한다.
    """
    if live is None or not getattr(live, "has_mfds", False) or not product_name:
        return None
    from .live_api import (
        SOURCE_MFDS_PERMIT,
        normalize_mfds_improper_item,
        normalize_mfds_permit_item,
        normalize_mfds_product_item,
    )

    key = _cache_key("mfds", product_name, rows)
    cached = _cached_block(store, SOURCE_MFDS_PERMIT, key)
    if cached is not None:
        return cached

    block: Dict[str, Any] = {
        "state": "live",
        "fresh": True,
        "age_hours": 0.0,
        "product_name": product_name,
        "source": "식품의약품안전처 수입식품 계열(data.go.kr 15058273·15073949, 이용허락범위 제한 없음)",
        "note_ko": LIVE_NOTES["usage_ko"],
        "zero_note_ko": LIVE_NOTES["zero_ko"],
        "passthrough_ko": LIVE_NOTES["passthrough_ko"],
        "cache_ttl_hours": CACHE_TTL_HOURS,
    }

    def _product_db() -> Dict[str, Any]:
        fetch = live.mfds_product_db(product_name=product_name, rows=rows)
        return {
            "checked_at": fetch.fetched_at,
            "match_count": fetch.total_count if fetch.total_count is not None else len(fetch.items),
            "samples": [normalize_mfds_product_item(item) for item in fetch.items[:rows]],
        }

    def _permit_history() -> Dict[str, Any]:
        fetch = live.mfds_import_permit(product_name=product_name, rows=rows)
        return {
            "checked_at": fetch.fetched_at,
            "match_count": fetch.total_count if fetch.total_count is not None else len(fetch.items),
            "samples": [normalize_mfds_permit_item(item) for item in fetch.items[:rows]],
        }

    def _improper_history() -> Dict[str, Any]:
        fetch = live.mfds_improper(product_name=product_name, rows=rows)
        return {
            "checked_at": fetch.fetched_at,
            "match_count": fetch.total_count if fetch.total_count is not None else len(fetch.items),
            "samples": [normalize_mfds_improper_item(item) for item in fetch.items[:rows]],
            "note_ko": "수입식품 검사부적합 검색(15058273 오퍼레이션 2). 0건은 부적합 이력 없음이 아니라 입력 표기·검색 범위 차이일 수 있습니다.",
        }

    jobs = (
        ("product_db", _product_db),
        ("import_permit_history", _permit_history),
        ("improper_history", _improper_history),
    )
    failures = 0
    with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="mfds") as pool:
        futures = [(name, pool.submit(func)) for name, func in jobs]
        for name, future in futures:
            try:
                block[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - 소스별 실패를 따로 표기
                block[name] = _live_error(exc)
                failures += 1

    if failures == 3:
        block["state"] = "error"
    elif failures:
        block["state"] = "partial"
    else:
        # 실패가 섞인 응답은 캐시하지 않는다(다음 호출에서 다시 시도할 수 있게).
        _store_block(store, SOURCE_MFDS_PERMIT, key, block)
    return block


def _rra_live(live: Any, cert_no: str, *, store: Any = None, rows: int = 3,
              reuse_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """국립전파연구원 적합성평가 조회(인증·등록번호 1건) + 7일 TTL 캐시.

    키가 필요 없는 공개 엔드포인트라 별도 활용신청 없이 호출한다.
    번호가 없으면 None(호출부가 '번호 필요' 상태를 안내한다).
    `reuse_key` 는 엔진 게이트웨이가 같은 요청에서 이미 저장한 스냅샷 키다
    (같은 요청에서 같은 API를 두 번 부르지 않기 위해 재사용한다).
    """
    if live is None or not getattr(live, "has_rra", False):
        return None
    from .live_api import (
        RRA_OFFICIAL_URL,
        SOURCE_RRA,
        LiveApiError,
        normalize_cert_no,
        normalize_rra_item,
        rra_cert_type,
    )

    number = normalize_cert_no(cert_no)
    if not number:
        return None
    key = _cache_key("rra", number)
    cached = _cached_block(store, SOURCE_RRA, key)
    if cached is not None:
        return cached

    block: Dict[str, Any] = {
        "state": "live",
        "fresh": True,
        "age_hours": 0.0,
        "cert_no": number,
        "cert_type_estimate": rra_cert_type(number),
        "source": "과학기술정보통신부 국립전파연구원_적합성평가 DB정보(data.go.kr 3034183, 이용허락범위 제한 없음, 키 불필요)",
        "official_url": RRA_OFFICIAL_URL,
        "note_ko": LIVE_NOTES["usage_ko"],
        "passthrough_ko": LIVE_NOTES["passthrough_ko"],
        "cache_ttl_hours": CACHE_TTL_HOURS,
        "type_note_ko": (
            "유형(적합인증·적합등록 등)은 번호 접두를 기준으로 표시한 추정값이며, "
            "공식 확인은 국립전파연구원 조회 화면을 따른다."
        ),
    }
    prefetched = _prefetched_rra(store, reuse_key, rows) if reuse_key else None
    if prefetched is not None:
        block.update(prefetched)
        _store_block(store, SOURCE_RRA, key, block)
        return block
    try:
        fetch = live.rra_certificate(number)
    except LiveApiError as exc:
        block.update(_live_error(exc))
        return block
    matches = [normalize_rra_item(item) for item in fetch.items][:rows]
    block["checked_at"] = fetch.fetched_at
    block["result_code"] = fetch.result_code
    block["match_count"] = len(matches)
    block["matches"] = matches
    if fetch.state == "not_found":
        block["state"] = "not_found"
        block["note_ko"] = (
            "이 인증·등록번호로 조회된 적합성평가 기록이 없습니다. 0건은 '미인증' 단정이 아니라 "
            "번호 표기·개정·시스템 반영 차이일 수 있으므로 번호를 다시 확인해야 합니다."
        )
    elif fetch.state != "live":
        block["state"] = "error"
        block["note_ko"] = "적합성평가 조회가 정상 처리되지 않았습니다(결과코드 확인 필요)."
    else:
        _store_block(store, SOURCE_RRA, key, block)
    return block


def _prefetched_rra(store: Any, key: str, rows: int) -> Optional[Dict[str, Any]]:
    """같은 요청에서 엔진 게이트웨이가 남긴 적합성평가 스냅샷(최근 3분)을 블록으로 되살린다."""
    if store is None or not key:
        return None
    from .live_api import SOURCE_RRA

    try:
        row = store.latest_snapshot(SOURCE_RRA, key)
    except Exception:  # noqa: BLE001 - 캐시 조회 실패는 네트워크 호출로 넘긴다
        return None
    if row is None:
        return None
    age = snapshot_age_hours(row["fetched_at"])
    if age > 0.05:  # 3분
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, ValueError):
        return None
    items = payload.get("items") or []
    return {
        "state": "live",
        "fresh": True,
        "age_hours": round(age, 3),
        "checked_at": row["fetched_at"],
        "result_code": payload.get("result_code"),
        "match_count": len(items),
        "matches": items[:rows],
    }


def _apply_rra_result(result: Dict[str, Any], block: Dict[str, Any]) -> None:
    """적합성평가 조회 결과를 안내문·data_provenance 에 반영한다."""
    from .live_api import SOURCE_RRA

    answer = result.setdefault("answer", {})
    guidance = answer.setdefault("guidance", [])
    state = str(block.get("state") or "")
    cert_no = str(block.get("cert_no") or "")
    _mark_live_provenance(
        result, SOURCE_RRA, state=state if state in ("live", "not_found", "error") else "error",
        fetched_at=str(block.get("checked_at") or ""), fresh=bool(block.get("fresh")),
        age_hours=block.get("age_hours"), item_count=block.get("match_count"),
        cert_no=cert_no or None,
    )
    if state == "live" and block.get("matches"):
        top = block["matches"][0]
        guidance.append(
            f"국립전파연구원 적합성평가 DB에서 인증·등록번호 {cert_no}의 기록을 확인했습니다"
            f"(기자재명 {top.get('equipment_name') or '-'}, 기본모델 {top.get('base_model') or '-'}, "
            f"인증일 {top.get('certified_on') or '-'}). 조회된 기록은 인증 사실의 확인이며, "
            "해당 모델이 이번 수입 건의 모델과 같은지는 모델명·파생모델로 대조해야 합니다."
        )
    elif state == "not_found":
        guidance.append(
            f"인증·등록번호 {cert_no}로는 적합성평가 기록이 조회되지 않았습니다. 0건은 '미인증' "
            "단정이 아니므로 번호 표기(하이픈·연도)와 개정 여부를 다시 확인해야 합니다."
        )
    elif state == "error":
        guidance.append(
            "적합성평가 실시간 조회에 실패했습니다"
            f"(코드 {block.get('code') or block.get('result_code') or 'n/a'}). "
            "전파법 적합성평가 쟁점은 코퍼스·법령 근거로만 판단했습니다."
        )


def _law_live(live: Any, law_names: List[str], limit: int = 3,
              article: str = "", store: Any = None) -> Optional[Dict[str, Any]]:
    if live is None or not getattr(live, "has_law", False) or not law_names:
        return None
    from .live_api import SOURCE_LAW, LiveApiError, normalize_law_article, normalize_law_item

    key = _cache_key("law", ",".join(law_names[:limit]), article)
    cached = _cached_block(store, SOURCE_LAW, key)
    if cached is not None:
        return cached

    out: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for name in law_names[:limit]:
        try:
            fetch = live.law_search(name, display=10)
        except LiveApiError as exc:
            errors.append({"law": name, **_live_error(exc)})
            continue
        if not fetch.items:
            errors.append({"law": name, "state": "not_found",
                           "note_ko": "검색 결과가 없습니다. 법령명 표기를 확인해야 합니다."})
            continue
        rows = [normalize_law_item(item) for item in fetch.items]
        exact = [row for row in rows if row["law_name"].replace(" ", "") == name.replace(" ", "")]
        chosen = exact[0] if exact else rows[0]
        chosen["exact_match"] = bool(exact)
        out.append(chosen)

    article_block: Optional[Dict[str, Any]] = None
    if article and out:
        wanted = str(article).lstrip("제").replace("조", "").strip()
        target = out[0]
        if target.get("mst"):
            try:
                body = live.law_articles(target["mst"], article=wanted)
                if body.items:
                    unit = normalize_law_article(body.items[0])
                    article_block = {
                        "law_name": target["law_name"],
                        "article": unit["article"],
                        "title": unit["title"],
                        "text": unit["text"],
                        "paragraphs": unit["paragraphs"],
                        "effective_from": unit["effective_from"],
                        "url": target["url"],
                        "source": "법제처 국가법령정보센터",
                    }
                else:
                    article_block = {"law_name": target["law_name"], "article": f"제{wanted}조",
                                     "state": "not_found",
                                     "note_ko": "해당 조문을 본문에서 찾지 못했습니다."}
            except LiveApiError as exc:
                article_block = {"law_name": target["law_name"], **_live_error(exc)}

    if not out and not errors:
        return None
    result = {
        "state": "live" if out else "error",
        "confirmed": out,
        "errors": errors,
        "attribution_ko": "출처: 법제처 국가법령정보센터",
        "note_ko": (
            "시행일자는 법제처 현행 법령 기준입니다. 인용 시 '출처: 법제처 국가법령정보센터'를 "
            "빠짐없이 표시해야 하며, 출처를 다른 기관으로 바꾸어 표기할 수 없습니다."
        ),
    }
    if article_block is not None:
        result["article_text"] = article_block
    if result["state"] == "live":
        _store_block(store, SOURCE_LAW, key, result)
    return result


def _apply_customs_requirements(result: Dict[str, Any], block: Dict[str, Any]) -> None:
    """HS 10자리 세관장확인 실조회 결과를 종합 판정·안내·provenance 에 반영한다.

    고친 버그: assess 는 요건 목록을 응답에 담지 않고 판정도 올리지 않아, 같은 HS로
    lookup_hs_requirements 를 부르면 'check_likely' 인데 assess 는 'low_risk' 였다.
    """
    answer = result.setdefault("answer", {})
    guidance = answer.setdefault("guidance", [])
    state = str(block.get("state") or "")
    count = int(block.get("requirement_count") or 0)
    hs_code = block.get("hs_code") or ""

    if state == "live":
        _mark_live_provenance(result, "customs_requirements", state="live",
                              fetched_at=str(block.get("checked_at") or ""), fresh=True,
                              item_count=count)
        if count > 0:
            laws = _unique([str(row.get("requirement_law") or "")
                            for row in (block.get("requirements") or [])])
            law_hint = f" (주요 요건 법령: {', '.join(laws[:3])})" if laws else ""
            guidance.append(
                f"관세청 세관장확인대상물품 API에서 HS {hs_code}에 대한 요건 {count}건이 조회되었습니다{law_hint}. "
                "요건별 확인 기관·서류는 조회 결과를 참고하되 소관 기관 확인이 필요합니다."
            )
            _raise_verdict(result, "check_likely")
        else:
            guidance.append(
                f"관세청 API에서 HS {hs_code}로 조회된 세관장확인 요건이 0건입니다. "
                "0건은 '요건 없음'이 아니라 '조회되지 않음'이므로 HS 10자리·수입/수출 구분을 다시 확인해야 합니다."
            )
        return

    _mark_live_provenance(result, "customs_requirements", state="error", fresh=False,
                          code=block.get("code"))
    guidance.append(
        "관세청 실시간 조회에 실패해 세관장확인 요건 목록을 제시하지 못했습니다"
        f"(코드 {block.get('code') or 'n/a'}). 판정은 코퍼스·법령 근거만으로 이루어졌습니다."
    )


def tool_assess_import_case(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                            live: Any = None) -> Dict[str, Any]:
    query = str(args.get("query", "")).strip()
    facts = args.get("facts") or {}
    if not isinstance(facts, dict):
        raise ValueError("facts_must_be_object")
    result = assess(query, facts, store=store, client_id=client_id, tier=tier,
                    limit=int(args.get("limit", 3)), live=live)
    # 질의문에서 추론한 HS까지 포함해 10자리면 세관장확인을 실조회해 판정에 반영한다.
    resolved = (result.get("query") or {}).get("facts_resolved") or {}
    hs_code = str(resolved.get("hs_code") or "").strip()
    if len(hs_code) == 10 and hs_code.isdigit():
        block = _customs_live(live, hs_code, str(resolved.get("direction") or "import"))
        if block is not None:
            result["hs_requirements_live"] = block
            _apply_customs_requirements(result, block)
            if store is not None:  # 판정을 올렸으면 저장된 사본도 같은 결론으로 맞춘다
                store.update_assessment(str(result.get("assessment_id") or ""),
                                        str(result["verdict"]["code"]), result)
    # 적합성평가(전파법): 인증·등록번호가 있으면 국립전파연구원 DB를 실시간 조회한다.
    cert_no = str(resolved.get("rra_cert_no") or facts.get("rra_cert_no")
                  or facts.get("cert_no") or "").strip()
    if cert_no:
        rra_block = _rra_live(live, cert_no, store=store,
                              reuse_key=normalize(query)[:60] if store is not None else None)
        if rra_block is not None:
            result["rra_conformity_live"] = rra_block
            _apply_rra_result(result, rra_block)
    elif any("RF_CONFORMITY" in (finding.get("regulation_tags") or [])
             for finding in result.get("findings") or []):
        _add_rra_hint(result, store)
    # 관세율·FTA 원산지 가이드 및 화장품 배합금지 대조(선택)
    from . import cosmetic_ingredients, tariff_fta

    origin_val = str(facts.get("origin") or resolved.get("origin") or "").strip()
    if not origin_val:
        for country in tariff_fta.FTA_BY_ORIGIN:
            if country in query:
                origin_val = country
                break
    result["tariff_fta"] = tariff_fta.assess_tariff_fta(
        product=query,
        hs_code=hs_code,
        origin=origin_val,
        purpose=str(facts.get("purpose") or resolved.get("purpose") or "resale"),
    )

    cos_ing = str(facts.get("cosmetic_ingredients") or "").strip()
    if cos_ing:
        cos_res = cosmetic_ingredients.screen_cosmetic_ingredients(cos_ing)
        result["cosmetic_screening"] = cos_res
        if cos_res.get("prohibited"):
            _raise_verdict(result, "check_likely")

    # 실시간 조회로 verdict 가 올라갔으면 표준 판정 상태도 함께 맞춘다.
    apply_status(result)
    verdict_obj = result.get("verdict") or {}
    result.setdefault("summary_en", {
        "verdict_code": verdict_obj.get("code"),
        "verdict_label_en": verdict_obj.get("label_en"),
        "findings_count": len(result.get("findings") or []),
        "origin": origin_val or None,
        "hs_code": hs_code or None,
        "has_prohibited_cosmetic_ingredient": bool((result.get("cosmetic_screening") or {}).get("prohibited")),
    })
    return _envelope("assess_import_case", result)


def tool_check_drug_import(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                           live: Any = None) -> Dict[str, Any]:
    """의약품·영양제의 반입 금지성분·제한성분을 확인한다.

    성분 사전(시행령 별표 1~8) + 자가사용 인정기준(6병·3개월분) 대조를 한 번에 하고,
    마약류·원료물질·국내 전용 성분 쟁점(TRAP-23·24)과 근거 조항을 함께 돌려준다.
    """
    from . import drugs

    product = str(args.get("product_name") or args.get("ingredient") or "").strip()
    if len(product) < 2:
        raise ValueError("product_name_required")
    channel = str(args.get("channel") or "unknown").strip().lower()
    if channel not in ("carry", "online", "unknown"):
        raise ValueError("channel_must_be_carry_or_online")
    quantity = args.get("quantity")
    if quantity not in (None, ""):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("quantity_must_be_integer") from exc
    else:
        quantity = None

    parts = [product]
    if channel == "online":
        parts.append("해외직구 온라인 구매")
    elif channel == "carry":
        parts.append("휴대 반입")
    if quantity:
        parts.append(f"{quantity}{args.get('unit') or '병'}")
    if str(args.get("purpose") or "") == "resale":
        parts.append("판매용")
    query = " ".join(parts)

    facts: Dict[str, Any] = {"drug_name": product, "drug_ingredient": product}
    if channel in ("carry", "online"):
        facts["channel"] = channel
    if quantity:
        facts["quantity"] = quantity
        facts["quantity_unit"] = str(args.get("unit") or "병")
    if args.get("purpose"):
        facts["purpose"] = str(args["purpose"])
    if args.get("prescription"):
        facts["prescription"] = str(args["prescription"])

    result = assess(query, facts, store=store, client_id=client_id, tier=tier,
                    limit=int(args.get("limit", 3)), live=live)
    screening = result.get("drug_screening")
    if screening is None:  # 의약품 힌트가 없는 입력이면 직접 스크리닝해 블록을 반드시 만든다
        screening = drugs.assess(query, facts)
        result["drug_screening"] = screening
    prescription = str(args.get("prescription") or "").strip().lower()
    if prescription and screening.get("matches"):
        screening["prescription_status"] = prescription
        screening.setdefault("guidance_ko", []).append(
            "처방전 유무는 6병·3개월분 자가사용 판단의 소명자료로 쓰이지만,"
            " 마약류·원료물질·요건확인 대상 성분에는 그 자체로 반입 근거가 되지 않습니다."
        )
    result["drug_import_check"] = {
        "product_name": product,
        "state": screening.get("state"),
        "schedule_version": screening.get("schedule_version"),
        "schedule_generated_on": screening.get("schedule_generated_on"),
        "checked_counts": screening.get("checked_counts"),
        "channel": screening.get("channel"),
        "quantity": screening.get("quantity"),
        "self_use_status": screening.get("self_use_status"),
        "self_use_rule": screening.get("self_use_rule"),
        "coverage_ko": screening.get("coverage_ko"),
        "api_candidates": screening.get("api_candidates"),
        "official_urls": screening.get("official_urls"),
    }
    return _envelope("check_drug_import", result)


def _add_rra_hint(result: Dict[str, Any], store: Any = None) -> None:
    """인증·등록번호가 없을 때: '미연결'이 아니라 '번호를 주면 조회 가능'을 안내한다."""
    from .live_api import RRA_OFFICIAL_URL, SOURCE_RRA

    guidance = result.setdefault("answer", {}).setdefault("guidance", [])
    provenance = result.get("data_provenance")
    already = False
    if isinstance(provenance, dict):
        for entry in provenance.get("sources") or []:
            if entry.get("source_id") == SOURCE_RRA:
                already = True
                entry.setdefault("state", "certificate_number_required")
                entry["official_url"] = RRA_OFFICIAL_URL
                entry["lookup_field"] = "rra_cert_no"
    if not already:
        _mark_live_provenance(result, SOURCE_RRA, state="certificate_number_required",
                              fresh=None, official_url=RRA_OFFICIAL_URL,
                              lookup_field="rra_cert_no")
    guidance.append(
        "전파 적합성평가(적합인증·적합등록)는 인증·등록번호가 있어야 실시간 확인됩니다. "
        "번호를 facts.rra_cert_no 로 알려주면 국립전파연구원 DB에서 바로 조회하고, "
        f"번호가 없으면 모델명으로 {RRA_OFFICIAL_URL} 에서 확인해야 합니다."
    )


def tool_lookup_hs_requirements(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                                live: Any = None) -> Dict[str, Any]:
    hs_code = str(args.get("hs_code", "")).strip()
    direction = args.get("direction", "import")
    if not hs_code.isdigit():
        raise ValueError("hs_code_must_be_numeric")
    query = f"HS {hs_code} 세관장확인 수입요건"
    result = assess(query, {"hs_code": hs_code, "direction": direction}, store=store,
                    client_id=client_id, tier=tier, limit=1, live=live)
    result["hs_lookup"] = {
        "hs_code": hs_code,
        "digits": len(hs_code),
        "sufficient_for_checkpoint": len(hs_code) == 10,
        "note_ko": "세관장확인대상물품 조회는 HS 10자리(품목코드) 기준이며, 0건은 '요건 없음'이 아니라 '조회되지 않음'입니다.",
    }
    if len(hs_code) < 10:
        result["verdict"]["code"] = "info_needed"
        result["verdict"]["label_ko"] = "추가 정보 필요"
        result["verdict"]["label_en"] = "More information needed"

    live_block = _customs_live(live, hs_code, direction) if len(hs_code) == 10 else None
    if live_block is not None:
        result["hs_requirements_live"] = live_block
        _mark_live_provenance(result, "customs_requirements",
                              state=str(live_block.get("state") or "error"),
                              fetched_at=str(live_block.get("checked_at") or ""),
                              fresh=bool(live_block.get("fresh", False)),
                              item_count=live_block.get("requirement_count"))
        if live_block["state"] == "live":
            if live_block["requirement_count"] > 0:
                result["verdict"]["code"] = "check_likely"
                result["verdict"]["label_ko"] = "확인 대상 가능성 높음"
                result["verdict"]["label_en"] = "Likely requires review"
                result["answer"]["guidance"].append(
                    f"관세청 세관장확인대상물품 API에서 이 HS에 대한 요건 {live_block['requirement_count']}건이 조회되었습니다. "
                    "요건별 서류·기관은 조회 결과를 참고하되 소관 기관 확인이 필요합니다."
                )
            else:
                result["verdict"]["code"] = "info_needed"
                result["verdict"]["label_ko"] = "추가 정보 필요"
                result["verdict"]["label_en"] = "More information needed"
                result["answer"]["guidance"].append(
                    "관세청 API에서 이 HS로 조회된 요건이 0건입니다. HS 10자리·수입/수출 구분을 다시 확인하거나 "
                    "「관세법 제226조에 따른 세관장확인물품 및 확인방법 지정고시」 원문을 확인해야 합니다."
                )
        else:
            result["answer"]["guidance"].append(
                "관세청 실시간 조회에 실패해 요건 목록을 제시하지 못했습니다(" 
                f"코드 {live_block.get('code') or 'n/a'}). 판정은 코퍼스·법령 근거만으로 이루어졌습니다."
            )
    apply_status(result)
    return _envelope("lookup_hs_requirements", result)


def tool_check_kc_certification(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                                live: Any = None) -> Dict[str, Any]:
    product = str(args.get("product_name", "")).strip()
    facts: Dict[str, Any] = {}
    if args.get("target_age"):
        facts["target_age"] = args["target_age"]
    if args.get("rf_tx"):
        facts["rf_tx"] = args["rf_tx"]
    if args.get("battery"):
        facts["battery_type"] = args["battery"]
    if args.get("ac_plug"):
        facts["ac_plug"] = args["ac_plug"]
    if args.get("rra_cert_no"):
        facts["rra_cert_no"] = str(args["rra_cert_no"]).strip()
    query = f"{product} KC 인증 전기용품 전기용품안전관리법"
    if args.get("target_age"):
        query += " 어린이제품"
    if args.get("rf_tx") == "yes":
        query += " 전파 적합성"
    result = assess(query, facts, store=store, client_id=client_id, tier=tier, limit=3)
    # 적합성평가 번호가 있으면 국립전파연구원 DB를 바로 조회해 붙인다(키 불필요).
    from .live_api import detect_cert_no

    cert_no = str(facts.get("rra_cert_no") or "")
    if not cert_no:
        found = detect_cert_no(query)
        cert_no = found or ""
    if cert_no:
        rra_block = _rra_live(live, cert_no, store=store)
        if rra_block is not None:
            result["rra_conformity_live"] = rra_block
            _apply_rra_result(result, rra_block)
    elif any("RF_CONFORMITY" in (finding.get("regulation_tags") or [])
             for finding in result.get("findings") or []):
        _add_rra_hint(result, store)
    apply_status(result)
    return _envelope("check_kc_certification", result)


def tool_check_food_cosmetics(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                              live: Any = None) -> Dict[str, Any]:
    product = str(args.get("product_name", "")).strip()
    kind = str(args.get("kind", "food"))
    facts: Dict[str, Any] = {}
    if args.get("purpose"):
        facts["purpose"] = args["purpose"]
    if args.get("functional"):
        facts["functional"] = args["functional"]
    kind_kr = {
        "food": "식품",
        "health_functional": "건강기능식품",
        "cosmetics": "화장품",
        "food_contact": "식품용 기구 용기 포장",
        "additive": "식품첨가물",
    }.get(kind, "식품")
    query = f"{product} {kind_kr} 수입 판매 표시 한글표시"
    result = assess(query, facts, store=store, client_id=client_id, tier=tier, limit=3, live=live)
    live_block = _mfds_live(live, product, store=store)
    if live_block is not None:
        result["food_import_live"] = live_block
        state = str(live_block.get("state") or "")
        lookup = live_block.get("import_permit_history") or {}
        item_count = lookup.get("match_count") if isinstance(lookup, dict) else None
        # 한 응답이 "live"와 "실시간 소스 연결 실패"를 동시에 말하던 모순을 없앤다.
        _mark_live_provenance(result, "mfds_import_food", state=state,
                              fetched_at=str((live_block.get("product_db") or {}).get("checked_at") or ""),
                              fresh=bool(live_block.get("fresh", state == "live")),
                              age_hours=live_block.get("age_hours"),
                              item_count=item_count)
        if state in ("live", "partial"):
            result["answer"]["guidance"].append(
                "식약처 수입식품 API에서 제품DB·수입신고 이력을 조회했습니다. "
                "조회 건수는 신고 이력의 규모를 보여줄 뿐, 이 제품의 요건 적용을 확정하지 않습니다."
            )
        elif state == "cached_fallback":
            result["answer"]["guidance"].append(
                f"식약처 수입식품 조회는 7일 TTL 캐시에서 제공되었습니다(원 조회 후 {live_block.get('age_hours', 0)}시간 경과). "
                "최신 값은 식약처 원문에서 확인해야 합니다."
            )
    return _envelope("check_food_cosmetics", result)


def tool_lookup_recall(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                       live: Any = None) -> Dict[str, Any]:
    from . import recall_index

    brand = str(args.get("brand", "")).strip()
    model = str(args.get("model", "")).strip()
    product = str(args.get("product_name", "")).strip()
    category = str(args.get("category", "")).strip()
    keywords = [k for k in (brand, model, product, category) if k]
    local = recall_index.summary(store)
    if local["items"] > 0:
        matches = recall_index.search(store, keywords, model=model, limit=int(args.get("limit", 5)))
        return _envelope("lookup_recall", {
            "verdict": {
                "code": "check_likely" if matches else "info_needed",
                "label_ko": "리콜 이력 확인됨" if matches else "추가 정보 필요",
                "label_en": "Recall history found" if matches else "More information needed",
                "determinative": False,
            },
            "recall": {
                "brand": brand,
                "model": model,
                "product_name": product,
                "query_keywords": keywords,
                "state": "local_index" if matches else "local_index_no_match",
                "fresh": False,
                "match_count": len(matches),
                "matches": matches,
                "coverage": {
                    "items": local["items"],
                    "first_registered_on": local["first_registered_on"],
                    "last_registered_on": local["last_registered_on"],
                    "loaded_at": local["loaded_at"],
                    "dataset": "산업통상부_국가기술표준원_제품안전_국내리콜정보(data.go.kr 15040696, 이용허락범위 제한 없음)",
                },
                "stats_recent": recall_index.stats_table(store)[:6],
                "note_ko": local["coverage_note_ko"],
                "official_url": "https://www.safetykorea.kr",
            },
            "disclaimer_ko": "본 조회는 사전 참고용이며, 리콜 여부의 최종 확인은 제품안전정보센터 및 제조·수입사 책임입니다.",
        })
    gateway = SourceGateway(store)
    snapshot = gateway.get("kats_product_safety", f"{brand}|{model}")
    if snapshot["state"] == "unavailable":
        return _envelope("lookup_recall", {
            "verdict": {
                "code": "info_needed",
                "label_ko": "추가 정보 필요",
                "label_en": "More information needed",
                "determinative": False,
            },
            "recall": {
                "brand": brand,
                "model": model,
                "state": "source_unavailable",
                "note_ko": "실시간 리콜정보 소스가 연결되지 않아 조회 결과를 제공할 수 없습니다. 국가기술표준원 제품안전정보센터에서 모델명으로 직접 확인이 필요합니다.",
                "official_url": "https://www.safetykorea.kr",
                "data_source": "산업통상부 국가기술표준원_제품 안전인증 및 리콜 정보(data.go.kr 15116894, 이용허락범위 제한 없음)",
            },
            "disclaimer_ko": "본 조회는 사전 참고용이며, 리콜 여부의 최종 확인은 제품안전정보센터 및 제조·수입사 책임입니다.",
        })
    return _envelope("lookup_recall", {
        "verdict": {"code": "info_needed", "label_ko": "추가 정보 필요", "label_en": "More information needed"},
        "recall": {
            "brand": brand,
            "model": model,
            "state": snapshot["state"],
            "fresh": snapshot["fresh"],
            "age_hours": snapshot["age_hours"],
            "matches": snapshot.get("data"),
        },
    })


def tool_get_legal_basis(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                         live: Any = None) -> Dict[str, Any]:
    law = str(args.get("law", "")).strip()
    article = str(args.get("article", "")).strip()
    corpus = load_corpus()
    hits: List[Dict[str, Any]] = []
    for trap in corpus.traps:
        for basis in trap.legal_basis:
            if law and law not in basis.law:
                continue
            if article and article not in basis.article:
                continue
            item = basis.to_dict()
            item["case_id"] = trap.id
            if item not in hits:
                hits.append(item)
    payload: Dict[str, Any] = {
        "query": {"law": law, "article": article},
        "match_count": len(hits),
        "basis": hits,
        "note_ko": "인용문은 요지 발췌이며, 조문 전체는 원문 URL에서 확인해야 합니다. 출처 표시 없이 재배포할 수 없습니다.",
        "checked_at": iso(now_kst()),
    }
    names = _unique([h["law"] for h in hits]) if law else []
    live_block = _law_live(live, names or ([law] if law else []), article=article, store=store)
    if live_block is not None:
        payload["law_live"] = live_block
    return _envelope("get_legal_basis", payload)


def tool_get_compliance_trends(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                               live: Any = None) -> Dict[str, Any]:
    """일일 스냅샷 기반 리콜·행정처분 시계열 추이(읽기 전용).

    전일 대비 신규/변경/삭제 건수와, 리콜 등록일·처분 확정일 기준 최근 N일 급증
    품목군·위해유형·위반법령을 함께 돌려준다. 스냅샷이 없으면 0을 꾸며내지 않고
    '스냅샷 없음'을 그대로 밝힌다.
    """
    from . import snapshots
    from .policy import DISCLAIMER_EN, DISCLAIMER_KO

    try:
        days = int(args.get("days") or snapshots.DEFAULT_TREND_DAYS)
    except (TypeError, ValueError) as exc:
        raise ValueError("days_must_be_integer") from exc
    days = max(1, min(days, snapshots.MAX_TREND_DAYS))
    source = str(args.get("source") or "all").strip().lower()
    if source not in ("all",) + tuple(snapshots.SOURCES):
        raise ValueError("source_must_be_all_or_known_source")
    try:
        limit = int(args.get("limit") or snapshots.TOP_LIMIT)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit_must_be_integer") from exc
    as_of = str(args.get("as_of") or "").strip() or None
    data = snapshots.trends(store, days=days, today=as_of, source=source, limit=limit)

    window = data["current_window"]
    series = data["series"]
    latest = data.get("last_observed_diff")
    recall_total = int(window.get("recall_total") or 0)
    disposition_total = int(window.get("disposition_total") or 0)
    previous_total = (int(window.get("previous_recall_total") or 0)
                      + int(window.get("previous_disposition_total") or 0))
    current_total = recall_total + disposition_total
    if current_total or previous_total:
        headline = (
            f"최근 {days}일 이벤트 {current_total}건(리콜 {recall_total}건·처분 {disposition_total}건), "
            f"직전 같은 기간 {previous_total}건으로 집계되었습니다."
        )
    else:
        reference = data.get("reference") or {}
        headline = (
            f"최근 {days}일에는 등록되거나 처분된 리콜·행정처분 이벤트가 조회되지 않았습니다"
            + (f"(데이터 기준일 {reference.get('as_of')} 기준 참고 창을 함께 제공)."
               if reference.get("as_of") else ".")
        )

    guidance: List[str] = [headline]
    if latest:
        guidance.append(
            f"{latest['day']} 스냅샷에서는 전일 대비 신규 {latest['new']}건·변경 "
            f"{latest['changed']}건·삭제 {latest['removed']}건이 확인되었습니다."
        )
    else:
        guidance.append(
            "저장된 일일 스냅샷이 없어 전일 대비 값은 제공하지 않습니다. "
            "스냅샷을 적재한 뒤부터 일별 신규·변경·삭제가 집계됩니다."
        )
    for row in (window.get("by_category") or [])[:3]:
        guidance.append(
            f"리콜 품목군 '{row['key']}' — 최근 {days}일 {row['count']}건"
            f"(직전 {row['previous_count']}건, 증감 {row['delta']:+d})."
        )
    for row in (window.get("by_law") or [])[:2]:
        guidance.append(
            f"행정처분 위반법령 '{row['key']}' — 최근 {days}일 {row['count']}건"
            f"(직전 {row['previous_count']}건, 증감 {row['delta']:+d})."
        )
    reference = data.get("reference") or {}
    if reference.get("as_of"):
        guidance.append(
            f"요청 기간에 이벤트가 0건이라 데이터 기준일 {reference['as_of']} 기준 "
            f"최근 {days}일을 참고 창으로 함께 계산했습니다. 0건은 '급증 없음'을 뜻하지 않습니다."
        )

    payload: Dict[str, Any] = {
        "verdict": {
            "code": "info_needed",
            "label_ko": "시계열 추이 참고",
            "label_en": "Trend reference",
            "determinative": False,
            "note_ko": (
                "추이는 관측된 스냅샷과 공개 데이터의 이벤트 날짜를 센 값이며, "
                "향후 발생 건수나 위험도를 예측하지 않습니다."
            ),
        },
        "answer": {"headline": headline, "guidance": guidance},
        "trends": data,
        "evidence": [],
        "missing_information": [] if series else ["snapshot"],
        "next_actions": [
            "일별 적재를 자동화하려면 `python -m import_compliance.snapshots --take` 를 매일 실행하세요.",
            "급증 품목군은 리콜 등록일 기준이므로, 실제 시장 상황은 제품안전정보센터·식약처 원문을 확인하세요.",
            "특정 품목·업소 이력은 `lookup_recall`·`lookup_mfds_disposition` 으로 따로 조회하세요.",
        ],
        "data_provenance": {
            "policy": "원본 API 1:1 재전송 금지 · 로컬 스냅샷 지문 집계 · 개인정보 필드 미포함",
            "sources": [
                {"source_id": src, "label_ko": snapshots.SOURCE_LABEL_KO[src],
                 "state": "local_snapshot" if series else "no_snapshot"}
                for src in (snapshots.SOURCES if source == "all" else (source,))
            ],
            "checked_at": iso(now_kst()),
            "schema": snapshots.TRENDS_SCHEMA,
        },
        "disclaimer": {"ko": DISCLAIMER_KO, "en": DISCLAIMER_EN},
        "scope_limits_ko": SCOPE_LIMITS_KO,
        "tier": {"name": tier, "boundaries": TIER_BOUNDARIES["free"],
                 "paid_notice_ko": PAID_TIER_NOTICE_KO},
        "client_id": client_id,
    }
    apply_status(payload)
    return _envelope("get_compliance_trends", payload)


def _unique(values: List[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def tool_explain_trap(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                      live: Any = None) -> Dict[str, Any]:
    case_id = str(args.get("case_id", "")).strip().upper()
    corpus = load_corpus()
    trap = corpus.by_id(case_id)
    if trap is None:
        raise ValueError("case_not_found")
    return _envelope("explain_trap", {
        "case_id": trap.id,
        "title": trap.title,
        "issue_ko": trap.issue_ko,
        "category": trap.category,
        "scenario": trap.scenario,
        "common_ai_wrong": trap.common_ai_wrong,
        "correct_answer": trap.correct_answer,
        "default_verdict": trap.default_verdict,
        "legal_basis": [b.to_dict() for b in trap.legal_basis],
        "next_steps": trap.next_steps,
        "notes": trap.notes,
        "corpus_version": corpus.version,
    })


def _guide_meta() -> Dict[str, Any]:
    try:
        from . import guides

        return guides.catalog_meta()
    except Exception:  # noqa: BLE001 - 카탈로그 문제가 메타 응답을 막지 않게
        return {}


def _snapshot_sources() -> List[str]:
    try:
        from . import snapshots

        return list(snapshots.SOURCES)
    except Exception:  # noqa: BLE001
        return []


def _snapshot_days(store: Store) -> int:
    try:
        from . import snapshots

        return len(snapshots.days(store))
    except Exception:  # noqa: BLE001
        return 0


def tool_get_service_meta(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                          live: Any = None) -> Dict[str, Any]:
    from . import advertising, drugs, labeling, mfds_dispositions

    corpus = load_corpus()
    testset = testset_meta()
    schedules = drugs.load_schedules()
    return _envelope("get_service_meta", {
        "service": "CLNS",
        "service_subtitle_en": "PRODUCT COMPLIANCE INTELLIGENCE · KOREA",
        "service_subtitle_ko": "복잡한 한국 수입 규제를 10초 만에 확인",
        "service_slogan": "Clearance, simplified.",
        "service_axes": ["CLNS Check", "CLNS Intelligence", "CLNS API & MCP"],
        "stage": "무료 베타 · 결제창 없음",
        "corpus": {"version": corpus.version, "verified_on": corpus.verified_on, "cases": len(corpus.traps)},
        "verdict_levels": ["check_likely", "info_needed", "low_risk"],
        "schema_version": SCHEMA_VERSION,
        "assessment_status_levels": list(ASSESSMENT_STATUS_ORDER),
        "destination": DEFAULT_DESTINATION,
        "jurisdiction": DEFAULT_JURISDICTION,
        "regulation_tags": REGULATION_TAGS,
        "testset": testset,
        "drug_testset": testset_meta(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "drug_testset.json")),
        "drug_schedules": {
            "version": schedules.get("schedule_version"),
            "generated_on": schedules.get("generated_on"),
            "law": schedules.get("decree"),
            "controlled_substances": len(schedules.get("substances") or []),
            "precursors": len(schedules.get("precursors") or []),
            "self_use_limit": drugs.SELF_USE_RULE,
            "api_candidates": [{"dataset_id": row["dataset_id"], "name_ko": row["name_ko"],
                                "state": row["state"]} for row in drugs.API_CANDIDATES],
        },
        "ad_labeling": {
            "rules": len(advertising.CLAIM_RULES),
            "rule_ids": [rule["id"] for rule in advertising.CLAIM_RULES],
            "risk_levels": ["high", "caution"],
            "product_types": [{"code": code, "label_ko": meta["label_ko"]}
                              for code, meta in advertising.PRODUCT_TYPES.items()],
            "label_items": {code: len(rows) for code, rows in labeling.CHECKLISTS.items()},
            "checked_on": advertising.VERIFIED_ON,
            "ad_content_standard_ko": "식품등의 부당한 표시 또는 광고의 내용 기준(식약처고시 제2025-79호)",
        },
        "guides": {
            "path": "/guides/",
            "count": _guide_meta().get("count"),
            "verified_on": _guide_meta().get("verified_on"),
            "page_pattern": "/guides/{slug}",
            "structured_data": ["FAQPage", "WebPage", "BreadcrumbList"],
            "links": ["/", "/mcp", "/v1/tools/{tool}"],
        },
        "trends": {
            "endpoint": "/v1/trends?days=30",
            "tool": "get_compliance_trends",
            "snapshot_sources": list(_snapshot_sources()),
            "snapshot_available_days": _snapshot_days(store),
            "note_ko": "일일 스냅샷은 리콜·행정처분·금지성분·성분 사전의 항목별 지문을 일자 단위로 쌓은 것으로, 전일 대비 신규/변경/삭제와 최근 N일 급증을 계산합니다.",
        },
        "mfds_dispositions": {
            "datasets": [{"dataset_id": meta["dataset_id"], "name_ko": meta["name_ko"],
                          "industry_ko": meta["industry_ko"]}
                         for meta in mfds_dispositions.DATASETS.values()],
            "fallback_patterns": len(mfds_dispositions.BUILTIN_PATTERNS),
            "pii_policy_ko": "원본의 업소명ㆍ대표자명ㆍ전화번호ㆍ주소ㆍ인허가번호는 저장하지 않습니다.",
        },
        "tiers": TIER_BOUNDARIES,
        "free_tier": {"monthly_calls": FREE_MONTHLY_CALLS, "used": store.quota_used(client_id)},
        "paid_notice_ko": PAID_TIER_NOTICE_KO,
        "scope_limits_ko": SCOPE_LIMITS_KO,
        "live_sources": (
            live.capabilities() if live is not None else
            {"customs_checkpoint": False, "mfds_import_permit": False,
             "mfds_product_db": False, "law_search": False,
             "rra_conformity": False, "mfds_drug_api": False}
        ),
        "principles": [
            "원본 API 1:1 재전송 금지",
            "다기관 결합·정규화 판정만 제공",
            "근거 법령·시행일·원문 URL 강제 포함",
            "국·영문 면책 강제 포함",
        ],
        "attribution_ko": "출처: 관세청 / 식품의약품안전처 / 산업통상부 국가기술표준원 / 법제처 국가법령정보센터",
    })


PRODUCT_KIND_KO = {
    "general_food": "식품",
    "health_functional_food": "건강기능식품",
    "cosmetics": "화장품",
    "functional_cosmetics": "기능성화장품",
}


def _ad_finding(entry: Dict[str, Any]) -> Dict[str, Any]:
    """광고 검수 결과를 기존 findings 와 같은 모양으로 바꾼다(UI·후속 처리 호환)."""
    verdict = "check_likely" if entry.get("risk") == "high" else "info_needed"
    return {
        "case_id": entry.get("rule_id"),
        "title": entry.get("name_ko"),
        "issue_ko": "광고 문구에서 " + ", ".join(entry.get("matched_phrases") or []) + " 표현이 탐지됨",
        "category": "advertising",
        "regulation_tags": [],
        "verdict": verdict,
        "verdict_label_ko": VERDICT_LABEL_KO[verdict],
        "verdict_label_en": VERDICT_LABEL_EN[verdict],
        "confidence": 0.8 if verdict == "check_likely" else 0.6,
        "reason": "광고문구 패턴 대조(위험도 " + str(entry.get("risk_label_ko")) + ")",
        "matched_signals": list(entry.get("matched_phrases") or []),
        "missing_inputs": [],
        "misconception": "",
        "explanation": entry.get("why_ko", ""),
        "scenario": "",
        "next_steps": [entry.get("safer_ko", "")],
        "notes": entry.get("category_note_ko", ""),
        "legal_basis": list(entry.get("legal_basis") or []),
    }


def _label_finding(label_check: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """라벨 누락을 findings 모양으로 만든다(누락이 있을 때만)."""
    missing = label_check.get("missing") or []
    conditional = label_check.get("conditional_missing") or []
    if not missing and not conditional:
        return None
    verdict = "check_likely" if missing else "info_needed"
    target = missing or conditional
    basis: List[Dict[str, str]] = []
    for row in label_check.get("checklist") or []:
        if row.get("label_ko") in target:
            basis.append(row.get("legal_basis") or {})
    return {
        "case_id": "LABEL-01",
        "title": "한글표시사항 필수 항목 점검",
        "issue_ko": "입력한 라벨에서 확인되지 않은 항목: " + ", ".join(target[:6]),
        "category": "label",
        "regulation_tags": ["KOREAN_LABELING"],
        "verdict": verdict,
        "verdict_label_ko": VERDICT_LABEL_KO[verdict],
        "verdict_label_en": VERDICT_LABEL_EN[verdict],
        "confidence": 0.75 if missing else 0.55,
        "reason": "필수 표시항목 대조",
        "matched_signals": target[:6],
        "missing_inputs": [],
        "misconception": "",
        "explanation": label_check.get("verdict_note_ko", ""),
        "scenario": "",
        "next_steps": label_check.get("next_actions") or [],
        "notes": "",
        "legal_basis": [b for b in basis if b],
    }


def tool_check_ad_labeling(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                           live: Any = None) -> Dict[str, Any]:
    """과대광고 문구 검수 + 한글표시사항 필수항목 점검을 한 번에 수행한다.

    품목 유형(일반식품/건강기능식품/화장품/기능성화장품)에 따라 허용·금지 기준을 다르게
    적용하고, 같은 문구가 유형별로 어떻게 달라지는지(`category_comparison`)도 함께 보여준다.
    """
    from . import advertising, labeling

    product_name = str(args.get("product_name") or "").strip()
    ad_copy = str(args.get("ad_copy") or args.get("ad_text") or "").strip()
    label_text = str(args.get("label_text") or "").strip()
    if len(ad_copy) > 4000:
        raise ValueError("ad_copy_too_long")
    if len(label_text) > 4000:
        raise ValueError("label_text_too_long")
    label_items = args.get("label_items")
    if label_items is not None and not isinstance(label_items, dict):
        raise ValueError("label_items_must_be_object")
    label_items = label_items or {}
    probe = " ".join(part for part in (product_name, ad_copy, label_text) if part)
    if not probe and not label_items:
        raise ValueError("ad_copy_or_label_text_required")
    if ad_copy and len(ad_copy) < 2:
        raise ValueError("ad_copy_too_short")
    if label_text and len(label_text) < 2:
        raise ValueError("label_text_too_short")

    product_type = advertising.normalize_product_type(args.get("product_type"), probe)
    limit = max(1, min(int(args.get("limit", 8) or 8), 20))
    ad_review = advertising.review(ad_copy, product_type, functional=args.get("functional"), limit=limit)
    label_check = labeling.check(product_type, label_text=label_text, provided=label_items,
                                 imported=args.get("imported"))

    kind_ko = PRODUCT_KIND_KO.get(product_type, "식품")
    if product_type in ("cosmetics", "functional_cosmetics"):
        query = " ".join(part for part in (
            product_name or "화장품", "화장품", "수입 판매 기재사항 광고",
        ) if part)
    else:
        query = " ".join(part for part in (
            product_name or kind_ko, kind_ko, "수입 판매 표시 광고 한글표시",
        ) if part)
    facts: Dict[str, Any] = {"purpose": str(args.get("purpose") or "resale")}
    if args.get("functional") is not None:
        facts["functional"] = str(args["functional"])
    if args.get("imported") is not None:
        facts["imported"] = str(args["imported"])
    result = assess(query, facts, store=store, client_id=client_id, tier=tier, limit=3, live=live)

    findings = list(result.get("findings") or [])
    ad_findings = [_ad_finding(entry) for entry in ad_review.get("findings") or []]
    for finding in ad_findings:
        finding["regulation_tags"] = [advertising.tag_for_rule(
            str(finding.get("case_id") or ""), product_type)]
    findings.extend(ad_findings)
    label_finding = _label_finding(label_check)
    if label_finding is not None:
        findings.append(label_finding)

    codes = [str((result.get("verdict") or {}).get("code") or "info_needed")]
    if ad_copy:
        codes.append(str(ad_review.get("verdict") or "info_needed"))
    if label_text or label_items:
        codes.append(str(label_check.get("verdict") or "info_needed"))
    overall = max(codes, key=lambda code: VERDICT_SEVERITY.get(code, 1))
    result["verdict"] = {"code": overall, "label_ko": VERDICT_LABEL_KO[overall],
                         "label_en": VERDICT_LABEL_EN[overall], "determinative": False,
                         "note_ko": "광고·표시 검수는 문구·라벨 패턴 대조 결과이며, 최종 판단은 식약처 기준과 전문가 검토를 따릅니다."}
    result["findings"] = findings
    result["regulation_tags"] = tags_for_findings(findings)

    answer = result.setdefault("answer", {})
    if ad_review.get("risk_high"):
        answer["headline"] = "광고 문구에서 금지 위험 표현이 확인되었습니다. 문구를 수정하고 근거를 확인하세요."
    elif label_check.get("missing"):
        answer["headline"] = "한글표시사항 필수 항목의 누락 가능성이 있습니다. 라벨을 보완하세요."
    guidance = answer.setdefault("guidance", [])
    if ad_copy:
        guidance.extend(advertising.summarize(ad_review))
    if label_text or label_items:
        guidance.extend(labeling.summarize(label_check))
    if not ad_copy:
        guidance.append("상세페이지·상품명 등 광고 문구를 ad_copy 로 넣으면 유형별 금지 표현을 함께 검수합니다.")
    if not label_text and not label_items:
        guidance.append("라벨 문구를 label_text 로 넣으면 필수 표시항목 누락을 대조합니다.")

    evidence = list(result.get("evidence") or [])
    seen = {(row.get("law"), row.get("article")) for row in evidence}
    extra_basis: List[Dict[str, str]] = []
    for finding in ad_findings + ([label_finding] if label_finding else []):
        extra_basis.extend(finding.get("legal_basis") or [])
    for row in extra_basis:
        key = (row.get("law"), row.get("article"))
        if key in seen or not row.get("law"):
            continue
        seen.add(key)
        evidence.append(row)
    result["evidence"] = evidence

    missing = [m for m in result.get("missing_information") or []]
    if not ad_copy and "ad_copy" not in missing:
        missing.append("ad_copy")
    if not label_text and not label_items and "label_text" not in missing:
        missing.append("label_text")
    result["missing_information"] = missing

    result["ad_review"] = ad_review
    result["labeling_check"] = label_check
    result["ad_labeling"] = {
        "product_type": product_type,
        "product_type_label_ko": advertising.product_type_label(product_type),
        "ad_copy_chars": len(ad_copy),
        "label_text_chars": len(label_text),
        "ad_finding_count": len(ad_findings),
        "ad_risk_high": ad_review.get("risk_high"),
        "ad_risk_caution": ad_review.get("risk_caution"),
        "label_missing_count": len(label_check.get("missing") or []),
        "label_completion_rate": label_check.get("completion_rate"),
        "combined_verdict": overall,
    }
    result["next_actions"] = (label_check.get("next_actions") or []) + list(result.get("next_actions") or [])[:2] + [
        "광고 문구는 근거자료(시험성적서ㆍ인증번호)와 함께 보관하세요(식품표시광고법 제9조 실증 의무).",
    ]
    apply_status(result)
    return _envelope("check_ad_labeling", result)


def tool_lookup_mfds_disposition(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                                 live: Any = None) -> Dict[str, Any]:
    """식약처 행정처분 이력(식품제조가공업ㆍ식품판매업)을 조회한다.

    실시간 API → 로컬 적재분 → 내장 대표 적발 패턴 순으로 폴백하고, 원본의 개인정보
    (업소명ㆍ대표자ㆍ연락처ㆍ주소ㆍ인허가번호)는 읽지 않고 버린다.
    """
    from . import mfds_dispositions
    from .policy import DISCLAIMER_EN, DISCLAIMER_KO

    raw_industry = str(args.get("industry") or "all").strip().lower()
    if raw_industry not in mfds_dispositions.INDUSTRY_ALIASES:
        raise ValueError("industry_must_be_manufacturing_sales_or_all")
    confirmed_on = str(args.get("confirmed_on") or "").strip()
    if confirmed_on and len("".join(ch for ch in confirmed_on if ch.isdigit())) != 8:
        raise ValueError("confirmed_on_must_be_yyyymmdd")
    rows = max(1, min(int(args.get("rows", 20) or 20), 100))
    limit = max(1, min(int(args.get("limit", 5) or 5), 20))
    block = mfds_dispositions.lookup(store, live, industry=raw_industry,
                                     keyword=str(args.get("keyword") or "")[:60],
                                     license_no=str(args.get("license_no") or "").strip(),
                                     confirmed_on=confirmed_on, rows=rows, limit=limit)

    basis_by_law = _disposition_basis()
    findings: List[Dict[str, Any]] = []
    for match in block.get("matches") or []:
        law = str(match.get("law_reference") or "")
        basis = next((row for key, row in basis_by_law.items() if key in law), None)
        pattern = next((p for p in block.get("patterns") or []
                        if str(p.get("law_reference", "")).split("(")[0] in law), None)
        findings.append({
            "case_id": "MFDS-" + str(match.get("disposition_seq") or "0"),
            "title": (law or "행정처분") + " 위반",
            "issue_ko": str(match.get("violation_summary") or ""),
            "category": "disposition",
            "regulation_tags": ["MFDS_DISPOSITION"],
            "verdict": "check_likely",
            "verdict_label_ko": VERDICT_LABEL_KO["check_likely"],
            "verdict_label_en": VERDICT_LABEL_EN["check_likely"],
            "confidence": 0.8,
            "reason": "식약처 행정처분결과 조회",
            "matched_signals": [str(match.get("disposition_type") or "")],
            "missing_inputs": [],
            "misconception": "",
            "explanation": str(match.get("disposition_summary") or ""),
            "scenario": "",
            "next_steps": [pattern.get("check_ko", "")] if pattern else [],
            "notes": "개인정보(업소명ㆍ대표자ㆍ연락처ㆍ주소ㆍ인허가번호)는 표시하지 않습니다.",
            "legal_basis": [basis] if basis else [],
        })

    state = block.get("state")
    if not findings and block.get("patterns"):
        top = block["patterns"][:3]
        first = top[0]
        basis = next((row for key, row in basis_by_law.items()
                      if key in str(first.get("law_reference", ""))), None)
        findings.append({
            "case_id": "MFDS-PATTERN",
            "title": "업종별 빈발 위반 유형(내장 패턴)",
            "issue_ko": ", ".join(str(p.get("name_ko")) for p in top),
            "category": "disposition",
            "regulation_tags": ["MFDS_DISPOSITION"],
            "verdict": "info_needed",
            "verdict_label_ko": VERDICT_LABEL_KO["info_needed"],
            "verdict_label_en": VERDICT_LABEL_EN["info_needed"],
            "confidence": 0.5,
            "reason": "실시간 조회 불가로 내장 패턴 사전 적용",
            "matched_signals": [str(p.get("pattern_id")) for p in top],
            "missing_inputs": [],
            "misconception": "",
            "explanation": block.get("coverage_ko", ""),
            "scenario": "",
            "next_steps": [str(p.get("check_ko")) for p in top],
            "notes": "개별 업소 이력이 아니라 업종별 빈발 위반 유형입니다.",
            "legal_basis": [basis] if basis else [],
        })

    if findings and block.get("source") != "pattern_fallback":
        headline = "해당 조건에서 행정처분 이력이 조회되었습니다. 위반법령과 처분유형을 확인하세요."
        overall = "check_likely"
    elif state == "approval_pending":
        headline = "이 데이터셋은 활용신청 승인 전파 전입니다. 내장 대표 적발 패턴으로 안내합니다."
        overall = "info_needed"
    elif block.get("source") == "pattern_fallback" and state == "live":
        headline = "실시간 조회는 되었지만 이 조건의 결과가 0건이라 내장 대표 적발 패턴으로 안내합니다."
        overall = "info_needed"
    elif block.get("source") == "pattern_fallback" or state in ("corpus_only", "key_missing", "error"):
        headline = "실시간 행정처분 조회가 불가능해 내장 대표 적발 패턴으로 안내합니다."
        overall = "info_needed"
    else:
        headline = "조회 결과 0건입니다. 0건은 '위반 이력 없음'을 뜻하지 않습니다."
        overall = "info_needed"

    guidance: List[str] = [headline, block.get("pii_policy_ko") or ""]
    for pattern in (block.get("patterns") or [])[:4]:
        observed = pattern.get("observed_2026_11_19")
        share = f"(2026-11-19 스냅샷 {observed}건)" if observed else ""
        guidance.append(f"{pattern['name_ko']}{share} — {pattern['check_ko']}")
    if not block.get("patterns"):
        guidance.append("업종을 manufacturing 또는 sales 로 지정하면 해당 업종의 대표 적발 패턴을 함께 보여줍니다.")

    evidence: List[Dict[str, str]] = []
    for pattern in block.get("patterns") or []:
        law = str(pattern.get("law_reference") or "")
        basis = next((row for key, row in basis_by_law.items() if key in law), None)
        if basis and basis not in evidence:
            evidence.append(basis)

    payload: Dict[str, Any] = {
        "verdict": {"code": overall, "label_ko": VERDICT_LABEL_KO[overall],
                    "label_en": VERDICT_LABEL_EN[overall], "determinative": False,
                    "note_ko": "행정처분 이력은 과거 처분 사실이며, 현재 영업 상태나 제품 안전성을 뜻하지 않습니다."},
        "answer": {"headline": headline, "guidance": [g for g in guidance if g]},
        "findings": findings,
        "evidence": evidence,
        "regulation_tags": ["MFDS_DISPOSITION"],
        "missing_information": [] if findings else ["industry"],
        "disposition_lookup": block,
        "next_actions": [
            "처분 이력이 있는 업소와 거래할 때는 처분일ㆍ처분 종료 여부를 확인하세요.",
            "내장 패턴은 업종별 빈발 위반 유형이며 개별 업소 이력이 아닙니다.",
        ],
        "data_provenance": {
            "policy": "원본 API 1:1 재전송 금지 · 개인정보 필드 폐기 · 정규화 결과만 제공",
            "sources": [
                {"source_id": row.get("source_id"), "dataset_id": row.get("dataset_id"),
                 "state": row.get("state"), "item_count": row.get("item_count"),
                 "checked_at": row.get("checked_at"), "note_ko": row.get("note_ko")}
                for row in block.get("datasets") or []
            ] or [{"state": "corpus_only", "note_ko": "내장 패턴 사전만 사용"}],
            "checked_at": iso(now_kst()),
        },
        "disclaimer": {"ko": DISCLAIMER_KO, "en": DISCLAIMER_EN},
        "scope_limits_ko": SCOPE_LIMITS_KO,
        "tier": {"name": tier, "boundaries": TIER_BOUNDARIES["free"], "paid_notice_ko": PAID_TIER_NOTICE_KO},
        "client_id": client_id,
    }
    apply_status(payload)
    return _envelope("lookup_mfds_disposition", payload)


def _disposition_basis() -> Dict[str, Dict[str, str]]:
    """행정처분 단골 위반법령의 근거 조문(2026-11-19 법제처 API 조회본)."""
    law_url = "https://www.law.go.kr/법령/식품위생법"

    def _row(article: str, title: str, quote: str) -> Dict[str, str]:
        return {"law": "식품위생법", "article": article, "effective_date": "2026-10-08",
                "url": law_url, "quote": quote, "verified_on": "2026-11-19"}

    return {
        "제36조": _row("제36조", "시설기준",
                      "다음의 영업을 하려는 자는 총리령으로 정하는 시설기준에 맞는 시설을 갖추어야 한다."),
        "제37조": _row("제37조", "영업허가 등",
                      "허가받은 사항 중 대통령령으로 정하는 중요한 사항을 변경할 때에도 허가를 받아야 하고, "
                      "폐업하거나 경미한 사항을 변경할 때에는 신고하여야 한다."),
        "제31조": _row("제31조", "자가품질검사 의무",
                      "식품등을 제조ㆍ가공하는 영업자는 총리령으로 정하는 바에 따라 기준과 규격에 맞는지를 "
                      "검사하여야 한다."),
        "제44조": _row("제44조", "영업자 등의 준수사항",
                      "영업자와 그 종업원은 영업의 위생관리와 질서유지, 국민의 보건위생 증진을 위하여 "
                      "영업의 종류에 따라 정해진 사항을 지켜야 하며, 소비기한이 경과된 제품을 판매 목적으로 "
                      "보관ㆍ진열해서는 아니 된다."),
        "제7조": _row("제7조", "기준 및 규격",
                     "식품의약품안전처장은 판매를 목적으로 하는 식품 또는 식품첨가물에 관한 제조ㆍ가공 "
                     "기준과 성분에 관한 규격을 정하여 고시한다."),
        "제4조": _row("제4조", "위해식품등의 판매 등 금지",
                     "누구든지 위해식품등을 판매하거나 판매할 목적으로 제조ㆍ수입ㆍ가공ㆍ사용ㆍ저장ㆍ"
                     "운반 또는 진열하여서는 아니 된다."),
        "표시ㆍ광고에 관한 법률 제4조": {
            "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제4조제1항", "effective_date": "2025-09-19",
            "url": "https://www.law.go.kr/법령/식품등의표시ㆍ광고에관한법률",
            "quote": "식품ㆍ건강기능식품 등에는 제품명ㆍ원재료명ㆍ영업소ㆍ소비기한 등 정해진 사항을 표시하여야 한다.",
            "verified_on": "2026-11-19",
        },
        "표시ㆍ광고에 관한 법률 제8조": {
            "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제8조제1항", "effective_date": "2025-09-19",
            "url": "https://www.law.go.kr/법령/식품등의표시ㆍ광고에관한법률",
            "quote": "질병의 예방ㆍ치료 효능, 의약품 오인, 거짓ㆍ과장 등에 해당하는 표시 또는 광고를 "
                      "하여서는 아니 된다.",
            "verified_on": "2026-11-19",
        },
        "수입식품안전관리 특별법 제20조": {
            "law": "수입식품안전관리 특별법", "article": "제20조제1항", "effective_date": "2026-10-08",
            "url": "https://www.law.go.kr/법령/수입식품안전관리특별법",
            "quote": "영업자가 판매를 목적으로 수입식품등을 수입하려면 식품의약품안전청장에게 수입신고를 "
                      "하여야 한다.",
            "verified_on": "2026-11-19",
        },
    }


TOOL_DEFS: List[Dict[str, Any]] = [    {
        "name": "assess_import_case",
        "title_ko": "수입 컴플라이언스 종합 판정",
        "description_ko": "품목·상황을 자연어로 받아 수입요건·인증·표시·통관 함정을 3단계로 판정하고 근거 조항과 면책을 반환합니다.",
        "handler": tool_assess_import_case,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "품목과 상황 설명(예: '중국산 블루투스 스피커를 수입해 판매')"},
                "facts": {"type": "object", "description": "purpose(resale|self_use), channel(direct|agency), price_usd, hs_code, rra_cert_no(적합성평가 인증·등록번호), target_age 등"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 3, "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup_hs_requirements",
        "title_ko": "HS 10자리 세관장확인 요건",
        "description_ko": "HS 코드로 세관장확인대상 여부·법령·기관을 판정합니다. 6자리는 요건 판정에 부족합니다.",
        "handler": tool_lookup_hs_requirements,
        "input_schema": {
            "type": "object",
            "properties": {
                "hs_code": {"type": "string", "description": "HS 10자리 품목코드"},
                "direction": {"type": "string", "enum": ["import", "export"], "default": "import"},
            },
            "required": ["hs_code"],
        },
    },
    {
        "name": "check_kc_certification",
        "title_ko": "KC 인증 유형 판정",
        "description_ko": "전기용품·생활용품·어린이제품·전파 적합성평가 중 어떤 절차가 걸리는지 판정합니다.",
        "handler": tool_check_kc_certification,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "target_age": {"type": "string", "description": "어린이제품 판단용 대상 연령"},
                "rf_tx": {"type": "string", "enum": ["yes", "no", "unknown"]},
                "battery": {"type": "string", "description": "배터리 종류/내장 여부"},
                "ac_plug": {"type": "string", "enum": ["yes", "no", "unknown"]},
                "rra_cert_no": {"type": "string", "description": "전파 적합성평가 인증·등록번호(예: R-LARN-00-0210). 있으면 국립전파연구원 DB를 즉시 조회"},
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "check_food_cosmetics",
        "title_ko": "식품·화장품·건기식 요건 판정",
        "description_ko": "수입신고·영업등록·한글표시·광고심의 등 식약처 요건을 판정합니다.",
        "handler": tool_check_food_cosmetics,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "kind": {"type": "string", "enum": ["food", "health_functional", "cosmetics", "food_contact", "additive"]},
                "purpose": {"type": "string", "enum": ["resale", "self_use"]},
                "functional": {"type": "string", "enum": ["yes", "no", "unknown"]},
            },
            "required": ["product_name", "kind"],
        },
    },
    {
        "name": "check_drug_import",
        "title_ko": "의약품·영양제 금지성분·반입 제한",
        "description_ko": "성분명·제품명(한·영)으로 마약류(마약·향정신성의약품·대마)·마약류 원료물질·국내 전용 성분 여부를 대조하고, 휴대 반입/직구와 수량을 자가사용 인정기준(6병·3개월분)과 비교해 판정합니다.",
        "handler": tool_check_drug_import,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "성분명 또는 제품명(한글·영어 모두 가능, 예: '졸피뎀', 'Zolpidem', 'Adderall')"},
                "ingredient": {"type": "string", "description": "성분명을 따로 넘길 때(있으면 product_name 보다 우선)"},
                "channel": {"type": "string", "enum": ["carry", "online", "unknown"], "default": "unknown"},
                "quantity": {"type": "integer", "minimum": 1, "description": "수량(병·정 등). 6병 기준과 대조"},
                "unit": {"type": "string", "description": "수량 단위(병·정·캡슐 등)"},
                "prescription": {"type": "string", "enum": ["yes", "no", "unknown"], "description": "처방전 보유 여부(소명자료 힌트)"},
                "purpose": {"type": "string", "enum": ["self_use", "resale"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 3, "default": 3},
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "check_ad_labeling",
        "title_ko": "과대광고·한글표시사항 검수",
        "description_ko": "상세페이지·상품명 문구와 라벨 문구를 품목 유형(일반식품/건강기능식품/화장품/기능성화장품)별로 대조해 질병 효능·의약품 오인·거짓과장·체험기·기능성 오인 등 위험 표현과 한글표시사항 누락 항목을 근거 법령·대체 표현과 함께 반환합니다.",
        "handler": tool_check_ad_labeling,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "제품명(선택). 있으면 수입요건도 함께 판정"},
                "product_type": {"type": "string",
                                 "enum": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
                                 "description": "품목 유형. 생략하면 문구·제품명에서 판단"},
                "ad_copy": {"type": "string", "description": "상세페이지·상품명·홍보 문구(최대 4,000자)"},
                "label_text": {"type": "string", "description": "라벨·한글표시사항을 텍스트로 옮긴 내용(최대 4,000자)"},
                "label_items": {"type": "object", "description": "항목별 체크(예: {'product_name': true, 'expiry_storage': false})"},
                "functional": {"type": "string", "enum": ["yes", "no", "unknown"], "description": "기능성 여부(화장품이면 기능성화장품)"},
                "imported": {"type": "string", "enum": ["yes", "no", "unknown"], "description": "수입 제품 여부"},
                "purpose": {"type": "string", "enum": ["resale", "self_use"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "required": [],
        },
    },
    {
        "name": "lookup_mfds_disposition",
        "title_ko": "식약처 행정처분 이력 조회",
        "description_ko": "식품제조가공업(15124560)·식품판매업(15124559) 행정처분결과를 조회합니다. 승인 전파 전·오프라인이면 내장 대표 적발 패턴으로 안내하며, 업소명·대표자·연락처·주소·인허가번호는 반환하지 않습니다.",
        "handler": tool_lookup_mfds_disposition,
        "input_schema": {
            "type": "object",
            "properties": {
                "industry": {"type": "string", "enum": ["manufacturing", "sales", "all"], "default": "all"},
                "keyword": {"type": "string", "description": "위반법령·위반내용 키워드(예: '표시', '자가품질검사')"},
                "license_no": {"type": "string", "description": "인허가번호로 조회할 때(응답·저장에는 남기지 않음)"},
                "confirmed_on": {"type": "string", "description": "처분확정일 YYYYMMDD"},
                "rows": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": [],
        },
    },
    {
        "name": "lookup_recall",
        "title_ko": "리콜 이력 조회",
        "description_ko": "브랜드·모델명·제품명으로 국내 리콜 이력을 조회합니다. 로컬 인덱스(국표원 15040696) 우선, 없으면 소스 미연결을 그대로 알립니다.",
        "handler": tool_lookup_recall,
        "input_schema": {
            "type": "object",
            "properties": {
                "brand": {"type": "string"},
                "model": {"type": "string"},
                "product_name": {"type": "string", "description": "제품명·품목군 키워드(예: '미니 선풍기')"},
                "category": {"type": "string", "description": "법정제품분류 키워드(예: '전지', '직류전원장치')"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["brand"],
        },
    },
    {
        "name": "get_legal_basis",
        "title_ko": "근거 조항 조회",
        "description_ko": "코퍼스에 수록된 법령 조항의 요지·시행일·원문 URL을 반환합니다.",
        "handler": tool_get_legal_basis,
        "input_schema": {
            "type": "object",
            "properties": {"law": {"type": "string"}, "article": {"type": "string"}},
            "required": ["law"],
        },
    },
    {
        "name": "explain_trap",
        "title_ko": "함정 케이스 해설",
        "description_ko": "케이스 ID(TRAP-01~22)의 시나리오, 흔한 AI 오답, 정답, 근거를 반환합니다.",
        "handler": tool_explain_trap,
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "pattern": "^TRAP-(0[1-9]|1[0-9]|2[0-2])$"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "get_compliance_trends",
        "title_ko": "리콜·행정처분 시계열 추이",
        "description_ko": "일일 스냅샷 기반으로 전일 대비 리콜·행정처분·금지성분 기준의 신규/변경/삭제 건수와, 최근 N일(기본 30) 급증 폼목군·위해유형·위반법령을 반환합니다. 스냅샷이 없으면 '없음'을 그대로 밝히며 0을 꾸며내지 않습니다.",
        "handler": tool_get_compliance_trends,
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 30,
                         "description": "조회 기간(일). 기본 30, 최대 90"},
                "source": {"type": "string",
                            "enum": ["all", "recall", "disposition", "cosmetic_prohibited",
                                     "cosmetic_restricted", "drug_schedule"],
                            "default": "all"},
                "as_of": {"type": "string", "description": "기준일 YYYY-MM-DD(기본 오늘)"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8,
                          "description": "급증 표 행 수"},
            },
            "required": [],
        },
    },
    {
        "name": "get_service_meta",
        "title_ko": "서비스·티어 정보",
        "description_ko": "코퍼스 버전, 3단계 판정 정의, 무료/유료 경계, 잔여 호출 수를 반환합니다.",
        "handler": tool_get_service_meta,
        "input_schema": {"type": "object", "properties": {}},
    },
]

TOOL_INDEX: Dict[str, Dict[str, Any]] = {d["name"]: d for d in TOOL_DEFS}

BILLABLE_TOOLS = {name for name in TOOL_INDEX if name != "get_service_meta"}

# MCP tools/list·서버 카드가 쓰는 툴 정의(스키마는 TOOL_DEFS 한 곳만 고치면 된다).
TOOL_ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}


def mcp_tools() -> List[Dict[str, Any]]:
    """MCP `tools/list` 응답용 툴 정의(이름·제목·설명·inputSchema·annotations)."""
    tools: List[Dict[str, Any]] = []
    for definition in TOOL_DEFS:
        entry: Dict[str, Any] = {
            "name": definition["name"],
            "description": definition["description_ko"],
            "inputSchema": definition["input_schema"],
            "annotations": dict(TOOL_ANNOTATIONS),
        }
        if definition.get("title_ko"):
            entry["title"] = definition["title_ko"]
            entry["annotations"]["title"] = definition["title_ko"]
        tools.append(entry)
    return tools


def mcp_manifest() -> Dict[str, Any]:
    """`GET /v1/mcp` — 사람이 읽는 툴 매니페스트(JSON-RPC 는 POST /mcp 가 담당)."""
    server_info = {
        "name": "clns",
        "version": "clns/" + PACKAGE_VERSION,
        "description": "CLNS — Korea Import Compliance MCP & API · PRODUCT COMPLIANCE INTELLIGENCE · KOREA",
    }
    return {
        "name": server_info["name"],
        "version": server_info["version"],
        "description": server_info["description"] + " · 한국 수입 규제 3단계 판정 · 근거 조항 · 면책 포함",
        "serverInfo": server_info,
        "tools": [
            {"name": d["name"], "description": d["description_ko"], "inputSchema": d["input_schema"]}
            for d in TOOL_DEFS
        ],
    }


def call_tool(name: str, arguments: Optional[Dict[str, Any]], store: Store,
              client_id: str = "anonymous", tier: str = "free", live: Any = None) -> Dict[str, Any]:
    if name not in TOOL_INDEX:
        return {"ok": False, "error": "unknown_tool", "tool": name}
    try:
        if name in BILLABLE_TOOLS:
            store.consume_quota(client_id, tier=tier)
        result = TOOL_INDEX[name]["handler"](arguments or {}, store, client_id, tier, live)
    except QuotaExceeded as exc:
        result = {"ok": False, "error": "quota_exceeded", "tool": name,
                  "message": str(exc), "free_monthly_calls": FREE_MONTHLY_CALLS}
    except ValueError as exc:
        result = {"ok": False, "error": "invalid_argument", "tool": name, "message": str(exc)}
    # 익명 일별 카운터(툴·verdict.code·0건/오류). IP·UA·쿠키·질의문은 넘기지 않는다.
    usage.record_tool(store, name, result)
    return result
