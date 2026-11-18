"""표준 응답 스키마(0.1.3): 판정 상태·규제 태그·국가코드·누락 정보 표기.

이 모듈은 응답에 붙는 **표준 어휘**만 정의한다. 판정 로직은 engine.py, 툴 래퍼는
api.py 에 있고, 여기서는 다음 4가지를 한 곳에서 관리한다.

1. `ASSESSMENT_STATUS` — 표준 판정 상태 5단계(APPLICABLE / NOT_APPLICABLE /
   POTENTIALLY_APPLICABLE / REVIEW_REQUIRED / UNKNOWN)와 기존 3단계 `verdict` 의
   대응 관계. 기존 `verdict` 는 하위 호환을 위해 그대로 두고 상태를 **추가**한다.
2. `REGULATION_TAGS` — 케이스별 규제 태그(분야 횡단 공통 어휘). 테스트셋의
   `required_findings` 가 이 태그를 쓰고, 응답의 각 finding 에 `regulation_tags`
   로 실린다.
3. `MISSING_FIELD_ALIAS` — 내부 입력 필드명을 외부 표준 스펙명으로 바꾼다
   (target_age → intended_age, hs_code → hs_10_code, rf_tx → wireless_function).
4. `detect_origin` — 질의문·사실관계에서 원산지 ISO 3166-1 alpha-2 코드를 찾는다.
   찾지 못하면 None. 추측으로 국가를 만들어 넣지 않는다.

이 파일은 개인정보·시크릿을 담지 않는다(서비스 식별자는 `CLNS-KR` 뿐).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA_VERSION = "0.1.3"
DEFAULT_DESTINATION = "KR"
DEFAULT_JURISDICTION = "KR"

# ---------------------------------------------------------------------------
# 1. 표준 판정 상태
# ---------------------------------------------------------------------------
ASSESSMENT_STATUS: Dict[str, Dict[str, str]] = {
    "APPLICABLE": {
        "label_ko": "적용 대상",
        "label_en": "Applicable",
        "note_ko": "현재 정보로는 해당 규제가 적용되는 것으로 판정했습니다. 확정 판단이 아니므로 근거 조항과 확인 기관을 함께 보세요.",
    },
    "NOT_APPLICABLE": {
        "label_ko": "현재 정보로 미적용",
        "label_en": "Not applicable",
        "note_ko": "입력한 사실관계 기준으로 쟁점의 적용 가능성이 낮습니다. 입력이 바뀌면 결과도 달라질 수 있습니다.",
    },
    "POTENTIALLY_APPLICABLE": {
        "label_ko": "적용 가능성 있음",
        "label_en": "Potentially applicable",
        "note_ko": "적용될 수 있으나 일부 스펙이 비어 있습니다. missing_information 항목을 채우면 판정이 좁혀집니다.",
    },
    "REVIEW_REQUIRED": {
        "label_ko": "검토 필요",
        "label_en": "Review required",
        "note_ko": "쟁점은 확인되었으나 입력만으로는 적용 여부를 정할 수 없습니다. 담당자·전문가 검토가 필요합니다.",
    },
    "UNKNOWN": {
        "label_ko": "판단 불가",
        "label_en": "Unknown",
        "note_ko": "입력에서 해당 규정 신호를 찾지 못했습니다. 품목명·HS 10자리·수입 목적을 보강해야 합니다.",
    },
}

ASSESSMENT_STATUS_ORDER: List[str] = list(ASSESSMENT_STATUS.keys())

# 기존 verdict → 표준 상태 기본 대응(누락 정보 유무로 한 단계 조정).
_VERDICT_TO_STATUS: Dict[str, str] = {
    "check_likely": "APPLICABLE",
    "info_needed": "REVIEW_REQUIRED",
    "low_risk": "NOT_APPLICABLE",
}


def status_for(verdict_code: Optional[str], *, finding_count: int,
               missing_information: Sequence[str] = ()) -> str:
    """기존 3단계 판정과 누락 정보 목록으로 표준 상태를 계산한다.

    - finding 없음 → UNKNOWN (규정 신호를 못 찾음)
    - check_likely + 빠진 스펙 없음 → APPLICABLE
    - check_likely + 빠진 스펙 있음 → POTENTIALLY_APPLICABLE
    - info_needed → REVIEW_REQUIRED (쟁점은 있으나 판단 불가)
    - low_risk → NOT_APPLICABLE
    """
    if finding_count <= 0:
        return "UNKNOWN"
    code = str(verdict_code or "")
    if code not in _VERDICT_TO_STATUS:
        return "UNKNOWN"
    if code == "check_likely" and missing_information:
        return "POTENTIALLY_APPLICABLE"
    return _VERDICT_TO_STATUS[code]


def status_block(status: str) -> Dict[str, str]:
    meta = ASSESSMENT_STATUS.get(status) or ASSESSMENT_STATUS["UNKNOWN"]
    return {
        "status": status,
        "label_ko": meta["label_ko"],
        "label_en": meta["label_en"],
        "note_ko": meta["note_ko"],
    }


def apply_status(result: Dict[str, Any]) -> Dict[str, Any]:
    """응답 dict 의 verdict·findings·missing_information 을 읽어 상태 필드를 맞춘다.

    api 계층이 실시간 조회 결과로 verdict 를 올린 뒤에도 상태가 어긋나지 않도록
    저장·응답 직전에 다시 호출한다.
    """
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    findings = result.get("findings") or []
    missing = result.get("missing_information") or []
    status = status_for(verdict.get("code"), finding_count=len(findings),
                        missing_information=missing)
    block = status_block(status)
    result["assessment_status"] = status
    result["assessment_status_label_ko"] = block["label_ko"]
    result["assessment_status_label_en"] = block["label_en"]
    result["assessment_status_note_ko"] = block["note_ko"]
    return result


# ---------------------------------------------------------------------------
# 2. 규제 태그(분야 횡단 공통 어휘)
# ---------------------------------------------------------------------------
REGULATION_TAGS: Dict[str, Dict[str, str]] = {
    "FOOD_IMPORT_DECLARATION": {"label_ko": "수입식품 신고·영업", "label_en": "Imported food declaration"},
    "FOOD_BUSINESS_REGISTRATION": {"label_ko": "수입판매업 영업등록", "label_en": "Food business registration"},
    "FOOD_ADDITIVE": {"label_ko": "식품첨가물 기준", "label_en": "Food additive standard"},
    "HEALTH_FUNCTIONAL_FOOD": {"label_ko": "건강기능식품 신고·광고", "label_en": "Health functional food"},
    "FOOD_CONTACT_MATERIAL": {"label_ko": "식품용 기구·용기·포장", "label_en": "Food contact material"},
    "KOREAN_LABELING": {"label_ko": "한글표시사항", "label_en": "Korean labeling"},
    "COSMETICS_RESPONSIBLE_SALES": {"label_ko": "화장품 책임판매업", "label_en": "Cosmetics responsible seller"},
    "CHILDREN_PRODUCT_SAFETY": {"label_ko": "어린이제품 안전관리", "label_en": "Children's product safety"},
    "ELECTRICAL_KC": {"label_ko": "전기용품 KC", "label_en": "Electrical KC certification"},
    "BATTERY_SAFETY": {"label_ko": "전지·배터리 안전", "label_en": "Battery safety"},
    "RF_CONFORMITY": {"label_ko": "전파 적합성평가", "label_en": "RF conformity assessment"},
    "HOUSEHOLD_CHEMICAL": {"label_ko": "생활화학제품 안전확인", "label_en": "Household chemical safety"},
    "CUSTOMS_CHECKPOINT": {"label_ko": "세관장확인 요건", "label_en": "Customs checkpoint requirement"},
    "CUSTOMS_LOW_VALUE": {"label_ko": "소액 목록통관·면세", "label_en": "Low-value simplified clearance"},
    "CUSTOMS_PERSONAL_ID": {"label_ko": "개인통관고유부호", "label_en": "Personal customs ID"},
    "DRUG_IMPORT": {"label_ko": "의약품 반입", "label_en": "Drug import restriction"},
    "TOBACCO_VAPE": {"label_ko": "담배류(전자담배)", "label_en": "Tobacco / vape"},
    "ORIGIN_FTA": {"label_ko": "FTA 원산지", "label_en": "FTA origin"},
    "ORIGIN_MARKING": {"label_ko": "원산지 표시", "label_en": "Origin marking"},
    "IP_PARALLEL_IMPORT": {"label_ko": "지재권·병행수입", "label_en": "IP / parallel import"},
}

# 코퍼스 케이스 → 규제 태그(테스트셋 required_findings 가 참조하는 유일한 매핑).
CASE_REGULATION_TAGS: Dict[str, List[str]] = {
    "TRAP-01": ["FOOD_IMPORT_DECLARATION"],
    "TRAP-02": ["COSMETICS_RESPONSIBLE_SALES"],
    "TRAP-03": ["CHILDREN_PRODUCT_SAFETY"],
    "TRAP-04": ["ELECTRICAL_KC"],
    "TRAP-05": ["BATTERY_SAFETY"],
    "TRAP-06": ["RF_CONFORMITY"],
    "TRAP-07": ["FOOD_BUSINESS_REGISTRATION"],
    "TRAP-08": ["FOOD_ADDITIVE"],
    "TRAP-09": ["HEALTH_FUNCTIONAL_FOOD"],
    "TRAP-10": ["KOREAN_LABELING"],
    "TRAP-11": ["FOOD_CONTACT_MATERIAL"],
    "TRAP-12": ["CUSTOMS_LOW_VALUE"],
    "TRAP-13": ["CUSTOMS_PERSONAL_ID"],
    "TRAP-14": ["DRUG_IMPORT"],
    "TRAP-15": ["TOBACCO_VAPE"],
    "TRAP-16": ["HOUSEHOLD_CHEMICAL"],
    "TRAP-17": ["ORIGIN_FTA"],
    "TRAP-18": ["ORIGIN_MARKING"],
    "TRAP-19": ["CUSTOMS_CHECKPOINT"],
    "TRAP-20": ["IP_PARALLEL_IMPORT"],
}


def tags_for_case(case_id: str) -> List[str]:
    return list(CASE_REGULATION_TAGS.get(case_id, []))


def tags_for_findings(findings: Iterable[Dict[str, Any]]) -> List[str]:
    """응답 findings 에서 규제 태그를 뽑아 순서를 유지한 채 중복 제거한다."""
    out: List[str] = []
    for finding in findings:
        for tag in finding.get("regulation_tags") or []:
            if tag not in out:
                out.append(tag)
    return out


def unknown_tags(tags: Iterable[str]) -> List[str]:
    return [tag for tag in tags if tag not in REGULATION_TAGS]


# ---------------------------------------------------------------------------
# 3. 누락 정보 표준 스펙명
# ---------------------------------------------------------------------------
# 내부 required_inputs.field → 외부 표준 스펙명. 기존 필드명은 findings.missing_inputs
# 에 그대로 남기고, 응답 최상위 missing_information 만 표준명으로 노출한다.
MISSING_FIELD_ALIAS: Dict[str, str] = {
    "ac_plug": "ac_plug",
    "additive_names": "additive_names",
    "agreement": "fta_agreement",
    "battery_type": "battery_type",
    "business_type": "business_type",
    "channel": "import_channel",
    "claim_type": "claim_type",
    "direction": "trade_direction",
    "domestic_sales": "domestic_sales_status",
    "drug_class": "drug_class",
    "energy_density": "energy_density",
    "food_contact": "food_contact_use",
    "food_type": "food_type",
    "functional": "functional_cosmetic",
    "has_cert": "safety_confirmation_certificate",
    "has_pccc": "personal_customs_id",
    "hs_code": "hs_10_code",
    "ingredient": "ingredient",
    "item": "item_name",
    "material": "material",
    "material_origin": "material_origin",
    "nicotine": "nicotine_content",
    "price_usd": "declared_value_usd",
    "process": "manufacturing_process",
    "product_name": "product_name",
    "product_type": "product_type",
    "purpose": "import_purpose",
    "rated_power": "rated_power",
    "rf_tx": "wireless_function",
    "target_age": "intended_age",
    "trademark_owner": "trademark_owner",
}


def missing_field_name(field: str) -> str:
    """표준 스펙명으로 변환한다. 매핑에 없으면 원래 이름을 그대로 쓴다."""
    return MISSING_FIELD_ALIAS.get(str(field), str(field))


def missing_information(findings: Iterable[Dict[str, Any]]) -> List[str]:
    """findings 의 missing_inputs 를 표준 스펙명으로 모아 중복 없이 나열한다."""
    out: List[str] = []
    for finding in findings:
        for missing in finding.get("missing_inputs") or []:
            name = missing_field_name(missing.get("field", ""))
            if name and name not in out:
                out.append(name)
    return out


def missing_information_detail(findings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for finding in findings:
        for missing in finding.get("missing_inputs") or []:
            name = missing_field_name(missing.get("field", ""))
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({
                "field": name,
                "source_field": missing.get("field", ""),
                "prompt": missing.get("prompt", ""),
                "allowed_values": missing.get("allowed_values") or [],
                "case_id": finding.get("case_id"),
            })
    return out


# ---------------------------------------------------------------------------
# 4. 원산지(ISO 3166-1 alpha-2) 탐지
# ---------------------------------------------------------------------------
# 한국어·영문 국가명 → ISO 코드. 긴 이름부터 검사해 '인도'/'인도네시아' 같은
# 부분일치 오탐을 막는다. 국가가 확인되지 않으면 None 을 돌려준다(추측 금지).
COUNTRY_ALIASES: Dict[str, str] = {
    "대한민국": "KR", "한국": "KR", "korea": "KR", "south korea": "KR", "korea, republic of": "KR",
    "중국": "CN", "중화인민공화국": "CN", "china": "CN", "mainland china": "CN", "prc": "CN",
    "미국": "US", "미합중국": "US", "usa": "US", "u.s.a": "US", "u.s.": "US",
    "united states": "US", "america": "US",
    "일본": "JP", "japan": "JP",
    "베트남": "VN", "vietnam": "VN", "viet nam": "VN",
    "태국": "TH", "thailand": "TH",
    "인도네시아": "ID", "indonesia": "ID",
    "말레이시아": "MY", "malaysia": "MY",
    "필리핀": "PH", "philippines": "PH",
    "인도": "IN", "india": "IN",
    "대만": "TW", "타이완": "TW", "taiwan": "TW",
    "홍콩": "HK", "hong kong": "HK",
    "싱가포르": "SG", "singapore": "SG",
    "호주": "AU", "오스트레일리아": "AU", "australia": "AU",
    "뉴질랜드": "NZ", "new zealand": "NZ",
    "캐나다": "CA", "canada": "CA",
    "멕시코": "MX", "mexico": "MX",
    "브라질": "BR", "brazil": "BR",
    "독일": "DE", "germany": "DE",
    "프랑스": "FR", "france": "FR",
    "이탈리아": "IT", "italy": "IT",
    "스페인": "ES", "spain": "ES",
    "영국": "GB", "uk": "GB", "united kingdom": "GB", "great britain": "GB",
    "네덜란드": "NL", "netherlands": "NL",
    "벨기에": "BE", "belgium": "BE",
    "폴란드": "PL", "poland": "PL",
    "체코": "CZ", "czech": "CZ",
    "스웨덴": "SE", "sweden": "SE",
    "덴마크": "DK", "denmark": "DK",
    "스위스": "CH", "switzerland": "CH",
    "오스트리아": "AT", "austria": "AT",
    "튀르키예": "TR", "터키": "TR", "turkey": "TR", "türkiye": "TR",
    "이스라엘": "IL", "israel": "IL",
    "사우디아라비아": "SA", "사우디": "SA", "saudi arabia": "SA",
    "아랍에미리트": "AE", "uae": "AE",
    "남아프리카공화국": "ZA", "south africa": "ZA",
    "이집트": "EG", "egypt": "EG",
    "러시아": "RU", "russia": "RU",
    "우크라이나": "UA", "ukraine": "UA",
    "캄보디아": "KH", "cambodia": "KH",
    "미얀마": "MM", "myanmar": "MM",
    "방글라데시": "BD", "bangladesh": "BD",
    "스리랑카": "LK", "sri lanka": "LK",
    "파키스탄": "PK", "pakistan": "PK",
    "멕시코시티": "MX",
}

# 별칭 길이 내림차순(긴 이름 우선 매칭)
_ALIAS_ORDER: List[str] = sorted(COUNTRY_ALIASES, key=len, reverse=True)
_ISO_CODES = set(COUNTRY_ALIASES.values())


def normalize_origin(value: Any) -> Optional[str]:
    """사실관계로 받은 원산지 값을 ISO 코드로 정규화한다(모르면 None)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    upper = text.upper()
    if len(upper) == 2 and upper in _ISO_CODES:
        return upper
    lowered = text.lower()
    if lowered in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[lowered]
    detected = detect_origin(text)
    return detected


