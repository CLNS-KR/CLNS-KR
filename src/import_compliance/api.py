"""API / MCP 툴 8종."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .corpus import load_corpus, normalize
from .engine import assess
from .models import VERDICT_LABEL_EN, VERDICT_LABEL_KO, VERDICT_SEVERITY
from .policy import PAID_TIER_NOTICE_KO, SCOPE_LIMITS_KO, TIER_BOUNDARIES
from .store import FREE_MONTHLY_CALLS, QuotaExceeded, SourceGateway, Store, iso, now_kst

# 공공데이터 스냅샷 TTL(문서 03 설계값: 7일). 이 시간 안의 캐시는 'cached_fallback'으로 정직하게 표시한다.
CACHE_TTL_HOURS = 24 * 7


def _envelope(tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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
    return _envelope("assess_import_case", result)


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
    query = f"{product} KC 인증 전기용품 전기용품안전관리법"
    if args.get("target_age"):
        query += " 어린이제품"
    if args.get("rf_tx") == "yes":
        query += " 전파 적합성"
    result = assess(query, facts, store=store, client_id=client_id, tier=tier, limit=3)
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


def tool_get_service_meta(args: Dict[str, Any], store: Store, client_id: str, tier: str,
                          live: Any = None) -> Dict[str, Any]:
    corpus = load_corpus()
    return _envelope("get_service_meta", {
        "service": "CLNS",
        "service_subtitle_en": "PRODUCT COMPLIANCE INTELLIGENCE · KOREA",
        "service_subtitle_ko": "복잡한 한국 수입 규제를 10초 만에 확인",
        "service_slogan": "Clearance, simplified.",
        "service_axes": ["CLNS Check", "CLNS Intelligence", "CLNS API & MCP"],
        "stage": "무료 베타 · 결제창 없음",
        "corpus": {"version": corpus.version, "verified_on": corpus.verified_on, "cases": len(corpus.traps)},
        "verdict_levels": ["check_likely", "info_needed", "low_risk"],
        "tiers": TIER_BOUNDARIES,
        "free_tier": {"monthly_calls": FREE_MONTHLY_CALLS, "used": store.quota_used(client_id)},
        "paid_notice_ko": PAID_TIER_NOTICE_KO,
        "scope_limits_ko": SCOPE_LIMITS_KO,
        "live_sources": (
            live.capabilities() if live is not None else
            {"customs_checkpoint": False, "mfds_import_permit": False,
             "mfds_product_db": False, "law_search": False}
        ),
        "principles": [
            "원본 API 1:1 재전송 금지",
            "다기관 결합·정규화 판정만 제공",
            "근거 법령·시행일·원문 URL 강제 포함",
            "국·영문 면책 강제 포함",
        ],
        "attribution_ko": "출처: 관세청 / 식품의약품안전처 / 산업통상부 국가기술표준원 / 법제처 국가법령정보센터",
    })


TOOL_DEFS: List[Dict[str, Any]] = [
    {
        "name": "assess_import_case",
        "title_ko": "수입 컴플라이언스 종합 판정",
        "description_ko": "품목·상황을 자연어로 받아 수입요건·인증·표시·통관 함정을 3단계로 판정하고 근거 조항과 면책을 반환합니다.",
        "handler": tool_assess_import_case,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "품목과 상황 설명(예: '중국산 블루투스 스피커를 수입해 판매')"},
                "facts": {"type": "object", "description": "purpose(resale|self_use), channel(direct|agency), price_usd, hs_code, target_age 등"},
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
        "description_ko": "케이스 ID(TRAP-01~20)의 시나리오, 흔한 AI 오답, 정답, 근거를 반환합니다.",
        "handler": tool_explain_trap,
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "pattern": "^TRAP-(0[1-9]|1[0-9]|20)$"}},
            "required": ["case_id"],
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
        "version": "clns/0.1",
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
        return TOOL_INDEX[name]["handler"](arguments or {}, store, client_id, tier, live)
    except QuotaExceeded as exc:
        return {"ok": False, "error": "quota_exceeded", "tool": name,
                "message": str(exc), "free_monthly_calls": FREE_MONTHLY_CALLS}
    except ValueError as exc:
        return {"ok": False, "error": "invalid_argument", "tool": name, "message": str(exc)}
