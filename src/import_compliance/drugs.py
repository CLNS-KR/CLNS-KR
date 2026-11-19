"""의약품·영양제 반입 금지성분·제한성분 스크리닝.

무엇을 하는가
-------------
1. **마약류(마약·향정신성의약품·대마 및 그 합성품)** — 질의문·성분명에서 찾아내고,
   "처방전·수량과 무관하게 개인 반입이 제한된다"는 판정 근거를 붙인다.
2. **마약류 원료물질**(에페드린·슈도에페드린·에르고타민 등) — 마약류는 아니지만 수출입
   허가 대상이고, 「수입통관 사무처리에 관한 고시」 별표 11이 이들을 함유한 단일완제
   의약품을 요건확인 대상으로 따로 적고 있다.
3. **국내에서 의약품으로 관리되는 성분**(멜라토닌·DHEA·요힘빈·실데나필 등) — 건강기능식품
   ·식품으로 반입할 수 없고, 의약품으로 들여올 때는 수입업 신고·품목허가 또는 자가사용
   인정기준(6병·3개월분)을 따진다.
4. **자가사용 인정기준**(총 6병, 6병 초과 시 용법상 3개월 복용량) — 수량·반입 경로와
   대조해 "휴대 반입 허용 범위 안" / "온라인 구매는 이 기준으로 허용되지 않음"을 구분한다.

데이터의 성격(정직하게)
----------------------
- 마약류·원료물질 목록은 **법제처 시행령 별표 1~8을 파싱해 만든 로컬 사전**
  (`drug_schedules.json`, 출처: 법제처 국가법령정보센터)이다. 손으로 적은 추정 목록이 아니다.
- 국내 의약품 성분(KR_RX)은 **대표 성분 시드 목록**이며 전수가 아니다. 식약처 의약품
  허가정보·e약은요·DUR API는 이 계정에 활용승인이 없어(코드 30) 실시간 대조가 불가능하다.
  응답은 그 한계를 `coverage_ko`·`api_candidates`로 항상 함께 돌려준다.
- 브랜드명(아데랄·리탈린 등)은 **제품명 → 성분 참고 매핑**이며, 식약처 허가정보 조회가
  아니라 성분 사전 대조용 힌트다.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEDULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "drug_schedules.json")
VERIFIED_ON = "2026-11-18"

CLASS_LABEL_KO: Dict[str, str] = {
    "NARCOTIC": "마약",
    "PSYCHOTROPIC": "향정신성의약품",
    "CANNABIS_SYNTHETIC": "대마와 동일한 화학적합성품",
    "PRECURSOR": "마약류 원료물질",
    "KR_RX": "국내 의약품 성분(참고)",
    "KR_OTC": "국내 일반의약품 성분(참고)",
}

# 반입이 원칙적으로 제한되는 분류(마약류). 이 분류가 하나라도 걸리면 TRAP-23.
CONTROLLED_CLASSES = ("NARCOTIC", "PSYCHOTROPIC", "CANNABIS_SYNTHETIC")
# 6병 기준을 그대로 적용할 수 없는 분류. 걸리면 TRAP-24.
RESTRICTED_CLASSES = ("PRECURSOR", "KR_RX")

CLASS_SEVERITY = {"NARCOTIC": 4, "PSYCHOTROPIC": 4, "CANNABIS_SYNTHETIC": 4,
                  "PRECURSOR": 2, "KR_RX": 1, "KR_OTC": 1}

# --- 근거 조문 (2026-11-18 법제처 OPEN API 실조회, drug-law-verification.json 과 대조) ----
LAW_URL_MEDICINE = "https://www.law.go.kr/법령/약사법"
LAW_URL_NARCOTIC = "https://www.law.go.kr/법령/마약류관리에관한법률"
LAW_URL_DECREE = "https://www.law.go.kr/법령/마약류관리에관한법률시행령"
LAW_URL_CUSTOMS = "https://www.law.go.kr/법령/관세법"
NOTICE_URL = "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000269780"

BASIS_NARCOTIC: List[Dict[str, str]] = [
    {
        "law": "마약류 관리에 관한 법률", "article": "제2조", "effective_date": "2026-11-12",
        "url": LAW_URL_NARCOTIC,
        "quote": "\"마약류\"란 마약ㆍ향정신성의약품 및 대마를 말한다. \"대마\"란 대마초와 그 수지, "
                 "대마초 또는 그 수지를 원료로 하여 제조된 모든 제품 등을 말한다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "마약류 관리에 관한 법률", "article": "제4조제1항", "effective_date": "2026-11-12",
        "url": LAW_URL_NARCOTIC,
        "quote": "마약류취급자가 아니면 마약 또는 향정신성의약품을 소지ㆍ소유ㆍ사용ㆍ운반ㆍ관리ㆍ"
                 "수입ㆍ수출…하는 행위, 대마를 재배ㆍ소지ㆍ소유ㆍ수수ㆍ운반ㆍ보관 또는 사용하는 "
                 "행위를 하여서는 아니 된다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "마약류 관리에 관한 법률", "article": "제18조제1항", "effective_date": "2026-11-12",
        "url": LAW_URL_NARCOTIC,
        "quote": "마약류수출입업자가 아니면 마약 또는 향정신성의약품을 수출입하지 못한다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "마약류 관리에 관한 법률 시행령", "article": "별표 7의2", "effective_date": "2026-11-10",
        "url": LAW_URL_DECREE,
        "quote": "대마초와 그 수지 또는 이를 원료로 하여 제조된 모든 제품과 동일한 화학적합성품은 "
                 "칸나비놀ㆍ테트라히드로칸나비놀ㆍ칸나비디올 등이며, 이는 마약류로 관리된다.",
        "verified_on": VERIFIED_ON,
    },
]

BASIS_PRECURSOR: List[Dict[str, str]] = [
    {
        "law": "마약류 관리에 관한 법률", "article": "제2조제6호", "effective_date": "2026-11-12",
        "url": LAW_URL_NARCOTIC,
        "quote": "\"원료물질\"이란 마약류가 아닌 물질 중 마약 또는 향정신성의약품의 제조에 사용되는 "
                 "물질로서 대통령령으로 정하는 것을 말한다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "마약류 관리에 관한 법률", "article": "제6조의2제1항", "effective_date": "2026-11-12",
        "url": LAW_URL_NARCOTIC,
        "quote": "대통령령으로 정하는 원료물질의 수출입 또는 제조를 업으로 하려는 자는 총리령으로 "
                 "정하는 바에 따라 식품의약품안전처장의 허가를 받아야 한다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "수입통관 사무처리에 관한 고시", "article": "제67조 및 별표 11",
        "effective_date": "2025-12-17", "url": NOTICE_URL,
        "quote": "별표 11: 의약품 총 6병(6병 초과의 경우 의약품 용법상 3개월 복용량). "
                 "다만, 에페드린ㆍ놀에페드린ㆍ슈도에페드린ㆍ에르고타민ㆍ에르고메트린 함유 "
                 "단일완제의약품, 식품의약품안전처장의 수입불허 또는 유해 통보를 받은 품목 등은 "
                 "요건확인 대상이다.",
        "verified_on": VERIFIED_ON,
    },
]

BASIS_SELF_USE: List[Dict[str, str]] = [
    {
        "law": "수입통관 사무처리에 관한 고시", "article": "제67조 및 별표 11",
        "effective_date": "2025-12-17", "url": NOTICE_URL,
        "quote": "규칙 제45조제2항제1호에 따른 소액물품의 자가사용 인정기준은 [별표 11]과 같다. "
                 "의약품은 총 6병(6병 초과의 경우 의약품 용법상 3개월 복용량), 오남용우려의약품은 "
                 "국내 의사 처방전에 정해진 수량만 통관한다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "약사법", "article": "제42조제1항", "effective_date": "2026-11-12",
        "url": LAW_URL_MEDICINE,
        "quote": "의약품등의 수입을 업으로 하려는 자는 총리령으로 정하는 바에 따라 "
                 "식품의약품안전처장에게 수입업 신고를 하여야 하며, 품목마다 허가를 받거나 "
                 "신고를 하여야 한다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "약사법", "article": "제61조의2제1항", "effective_date": "2026-11-12",
        "url": LAW_URL_MEDICINE,
        "quote": "누구든지 제44조, 제50조제1항ㆍ제2항에 위반되는 의약품의 판매를 알선하거나 "
                 "광고해서는 아니 된다.",
        "verified_on": VERIFIED_ON,
    },
    {
        "law": "관세법", "article": "제226조", "effective_date": "2026-10-02", "url": LAW_URL_CUSTOMS,
        "quote": "수출입을 할 때 법령에서 정하는 바에 따라 허가ㆍ승인ㆍ표시 또는 그 밖의 조건을 "
                 "갖출 필요가 있는 물품은 세관장에게 그 조건을 갖춘 것임을 증명하여야 한다.",
        "verified_on": VERIFIED_ON,
    },
]

# 식약처 의약품 계열 data.go.kr 데이터셋 — 2026-11-18 실호출 결과 이 계정은 활용승인 없음(코드 30).
API_CANDIDATES: List[Dict[str, str]] = [
    {"dataset_id": "15058963", "name_ko": "식약처_마약류 약물 및 오남용 정보",
     "endpoint": "https://apis.data.go.kr/1471000/NrcdGnrlzInfoService01/getNrcdGnrlzList",
     "apply_url": "https://www.data.go.kr/data/15058963/openapi.do",
     "state": "approval_required"},
    {"dataset_id": "15058041", "name_ko": "식약처_마약류 및 원료물질 정보",
     "endpoint": "https://apis.data.go.kr/1471000/NrcdNdRwmtrInfoService01/getNrcdNdRwmtrInfoList01",
     "apply_url": "https://www.data.go.kr/data/15058041/openapi.do",
     "state": "approval_required"},
    {"dataset_id": "15095677", "name_ko": "식약처_의약품 제품 허가정보",
     "endpoint": "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnInq08",
     "apply_url": "https://www.data.go.kr/data/15095677/openapi.do",
     "state": "approval_required"},
    {"dataset_id": "15075057", "name_ko": "식약처_의약품개요정보(e약은요)",
     "endpoint": "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList",
     "apply_url": "https://www.data.go.kr/data/15075057/openapi.do",
     "state": "approval_required"},
    {"dataset_id": "15059486", "name_ko": "식약처_의약품안전사용서비스(DUR) 품목정보",
     "endpoint": "https://apis.data.go.kr/1471000/DURPrdlstInfoService03/getDurPrdlstInfoList03",
     "apply_url": "https://www.data.go.kr/data/15059486/openapi.do",
     "state": "approval_required"},
]

SELF_USE_RULE = {
    "limit_bottles": 6,
    "limit_months": 3,
    "legal_source_ko": "수입통관 사무처리에 관한 고시 별표 11(관세법 시행규칙 제45조제2항제1호)",
    "scope_note_ko": (
        "6병·3개월분은 자가사용 인정(면세통관) 기준이며, 요건확인 면제·온라인 구매(직구) 허용을 "
        "뜻하지 않습니다. 초과분은 세관장이 용법·용량을 보고 자가사용 여부를 판단합니다."
    ),
}

# 대마(식물·수지·제품) 자체 — 시행령 별표 7의2는 '합성품'만 열거하므로 식물·제품 표현을 따로 둔다.
CANNABIS_TERMS = ("대마", "대마초", "마리화나", "마리후아나", "marijuana", "cannabis", "hashish",
                  "해시시", "cbd", "thc", "칸나비디올", "칸나비놀", "테트라히드로칸나비놀",
                  "cannabidiol", "cannabinol", "tetrahydrocannabinol")

# 제품명 → 성분 참고 매핑(식약처 허가정보 조회가 아니라 성분 사전 대조용 힌트).
BRAND_ALIASES: Dict[str, Tuple[str, str]] = {
    "아데랄": ("암페타민", "Adderall(혼합 암페타민염)"),
    "애더럴": ("암페타민", "Adderall(혼합 암페타민염)"),
    "adderall": ("암페타민", "Adderall"),
    "리탈린": ("메틸페니데이트", "Ritalin"),
    "ritalin": ("메틸페니데이트", "Ritalin"),
    "콘서타": ("메틸페니데이트", "Concerta"),
    "concerta": ("메틸페니데이트", "Concerta"),
    "비반스": ("리스덱스암페타민", "Vyvanse"),
    "vyvanse": ("리스덱스암페타민", "Vyvanse"),
    "자낙스": ("알프라졸람", "Xanax"),
    "xanax": ("알프라졸람", "Xanax"),
    "스틸녹스": ("졸피뎀", "Stilnox"),
    "stilnox": ("졸피뎀", "Stilnox"),
    "암비엔": ("졸피뎀", "Ambien"),
    "ambien": ("졸피뎀", "Ambien"),
    "옥시콘틴": ("옥시코돈", "OxyContin"),
    "oxycontin": ("옥시코돈", "OxyContin"),
    "데메롤": ("페티딘", "Demerol"),
    "demerol": ("페티딘", "Demerol"),
    "위고비": ("세마글루타이드", "Wegovy"),
    "wegovy": ("세마글루타이드", "Wegovy"),
    "오젬픽": ("세마글루타이드", "Ozempic"),
    "ozempic": ("세마글루타이드", "Ozempic"),
    "마운자로": ("티르제파타이드", "Mounjaro"),
    "mounjaro": ("티르제파타이드", "Mounjaro"),
    "비아그라": ("실데나필", "Viagra"),
    "viagra": ("실데나필", "Viagra"),
    "시알리스": ("타다라필", "Cialis"),
    "cialis": ("타다라필", "Cialis"),
    "타이레놀": ("아세트아미노펜", "Tylenol"),
    "tylenol": ("아세트아미노펜", "Tylenol"),
    "부루펜": ("이부프로펜", "Brufen"),
    "지르텍": ("세티리진", "Zyrtec"),
    "zyrtec": ("세티리진", "Zyrtec"),
    "클라리틴": ("로라타딘", "Claritin"),
    "claritin": ("로라타딘", "Claritin"),
}

# 국내에서 의약품으로 관리되는 대표 성분(전수 아님). 근거: 국내 허가·급여 체계상 의약품.
KR_RX_INGREDIENTS: List[Dict[str, str]] = [
    {"name_ko": "멜라토닌", "name_en": "Melatonin",
     "note_ko": "국내에서는 의약품(수면 관련)으로 관리됩니다. 미국 보충제로 판매되어도 건강기능식품으로 반입할 수 있는 성분이 아닙니다."},
    {"name_ko": "DHEA", "name_en": "Dehydroepiandrosterone",
     "note_ko": "국내에서는 식품 원료로 인정되지 않아 건강기능식품·식품으로 반입할 수 없습니다."},
    {"name_ko": "요힘빈", "name_en": "Yohimbine",
     "note_ko": "국내에서는 의약품 성분으로 관리되어 보충제로 반입할 수 없습니다."},
    {"name_ko": "실데나필", "name_en": "Sildenafil",
     "note_ko": "전문의약품 성분입니다. 처방·수입허가 없이 개인 구매·반입은 인정되기 어렵습니다."},
    {"name_ko": "타다라필", "name_en": "Tadalafil",
     "note_ko": "전문의약품 성분입니다. 처방·수입허가 없이 개인 구매·반입은 인정되기 어렵습니다."},
    {"name_ko": "트라마돌", "name_en": "Tramadol",
     "note_ko": "마약류는 아니지만 전문의약품입니다. 의약품 수입 절차 또는 자가사용 인정기준을 따집니다."},
    {"name_ko": "세마글루타이드", "name_en": "Semaglutide",
     "note_ko": "전문의약품(비만·당뇨) 성분입니다. 해외 처방 제품의 개인 직구는 인정되지 않습니다."},
    {"name_ko": "티르제파타이드", "name_en": "Tirzepatide",
     "note_ko": "전문의약품 성분입니다. 해외 처방 제품의 개인 직구는 인정되지 않습니다."},
    {"name_ko": "피나스테리드", "name_en": "Finasteride",
     "note_ko": "전문의약품 성분입니다. 자가사용 인정기준을 넘는 수량은 요건확인이 필요합니다."},
    {"name_ko": "이소트레티노인", "name_en": "Isotretinoin",
     "note_ko": "전문의약품 성분입니다. 처방전이 있어도 수입 요건은 별도로 확인해야 합니다."},
]

# 국내 일반의약품 성분(참고). 마약류·원료물질과 달리 6병 기준이 그대로 적용되는 축이다.
OTC_INGREDIENTS: List[Dict[str, Any]] = [
    {"name_ko": "아세트아미노펜", "name_en": "Acetaminophen",
     "aliases": ["파라세타몰", "paracetamol"],
     "note_ko": "국내 일반의약품 성분입니다. 약국에서 판매되며, 개인 반입은 자가사용 인정기준(6병·3개월분)과 대조해야 합니다."},
    {"name_ko": "이부프로펜", "name_en": "Ibuprofen", "aliases": ["advil", "motrin"],
     "note_ko": "국내 일반의약품 성분입니다. 개인 반입은 자가사용 인정기준과 대조해야 합니다."},
    {"name_ko": "아스피린", "name_en": "Aspirin", "aliases": [],
     "note_ko": "국내 일반의약품 성분입니다. 개인 반입은 자가사용 인정기준과 대조해야 합니다."},
    {"name_ko": "로라타딘", "name_en": "Loratadine", "aliases": [],
     "note_ko": "국내 일반의약품 성분입니다. 개인 반입은 자가사용 인정기준과 대조해야 합니다."},
    {"name_ko": "세티리진", "name_en": "Cetirizine", "aliases": [],
     "note_ko": "국내 일반의약품 성분입니다. 개인 반입은 자가사용 인정기준과 대조해야 합니다."},
]

# 아주 짧은 영문 약어는 단어 경계로만 매칭한다(예: 'MDA'가 다른 단어 안에서 걸리지 않게).
_SHORT_LATIN = {"mda", "mdma", "thc", "cbd", "det", "dmt", "doe", "pma", "stp", "dom", "2c-b"}
_WORD_RE_CACHE: Dict[str, re.Pattern] = {}


def _compact(text: str) -> str:
    """공백·구두점을 모두 지운 비교용 문자열(별표 줄바꿈으로 끊긴 이름도 붙여서 비교)."""
    lowered = (text or "").lower()
    return re.sub(r"[\s\-_·ㆍ,.;:()\[\]{}'\"`~/\\|]+", "", lowered)


def _word_re(alias: str) -> re.Pattern:
    if alias not in _WORD_RE_CACHE:
        _WORD_RE_CACHE[alias] = re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])",
                                           re.IGNORECASE)
    return _WORD_RE_CACHE[alias]


@lru_cache(maxsize=2)
def load_schedules(path: Optional[str] = None) -> Dict[str, Any]:
    """`drug_schedules.json` 을 읽는다. 파일이 없으면 빈 사전(서비스가 죽지 않게)."""
    target = path or SCHEDULES_PATH
    try:
        with open(target, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"schedule_version": None, "generated_on": None, "substances": [], "precursors": [],
                "counts": {}, "attribution_ko": "", "note_ko": "성분 사전을 읽지 못했습니다."}


def _entry_aliases(entry: Dict[str, str]) -> List[str]:
    aliases: List[str] = []
    korean = str(entry.get("name_ko") or "").strip()
    if korean:
        aliases.append(korean)
    english = str(entry.get("name_en") or "").strip()
    for chunk in re.split(r"[,;/]", english):
        chunk = chunk.strip()
        if len(chunk) < 3:
            continue
        aliases.append(chunk)
        # '2,5-D MA' 처럼 줄바꿈으로 끊긴 표기를 붙인 형태도 넣는다.
        compact_chunk = _compact(chunk)
        if compact_chunk and compact_chunk != chunk.lower():
            aliases.append(compact_chunk)
    return aliases


@lru_cache(maxsize=2)
def _index(path: Optional[str] = None) -> Tuple[Tuple[str, str, str], ...]:
    """(alias, class, name_ko) 를 긴 별칭 우선으로 정렬한 색인."""
    data = load_schedules(path)
    rows: List[Tuple[str, str, str]] = []
    seen = set()
    for entry in list(data.get("substances") or []) + list(data.get("precursors") or []):
        class_code = str(entry.get("class") or "")
        name_ko = str(entry.get("name_ko") or "")
        for alias in _entry_aliases(entry):
            key = (alias.lower(), class_code)
            if key in seen or len(alias) < 2:
                continue
            seen.add(key)
            rows.append((alias, class_code, name_ko))
    for entry in KR_RX_INGREDIENTS:
        for alias in (entry["name_ko"], entry["name_en"]):
            key = (alias.lower(), "KR_RX")
            if key in seen:
                continue
            seen.add(key)
            rows.append((alias, "KR_RX", entry["name_ko"]))
    for entry in OTC_INGREDIENTS:
        for alias in [entry["name_ko"], entry["name_en"]] + list(entry.get("aliases") or []):
            key = (alias.lower(), "KR_OTC")
            if key in seen:
                continue
            seen.add(key)
            rows.append((alias, "KR_OTC", entry["name_ko"]))
    rows.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(rows)


def _matches(alias: str, text: str, compact: str) -> bool:
    if not alias:
        return False
    if re.search(r"[가-힣]", alias):
        compact_alias = _compact(alias)
        return len(compact_alias) >= 2 and compact_alias in compact
    lowered = alias.lower()
    if lowered in _SHORT_LATIN or len(lowered) <= 4:
        return bool(_word_re(alias).search(text))
    compact_alias = _compact(lowered)
    return len(compact_alias) >= 5 and compact_alias in compact


def detect_quantity(text: str) -> Optional[Dict[str, Any]]:
    """'30정', '2병', '6개' 같은 수량을 찾는다. mg·g는 함량이라 세지 않는다."""
    match = re.search(r"(\d{1,3})\s*(병|정|캡슐|알|개|통|박스|팩)", text or "")
    if not match:
        return None
    return {"value": int(match.group(1)), "unit": match.group(2)}


def detect_channel(text: str, facts: Optional[Dict[str, Any]] = None) -> str:
    """online(직구·온라인 구매) / carry(휴대 반입) / unknown."""
    value = str((facts or {}).get("channel") or "").strip().lower()
    if value in ("carry", "online"):
        return "carry" if value in ("carry", "휴대", "hand") else "online"
    lowered = (text or "").lower()
    if any(key in lowered for key in ("직구", "온라인", "인터넷", "해외몰", "아이허브", "iherb",
                                      "아마존", "amazon", "택배", "배송대행", "구매대행")):
        return "online"
    if any(key in lowered for key in ("휴대", "가방", "여행", "가지고", "들고", "출국", "입국")):
        return "carry"
    return "unknown"


DRUG_HINTS = ("의약품", "처방", "알약", "약품", "영양제", "보충제", "supplement", "medicine",
              "prescription")


def looks_like_drug_query(text: str, facts: Optional[Dict[str, Any]] = None) -> bool:
    """의약품 쟁점을 볼 만한 질의인지 판단한다(범용 단어만으로는 켜지 않게)."""
    facts = facts or {}
    if any(key in facts for key in ("drug_class", "drug_ingredient", "quantity")):
        return True
    lowered = (text or "").lower()
    if any(key in lowered for key in DRUG_HINTS):
        return True
    return bool(_direct_matches(text) or _brand_matches(text) or _cannabis_matches(text, set()))


def _direct_matches(text: str) -> List[Dict[str, Any]]:
    """성분 사전·브랜드 매핑·대마 표현과 직접 일치하는 항목."""
    compact = _compact(text)
    found: List[Dict[str, Any]] = []
    taken = set()
    for alias, class_code, name_ko in _index():
        if class_code in taken and name_ko in taken:
            continue
        if not _matches(alias, text, compact):
            continue
        if any(name_ko and name_ko in existing["name_ko"] and name_ko != existing["name_ko"]
               for existing in found):
            continue
        found.append({"alias": alias, "class": class_code, "name_ko": name_ko,
                      "match_type": "ingredient"})
        taken.add(class_code)
    return found


def _brand_matches(text: str) -> List[Dict[str, Any]]:
    compact = _compact(text)
    found: List[Dict[str, Any]] = []
    for brand, (ingredient_ko, label) in BRAND_ALIASES.items():
        if not _matches(brand, text, compact):
            continue
        class_code = "KR_RX"
        for alias, code, name_ko in _index():
            if name_ko == ingredient_ko:
                class_code = code
                break
        found.append({"alias": brand, "class": class_code, "name_ko": ingredient_ko,
                      "match_type": "product_alias", "product": label})
    return found


def _cannabis_matches(text: str, already: Iterable[str]) -> List[Dict[str, Any]]:
    compact = _compact(text)
    if any(name in already for name in ("칸나비디올", "칸나비놀", "테트라히드로칸나비놀")):
        return []
    # '대마도'(섬)처럼 행정지명에 섞인 경우는 대마 성분 질의로 보지 않는다.
    probe = str(text or "").replace("대마도", " ")
    hits = [term for term in CANNABIS_TERMS if _matches(term, probe, _compact(probe))]
    if not hits:
        return []
    return [{"alias": hits[0], "class": "CANNABIS_SYNTHETIC", "name_ko": "대마(대마초·수지·제품)",
             "match_type": "cannabis_term"}]


def _describe(match: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """사전 항목의 분류·근거·비고를 붙인다."""
    class_code = match["class"]
    entry = None
    for row in list(data.get("substances") or []) + list(data.get("precursors") or []):
        if row.get("name_ko") == match["name_ko"]:
            entry = row
            break
    out = {
        "name_ko": match["name_ko"],
        "class": class_code,
        "class_ko": CLASS_LABEL_KO.get(class_code, class_code),
        "matched_alias": match.get("alias", ""),
        "match_type": match.get("match_type", "ingredient"),
        "reference_ko": (entry or {}).get("reference") or (
            "법 제2조제4호" if class_code == "CANNABIS_SYNTHETIC" else ""),
        "schedule_table_ko": (entry or {}).get("table") or "",
        "name_en": (entry or {}).get("name_en") or "",
        "note_ko": "",
    }
    if match.get("product"):
        out["note_ko"] = f"제품명 '{match['product']}'을(를) 성분 '{match['name_ko']}'(으)로 본 참고 매핑입니다."
    if class_code == "PRECURSOR":
        out["note_ko"] = (out["note_ko"] + " " if out["note_ko"] else "") + (
            "마약류는 아니지만 마약류 원료물질(수출입 허가 대상)이며, 고시 별표 11은 이 성분을 함유한 "
            "단일완제의약품을 요건확인 대상으로 적고 있습니다."
        )
    if class_code == "KR_RX":
        for row in KR_RX_INGREDIENTS:
            if row["name_ko"] == match["name_ko"]:
                out["note_ko"] = row["note_ko"]
                break
    if class_code == "KR_OTC":
        for row in OTC_INGREDIENTS:
            if row["name_ko"] == match["name_ko"]:
                out["note_ko"] = row["note_ko"]
                break
    return out


def _basis_for(matches: List[Dict[str, Any]], channel: str, quantity: Optional[Dict[str, Any]]):
    classes = {item["class"] for item in matches}
    basis: List[Dict[str, str]] = []
    if classes & set(CONTROLLED_CLASSES):
        basis.extend(BASIS_NARCOTIC)
    if classes & {"PRECURSOR", "KR_RX"}:
        basis.extend(BASIS_PRECURSOR if "PRECURSOR" in classes else [])
        basis.extend(BASIS_SELF_USE)
    if not basis:
        basis.extend(BASIS_SELF_USE)
    out: List[Dict[str, str]] = []
    seen = set()
    for row in basis:
        key = (row["law"], row["article"])
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def _guidance(matches: List[Dict[str, Any]], channel: str, quantity: Optional[Dict[str, Any]],
              self_use_status: str) -> List[str]:
    guidance: List[str] = []
    classes = {item["class"] for item in matches}
    if classes & set(CONTROLLED_CLASSES):
        names = ", ".join(sorted({item["name_ko"] for item in matches
                                  if item["class"] in CONTROLLED_CLASSES}))
        guidance.append(
            f"입력하신 성분({names})은 마약류(마약·향정신성의약품·대마 또는 그 합성품)로 관리됩니다. "
            "마약류취급자가 아니면 수입·소지가 금지되고, 마약류수출입업자가 아니면 마약·향정신성의약품을 "
            "수출입할 수 없습니다. 처방전·복용 중인 약이라는 사정이나 수량(6병·3개월분)과 관계없이 "
            "개인 반입은 인정되기 어렵습니다."
        )
    if "PRECURSOR" in classes:
        names = ", ".join(sorted({item["name_ko"] for item in matches if item["class"] == "PRECURSOR"}))
        guidance.append(
            f"{names}은(는) 마약류 원료물질로, 마약류는 아니지만 수출입 허가 대상입니다. "
            "이 성분을 함유한 단일완제의약품은 고시 별표 11에서 6병 기준의 요건확인 면제 대상에서 "
            "빠져 있으므로, 감기약·다이어트 보조제라도 통관 전 요건확인 여부를 세관에 확인해야 합니다."
        )
    if "KR_RX" in classes:
        names = ", ".join(sorted({item["name_ko"] for item in matches if item["class"] == "KR_RX"}))
        guidance.append(
            f"{names}은(는) 국내에서 의약품으로 관리되는 성분입니다. 해외에서 보충제로 팔려도 "
            "건강기능식품·식품으로 반입하는 절차가 없고, 의약품으로 들여오려면 수입업 신고·품목허가 "
            "또는 자가사용 인정기준 확인이 필요합니다."
        )
    if "KR_OTC" in classes:
        names = ", ".join(sorted({item["name_ko"] for item in matches if item["class"] == "KR_OTC"}))
        guidance.append(
            f"{names}은(는) 국내 일반의약품 성분입니다. 약국 판매가 원칙이고 온라인 판매·알선은 "
            "금지되며, 개인 반입은 자가사용 인정기준(6병·3개월분)과 대조해야 합니다."
        )
    if not matches:
        guidance.append(
            "입력에서 마약류·원료물질·국내 전용 성분 사전과 일치하는 성분을 찾지 못했습니다. "
            "성분표(Supplement Facts·주성분)의 표기를 그대로 넣으면 다시 대조할 수 있습니다."
        )
    if self_use_status == "online":
        guidance.append(
            "온라인 직접 구매(직구)는 6병·3개월분 자가사용 인정기준으로 허용되는 경로가 아닙니다. "
            "이 기준은 휴대 반입·소액물품 통관에서 자가사용을 인정하는 범위입니다."
        )
    elif self_use_status == "within_carry_allowance":
        guidance.append(
            "휴대 반입으로 입력하신 수량은 자가사용 인정기준(총 6병, 초과 시 용법상 3개월 복용량) "
            "안입니다. 다만 마약류·원료물질·요건확인 대상 성분이 섞여 있으면 이 기준이 그대로 "
            "적용되지 않으므로, 처방전·구매내역 등 소명자료를 함께 준비해야 합니다."
        )
    elif self_use_status == "over_carry_allowance":
        guidance.append(
            "입력하신 수량이 6병 기준을 넘습니다. 6병을 넘는 경우에는 의약품 용법상 3개월 복용량 "
            "범위에서 세관장이 자가사용 여부를 판단하므로, 처방전·복약 설명자료로 소명해야 합니다."
        )
    elif self_use_status == "unknown":
        guidance.append(
            "휴대 반입인지 온라인 구매인지, 수량이 얼마인지 알려주시면 자가사용 인정기준(6병·3개월분)과 "
            "대조해 드릴 수 있습니다."
        )
    guidance.append(
        "최종 통관·반입 가능 여부는 세관장과 식품의약품안전처가 판단하며, 이 결과로 그 판정을 "
        "확정하지 않습니다. 사전 참고용으로만 쓰세요."
    )
    return guidance


def assess(query: str, facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """질의문·사실관계로 의약품 반입 쟁점을 스크리닝한다(네트워크 불필요)."""
    facts = dict(facts or {})
    text = " ".join(str(part) for part in (query, facts.get("drug_ingredient", ""),
                                           facts.get("drug_name", "")) if part)
    data = load_schedules()
    direct = _direct_matches(text)
    brands = _brand_matches(text)
    merged: List[Dict[str, Any]] = []
    seen_names = set()
    for item in direct + brands:
        if item["name_ko"] in seen_names:
            continue
        seen_names.add(item["name_ko"])
        merged.append(item)
    merged.extend(_cannabis_matches(text, seen_names))
    described = [_describe(item, data) for item in merged]
    described.sort(key=lambda item: CLASS_SEVERITY.get(item["class"], 0), reverse=True)

    quantity = detect_quantity(text) or ({"value": facts["quantity"], "unit": facts.get("quantity_unit", "")}
                                         if isinstance(facts.get("quantity"), int) else None)
    channel = detect_channel(text, facts)
    classes = {item["class"] for item in described}
    if channel == "online":
        self_use_status = "online"
    elif channel == "carry" and quantity and quantity.get("value"):
        self_use_status = ("within_carry_allowance" if int(quantity["value"]) <= SELF_USE_RULE["limit_bottles"]
                           else "over_carry_allowance")
    else:
        self_use_status = "unknown"

    if classes & set(CONTROLLED_CLASSES):
        state = "controlled_substance"
    elif "PRECURSOR" in classes:
        state = "precursor_restricted"
    elif "KR_RX" in classes:
        state = "kr_prescription_only"
    elif "KR_OTC" in classes:
        state = "kr_otc"
    else:
        state = "no_schedule_match" if not looks_like_drug_query(text) else "schedule_clear"

    return {
        "state": state,
        "channel": channel,
        "quantity": quantity,
        "self_use_status": self_use_status,
        "self_use_rule": dict(SELF_USE_RULE),
        "matches": described,
        "match_count": len(described),
        "guidance_ko": _guidance(described, channel, quantity, self_use_status),
        "basis": _basis_for(described, channel, quantity),
        "schedule_version": data.get("schedule_version"),
        "schedule_generated_on": data.get("generated_on"),
        "checked_counts": {
            "controlled_substances": len(data.get("substances") or []),
            "precursors": len(data.get("precursors") or []),
            "kr_rx_seed_ingredients": len(KR_RX_INGREDIENTS),
            "kr_otc_seed_ingredients": len(OTC_INGREDIENTS),
        },
        "coverage_ko": (
            "마약류·원료물질은 마약류 관리에 관한 법률 시행령 별표 1~8에서 생성한 로컬 사전"
            f"({len(data.get('substances') or [])}건 + 원료물질 {len(data.get('precursors') or [])}건)과 "
            "대조했습니다. 국내 의약품 성분은 대표 시드 목록만 대조했고, 식약처 의약품 허가정보·e약은요·"
            "DUR API는 활용신청 승인 전이라 실시간 전수 대조는 제공하지 않습니다."
        ),
        "api_candidates": [{"dataset_id": row["dataset_id"], "name_ko": row["name_ko"],
                            "state": row["state"], "apply_url": row["apply_url"]}
                           for row in API_CANDIDATES],
        "attribution_ko": data.get("attribution_ko") or "출처: 법제처 국가법령정보센터",
        "official_urls": [
            "https://nedrug.mfds.go.kr",  # 식약처 의약품안전나라(품목·성분 확인)
            "https://unipass.customs.go.kr",  # 관세청 유니패스(통관 조회)
            NOTICE_URL,
        ],
        "verified_on": VERIFIED_ON,
    }


CARD_TRIGGERS: Dict[str, Tuple[str, ...]] = {
    "TRAP-23": CONTROLLED_CLASSES,
    "TRAP-24": RESTRICTED_CLASSES,
}


def cards_for(screening: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    """스크리닝 결과로 반드시 함께 보여야 할 카드와 근거 신호를 돌려준다."""
    classes = {item["class"] for item in screening.get("matches") or []}
    out: List[Tuple[str, List[str]]] = []
    if classes & set(CONTROLLED_CLASSES):
        names = [item["name_ko"] for item in screening["matches"] if item["class"] in CONTROLLED_CLASSES]
        out.append(("TRAP-23", names[:3]))
    if classes & set(RESTRICTED_CLASSES):
        names = [item["name_ko"] for item in screening["matches"] if item["class"] in RESTRICTED_CLASSES]
        out.append(("TRAP-24", names[:3]))
    return out


def self_use_card_facts(screening: Dict[str, Any]) -> Dict[str, Any]:
    """TRAP-14(의약품 직구) 판정을 사실관계로 낮출 때 쓰는 값."""
    return {
        "channel": screening.get("channel"),
        "quantity": (screening.get("quantity") or {}).get("value"),
        "self_use_status": screening.get("self_use_status"),
    }