def detect_origin(text: str) -> Optional[str]:
    """질의문에서 원산지 국가를 찾는다. 여러 국가가 나오면 가장 길게 일치한 이름을 쓴다."""
    if not text:
        return None
    lowered = str(text).lower()
    for alias in _ALIAS_ORDER:
        if alias in lowered:
            return COUNTRY_ALIASES[alias]
    return None


def origin_from(query: str, facts: Optional[Dict[str, Any]] = None) -> tuple:
    """(origin, source) 를 돌려준다. source 는 'facts' | 'query' | None."""
    facts = facts or {}
    for key in ("origin", "origin_country", "made_in", "country_of_origin"):
        if key in facts:
            code = normalize_origin(facts[key])
            if code:
                return code, "facts"
    code = detect_origin(query)
    if code:
        return code, "query"
    return None, None


# ---------------------------------------------------------------------------
# 5. 응답 지리·스키마 표준 필드
# ---------------------------------------------------------------------------
def geography(query: str = "", facts: Optional[Dict[str, Any]] = None,
              destination: Optional[str] = None) -> Dict[str, Any]:
    origin, source = origin_from(query, facts)
    dest = str(destination or (facts or {}).get("destination") or DEFAULT_DESTINATION).upper()
    return {
        "schema_version": SCHEMA_VERSION,
        "destination": dest,
        "jurisdiction": DEFAULT_JURISDICTION,
        "origin": origin,
        "origin_source": source,
    }


def testset_meta(path: Optional[str] = None) -> Dict[str, Any]:
    """대표 100개 테스트셋의 버전·케이스 수·분야별 분포(문서·메타 노출용).

    테스트셋 파일이 없는 배포본에서도 서비스 메타가 깨지지 않도록 조용히 빈 값을 돌려준다.
    """
    import json
    import os

    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "testset_100.json")
    empty = {"version": None, "cases": 0, "domains": {}}
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (FileNotFoundError, OSError, ValueError):
        return empty
    counts: Dict[str, int] = {}
    for case in raw.get("cases") or []:
        domain = str(case.get("domain", ""))
        counts[domain] = counts.get(domain, 0) + 1
    return {"version": raw.get("testset_version"), "cases": len(raw.get("cases") or []),
            "domains": counts}


def apply_geography(payload: Dict[str, Any], query: str = "",
                    facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """이미 계산된 지리 필드는 건드리지 않고 없는 것만 채운다(모든 툴 응답 공통)."""
    for key, value in geography(query, facts).items():
        payload.setdefault(key, value)
    return payload
