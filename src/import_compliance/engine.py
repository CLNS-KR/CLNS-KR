"""판정 엔진: 코퍼스 매칭 → 3단계 판정 → 근거·면책 포함 응답 생성."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .corpus import Corpus, load_corpus, normalize
from .models import VERDICT_LABEL_EN, VERDICT_LABEL_KO, VERDICT_SEVERITY, Finding, Trap
from .policy import (
    DISCLAIMER_EN,
    DISCLAIMER_KO,
    PAID_TIER_NOTICE_KO,
    SCOPE_LIMITS_KO,
    TIER_BOUNDARIES,
    find_conclusive_phrasing,
)
from .store import SourceGateway, Store, iso, now_kst

KST = timezone(timedelta(hours=9))

PRICE_RE = re.compile(r"(?:\$|usd\s?)(\d{1,6})|(\d{1,6})\s*(?:달러|불|usd)", re.IGNORECASE)
HS_RE = re.compile(r"\b(\d{6}|\d{8}|\d{10})\b")
MONTH_RE = re.compile(r"(20\d{2})-(\d{2})")


def _infer_facts(query: str, facts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """질의문에서 확인 가능한 사실만 추론한다. 추론 불가는 비워 둔다."""
    norm = normalize(query)
    out: Dict[str, Any] = dict(facts or {})

    if "purpose" not in out:
        if any(k in norm for k in ("판매", "되팔", "유통", "팔려", "판매할", "판매용")):
            out["purpose"] = "resale"
        elif any(k in norm for k in ("자가소비", "자가사용", "직접 쓸", "개인 사용")):
            out["purpose"] = "self_use"

    if "channel" not in out:
        if "구매대행" in norm or "배송대행" in norm:
            out["channel"] = "agency"
        elif "직구" in norm or "직접 구매" in norm or "직접구매" in norm:
            out["channel"] = "direct"

    if "price_usd" not in out:
        match = PRICE_RE.search(norm)
        if match:
            out["price_usd"] = int(match.group(1) or match.group(2))

    if "hs_code" not in out:
        match = HS_RE.search(norm)
        if match:
            out["hs_code"] = match.group(1)

    if "nicotine" not in out and "니코틴" in norm:
        out["nicotine"] = "no" if "무니코틴" in norm else "yes"

    if "rf_tx" not in out and any(k in norm for k in ("블루투스", "와이파이", "무선", "wi-fi", "wifi")):
        out["rf_tx"] = "yes"

    if "ac_plug" not in out:
        if "어댑터" in norm or "아답터" in norm or "충전기" in norm:
            out["ac_plug"] = "unknown"

    return out


def _condition_satisfied(condition: Dict[str, List[str]], norm: str) -> bool:
    all_of = condition.get("all_of", [])
    none_of = condition.get("none_of", [])
    if all_of and not all(k in norm for k in all_of):
        return False
    if any(k in norm for k in none_of):
        return False
    return True


def _required_satisfied(req, facts: Dict[str, Any], norm: str) -> bool:
    value = facts.get(req.field)
    if value in (None, "", "unknown"):
        return False
    # 세관장확인 조회는 HS 10자리가 있어야 충족(6자리는 요건이 갈림)
    if req.field == "hs_code":
        return len(str(value)) == 10
    return True


def _apply_fact_rules(rules: List[Dict[str, Any]], facts: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """사용자가 준 사실관계(facts)로 쟁점을 낮출 수 있는 규칙을 적용한다.

    규칙은 판정을 낮추는 데만 쓴다(예: rf_tx=no → 전파법 쟁점 low_risk).
    """
    for rule in rules or []:
        field = str(rule.get("field", "")).strip()
        if not field:
            continue
        value = facts.get(field)
        if value in (None, "", "unknown"):
            continue
        if str(value).strip().lower() != str(rule.get("equals", "")).strip().lower():
            continue
        verdict = str(rule.get("verdict", "info_needed"))
        if verdict not in VERDICT_SEVERITY:
            continue
        return {"verdict": verdict, "reason": str(rule.get("reason") or "사실관계 반영")}
    return None


def _match_traps(corpus: Corpus, norm: str) -> List[Tuple[Trap, List[str]]]:
    """1차 신호 3개 중 하나가 맞거나, 신호가 2개 이상 맞을 때만 채택한다.

    '판매'·'부품' 같은 범용 단어 하나로 엉뚱한 케이스가 걸리는 것을 막기 위한 장치다.
    """
    matched: List[Tuple[Trap, List[str]]] = []
    for trap in corpus.traps:
        hits = [signal for signal in trap.signals if normalize(signal) in norm]
        primary = [normalize(s) for s in trap.signals[:3]]
        primary_hit = any(sig in norm for sig in primary)
        if hits and (primary_hit or len(hits) >= 2):
            matched.append((trap, hits))
    return matched


def _freshness_cap(verdict: str, degraded: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    if not degraded:
        return verdict, None
    # '미연결(unavailable)'은 Phase 1의 정상 상태이므로 강등 사유가 아니다.
    # 캐시가 있으나 오래된 경우(fresh is False)만 판정을 낮춘다.
    stale = [s for s in degraded if s.get("fresh") is False]
    if stale:
        return "info_needed", "일부 근거 데이터가 최신이 아니어서 판정을 '추가 정보 필요'로 낮췄습니다."
    return verdict, None


def _build_answer(overall: str, findings: List[Finding]) -> Dict[str, Any]:
    if not findings:
        headline = "입력하신 내용으로는 해당 규정을 특정하지 못했습니다."
        guidance = [
            "품목명, HS 코드(가능하면 10자리), 수입 목적(판매/자가소비), 제조국을 함께 알려주시면 더 좁혀 볼 수 있습니다.",
        ]
    else:
        top = findings[0]
        headline = f"확인이 필요한 쟁점: {top.trap.issue_ko}"
        if overall == "low_risk":
            headline = f"현재 정보상 가능성이 낮은 쟁점: {top.trap.issue_ko}"
        elif overall == "info_needed":
            headline = f"확인 항목이 남아 있는 쟁점: {top.trap.issue_ko}"
        guidance = [top.trap.correct_answer]
        if top.missing_inputs:
            guidance.append("판정을 좁히려면 다음 정보가 필요합니다: " + ", ".join(m.field for m in top.missing_inputs))
        if top.trap.notes:
            guidance.append(top.trap.notes)

    answer = {"headline": headline, "guidance": guidance}
    text = " ".join([headline] + guidance)
    hits = find_conclusive_phrasing(text)
    if hits:  # 생성 문장에 단정 표현이 섞이면 안전한 문구로 대체
        answer["headline"] = "확인이 필요한 항목이 있습니다(단정하지 않습니다)."
        answer["guidance"] = [g for g in guidance if not find_conclusive_phrasing(g)]
    return answer


def _dedupe_basis(findings: List[Finding]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for finding in findings:
        for basis in finding.trap.legal_basis:
            key = (basis.law, basis.article, basis.url)
            if key in seen:
                continue
            seen.add(key)
            out.append(basis.to_dict())
    return out


def assess(
    query: str,
    facts: Optional[Dict[str, Any]] = None,
    *,
    corpus: Optional[Corpus] = None,
    store: Optional[Store] = None,
    gateway: Optional[SourceGateway] = None,
    client_id: str = "anonymous",
    tier: str = "free",
    limit: int = 3,
    live: Any = None,
) -> Dict[str, Any]:
    corpus = corpus or load_corpus()
    norm = normalize(query)
    if len(norm) < 2:
        raise ValueError("query_too_short")

    merged = _infer_facts(query, facts)
    matched_scored = []
    for trap, hits in _match_traps(corpus, norm):
        score = len(hits)
        verdict = trap.default_verdict
        reason = "규정 신호 일치"
        if any(_condition_satisfied(c, norm) for c in trap.low_risk_conditions):
            verdict = "low_risk"
            reason = "명시적 제외·저위험 조건 일치"
        missing = [r for r in trap.required_inputs if not _required_satisfied(r, merged, norm)]
        if missing and verdict == "check_likely":
            verdict = "info_needed"
            reason = "판정에 필요한 입력 누락: " + ", ".join(m.field for m in missing)
        implied = _apply_fact_rules(trap.fact_rules, merged)
        if implied and VERDICT_SEVERITY[implied["verdict"]] < VERDICT_SEVERITY[verdict]:
            verdict = implied["verdict"]
            reason = implied["reason"]
            missing = [] if verdict == "low_risk" else missing
        confidence = min(0.9, 0.45 + 0.12 * score)
        if missing:
            confidence = min(confidence, 0.6)
        matched_scored.append((score, TrapMatch(trap, verdict, confidence, hits, missing, reason)))

    matched_scored.sort(key=lambda item: (-VERDICT_SEVERITY[item[1].verdict], -item[0], item[1].trap.id))
    findings = [
        Finding(
            trap=m.trap,
            verdict=m.verdict,
            confidence=m.confidence,
            matched_signals=m.hits,
            missing_inputs=m.missing,
            reason=m.reason,
        )
        for _, m in matched_scored[:limit]
    ]

    degraded: List[Dict[str, Any]] = []
    if store is not None:
        gateway = gateway or SourceGateway(store, live=live)
        for source_id in _sources_for(findings):
            state = gateway.get(source_id, norm[:60], live_query=_live_query_for(source_id, merged))
            # 원본 payload는 외부로 내보내지 않고 상태 메타데이터만 남긴다.
            degraded.append({key: value for key, value in state.items() if key != "data"})

    overall = max((f.verdict for f in findings), key=lambda v: VERDICT_SEVERITY[v]) if findings else "info_needed"
    overall, cap_note = _freshness_cap(overall, degraded)
    if not findings:
        cap_note = "입력에서 규정 신호를 찾지 못했습니다. 품목명·HS·목적을 보강해 주세요."

    answer = _build_answer(overall, findings)
    if cap_note:
        answer["guidance"].append(cap_note)

    response = {
        "assessment_id": "asm_" + uuid.uuid4().hex[:16],
        "engine": {"name": "import-compliance", "version": corpus.version, "corpus_verified_on": corpus.verified_on},
        "query": {"text": query, "facts_resolved": merged},
        "verdict": {
            "code": overall,
            "label_ko": VERDICT_LABEL_KO[overall],
            "label_en": VERDICT_LABEL_EN[overall],
            "determinative": False,
            "note_ko": "판정은 확률적 검토 결과이며, 법적 확정 판단이 아닙니다.",
        },
        "answer": answer,
        "findings": [f.to_dict() for f in findings],
        "evidence": _dedupe_basis(findings),
        "data_provenance": {
            "policy": "원본 API 1:1 재전송 금지 · 다기관 결합·정규화 결과만 제공",
            "sources": degraded if degraded else [{"state": "corpus_only",
                                                  "note": "실시간 소스 호출 없음(코퍼스·법령 근거만)"}],
            "checked_at": iso(now_kst()),
        },
        "disclaimer": {"ko": DISCLAIMER_KO, "en": DISCLAIMER_EN},
        "scope_limits_ko": SCOPE_LIMITS_KO,
        "tier": {"name": tier, "boundaries": TIER_BOUNDARIES["free"], "paid_notice_ko": PAID_TIER_NOTICE_KO},
        "client_id": client_id,
        "next_actions": findings[0].trap.next_steps if findings else [
            "품목명·HS 10자리·수입 목적·제조국을 입력해 다시 조회",
        ],
    }
    if store is not None:
        store.record_assessment(response["assessment_id"], client_id, tier, query, overall, response)
    return response


class TrapMatch:
    __slots__ = ("trap", "verdict", "confidence", "hits", "missing", "reason")

    def __init__(self, trap, verdict, confidence, hits, missing, reason):
        self.trap = trap
        self.verdict = verdict
        self.confidence = confidence
        self.hits = hits
        self.missing = missing
        self.reason = reason


SOURCE_MAP = {
    "food": ["mfds_import_food", "customs_requirements"],
    "cosmetics": ["mfds_import_food", "customs_requirements"],
    "label": ["mfds_import_food", "law_api"],
    "kc": ["kats_product_safety", "customs_requirements"],
    "rf": ["rra_conformity", "customs_requirements"],
    "customs": ["customs_requirements", "law_api"],
    "origin": ["law_api", "fta_portal"],
    "ip": ["customs_requirements", "law_api"],
    "chemical": ["keco_chemical", "customs_requirements"],
}


def _sources_for(findings: List[Finding]) -> List[str]:
    out: List[str] = []
    for finding in findings:
        for source_id in SOURCE_MAP.get(finding.trap.category, []):
            if source_id not in out:
                out.append(source_id)
    return out


def _live_query_for(source_id: str, facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """실API로 바로 확인할 수 있는 소스만 실호출 인자를 만든다.

    HS 10자리가 없으면 세관장확인 API는 호출해도 의미가 없으므로 호출하지 않는다.
    """
    if source_id == "customs_requirements":
        hs_code = str(facts.get("hs_code", "") or "")
        if len(hs_code) == 10 and hs_code.isdigit():
            return {"hs_code": hs_code, "direction": facts.get("direction", "import")}
    return None
