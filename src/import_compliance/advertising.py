"""과대광고·부당표시 검수 엔진 (CLNS 0.2.0).

무엇을 하는가
-------------
상세페이지·상품명·홍보 문구를 넣으면 **품목 유형(일반식품 / 건강기능식품 / 화장품 /
기능성화장품)** 에 따라 허용·금지 기준을 다르게 적용해 위험 표현을 찾고, 근거 법령·조항,
위험도(높음/주의), 대체 표현을 돌려준다.

왜 유형별로 달라야 하는가
------------------------
같은 문구가 유형에 따라 합법이기도 하고 위법이기도 하다.

- "체지방 감소에 도움을 줄 수 있음" — 건강기능식품은 식약처가 인정한 기능성 범위 안이면
  표시할 수 있지만, 일반식품이 이 표현을 쓰면 건강기능식품으로 오인시키는 표시다
  (식품등의 표시ㆍ광고에 관한 법률 제8조제1항제3호).
- "미백", "주름개선", "자외선 차단" — 기능성화장품으로 심사·보고를 마치고 "기능성화장품"
  표시를 한 경우에만 쓸 수 있고, 일반화장품이 쓰면 화장품법 제13조제1항제2호 위반이다.
- "아토피 개선", "피부 재생", "항암" — 어느 유형에서도 질병의 예방·치료 효능을 표시하는
  것으로 보이면 금지된다(식품표시광고법 제8조제1항제1호, 화장품법 제13조제1항제1호).

근거의 성격(정직하게)
--------------------
- 법률·시행령·시행규칙 조문은 **2026-11-19 법제처 국가법령정보 OPEN API로 조회해
  조문시행일자가 오늘 이하인 최신 버전**의 본문을 인용했다(검증 결과:
  `ad-label-law-verification.json`).
- 고시(「식품등의 부당한 표시 또는 광고의 내용 기준」, 2025-12-04 시행)는 세부 판단기준으로
  안내만 하고, 조문 단위 인용은 법령 조문으로 한정한다. 고시는 수시 개정되므로 원문 확인이
  필요하다.
- 이 엔진은 **문구 패턴 대조**다. 같은 단어라도 문맥(부정문·인용·성분명)에 따라 판단이
  달라지므로, 결과는 "확인이 필요한 표현 목록"이며 확정 판정이 아니다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

VERIFIED_ON = "2026-11-19"

# ---------------------------------------------------------------------------
# 1. 품목 유형
# ---------------------------------------------------------------------------
PRODUCT_TYPES: Dict[str, Dict[str, Any]] = {
    "general_food": {
        "label_ko": "일반식품(가공식품·수입식품 포함)",
        "label_en": "General food",
        "governing_law_ko": "식품등의 표시ㆍ광고에 관한 법률",
        "functional_allowed": False,
    },
    "health_functional_food": {
        "label_ko": "건강기능식품",
        "label_en": "Health functional food",
        "governing_law_ko": "식품등의 표시ㆍ광고에 관한 법률 + 건강기능식품에 관한 법률",
        "functional_allowed": True,
    },
    "cosmetics": {
        "label_ko": "화장품(일반)",
        "label_en": "Cosmetics",
        "governing_law_ko": "화장품법",
        "functional_allowed": False,
    },
    "functional_cosmetics": {
        "label_ko": "기능성화장품",
        "label_en": "Functional cosmetics",
        "governing_law_ko": "화장품법",
        "functional_allowed": True,
    },
}

PRODUCT_TYPE_ALIASES: Dict[str, str] = {
    "food": "general_food", "general": "general_food", "general_food": "general_food",
    "식품": "general_food", "일반식품": "general_food", "가공식품": "general_food",
    "수입식품": "general_food", "processed_food": "general_food",
    "hff": "health_functional_food", "health_functional": "health_functional_food",
    "health_functional_food": "health_functional_food", "건강기능식품": "health_functional_food",
    "건기식": "health_functional_food", "supplement": "health_functional_food",
    "cosmetic": "cosmetics", "cosmetics": "cosmetics", "화장품": "cosmetics",
    "functional_cosmetics": "functional_cosmetics", "기능성화장품": "functional_cosmetics",
}

FOOD_TYPES = ("general_food", "health_functional_food")
COSMETIC_TYPES = ("cosmetics", "functional_cosmetics")


def normalize_product_type(value: Any, text: str = "") -> str:
    """입력값·문구에서 품목 유형을 정한다(추측으로 좁히지 않는다)."""
    raw = str(value or "").strip().lower()
    if raw in PRODUCT_TYPE_ALIASES:
        return PRODUCT_TYPE_ALIASES[raw]
    probe = str(text or "")
    if any(k in probe for k in ("건강기능식품", "건기식", "기능성 원료", "health functional")):
        return "health_functional_food"
    if "기능성화장품" in probe:
        return "functional_cosmetics"
    if any(k in probe for k in ("화장품", "크림", "세럼", "앰플", "로션", "토너", "cosmetic")):
        return "cosmetics"
    return "general_food"


def product_type_label(product_type: str) -> str:
    return PRODUCT_TYPES.get(product_type, PRODUCT_TYPES["general_food"])["label_ko"]


# ---------------------------------------------------------------------------
# 2. 근거 법령 (2026-11-19 법제처 API 실조회)
# ---------------------------------------------------------------------------
LAW_URL_FOOD_AD = "https://www.law.go.kr/법령/식품등의표시ㆍ광고에관한법률"
LAW_URL_FOOD_AD_RULE = "https://www.law.go.kr/법령/식품등의표시ㆍ광고에관한법률시행규칙"
LAW_URL_FOOD_AD_DECREE = "https://www.law.go.kr/법령/식품등의표시ㆍ광고에관한법률시행령"
LAW_URL_HFF = "https://www.law.go.kr/법령/건강기능식품에관한법률"
LAW_URL_COSMETICS = "https://www.law.go.kr/법령/화장품법"
LAW_URL_COSMETICS_RULE = "https://www.law.go.kr/법령/화장품법시행규칙"
LAW_URL_IMPORT_FOOD = "https://www.law.go.kr/법령/수입식품안전관리특별법"
AD_CONTENT_STANDARD_URL = "https://www.law.go.kr/행정규칙/식품등의부당한표시또는광고의내용기준"
LABEL_STANDARD_URL = "https://www.law.go.kr/행정규칙/식품등의표시기준"
HFF_STANDARD_URL = "https://www.law.go.kr/행정규칙/건강기능식품의기준및규격"


def _basis(law: str, article: str, effective_date: str, url: str, quote: str) -> Dict[str, str]:
    return {"law": law, "article": article, "effective_date": effective_date,
            "url": url, "quote": quote, "verified_on": VERIFIED_ON}


# --- 식품등의 표시ㆍ광고에 관한 법률 (시행 2025-09-19) ---------------------
B_FOOD_8_1_DISEASE = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제1호", "2025-09-19", LAW_URL_FOOD_AD,
    "누구든지 식품등의 명칭ㆍ제조방법ㆍ성분 등 대통령령으로 정하는 사항에 관하여 질병의 "
    "예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_MEDICINE = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제2호", "2025-09-19", LAW_URL_FOOD_AD,
    "식품등을 의약품으로 인식할 우려가 있는 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_HFF = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제3호", "2025-09-19", LAW_URL_FOOD_AD,
    "건강기능식품이 아닌 것을 건강기능식품으로 인식할 우려가 있는 표시 또는 광고를 "
    "하여서는 아니 된다.",
)
B_FOOD_8_1_FALSE = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제4호", "2025-09-19", LAW_URL_FOOD_AD,
    "거짓ㆍ과장된 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_DECEPTION = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제5호", "2025-09-19", LAW_URL_FOOD_AD,
    "소비자를 기만하는 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_DISPARAGE = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제6호", "2025-09-19", LAW_URL_FOOD_AD,
    "다른 업체나 다른 업체의 제품을 비방하는 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_COMPARE = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제7호", "2025-09-19", LAW_URL_FOOD_AD,
    "객관적인 근거 없이 자기 또는 자기의 식품등을 다른 영업자나 다른 영업자의 식품등과 "
    "부당하게 비교하는 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_INDECENT = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제8호", "2025-09-19", LAW_URL_FOOD_AD,
    "사행심을 조장하거나 음란한 표현을 사용하여 공중도덕이나 사회윤리를 현저하게 침해하는 "
    "표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_SIMILAR = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제9호", "2025-09-19", LAW_URL_FOOD_AD,
    "총리령으로 정하는 식품등이 아닌 물품의 상호ㆍ상표ㆍ용기ㆍ포장과 동일ㆍ유사한 것을 "
    "사용하여 해당 물품으로 오인ㆍ혼동할 수 있는 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_8_1_REVIEW = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제8조제1항제10호", "2025-09-19", LAW_URL_FOOD_AD,
    "제10조제1항에 따라 심의를 받지 아니하거나 같은 조 제4항을 위반하여 심의 결과에 따르지 "
    "아니한 표시 또는 광고를 하여서는 아니 된다.",
)
B_FOOD_9_PROOF = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제9조제1항", "2025-09-19", LAW_URL_FOOD_AD,
    "식품등에 표시를 하거나 식품등을 광고한 자는 자기가 한 표시 또는 광고에 대하여 "
    "실증(實證)할 수 있어야 한다.",
)
B_FOOD_DECREE_3 = _basis(
    "식품등의 표시ㆍ광고에 관한 법률 시행령", "제3조", "2025-09-19", LAW_URL_FOOD_AD_DECREE,
    "법 제8조제1항에 따른 부당한 표시 또는 광고의 구체적인 내용은 별표 1과 같다.",
)
B_FOOD_RULE_5 = _basis(
    "식품등의 표시ㆍ광고에 관한 법률 시행규칙", "제5조제1항", "2024-12-30", LAW_URL_FOOD_AD_RULE,
    "법 제4조제1항 및 제2항에 따른 소비자 안전을 위한 주의사항의 구체적인 표시사항은 "
    "별표 2와 같다.",
)
B_FOOD_7_AD_BASIC = _basis(
    "식품등의 표시ㆍ광고에 관한 법률", "제7조제1항", "2025-09-19", LAW_URL_FOOD_AD,
    "식품등을 광고할 때에는 제품명 및 업소명을 포함시켜야 한다.",
)

# --- 건강기능식품에 관한 법률 (시행 2026-10-08) ---------------------------
B_HFF_3_DEF = _basis(
    "건강기능식품에 관한 법률", "제3조제1호ㆍ제2호", "2026-10-08", LAW_URL_HFF,
    "\"건강기능식품\"이란 인체에 유용한 기능성을 가진 원료나 성분을 사용하여 제조한 식품을 "
    "말하고, \"기능성\"이란 인체의 구조 및 기능에 대하여 영양소를 조절하거나 생리학적 작용 "
    "등과 같은 보건 용도에 유용한 효과를 얻는 것을 말한다.",
)
B_HFF_15_NO_DISEASE = _basis(
    "건강기능식품에 관한 법률", "제15조제2항", "2026-10-08", LAW_URL_HFF,
    "식품의약품안전처장은 고시되지 아니한 건강기능식품의 원료나 성분에 대하여 안전성 및 "
    "기능성 등에 관한 자료를 검토한 후 사용할 수 있는 원료로 인정할 수 있다. 다만, 질병의 "
    "치료ㆍ예방 효과가 있는 원료나 성분은 인정하여서는 아니 된다.",
)
B_HFF_14_STANDARD = _basis(
    "건강기능식품에 관한 법률", "제14조", "2026-10-08", LAW_URL_HFF,
    "식품의약품안전처장은 건강기능식품의 제조ㆍ가공ㆍ사용 등에 필요한 기준 및 규격을 정하여 "
    "고시한다.",
)

# --- 화장품법 (시행 2026-10-20) ------------------------------------------
B_COS_13_1_MEDICINE = _basis(
    "화장품법", "제13조제1항제1호", "2026-10-20", LAW_URL_COSMETICS,
    "영업자 또는 판매자는 의약품으로 잘못 인식할 우려가 있는 표시 또는 광고를 하여서는 "
    "아니 된다.",
)
B_COS_13_1_FUNCTIONAL = _basis(
    "화장품법", "제13조제1항제2호", "2026-10-20", LAW_URL_COSMETICS,
    "기능성화장품이 아닌 화장품을 기능성화장품으로 잘못 인식할 우려가 있거나 "
    "기능성화장품의 안전성ㆍ유효성에 관한 심사결과와 다른 내용의 표시 또는 광고를 하여서는 "
    "아니 된다.",
)
B_COS_13_1_AI_EXPERT = _basis(
    "화장품법", "제13조제1항제4호", "2026-10-20", LAW_URL_COSMETICS,
    "인공지능시스템을 이용하여 생성한 실제와 구분하기 어려운 가상의 음향ㆍ이미지ㆍ영상을 "
    "활용한 광고로서 의사ㆍ약사ㆍ대학교수 등 관련 분야 전문가가 화장품을 보증ㆍ추천ㆍ"
    "사용하는 것으로 오인하게 할 우려가 있는 광고를 하여서는 아니 된다.",
)
B_COS_13_1_DECEPTION = _basis(
    "화장품법", "제13조제1항제5호", "2026-10-20", LAW_URL_COSMETICS,
    "그 밖에 사실과 다르게 소비자를 속이거나 소비자가 잘못 인식하도록 할 우려가 있는 "
    "표시 또는 광고를 하여서는 아니 된다.",
)
B_COS_2_FUNCTIONAL = _basis(
    "화장품법", "제2조제2호", "2026-10-20", LAW_URL_COSMETICS,
    "\"기능성화장품\"이란 피부의 미백에 도움을 주는 제품, 피부의 주름개선에 도움을 주는 "
    "제품, 자외선으로부터 피부를 보호하는 데에 도움을 주는 제품, 모발의 색상 변화ㆍ제거 "
    "또는 영양공급에 도움을 주는 제품, 피부나 모발의 기능 약화로 인한 건조함ㆍ갈라짐ㆍ"
    "빠짐ㆍ각질화 등을 방지하거나 개선하는 데에 도움을 주는 제품 등 총리령으로 정하는 "
    "화장품을 말한다.",
)

# ---------------------------------------------------------------------------
# 3. 탐지 규칙
# ---------------------------------------------------------------------------
# applies_to: 이 규칙을 적용할 품목 유형. food_allowed_when_hff=True 면 건강기능식품에서는
#           인정 기능성 범위 안이라는 전제로 '주의'로 낮춘다(범위 밖이면 여전히 높음).
# patterns: (정규식, 표시용 라벨) 쌍. 한국어는 조사가 붙으므로 어간으로 찾는다.
#
# 조사 허용(0.5.3)
# ---------------
# '치매 예방'과 '치매를 예방'은 같은 표현인데, 목적격ㆍ주격 조사가 하나 끼면 패턴이
# 끊겨 검수를 그냥 통과해 버렸다(외부 코드 검수 제보: 6문장 중 4문장 미탐지).
# 명사 어간과 서술어 사이에 을/를/이/가/은/는/의 가 들어가도 이어서 대조한다.
_JO = r"\s*(?:[을를이가은는의]\s*)?"

CLAIM_RULES: List[Dict[str, Any]] = [
    {
        "id": "AD-01",
        "name_ko": "질병 예방ㆍ치료 효능 표시",
        "risk": "high",
        "category": "질병 효능",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (rf"항암|항(?=암)|암{_JO}(예방|치료|억제)|종양{_JO}(억제|축소)", "항암·암 예방·치료"),
            (rf"당뇨(병)?{_JO}(예방|치료|개선|관리)|혈당{_JO}(조절|개선|낮춰|내려)", "당뇨·혈당 조절"),
            (rf"고혈압{_JO}(예방|치료|개선)|혈압{_JO}(조절|낮춰|내려|개선)", "고혈압·혈압 조절"),
            (rf"아토피|피부염{_JO}(치료|개선)|건선", "아토피·피부염 치료"),
            (rf"관절염|류마티스|통증{_JO}(완화|치료|없애)|디스크{_JO}(치료|개선)", "관절염·통증 치료"),
            (rf"치매{_JO}(예방|치료)|기억력{_JO}(치료|개선)|인지기능{_JO}(치료|개선)", "치매·인지기능 치료"),
            (rf"우울증|불면증{_JO}(치료|개선)|숙면{_JO}(치료|보장)", "우울증·불면증 치료"),
            (rf"간{_JO}(기능|수치){_JO}(개선|회복)|지방간|간경화|간{_JO}해독", "간질환 개선"),
            (rf"(위염|역류성\s*식도염|과민성\s*대장|변비){_JO}(치료|개선|없애)", "소화기 질환 치료"),
            (rf"탈모{_JO}(치료|예방|방지)|발모{_JO}(촉진)?", "탈모 치료·예방"),
            (rf"여드름{_JO}(치료|개선|없애)|뾰루지{_JO}(치료|없애)", "여드름 치료"),
            (rf"(질병|질환){_JO}(예방|치료)", "질병 예방·치료"),
            (r"cure|treat(s|ment)?\s+(cancer|diabetes|acne|atopy)|anti-?cancer", "질병 치료(영문)"),
        ],
        "why_ko": (
            "질병의 예방ㆍ치료에 효능이 있는 것으로 인식될 우려가 있는 표시는 금지됩니다. "
            "건강기능식품도 질병의 치료ㆍ예방 효과가 있는 원료는 인정 대상이 아니므로, "
            "인정 기능성 범위 안이라는 사정만으로 질병명을 붙여 표현할 수는 없습니다."
        ),
        "safer_ko": (
            "질병명 대신 '건강 관리'ㆍ'영양 보충'ㆍ'보습' 등 확인된 범위로 낮추고, "
            "건강기능식품이라면 식약처가 인정한 기능성 문구를 그대로 사용하세요"
            "(예: '칼슘과 인이 흡수되고 이용되는 데 필요')."
        ),
        "basis": [B_FOOD_8_1_DISEASE, B_HFF_15_NO_DISEASE, B_COS_13_1_MEDICINE],
    },
    {
        "id": "AD-02",
        "name_ko": "의약품 오인 표시",
        "risk": "high",
        "category": "의약품 오인",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"(복용|처방)\s*(하|받|전|후)", "복용·처방 표현"),
            (rf"약{_JO}(효과|처럼|보다)|약효|효능{_JO}효과|임상\s*(시험|실험|결과)", "약효·임상 표현"),
            (rf"부작용{_JO}(이)?\s*(없|전혀)", "부작용 없음"),
            (rf"의약품{_JO}(대체|수준|급)", "의약품 대체·수준"),
            (rf"치료제|치유|완치|재생{_JO}(치료|크림)?", "치료제·완치·재생"),
        ],
        "why_ko": "식품ㆍ화장품을 의약품으로 인식시킬 우려가 있는 표현은 금지됩니다.",
        "safer_ko": "‘먹는 약’, ‘바르는 치료제’ 같은 표현을 빼고, 섭취·사용 방법과 확인된 기능만 남기세요.",
        "basis": [B_FOOD_8_1_MEDICINE, B_COS_13_1_MEDICINE],
    },
    {
        "id": "AD-03",
        "name_ko": "건강기능식품 오인 표시",
        "risk": "high",
        "category": "건기식 오인",
        "applies_to": ["general_food"],
        "patterns": [
            (r"건강기능식품|건기식", "건강기능식품 표방"),
            (rf"기능성{_JO}(원료|인정|표방)|식약처\s*(인정|인증)\s*기능성", "기능성 원료·식약처 인정 표방"),
            (r"고시형\s*원료|개별인정형", "고시형·개별인정형 원료 표방"),
            (rf"면역력{_JO}(증진|강화|향상)|체지방{_JO}감소|혈중{_JO}중성지질|혈행{_JO}개선|"
             rf"눈{_JO}건강|장{_JO}건강|피부{_JO}건강|간{_JO}건강|항산화", "인정 기능성 표현(건기식 전용)"),
        ],
        "why_ko": (
            "건강기능식품이 아닌 식품이 건강기능식품으로 인식될 우려가 있는 표시는 금지됩니다. "
            "면역력 증진, 체지방 감소 같은 표현은 식약처가 인정한 기능성 원료에만 쓸 수 있는 "
            "문구라 일반식품 상세페이지에서는 건기식 오인으로 판단될 수 있습니다."
        ),
        "safer_ko": (
            "‘건강기능식품’·‘기능성’ 표방을 빼고 원재료와 영양성분 정보로 설명하세요. "
            "같은 기능성을 주장하려면 건강기능식품으로 제조·수입 신고한 제품이어야 합니다."
        ),
        "basis": [B_FOOD_8_1_HFF, B_HFF_3_DEF],
    },
    {
        "id": "AD-04",
        "name_ko": "거짓ㆍ과장 표시(절대 표현)",
        "risk": "high",
        "category": "거짓·과장",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"100\s*%|백\s*퍼센트", "100%"),
            (r"(완벽|완전)\s*(하게|한)?\s*(제거|차단|회복|개선|없)", "완벽·완전"),
            (r"무조건|절대(적)?\s*(로)?\s*(안전|효과|차단)", "무조건·절대"),
            (rf"즉시{_JO}(효과|개선|재생|사라|없어|완화)|즉각{_JO}(효과|반응|개선)|단\s*번에|하루\s*만에|3일\s*안에|일주일\s*만에", "즉시·단기 효과"),
            (r"최고|최상|최강|1위|유일(한|무이)?|세계\s*(최초|최고|1위)", "최상급·1위"),
            (rf"영구(적)?|평생{_JO}(유지|지속)|다시는\s*안", "영구·평생"),
            (rf"독성{_JO}없|부작용\s*0|0\s*%?\s*부작용", "무독성·부작용 0"),
        ],
        "why_ko": (
            "거짓ㆍ과장된 표시 또는 광고는 금지됩니다. ‘100%’, ‘즉시’, ‘최고’ 같은 절대 표현은 "
            "그 자체로 실증 부담이 커지고, 근거가 없으면 과장 표시로 판단됩니다."
        ),
        "safer_ko": "수치와 조건을 붙이세요(시험 대상ㆍ기간ㆍ측정 방법을 함께 표시하고, 개인차를 밝히세요).",
        "basis": [B_FOOD_8_1_FALSE, B_FOOD_9_PROOF, B_COS_13_1_DECEPTION],
    },
    {
        "id": "AD-05",
        "name_ko": "체험기ㆍ비포애프터 강조",
        "risk": "caution",
        "category": "체험기·전후 비교",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (rf"(먹|사용|발라|써)(어|아)?\s*봤더니|먹고\s*나서|사용\s*후기|체험{_JO}(후기|기|담)", "체험 후기"),
            (rf"비포\s*(앤|&|/)?\s*애프터|before\s*(&|and)?\s*after|전후{_JO}(사진|비교)", "비포·애프터"),
            (rf"\d+\s*(kg|킬로){_JO}(감량|빠졌|줄었)", "감량 수치"),
            (rf"\d+\s*(cm|센티){_JO}(줄었|감소|빠졌)", "둘레 감소 수치"),
        ],
        "why_ko": (
            "체험기·전후 사진은 소비자에게 효능을 단정적으로 인식시킬 수 있어 실증자료와 "
            "함께 관리해야 합니다. 개인차·시험 조건을 밝히지 않은 전후 비교는 기만적 표시로 "
            "판단될 수 있습니다."
        ),
        "safer_ko": "‘개인차가 있으며 식품은 질병 치료에 사용되지 않습니다’를 붙이고, 촬영 조건·기간을 함께 밝히세요.",
        "basis": [B_FOOD_8_1_FALSE, B_FOOD_8_1_DECEPTION, B_FOOD_9_PROOF, B_COS_13_1_DECEPTION],
    },
    {
        "id": "AD-06",
        "name_ko": "부당 비교ㆍ최상급 비교",
        "risk": "caution",
        "category": "부당 비교",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"타사|타\s*브랜드|경쟁사|다른\s*제품보다|시중\s*제품\s*(대비|보다)", "타사 비교"),
            (rf"\d+\s*배{_JO}(더|높|강|빠)", "배수 비교"),
            (r"(압도적|독보적)\s*(으로)?\s*(1위|최고|우수)", "압도적·독보적"),
        ],
        "why_ko": "객관적 근거 없이 다른 업체·제품과 비교하는 표시는 금지됩니다. 비교에는 측정 방법·출처가 필요합니다.",
        "safer_ko": "비교 대신 자사 제품의 확인된 수치만 쓰고, 비교하려면 시험기관·측정일·조건을 함께 표시하세요.",
        "basis": [B_FOOD_8_1_COMPARE, B_FOOD_9_PROOF, B_COS_13_1_DECEPTION],
    },
    {
        "id": "AD-07",
        "name_ko": "타 업체 비방",
        "risk": "high",
        "category": "비방",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"(타사|다른\s*업체|경쟁)\s*(제품|브랜드)은\s*(가짜|불량|저급|유해)", "타사 비방"),
            (r"짝퉁|가짜\s*(제품|원료)|불량\s*(원료|제품)라고", "가짜·불량 비방"),
        ],
        "why_ko": "다른 업체나 다른 업체의 제품을 비방하는 표시·광고는 금지됩니다.",
        "safer_ko": "타사 평가를 빼고 자사 제품의 원료·시험 결과만 제시하세요.",
        "basis": [B_FOOD_8_1_DISPARAGE, B_COS_13_1_DECEPTION],
    },
    {
        "id": "AD-08",
        "name_ko": "전문가ㆍ기관 보증 오인",
        "risk": "caution",
        "category": "보증·추천",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (rf"(의사|약사|피부과|전문의|교수|한의사){_JO}(추천|보증|지정|공인|처방)", "전문가 추천·보증"),
            (r"병원\s*(추천|사용)|임상\s*전문가", "병원·임상 전문가 추천"),
            (r"(FDA|유럽연합|EU)\s*(승인|인증)|미국\s*식약처\s*승인", "FDA·EU 승인 주장"),
            (r"특허\s*(받은|출원)?\s*(원료|성분|제조)", "특허 원료 강조"),
            (r"(AI|인공지능)\s*(생성|합성)?\s*(전문가|의사|약사)", "AI 생성 전문가 이미지"),
        ],
        "why_ko": (
            "전문가가 보증ㆍ추천하는 것으로 오인하게 하는 광고는 금지됩니다. 특히 2026-10-20 "
            "시행 화장품법은 AI로 만든 실제와 구분하기 어려운 전문가 이미지를 이용한 보증 광고를 "
            "명시적으로 금지합니다. 식품에 ‘FDA 승인’은 존재하지 않는 제도라 거짓 표시가 됩니다."
        ),
        "safer_ko": "추천·보증 표현을 빼고, 인증을 주장하려면 인증기관·번호·유효기간을 정확히 적으세요.",
        "basis": [B_COS_13_1_AI_EXPERT, B_FOOD_8_1_FALSE, B_FOOD_8_1_DECEPTION],
    },
    {
        "id": "AD-09",
        "name_ko": "기능성화장품 오인ㆍ심사 범위 초과",
        "risk": "high",
        "category": "기능성 오인",
        "applies_to": ["cosmetics", "functional_cosmetics"],
        "patterns": [
            (rf"미백|화이트닝|잡티{_JO}(제거|완화)|기미{_JO}(제거|완화)", "미백·잡티"),
            (rf"주름{_JO}(개선|제거|완화)|리프팅|탄력{_JO}(개선|회복)", "주름개선·리프팅"),
            (rf"자외선{_JO}(차단|보호)|SPF|선\s*크림", "자외선 차단"),
            (rf"탈모{_JO}(완화|예방|방지)|모발{_JO}(영양|성장)", "탈모·모발 기능성"),
            (rf"피부{_JO}장벽{_JO}(강화|회복)|각질{_JO}(제거|개선)", "피부장벽·각질 기능성"),
            (rf"기능성{_JO}화장품|식약처\s*(심사|보고)\s*(완료|필)", "기능성화장품 표방"),
        ],
        "why_ko": (
            "미백ㆍ주름개선ㆍ자외선 차단ㆍ탈모 완화 같은 효능은 기능성화장품으로 심사 또는 "
            "보고를 마치고 ‘기능성화장품’ 표시를 한 제품에만 허용됩니다. 일반화장품이 이 표현을 "
            "쓰면 기능성화장품 오인 표시가 됩니다."
        ),
        "safer_ko": (
            "일반화장품이면 ‘보습’, ‘세정’, ‘사용감’ 중심으로 쓰고, 기능성 표현은 심사·보고 "
            "완료 후 ‘기능성화장품’ 표시와 함께 사용하세요."
        ),
        "basis": [B_COS_13_1_FUNCTIONAL, B_COS_2_FUNCTIONAL],
    },
    {
        "id": "AD-10",
        "name_ko": "체중감량ㆍ다이어트 효능 표방",
        "risk": "high",
        "category": "다이어트 효능",
        "applies_to": ["general_food"],
        "patterns": [
            (rf"다이어트|체중{_JO}감량|살{_JO}빠|몸무게{_JO}(감소|줄)", "다이어트·체중감량"),
            (rf"지방{_JO}(분해|연소)|복부{_JO}지방|뱃살{_JO}(제거|감소)", "지방분해·복부지방"),
            (rf"식욕{_JO}(억제|조절)|폭식{_JO}(방지|억제)", "식욕 억제"),
        ],
        "why_ko": (
            "일반식품이 다이어트ㆍ체중감량 효능을 표방하면 건강기능식품 오인 또는 거짓ㆍ과장 "
            "표시로 판단될 수 있습니다. 체지방 감소는 식약처가 인정한 기능성 원료에 한해 "
            "건강기능식품에서만 표현할 수 있습니다."
        ),
        "safer_ko": "‘가볍게 즐기는 식사 대용’처럼 효능이 아닌 용도로 표현하고, 체중 변화 수치는 빼세요.",
        "basis": [B_FOOD_8_1_HFF, B_FOOD_8_1_FALSE],
    },
    {
        "id": "AD-11",
        "name_ko": "디톡스ㆍ배출 표현",
        "risk": "high",
        "category": "디톡스",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (rf"디톡스|detox|해독|독소{_JO}(배출|제거)|중금속{_JO}(배출|제거)", "디톡스·해독"),
            (rf"노폐물{_JO}(배출|제거)|숙변{_JO}(제거)", "노폐물·숙변 배출"),
        ],
        "why_ko": (
            "인체의 해독·독소 배출을 표방하는 표현은 의약품적 효능으로 인식될 우려가 큽니다. "
            "식품에 허용된 기능성 표현이 아니며, 근거 자료 없이 쓰면 거짓ㆍ과장 표시가 됩니다."
        ),
        "safer_ko": "‘디톡스’ 대신 원재료(예: 식이섬유 함유) 사실만 표시하세요.",
        "basis": [B_FOOD_8_1_MEDICINE, B_FOOD_8_1_FALSE, B_COS_13_1_MEDICINE],
    },
    {
        "id": "AD-12",
        "name_ko": "미백ㆍ재생 등 기능성 표현(일반식품)",
        "risk": "caution",
        "category": "피부 효능",
        "applies_to": ["general_food"],
        "patterns": [
            (rf"피부{_JO}(재생|탄력|미백|광채)|콜라겐{_JO}(재생|합성\s*촉진)", "피부 재생·미백"),
            (rf"모발{_JO}(성장|재생)|손톱{_JO}강화", "모발·손톱 효능"),
        ],
        "why_ko": "일반식품이 피부 재생·미백 같은 효능을 표방하면 기능성 오인으로 판단될 수 있습니다.",
        "safer_ko": "‘피부 건강에 필요한 영양소 함유’처럼 영양 사실 중심으로 표현하세요.",
        "basis": [B_FOOD_8_1_HFF, B_FOOD_8_1_FALSE],
    },
    {
        "id": "AD-13",
        "name_ko": "무첨가ㆍ천연 강조(근거 필요)",
        "risk": "caution",
        "category": "원료 강조",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"무첨가|무\s*(색소|방부제|합성|설탕|가당)|노\s*(슈거|설탕)|0\s*(칼로리|kcal)", "무첨가·제로"),
            (r"천연\s*(원료|성분)|100%\s*천연|유기농|무농약|Non-?GMO", "천연·유기농"),
            (r"동물\s*실험\s*(안|미)\s*(함|실시)|크루얼티\s*프리", "동물실험 미실시"),
        ],
        "why_ko": (
            "‘무첨가’, ‘천연’, ‘유기농’은 표시 기준(원료·인증)과 실증자료가 있어야 하는 표현입니다. "
            "특히 ‘무설탕’은 당류 정의에 따라 사실과 달라질 수 있어 기만 표시가 되기 쉽습니다."
        ),
        "safer_ko": "인증번호(유기농 등)와 함량 기준을 함께 적고, ‘무첨가’ 대신 실제 함량(0 g)을 표시하세요.",
        "basis": [B_FOOD_8_1_DECEPTION, B_FOOD_9_PROOF, B_COS_13_1_DECEPTION],
    },
    {
        "id": "AD-14",
        "name_ko": "사행심ㆍ음란 표현",
        "risk": "high",
        "category": "공중도덕",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"당첨|복권|대박\s*(이벤트|기회)|꽝\s*없", "사행심 조장"),
            (r"(성적|야한|선정적)", "음란·선정적 표현"),
        ],
        "why_ko": "사행심을 조장하거나 음란한 표현으로 공중도덕을 침해하는 표시·광고는 금지됩니다.",
        "safer_ko": "이벤트는 경품 내용과 조건만 사실대로 안내하세요.",
        "basis": [B_FOOD_8_1_INDECENT, B_COS_13_1_DECEPTION],
    },
    {
        "id": "AD-15",
        "name_ko": "광고 심의 미이행 위험",
        "risk": "caution",
        "category": "심의",
        "applies_to": ["general_food", "health_functional_food"],
        "patterns": [
            (rf"기능성{_JO}(표방|강조)|질병{_JO}예방|건강{_JO}기능{_JO}표방", "기능성·건강 표방"),
            (r"심의\s*(번호|필|완료)", "광고심의 번호"),
        ],
        "why_ko": (
            "일부 식품 광고는 사전 심의 대상입니다. 심의를 받지 않았거나 심의 결과와 다르게 "
            "표현하면 그 자체로 금지 대상이 됩니다."
        ),
        "safer_ko": "심의 대상 여부를 확인하고, 심의번호가 있으면 광고에 표시하세요.",
        "basis": [B_FOOD_8_1_REVIEW],
    },
    {
        "id": "AD-16",
        "name_ko": "유명 상표ㆍ용기 모방(오인ㆍ혼동)",
        "risk": "high",
        "category": "상표·용기 혼동",
        "applies_to": ["general_food", "health_functional_food", "cosmetics", "functional_cosmetics"],
        "patterns": [
            (r"(정품|오리지널)\s*(과|와)\s*(동일|같은)", "정품과 동일"),
            (r"(유명|히트)\s*(브랜드|제품)\s*(스타일|느낌)|짝퉁|카피\s*(제품|버전)", "유명 브랜드 모방"),
            (rf"(용기|패키지)\s*(까지)?{_JO}(똑같|동일)", "용기·패키지 동일"),
        ],
        "why_ko": (
            "다른 물품의 상호ㆍ상표 또는 용기ㆍ포장과 같거나 비슷한 것을 써서 해당 물품으로 "
            "오인ㆍ혼동하게 하는 표시는 금지됩니다."
        ),
        "safer_ko": "자사 상표와 용기로 교체하고, 타사 제품과의 유사성을 암시하는 표현을 빼세요.",
        "basis": [B_FOOD_8_1_SIMILAR, B_COS_13_1_DECEPTION],
    },
]

# 건강기능식품에서 '인정 기능성 범위'로 볼 수 있는 표현 — 조문 인용이 아니라 식약처 고시
# (기능성 원료 인정) 체계를 안내하기 위한 예시다. 실제 허용 범위는 제품별 인정 내용 확인 필요.
HFF_RECOGNIZED_CLAIMS: List[Dict[str, str]] = [
    {"keyword": "체지방 감소", "example_ko": "체지방 감소에 도움을 줄 수 있음",
     "note_ko": "체지방 감소 기능성 원료로 인정받은 제품에 한함"},
    {"keyword": "혈중 중성지질", "example_ko": "혈중 중성지질 개선에 도움을 줄 수 있음",
     "note_ko": "오메가3 등 인정 원료에 한함"},
    {"keyword": "면역력", "example_ko": "면역력 증진에 도움을 줄 수 있음",
     "note_ko": "인정 원료·함량 범위에 한함"},
    {"keyword": "칼슘 흡수", "example_ko": "칼슘과 인이 흡수되고 이용되는 데 필요",
     "note_ko": "비타민D의 인정 기능성 문구"},
    {"keyword": "눈 건강", "example_ko": "눈 건강에 도움을 줄 수 있음",
     "note_ko": "루테인 등 인정 원료에 한함"},
    {"keyword": "장 건강", "example_ko": "장 건강에 도움을 줄 수 있음",
     "note_ko": "프로바이오틱스 등 인정 원료에 한함"},
]

COSMETIC_FUNCTIONAL_CLAIMS: List[Dict[str, str]] = [
    {"keyword": "미백", "note_ko": "기능성화장품 심사·보고 + ‘기능성화장품’ 표시 필요"},
    {"keyword": "주름개선", "note_ko": "기능성화장품 심사·보고 + ‘기능성화장품’ 표시 필요"},
    {"keyword": "자외선 차단", "note_ko": "기능성화장품(자외선 차단) 심사·보고 필요"},
    {"keyword": "탈모 완화", "note_ko": "기능성화장품(모발) 심사·보고 필요"},
    {"keyword": "피부장벽", "note_ko": "인정 범위를 벗어난 표현은 기능성 오인 위험"},
]

# 문맥상 오탐을 줄이는 예외 — 성분명·제품 유형 설명 등
CONTEXT_EXCEPTIONS: List[Tuple[str, str]] = [
    # '질병의 예방 및 치료를 위한 의약품이 아닙니다'는 금지 고지문이지 효능 주장이 아니다.
    # (0.5.3) 종전 정규식은 '아닙니다'의 '아닙'을 잡지 못해 고지문 앞부분을 남겨 두었고,
    # 조사 허용을 넣은 AD-01이 그 잔여 문구를 다시 잡았다.
    (r"질병의?\s*예방\s*(?:및|과|ㆍ|·)?\s*치료를?\s*위한?\s*의약품이?\s*아닙?", "의약품 아님 고지"),
    (r"의약품이?\s*아닙|의약품이?\s*아니(라|다|며|고|면)", "의약품 아님 고지"),
    (rf"식품은?\s*질병을?{_JO}(예방|치료)", "질병 예방·치료 문구 금지 안내"),
    (r"치료를?\s*받(으|아|는)", "진료 안내"),
    # 원산지·함량 사실 표시(‘100% 국산’)는 절대 표현이 아니다.
    (r"100\s*%\s*(국산|국내산|우리\s*농산물|한우|제주|유기농\s*원료)", "원산지 표시"),
]

# 절대 표현이 다른 단어 안에 들어간 경우(예: '최고기온')를 피하기 위한 앞뒤 문자 검사
_WORD_BOUNDARY_RULES = {"최고", "최상", "최강", "1위", "유일", "100%"}


def _find_phrase(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    start = max(0, match.start() - 2)
    end = min(len(text), match.end() + 2)
    return text[start:end].strip()


def _mask_exceptions(text: str) -> str:
    """문맥 예외 문구를 지운 사본으로 대조한다(오탐 방지)."""
    masked = text
    for pattern, _label in CONTEXT_EXCEPTIONS:
        masked = re.sub(pattern, " ", masked, flags=re.IGNORECASE)
    return masked


def _filter_basis(basis_list: List[Dict[str, str]], product_type: str) -> List[Dict[str, str]]:
    """품목 유형에 맞는 근거만 남긴다(화장품에 식품표시광고법을 인용하지 않는다)."""
    out: List[Dict[str, str]] = []
    cosmetic = product_type in COSMETIC_TYPES
    for basis in basis_list or []:
        law = str(basis.get("law") or "")
        is_cosmetic_law = law.startswith("화장품법")
        if cosmetic != is_cosmetic_law:
            continue
        out.append(basis)
    return out


def _rule_applies(rule: Dict[str, Any], product_type: str) -> bool:
    return product_type in (rule.get("applies_to") or [])


def _downgrade_for_hff(rule: Dict[str, Any], product_type: str) -> Optional[str]:
    """건강기능식품에서 인정 기능성 범위로 볼 수 있는 문구인지 확인한다."""
    if product_type != "health_functional_food":
        return None
    if rule["id"] not in ("AD-03", "AD-10", "AD-12"):
        return None
    return "건강기능식품에서는 식약처가 인정한 기능성 원료·함량 범위 안에서만 같은 표현이 허용됩니다."


def _downgrade_for_functional_cosmetics(rule: Dict[str, Any], product_type: str) -> Optional[str]:
    if product_type != "functional_cosmetics" or rule["id"] != "AD-09":
        return None
    return "기능성화장품은 심사·보고를 마친 효능 범위 안에서 ‘기능성화장품’ 표시와 함께 표현할 수 있습니다."


def review(text: str, product_type: str = "", *, functional: Any = None,
           limit: int = 12, include_basis: bool = True) -> Dict[str, Any]:
    """광고 문구를 유형별 기준으로 검수한다(네트워크 불필요)."""
    ptype = normalize_product_type(product_type, text)
    if ptype == "cosmetics" and str(functional).lower() in ("yes", "true", "1", "y"):
        ptype = "functional_cosmetics"
    source = str(text or "").strip()
    probe = _mask_exceptions(source)
    findings: List[Dict[str, Any]] = []
    if len(source) >= 2:
        for rule in CLAIM_RULES:
            if not _rule_applies(rule, ptype):
                continue
            matched: List[str] = []
            for pattern, label in rule["patterns"]:
                phrase = _find_phrase(probe, pattern)
                if phrase and label not in matched:
                    matched.append(label)
            if not matched:
                continue
            risk = rule["risk"]
            note = _downgrade_for_hff(rule, ptype) or _downgrade_for_functional_cosmetics(rule, ptype)
            if note and risk == "high":
                risk = "caution"
            entry: Dict[str, Any] = {
                "rule_id": rule["id"],
                "name_ko": rule["name_ko"],
                "category": rule["category"],
                "risk": risk,
                "risk_label_ko": "높음" if risk == "high" else "주의",
                "matched_phrases": matched,
                "why_ko": rule["why_ko"],
                "safer_ko": rule["safer_ko"],
                "applies_to": [PRODUCT_TYPES[t]["label_ko"] for t in rule["applies_to"]],
                "category_note_ko": note or "",
            }
            if include_basis:
                entry["legal_basis"] = _filter_basis(rule["basis"], ptype)
            findings.append(entry)
    findings.sort(key=lambda row: (0 if row["risk"] == "high" else 1, row["rule_id"]))
    findings = findings[:max(1, int(limit))]

    high = sum(1 for f in findings if f["risk"] == "high")
    caution = sum(1 for f in findings if f["risk"] == "caution")
    if high:
        verdict, verdict_label = "check_likely", "고위험 표현이 확인되어 문구 수정·실증 검토가 필요합니다."
    elif caution:
        verdict, verdict_label = "info_needed", "주의 표현이 있습니다. 실증자료·심의 여부를 확인하세요."
    elif len(source) >= 4:
        verdict, verdict_label = "low_risk", "입력한 문구에서 유형별 금지 표현 패턴을 찾지 못했습니다."
    else:
        verdict, verdict_label = "info_needed", "문구가 너무 짧아 판단하지 못했습니다. 상세페이지 문구를 넣어 주세요."

    allowed_claims = _allowed_claims_for(ptype, probe)
    return {
        "product_type": ptype,
        "product_type_label_ko": PRODUCT_TYPES[ptype]["label_ko"],
        "governing_law_ko": PRODUCT_TYPES[ptype]["governing_law_ko"],
        "input_chars": len(source),
        "finding_count": len(findings),
        "risk_high": high,
        "risk_caution": caution,
        "risk_summary_ko": (
            f"높음 {high}건 · 주의 {caution}건" if findings else "탐지된 위험 표현 없음"
        ),
        "verdict": verdict,
        "verdict_note_ko": verdict_label,
        "findings": findings,
        "recognized_claim_hints": allowed_claims,
        "category_comparison": compare_categories(probe),
        "coverage_ko": (
            "문구 패턴 대조 결과입니다. 법령 조문과 고시(「식품등의 부당한 표시 또는 광고의 "
            "내용 기준」)의 유형을 참고해 규칙을 만들었으며, 같은 단어라도 문맥·성분·표시 위치에 "
            "따라 판단이 달라질 수 있습니다. 최종 판단은 식약처 광고심의·점검 기준을 따릅니다."
        ),
        "checked_on": VERIFIED_ON,
        "ad_content_standard": {
            "name_ko": "식품등의 부당한 표시 또는 광고의 내용 기준",
            "authority_ko": "식품의약품안전처 고시(제2025-79호, 2025-12-04 시행)",
            "url": AD_CONTENT_STANDARD_URL,
            "note_ko": "고시는 수시 개정되므로 최신본을 확인해야 합니다.",
        },
    }


def _allowed_claims_for(product_type: str, probe: str) -> List[Dict[str, str]]:
    """해당 유형에서 '허용될 수 있는' 표현 힌트(인정 범위 확인 전제)."""
    if product_type == "health_functional_food":
        hints = HFF_RECOGNIZED_CLAIMS
        note = "식약처가 인정한 기능성 원료·함량 범위 안에서만 사용할 수 있습니다."
    elif product_type == "functional_cosmetics":
        hints = COSMETIC_FUNCTIONAL_CLAIMS
        note = "심사·보고를 마친 효능 범위 안에서 ‘기능성화장품’ 표시와 함께 사용할 수 있습니다."
    elif product_type == "cosmetics":
        hints = COSMETIC_FUNCTIONAL_CLAIMS
        note = "일반화장품은 아래 효능을 표방할 수 없고, 심사·보고 후 ‘기능성화장품’으로만 표시할 수 있습니다."
    else:
        hints = [{"keyword": "영양성분", "note_ko": "일반식품은 확인된 영양성분 정보와 원재료 사실만 표시할 수 있습니다."}]
        note = "일반식품에는 인정 기능성 표현을 쓸 수 없습니다(건강기능식품 오인)."
    return [dict(row, applies_note_ko=note) for row in hints]


def compare_categories(text: str) -> List[Dict[str, Any]]:
    """같은 문구를 4개 유형에 적용해 허용/금지를 나란히 보여준다.

    "일반식품 vs 건기식 vs 기능성화장품 구분"을 사용자가 바로 확인할 수 있게 하는 블록.
    """
    probe = _mask_exceptions(str(text or ""))
    rows: List[Dict[str, Any]] = []
    for ptype in ("general_food", "health_functional_food", "cosmetics", "functional_cosmetics"):
        hits = []
        for rule in CLAIM_RULES:
            if not _rule_applies(rule, ptype):
                continue
            labels = [label for pattern, label in rule["patterns"] if _find_phrase(probe, pattern)]
            if not labels:
                continue
            note = _downgrade_for_hff(rule, ptype) or _downgrade_for_functional_cosmetics(rule, ptype)
            risk = "caution" if (note and rule["risk"] == "high") else rule["risk"]
            hits.append({"rule_id": rule["id"], "name_ko": rule["name_ko"], "risk": risk,
                         "matched_phrases": labels,
                         "note_ko": note or ""})
        rows.append({
            "product_type": ptype,
            "label_ko": PRODUCT_TYPES[ptype]["label_ko"],
            "finding_count": len(hits),
            "highest_risk": ("high" if any(h["risk"] == "high" for h in hits)
                             else ("caution" if hits else "none")),
            "findings": hits,
        })
    return rows


def label_items_for(product_type: str) -> List[Dict[str, Any]]:
    """한글표시사항 체크리스트를 유형별로 돌려준다(labeling.py 위임)."""
    from . import labeling

    return labeling.checklist(product_type)


def summarize(review_result: Dict[str, Any], limit: int = 5) -> List[str]:
    """응답 answer.guidance 에 넣을 문장을 만든다."""
    lines: List[str] = []
    findings = review_result.get("findings") or []
    if findings:
        for finding in findings[:limit]:
            lines.append(
                f"[{finding['risk_label_ko']}] {finding['name_ko']} 표현 {len(finding['matched_phrases'])}종이 "
                f"탐지되었습니다. {finding['safer_ko']}"
            )
    else:
        lines.append("입력한 광고 문구에서 유형별 금지 표현 패턴을 찾지 못했습니다. "
                     "그래도 실증자료는 보관해야 합니다(식품표시광고법 제9조).")
    return lines


def tag_for_rule(rule_id: str, product_type: str) -> str:
    """규칙 하나에 대응하는 규제 태그."""
    if rule_id == "AD-09":
        return "COSMETICS_FUNCTIONAL_CLAIM"
    if rule_id == "AD-03":
        return "HFF_CLAIM_MISREPRESENTATION"
    return "COSMETICS_AD_CLAIM" if product_type in COSMETIC_TYPES else "FOOD_AD_CLAIM"


def regulation_tags(review_result: Dict[str, Any]) -> List[str]:
    """리뷰 결과에 대응하는 규제 태그."""
    tags: List[str] = []
    ptype = str(review_result.get("product_type") or "")
    for finding in review_result.get("findings") or []:
        tag = tag_for_rule(str(finding.get("rule_id") or ""), ptype)
        if tag not in tags:
            tags.append(tag)
    return tags
