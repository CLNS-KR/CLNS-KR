"""식약처 행정처분 DB 연동·폴백 (CLNS 0.2.0).

무엇을 하는가
-------------
1. 공공데이터포털 식약처 행정처분결과 API 두 개를 조회한다.
   - `15124560` 식품제조가공업 — `…/AdmmRsltFoodMnftPrcsService01/getAdmmRsltFoodMnftPrcsBssh01`
   - `15124559` 식품판매업 — `…/AdmmRsltFoodSaleService01/getAdmmRsltFoodSaleBssh01`
2. 조회 결과를 **개인정보를 지운 형태로** 로컬 DB(`disposition_items`)에 적재하고,
   위반법령별 통계를 낸다.
3. 키 미승인(코드 30)·오프라인·네트워크 실패일 때는 내장 대표 적발 패턴 사전으로
   같은 형태의 결과를 돌려준다(서비스가 빈손으로 끝나지 않게).

개인정보 처리 원칙
------------------
원본에는 업소명ㆍ대표자명ㆍ전화번호ㆍ주소ㆍ인허가번호가 들어 있다. 이 모듈은 그 필드를
**읽지도 않고 버린다.** 저장·응답에 남기는 것은 업종, 처분유형, 처분기간, 위반일자,
위반내용(개인정보 패턴 마스킹), 위반법령, 처분내용, 처분기관, 확정일 뿐이다.
인허가번호는 조회 조건으로만 쓰고 응답·저장에 남기지 않는다.

원본 payload를 `api_snapshots` 에도 남기지 않는다 — 다른 소스와 달리 이 데이터는 원문에
개인정보가 들어 있어, 스냅샷 보관 자체가 개인정보 저장이 되기 때문이다. 정규화된
`disposition_items` 만 적재한다(스키마: `schema.sql`).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from .live_api import (
    LiveApiError,
    SOURCE_DISPOSITION_MFG,
    SOURCE_DISPOSITION_SALES,
    redact,
)

KST = timezone(timedelta(hours=9))
VERIFIED_ON = "2026-11-19"

DATASETS: Dict[str, Dict[str, str]] = {
    "manufacturing": {
        "dataset_id": "15124560",
        "name_ko": "식품의약품안전처_행정처분결과(식품제조가공업)",
        "industry_ko": "식품제조가공업(주류 포함)",
        "source_id": SOURCE_DISPOSITION_MFG,
        "endpoint": "https://apis.data.go.kr/1471000/AdmmRsltFoodMnftPrcsService01"
                    "/getAdmmRsltFoodMnftPrcsBssh01",
        "apply_url": "https://www.data.go.kr/data/15124560/openapi.do",
        "license_scope": "이용허락범위 제한 없음",
    },
    "sales": {
        "dataset_id": "15124559",
        "name_ko": "식품의약품안전처_행정처분결과(식품판매업)",
        "industry_ko": "식품판매업(유통전문판매업ㆍ기타식품판매업 등)",
        "source_id": SOURCE_DISPOSITION_SALES,
        "endpoint": "https://apis.data.go.kr/1471000/AdmmRsltFoodSaleService01"
                    "/getAdmmRsltFoodSaleBssh01",
        "apply_url": "https://www.data.go.kr/data/15124559/openapi.do",
        "license_scope": "이용허락범위 제한 없음",
    },
}

INDUSTRY_ALIASES: Dict[str, str] = {
    "manufacturing": "manufacturing", "mfg": "manufacturing", "food_manufacturing": "manufacturing",
    "제조": "manufacturing", "제조가공업": "manufacturing", "식품제조가공업": "manufacturing",
    "sales": "sales", "food_sales": "sales", "판매": "sales", "식품판매업": "sales",
    "all": "all", "전체": "all", "": "all",
}

# 개인정보 패턴 — 전화번호ㆍ주민번호 형태ㆍ6자리 이상 숫자(날짜 제외).
_PHONE_RE = re.compile(r"\b0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}\b")
_RRN_RE = re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")
_LONG_NUM_RE = re.compile(r"\b(\d{7,})\b")
_DATE_PREFIX_RE = re.compile(r"^\s*[\(\[（]?\s*20\d{2}[-.]?\d{2}[-.]?\d{2}\s*[\)\]）]?\s*")


def sanitize_text(value: Any, limit: int = 200) -> str:
    """위반내용 등 자유서술에서 개인정보 패턴을 지운다."""
    text = str(value or "").strip()
    text = _PHONE_RE.sub("[연락처]", text)
    text = _RRN_RE.sub("[식별번호]", text)

    def _mask_long(match: "re.Match[str]") -> str:
        digits = match.group(1)
        if re.fullmatch(r"20\d{2}\d{4}", digits) or re.fullmatch(r"20\d{6}", digits):
            return digits  # YYYYMMDD 형태는 날짜이므로 유지
        return "[번호]"

    text = _LONG_NUM_RE.sub(_mask_long, text)
    text = " ".join(text.split())
    return text[:limit]


def _date8(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 8:
        return ""
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def normalize_item(item: Dict[str, Any], dataset: str) -> Optional[Dict[str, Any]]:
    """원본 1건 → 개인정보를 지운 정규화 레코드. 식별정보는 만들지 않는다."""
    if not isinstance(item, dict):
        return None
    seq = str(item.get("DSPSDTLS_SEQ") or "").strip()
    violation = sanitize_text(item.get("VILTCN"))
    if not seq or not violation:
        return None
    return {
        "dataset_id": DATASETS[dataset]["dataset_id"],
        "disposition_seq": seq,
        "industry": sanitize_text(item.get("INDUTY_CD_NM"), 60),
        "disposition_type": sanitize_text(item.get("DSPS_TYPECD_NM"), 60),
        "confirmed_on": _date8(item.get("DSPS_DCSNDT")),
        "disposition_from": _date8(item.get("DSPS_BGNDT")),
        "disposition_to": _date8(item.get("DSPS_ENDDT")),
        "violation_summary": violation,
        "law_reference": sanitize_text(item.get("LAWORD_CD_NM"), 200),
        "disposition_summary": sanitize_text(item.get("DSPSCN"), 120),
        "agency": sanitize_text(item.get("DSPS_INSTTCD_NM"), 60),
        "last_updated": sanitize_text(item.get("LAST_UPDT_DTM"), 40),
    }


def _normalize_industry(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return INDUSTRY_ALIASES.get(raw, "all")


def _patterns_for(industry: str) -> List[Dict[str, Any]]:
    rows = [row for row in BUILTIN_PATTERNS if industry in ("all", row["industry"])]
    return rows


def lookup(store: Any = None, live: Any = None, *, industry: str = "all", keyword: str = "",
           license_no: str = "", confirmed_on: str = "", rows: int = 20,
           limit: int = 5) -> Dict[str, Any]:
    """행정처분 이력을 조회한다(라이브 → 로컬 캐시 → 내장 패턴 순)."""
    target = _normalize_industry(industry)
    datasets = list(DATASETS) if target == "all" else [target]
    live_states: List[Dict[str, Any]] = []
    fetched_items: List[Dict[str, Any]] = []

    for name in datasets:
        meta = DATASETS[name]
        state = _fetch_dataset(store, live, name, license_no=license_no, rows=rows)
        live_states.append(state)
        fetched_items.extend(state.pop("items", []))

    cached = store.search_dispositions(keyword=keyword, confirmed_on=_date8(confirmed_on),
                                       limit=limit) if store is not None else []
    matches = fetched_items
    if keyword and matches:
        probe = keyword.lower()
        matches = [row for row in matches
                   if probe in " ".join(str(row.get(key) or "") for key in
                                        ("law_reference", "violation_summary", "disposition_type", "industry")).lower()]
    matches = sorted(matches, key=lambda row: str(row.get("confirmed_on") or ""), reverse=True)
    source = "live"
    if not matches:
        matches = cached
        source = "local_cache" if cached else "pattern_fallback"

    if not matches and not fetched_items and cached == []:
        # 내장 패턴 사전은 '위반 유형' 통계이므로, 키워드가 있으면 그것으로 걸러 안내한다.
        patterns = _patterns_for(target)
        if keyword:
            probe = keyword.lower()
            patterns = [p for p in patterns
                        if probe in (p["name_ko"] + p["law_reference"] + p.get("check_ko", "")).lower()]
        return _payload(industry=target, keyword=keyword, state=_combined_state(live_states),
                        source="pattern_fallback", matches=[], patterns=patterns,
                        live_states=live_states, dataset_stats=[], confirmed_on=confirmed_on)

    stats = (store.disposition_summary(dataset_ids=[DATASETS[n]["dataset_id"] for n in datasets])
             if store is not None else [])
    if not stats:
        stats = _stats_from_items(fetched_items)
    return _payload(industry=target, keyword=keyword, state=_combined_state(live_states),
                    source=source, matches=matches[:limit], patterns=_patterns_for(target),
                    live_states=live_states, dataset_stats=stats, confirmed_on=confirmed_on)


def _fetch_dataset(store: Any, live: Any, name: str, *, license_no: str, rows: int) -> Dict[str, Any]:
    meta = DATASETS[name]
    block: Dict[str, Any] = {
        "dataset_id": meta["dataset_id"],
        "name_ko": meta["name_ko"],
        "industry_ko": meta["industry_ko"],
        "state": "corpus_only",
        "item_count": 0,
        "apply_url": meta["apply_url"],
        "note_ko": "",
    }
    if live is None:
        block["note_ko"] = "실시간 조회가 꺼져 있어 내장 대표 적발 패턴으로 안내합니다."
        return block
    if not getattr(live, "has_mfds", False):
        block["state"] = "key_missing"
        block["note_ko"] = "공공데이터포털 서비스키가 없어 실시간 조회를 하지 못했습니다."
        return block
    try:
        # 승인 전파 전 데이터셋에서 15초 재시도를 하지 않는다(호출 지연 방지).
        # 전파가 끝나면 다음 호출부터 자연스럽게 live 로 바뀐다.
        fetch = live.mfds_disposition(name, license_no=license_no, rows=rows,
                                      retry_on_unregistered=False)
    except LiveApiError as exc:
        code = getattr(exc, "code", None)
        message = redact(str(exc))
        block["state"] = "approval_pending" if code == "30" else "error"
        block["code"] = code or ""
        block["note_ko"] = (
            "활용신청 승인 전이거나 게이트웨이 전파 전이라 이 데이터셋은 조회되지 않습니다(코드 30). "
            "승인 후 자동으로 조회됩니다."
            if code == "30" else f"실시간 조회 실패: {message}"
        )
        return block
    items: List[Dict[str, Any]] = []
    for raw in getattr(fetch, "items", []) or []:
        normalized = normalize_item(raw, name)
        if normalized:
            items.append(normalized)
    if store is not None and items:
        store.save_dispositions(items)
    block["state"] = "live"
    block["item_count"] = len(items)
    block["total_count"] = getattr(fetch, "total_count", None)
    block["checked_at"] = getattr(fetch, "fetched_at", "")
    block["note_ko"] = "실시간 조회 결과에서 개인정보(업소명ㆍ대표자ㆍ연락처ㆍ주소ㆍ인허가번호)를 제거해 표시합니다."
    block["items"] = items
    return block


def _combined_state(states: List[Dict[str, Any]]) -> str:
    values = [s.get("state") for s in states]
    if "live" in values:
        return "live" if all(v == "live" for v in values) else "partial"
    if "approval_pending" in values:
        return "approval_pending"
    if "key_missing" in values:
        return "key_missing"
    if "error" in values:
        return "error"
    return "corpus_only"


def _stats_from_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for item in items:
        law = str(item.get("law_reference") or "").split(",")[0].strip()
        if not law:
            continue
        counts[law] = counts.get(law, 0) + 1
    total = sum(counts.values()) or 1
    return [{"law_reference": law, "count": count, "share": round(count / total, 3)}
            for law, count in sorted(counts.items(), key=lambda kv: -kv[1])]


def _payload(*, industry: str, keyword: str, state: str, source: str,
             matches: List[Dict[str, Any]], patterns: List[Dict[str, Any]],
             live_states: List[Dict[str, Any]], dataset_stats: List[Dict[str, Any]],
             confirmed_on: str) -> Dict[str, Any]:
    if matches:
        verdict = "check_likely"
        label = "행정처분 이력이 조회되었습니다"
    elif state == "approval_pending":
        verdict = "info_needed"
        label = "해당 데이터셋 승인 전파 전 — 내장 패턴으로만 안내"
    elif state in ("key_missing", "corpus_only", "error"):
        verdict = "info_needed"
        label = "실시간 조회 불가 — 내장 패턴으로만 안내"
    else:
        verdict = "info_needed"
        label = "조회 결과 0건(이력 없음 확정 아님)"
    return {
        "verdict": {"code": verdict, "label_ko": label},
        "industry": industry,
        "keyword": sanitize_text(keyword, 60),
        "confirmed_on": _date8(confirmed_on),
        "state": state,
        "source": source,
        "match_count": len(matches),
        "matches": matches,
        "patterns": patterns,
        "dataset_stats": dataset_stats,
        "datasets": [{k: v for k, v in s.items() if k != "items"} for s in live_states],
        "coverage_ko": (
            "행정처분결과 API는 업종별 데이터셋이 따로 있고, 승인·전파 상태가 데이터셋마다 "
            "다릅니다. 실시간 조회가 안 되는 데이터셋은 내장 대표 적발 패턴(2026-11-19 기준 "
            "식품제조가공업 249건 스냅샷의 위반법령 분포)으로 안내하며, 이는 개별 업소 이력이 "
            "아닙니다."
        ),
        "pii_policy_ko": (
            "원본의 업소명ㆍ대표자명ㆍ전화번호ㆍ주소ㆍ인허가번호는 읽지 않고 버립니다. "
            "응답·로컬 DB에는 위반법령ㆍ처분유형ㆍ처분기간ㆍ처분일만 남깁니다"
            "(확정 판단이 아니라 기록 보존 범위입니다)."
        ),
        "official_urls": ["https://www.foodsafetykorea.go.kr", "https://www.data.go.kr"],
        "checked_on": VERIFIED_ON,
    }


# ---------------------------------------------------------------------------
# 내장 대표 적발 패턴 사전
# ---------------------------------------------------------------------------
# observed_2026_11_19: 2026-11-19에 15124560 데이터셋 전체 249건을 받아 위반법령 문자열로
# 집계한 값(중복 법령이 한 행에 여러 번 적힌 경우도 각각 셈). 개별 업소 정보는 담지 않는다.
BUILTIN_PATTERNS: List[Dict[str, Any]] = [
    {
        "pattern_id": "PD-01",
        "industry": "manufacturing",
        "name_ko": "영업시설 기준 미비ㆍ시설 멸실",
        "law_reference": "식품위생법 제36조(시설기준)",
        "observed_2026_11_19": 94,
        "risk": "high",
        "check_ko": "영업소 시설기준(작업장ㆍ보관소ㆍ급수ㆍ배수 등)을 갖추고, 시설을 철거ㆍ이전할 때는 변경등록을 먼저 하세요.",
        "typical_disposition_ko": "영업허가ㆍ등록취소, 영업소폐쇄",
    },
    {
        "pattern_id": "PD-02",
        "industry": "manufacturing",
        "name_ko": "영업허가ㆍ등록 변경 미신고",
        "law_reference": "식품위생법 제37조(영업허가 등)",
        "observed_2026_11_19": 37,
        "risk": "high",
        "check_ko": "영업장 소재지ㆍ시설 일부를 바꾸면 변경등록(또는 신고)을 먼저 해야 합니다. 휴업ㆍ폐업 신고 누락도 처분 사유입니다.",
        "typical_disposition_ko": "영업허가ㆍ등록취소, 영업소폐쇄",
    },
    {
        "pattern_id": "PD-03",
        "industry": "manufacturing",
        "name_ko": "자가품질검사 미실시",
        "law_reference": "식품위생법 제31조(자가품질검사 의무)",
        "observed_2026_11_19": 16,
        "risk": "high",
        "check_ko": "자가품질검사 대상 업종이면 검사 주기ㆍ항목을 지키고 성적서를 보관하세요.",
        "typical_disposition_ko": "품목제조정지",
    },
    {
        "pattern_id": "PD-04",
        "industry": "manufacturing",
        "name_ko": "영업자 준수사항 위반",
        "law_reference": "식품위생법 제44조(영업자 등의 준수사항)",
        "observed_2026_11_19": 7,
        "risk": "caution",
        "check_ko": "종업원 건강진단ㆍ위생교육ㆍ원료 보관 온도 같은 준수사항을 기록으로 남기세요.",
        "typical_disposition_ko": "영업정지",
    },
    {
        "pattern_id": "PD-05",
        "industry": "manufacturing",
        "name_ko": "기준ㆍ규격 위반",
        "law_reference": "식품위생법 제7조(기준 및 규격)",
        "observed_2026_11_19": 6,
        "risk": "high",
        "check_ko": "원료ㆍ완제품이 「식품의 기준 및 규격」에 맞는지 시험성적서로 확인하세요.",
        "typical_disposition_ko": "품목제조정지, 해당 제품 폐기",
    },
    {
        "pattern_id": "PD-06",
        "industry": "manufacturing",
        "name_ko": "표시기준 위반(한글표시사항)",
        "law_reference": "식품등의 표시ㆍ광고에 관한 법률 제4조(표시의 기준)",
        "observed_2026_11_19": 4,
        "risk": "high",
        "check_ko": "제품명ㆍ원재료명ㆍ소비기한ㆍ영업소 등 필수 표시항목과 한글표시사항을 출고 전에 대조하세요.",
        "typical_disposition_ko": "영업정지, 품목제조정지",
    },
    {
        "pattern_id": "PD-07",
        "industry": "manufacturing",
        "name_ko": "부당 표시ㆍ광고",
        "law_reference": "식품등의 표시ㆍ광고에 관한 법률 제8조(부당한 표시 또는 광고행위의 금지)",
        "observed_2026_11_19": 1,
        "risk": "high",
        "check_ko": "질병 효능ㆍ의약품 오인ㆍ거짓과장 표현은 상세페이지까지 포함해 점검하세요.",
        "typical_disposition_ko": "시정명령, 영업정지",
    },
    {
        "pattern_id": "PD-08",
        "industry": "manufacturing",
        "name_ko": "위해식품 판매ㆍ사용",
        "law_reference": "식품위생법 제4조(위해식품등의 판매 등 금지)",
        "observed_2026_11_19": 2,
        "risk": "high",
        "check_ko": "부적합 판정 제품의 판매ㆍ사용을 즉시 중단하고 회수 절차를 기록하세요.",
        "typical_disposition_ko": "영업허가ㆍ등록취소, 제품 폐기",
    },
    {
        "pattern_id": "PD-09",
        "industry": "manufacturing",
        "name_ko": "수입신고 위반",
        "law_reference": "수입식품안전관리 특별법 제20조(수입신고 등)",
        "observed_2026_11_19": 1,
        "risk": "high",
        "check_ko": "수입 원료를 국내 제조에 사용할 때도 용도에 맞는 수입신고ㆍ용도변경 승인을 확인하세요.",
        "typical_disposition_ko": "영업정지",
    },
    {
        "pattern_id": "PD-10",
        "industry": "sales",
        "name_ko": "표시ㆍ광고 위반(판매업)",
        "law_reference": "식품등의 표시ㆍ광고에 관한 법률 제4조ㆍ제8조",
        "observed_2026_11_19": None,
        "risk": "high",
        "check_ko": "판매업은 취급 제품의 한글표시사항과 상세페이지 광고 문구를 함께 점검해야 합니다.",
        "typical_disposition_ko": "영업정지, 시정명령",
    },
    {
        "pattern_id": "PD-11",
        "industry": "sales",
        "name_ko": "유통기한 경과ㆍ보관기준 위반(판매업)",
        "law_reference": "식품위생법 제44조(영업자 등의 준수사항)",
        "observed_2026_11_19": None,
        "risk": "caution",
        "check_ko": "진열대 회전ㆍ보관온도ㆍ소비기한 경과 제품 분리 보관을 기록으로 남기세요.",
        "typical_disposition_ko": "영업정지",
    },
    {
        "pattern_id": "PD-12",
        "industry": "sales",
        "name_ko": "영업등록ㆍ신고 사항 변경 미반영(판매업)",
        "law_reference": "식품위생법 제37조(영업허가 등)",
        "observed_2026_11_19": None,
        "risk": "caution",
        "check_ko": "판매업소 소재지ㆍ대표자 변경 시 변경등록을 먼저 하세요.",
        "typical_disposition_ko": "영업소폐쇄",
    },
]
