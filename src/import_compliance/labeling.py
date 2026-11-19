"""한글표시사항(라벨) 필수항목 체크 (CLNS 0.2.0).

무엇을 하는가
-------------
수입·유통 품목 유형별로 라벨에 반드시 들어가야 하는 항목을 체크리스트로 주고, 입력한
라벨 문구(또는 항목 체크)와 대조해 **누락/확인 필요/확인 불가**를 나눈다.

근거
----
- 식품·건강기능식품: 「식품등의 표시ㆍ광고에 관한 법률」 제4조제1항(유형별 표시사항),
  제5조(영양표시), 같은 법 시행규칙 제3조(추가 표시사항)ㆍ제5조(소비자 안전을 위한
  주의사항)ㆍ제6조(영양표시 대상 성분). 조문은 2026-11-19 법제처 API로 조회한
  현행 시행본이다.
- 화장품: 「화장품법」 제10조(화장품의 기재사항).
- 세부 서식(글씨 크기, 알레르기 유발물질, 한글 표시 방법)은 총리령과 식약처 고시
  (「식품등의 표시기준」, 「화장품법 시행규칙」)에서 정하므로, 이 도구는 **항목의 존재
  여부**만 보고 세부 적합성은 "확인 필요"로 남긴다.

한계(정직하게)
--------------
- 라벨 사진을 인식하는 기능이 아니다. 텍스트로 옮긴 라벨이거나, 사용자가 체크한 항목을
  대조한다.
- "누락"은 입력한 텍스트에서 해당 항목을 찾지 못했다는 뜻이며, 실제 포장에 없다는 확정이
  아니다(사진·이미지 라벨은 인식하지 못함).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .advertising import (
    B_FOOD_RULE_5,
    LABEL_STANDARD_URL,
    LAW_URL_COSMETICS,
    LAW_URL_FOOD_AD,
    LAW_URL_FOOD_AD_RULE,
    LAW_URL_IMPORT_FOOD,
    PRODUCT_TYPES,
    VERIFIED_ON,
    normalize_product_type,
)

# --- 조문 근거 -------------------------------------------------------------
B_FOOD_4_1_1 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제4조제1항제1호", "effective_date": "2025-09-19",
    "url": LAW_URL_FOOD_AD,
    "quote": "식품, 식품첨가물 또는 축산물에는 제품명, 내용량 및 원재료명, 영업소 명칭 및 소재지, "
             "소비자 안전을 위한 주의사항, 제조연월일ㆍ소비기한 또는 품질유지기한 등을 표시하여야 한다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_4_1_3 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제4조제1항제3호", "effective_date": "2025-09-19",
    "url": LAW_URL_FOOD_AD,
    "quote": "건강기능식품에는 제품명ㆍ내용량 및 원료명, 영업소 명칭 및 소재지, 소비기한 및 "
             "보관방법, 섭취량ㆍ섭취방법 및 섭취 시 주의사항, ‘건강기능식품’이라는 문자 또는 도안, "
             "질병의 예방 및 치료를 위한 의약품이 아니라는 내용의 표현, 기능성에 관한 정보 및 "
             "기능성을 나타내는 성분의 함유량 등을 표시하여야 한다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_4_2 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제4조제2항", "effective_date": "2025-09-19",
    "url": LAW_URL_FOOD_AD,
    "quote": "제1항에 따른 표시의무자, 표시사항 및 글씨크기ㆍ표시장소 등 표시방법에 관하여는 "
             "총리령으로 정한다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_4_3 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제4조제3항", "effective_date": "2025-09-19",
    "url": LAW_URL_FOOD_AD,
    "quote": "제1항에 따른 표시가 없거나 제2항에 따른 표시방법을 위반한 식품등은 판매하거나 "
             "판매할 목적으로 제조ㆍ가공ㆍ소분ㆍ수입ㆍ포장ㆍ보관ㆍ진열 또는 운반하거나 영업에 "
             "사용해서는 아니 된다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_5_NUTRITION = {
    "law": "식품등의 표시ㆍ광고에 관한 법률", "article": "제5조제1항", "effective_date": "2025-09-19",
    "url": LAW_URL_FOOD_AD,
    "quote": "식품등을 제조ㆍ가공ㆍ소분하거나 수입하는 자는 총리령으로 정하는 식품등에 "
             "영양표시를 하여야 한다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_RULE_3_1 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률 시행규칙", "article": "제3조제1항", "effective_date": "2024-12-30",
    "url": LAW_URL_FOOD_AD_RULE,
    "quote": "법 제4조제1항제1호마목에서 ‘총리령으로 정하는 사항’이란 식품유형, 품목보고번호, "
             "성분명 및 함량, 용기ㆍ포장의 재질, 조사처리 표시, 보관방법 또는 취급방법, "
             "포장일자ㆍ생산연월일 또는 산란일 등을 말한다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_RULE_3_3 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률 시행규칙", "article": "제3조제3항", "effective_date": "2024-12-30",
    "url": LAW_URL_FOOD_AD_RULE,
    "quote": "법 제4조제1항제3호아목에서 ‘총리령으로 정하는 사항’이란 원료의 함량과 소비자 "
             "안전을 위한 주의사항을 말한다.",
    "verified_on": VERIFIED_ON,
}
B_FOOD_RULE_6_2 = {
    "law": "식품등의 표시ㆍ광고에 관한 법률 시행규칙", "article": "제6조제2항", "effective_date": "2024-12-30",
    "url": LAW_URL_FOOD_AD_RULE,
    "quote": "법 제5조제2항에 따른 표시 대상 영양성분은 열량, 나트륨, 탄수화물, 당류, 지방, "
             "트랜스지방, 포화지방, 콜레스테롤, 단백질 등이다.",
    "verified_on": VERIFIED_ON,
}
B_COS_10_1 = {
    "law": "화장품법", "article": "제10조제1항", "effective_date": "2026-10-20", "url": LAW_URL_COSMETICS,
    "quote": "화장품의 외부 포장에는 화장품의 명칭, 영업자의 상호 및 주소, 사용된 모든 성분, "
             "내용물의 용량 또는 중량, 제조번호, 사용기한 또는 개봉 후 사용기간, 가격, "
             "기능성화장품 표시, 사용할 때의 주의사항 등을 기재ㆍ표시하여야 한다.",
    "verified_on": VERIFIED_ON,
}
B_COS_10_2 = {
    "law": "화장품법", "article": "제10조제2항", "effective_date": "2026-10-20", "url": LAW_URL_COSMETICS,
    "quote": "1차 포장에 2차 포장을 추가한 화장품의 1차 포장에는 화장품의 명칭, 영업자의 상호, "
             "제조번호, 사용기한 또는 개봉 후 사용기간을 기재ㆍ표시하여야 한다.",
    "verified_on": VERIFIED_ON,
}
B_COS_10_5 = {
    "law": "화장품법", "article": "제10조제5항", "effective_date": "2026-10-20", "url": LAW_URL_COSMETICS,
    "quote": "제1항 및 제2항에 따른 표시기준과 표시방법 등은 총리령으로 정한다.",
    "verified_on": VERIFIED_ON,
}
B_IMPORT_15 = {
    "law": "수입식품안전관리 특별법", "article": "제15조제1항", "effective_date": "2026-10-08",
    "url": LAW_URL_IMPORT_FOOD,
    "quote": "수입식품등 수입ㆍ판매업을 하려는 자는 총리령으로 정하는 바에 따라 영업등록을 "
             "하여야 한다.",
    "verified_on": VERIFIED_ON,
}
B_IMPORT_20 = {
    "law": "수입식품안전관리 특별법", "article": "제20조제1항", "effective_date": "2026-10-08",
    "url": LAW_URL_IMPORT_FOOD,
    "quote": "영업자가 판매를 목적으로 하거나 영업상 사용할 목적으로 수입식품등을 수입하려면 "
             "총리령으로 정하는 바에 따라 식품의약품안전처장에게 수입신고를 하여야 한다.",
    "verified_on": VERIFIED_ON,
}

# --- 항목 정의 -------------------------------------------------------------
# detect: 라벨 텍스트에서 항목 존재를 추정하는 정규식 목록(하나라도 맞으면 present)
# required: True = 필수, False = 조건부(해당 제품에만)
COMMON_FOOD_ITEMS: List[Dict[str, Any]] = [
    {"id": "product_name", "label_ko": "제품명", "required": True, "basis": B_FOOD_4_1_1,
     "example_ko": "예: 제주 감귤 착즙주스",
     "detect": [r"제품명|상품명|품명"]},
    {"id": "content_amount", "label_ko": "내용량", "required": True, "basis": B_FOOD_4_1_1,
     "example_ko": "예: 500mL, 200g",
     "detect": [r"내용량|정량|총량|\d+\s*(ml|mL|g|kg|L)\b"]},
    {"id": "ingredient_names", "label_ko": "원재료명(원재료 및 함량)", "required": True, "basis": B_FOOD_4_1_1,
     "example_ko": "예: 원재료명 — 감귤과즙 99%(국산), 비타민C",
     "detect": [r"원재료\s*(명|및|:|은|:)|원료명"]},
    {"id": "seller_name_address", "label_ko": "영업소 명칭 및 소재지(수입품은 수입업소)", "required": True,
     "basis": B_FOOD_4_1_1, "example_ko": "예: (주)예시식품 / 인천광역시 서구 …",
     "detect": [r"영업소|제조원|수입(원|자|업소)|판매원|소재지|주소"]},
    {"id": "food_type", "label_ko": "식품유형", "required": True, "basis": B_FOOD_RULE_3_1,
     "example_ko": "예: 과채주스", "detect": [r"식품유형|식품\s*유형"]},
    {"id": "item_report_no", "label_ko": "품목보고번호", "required": True, "basis": B_FOOD_RULE_3_1,
     "example_ko": "예: 2019012345678", "detect": [r"품목\s*보고\s*번호|품목제조\s*보고"]},
    {"id": "date_marking", "label_ko": "소비기한(또는 품질유지기한ㆍ제조연월일)", "required": True,
     "basis": B_FOOD_4_1_1, "example_ko": "예: 소비기한 2027.03.15까지",
     "detect": [r"소비기한|유통기한|품질유지기한|제조연월일|제조일자"]},
    {"id": "storage_method", "label_ko": "보관방법 또는 취급방법", "required": True, "basis": B_FOOD_RULE_3_1,
     "example_ko": "예: 직사광선을 피해 서늘한 곳에 보관", "detect": [r"보관\s*방법|취급\s*방법|보관하"]},
    {"id": "consumer_caution", "label_ko": "소비자 안전을 위한 주의사항", "required": True, "basis": B_FOOD_RULE_5,
     "example_ko": "예: 개봉 후 냉장보관하고 빠른 시일 내 섭취하세요", "detect": [r"주의\s*사항|주의하"]},
    {"id": "nutrition", "label_ko": "영양성분 표시", "required": False, "basis": B_FOOD_5_NUTRITION,
     "applies_when_ko": "총리령이 정한 영양표시 대상 식품인 경우(과자류ㆍ음료류 등)",
     "example_ko": "예: 열량 120kcal, 나트륨 30mg …", "detect": [r"영양\s*(정보|성분)|열량|나트륨\s*\d"]},
    {"id": "allergen", "label_ko": "알레르기 유발물질 표시", "required": False, "basis": B_FOOD_4_1_1,
     "applies_when_ko": "알레르기 유발물질을 원재료로 사용한 경우(세부 대상은 「식품등의 표시기준」)",
     "example_ko": "예: 우유, 대두 함유", "detect": [r"알레르기|함유\s*:|우유|대두|땅콩|밀\b"]},
    {"id": "import_korean", "label_ko": "수입식품 한글표시사항", "required": False, "basis": B_FOOD_4_2,
     "applies_when_ko": "수입식품인 경우(한글 표시 방법은 총리령ㆍ「식품등의 표시기준」)",
     "example_ko": "예: 수입자명·수입신고 확인 문구를 한글로 표시",
     "detect": [r"수입(자|업소|원)|한글\s*표시|수입신고"]},
]

HFF_ITEMS: List[Dict[str, Any]] = [
    {"id": "product_name", "label_ko": "제품명", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 비타민D3 2000IU", "detect": [r"제품명|상품명|품명"]},
    {"id": "content_amount", "label_ko": "내용량", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 60정(90g)", "detect": [r"내용량|\d+\s*(정|캡슐|g|mL|포)\b"]},
    {"id": "ingredient_names", "label_ko": "원료명(원료 및 함량)", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 원료명 — 비타민D3 혼합제제(비타민D3 100%)",
     "detect": [r"원료\s*(명|및|:)|성분\s*명"]},
    {"id": "seller_name_address", "label_ko": "영업소 명칭 및 소재지(수입품은 수입업소)", "required": True,
     "basis": B_FOOD_4_1_3, "example_ko": "예: (주)예시헬스 / 서울특별시 …",
     "detect": [r"영업소|제조원|수입(원|자|업소)|판매원|소재지|주소"]},
    {"id": "expiry_storage", "label_ko": "소비기한 및 보관방법", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 소비기한 2027.03.15까지 / 직사광선을 피해 보관",
     "detect": [r"소비기한|유통기한|보관\s*방법"]},
    {"id": "intake_method", "label_ko": "섭취량ㆍ섭취방법", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 1일 1회 1정을 물과 함께 섭취", "detect": [r"섭취\s*(량|방법)|1일\s*\d"]},
    {"id": "intake_caution", "label_ko": "섭취 시 주의사항", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 임산부ㆍ수유부는 섭취 전 전문가와 상담하세요", "detect": [r"섭취\s*시\s*주의|주의\s*사항"]},
    {"id": "hff_mark", "label_ko": "‘건강기능식품’ 문자 또는 도안", "required": True, "basis": B_FOOD_4_1_3,
     "example_ko": "예: 건강기능식품 (도안 포함)", "detect": [r"건강기능식품"]},
    {"id": "not_medicine", "label_ko": "질병 예방ㆍ치료를 위한 의약품이 아니라는 표현", "required": True,
     "basis": B_FOOD_4_1_3,
     "example_ko": "예: 이 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다",
     "detect": [r"의약품이\s*아닙|의약품이\s*아니(라|다|면|고|며)|질병의?\s*예방\s*및?\s*치료"]},
    {"id": "functional_info", "label_ko": "기능성 정보(인정받은 기능성 내용)", "required": True,
     "basis": B_FOOD_4_1_3, "example_ko": "예: 비타민D는 칼슘과 인이 흡수되고 이용되는 데 필요합니다",
     "detect": [r"기능성|도움을\s*줄\s*수\s*있|에\s*필요"]},
    {"id": "functional_amount", "label_ko": "기능성을 나타내는 성분의 함유량", "required": True,
     "basis": B_FOOD_4_1_3, "example_ko": "예: 비타민D 20μg (1일 섭취량 기준 200%)",
     "detect": [r"%\s*\)|\d+\s*(mg|μg|ug|IU)"]},
    {"id": "ingredient_amount", "label_ko": "원료의 함량", "required": True, "basis": B_FOOD_RULE_3_3,
     "example_ko": "예: 비타민D3 20μg", "detect": [r"함량|\d+\s*(mg|μg|ug|IU)"]},
    {"id": "consumer_caution", "label_ko": "소비자 안전을 위한 주의사항", "required": True, "basis": B_FOOD_RULE_3_3,
     "example_ko": "예: 알레르기 체질은 성분을 확인하세요", "detect": [r"주의\s*사항|알레르기"]},
    {"id": "nutrition", "label_ko": "영양성분 표시", "required": False, "basis": B_FOOD_5_NUTRITION,
     "applies_when_ko": "영양표시 대상인 경우(건강기능식품은 원칙적으로 대상)",
     "example_ko": "예: 열량, 탄수화물, 단백질, 지방 표시", "detect": [r"영양\s*(정보|성분)"]},
    {"id": "import_korean", "label_ko": "수입 건강기능식품 한글표시사항", "required": False, "basis": B_FOOD_4_2,
     "applies_when_ko": "수입 건강기능식품인 경우(수입신고 확인 포함)",
     "example_ko": "예: 수입자명ㆍ수입신고 확인 문구를 한글로 표시",
     "detect": [r"수입(자|업소|원)|한글\s*표시|수입신고"]},
]

COSMETIC_ITEMS: List[Dict[str, Any]] = [
    {"id": "product_name", "label_ko": "화장품의 명칭", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 수분 진정 크림", "detect": [r"명칭|제품명|상품명"]},
    {"id": "seller_name_address", "label_ko": "영업자 상호 및 주소(수입품은 화장품책임판매업자)", "required": True,
     "basis": B_COS_10_1, "example_ko": "예: (주)예시코스메틱 / 서울특별시 …",
     "detect": [r"상호|책임판매업자|제조(원|자)|수입(원|자)|주소"]},
    {"id": "all_ingredients", "label_ko": "사용된 모든 성분(전성분)", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 정제수, 글리세린, …", "detect": [r"전성분|성분\s*:|Ingredients"]},
    {"id": "volume_weight", "label_ko": "내용물의 용량 또는 중량", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 50mL / 50g", "detect": [r"용량|중량|\d+\s*(ml|mL|g)\b"]},
    {"id": "manufacture_no", "label_ko": "제조번호", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 제조번호 A1B2", "detect": [r"제조\s*번호|Lot|LOT"]},
    {"id": "expiry", "label_ko": "사용기한 또는 개봉 후 사용기간", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 사용기한 2027.12.31 / 개봉 후 12개월",
     "detect": [r"사용기한|개봉\s*후|유통기한"]},
    {"id": "price", "label_ko": "가격", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 29,000원", "detect": [r"가격|\d{3,}\s*원"]},
    {"id": "functional_mark", "label_ko": "‘기능성화장품’ 글자 또는 도안", "required": False, "basis": B_COS_10_1,
     "applies_when_ko": "기능성화장품인 경우(심사·보고 완료 제품)",
     "example_ko": "예: 기능성화장품(미백)", "detect": [r"기능성\s*화장품"]},
    {"id": "usage_caution", "label_ko": "사용할 때의 주의사항", "required": True, "basis": B_COS_10_1,
     "example_ko": "예: 이상이 생기면 사용을 중지하고 전문의와 상담하세요",
     "detect": [r"주의\s*사항|사용\s*시|이상이\s*생기"]},
    {"id": "primary_package", "label_ko": "1차 포장 기재(명칭ㆍ상호ㆍ제조번호ㆍ사용기한)", "required": False,
     "basis": B_COS_10_2, "applies_when_ko": "1차 포장에 2차 포장을 추가한 제품",
     "example_ko": "예: 1차 포장에도 명칭ㆍ상호ㆍ제조번호ㆍ사용기한 표시", "detect": [r"1차\s*포장|본품"]},
    {"id": "import_korean", "label_ko": "수입 화장품 한글 표시", "required": False, "basis": B_COS_10_5,
     "applies_when_ko": "수입 화장품인 경우(표시기준ㆍ방법은 총리령)",
     "example_ko": "예: 한글 명칭ㆍ성분ㆍ사용기한 표시", "detect": [r"수입(원|자|업소)|한글\s*표시"]},
]

CHECKLISTS: Dict[str, List[Dict[str, Any]]] = {
    "general_food": COMMON_FOOD_ITEMS,
    "health_functional_food": HFF_ITEMS,
    "cosmetics": COSMETIC_ITEMS,
    "functional_cosmetics": COSMETIC_ITEMS,
}


def checklist(product_type: str) -> List[Dict[str, Any]]:
    ptype = normalize_product_type(product_type)
    rows = CHECKLISTS.get(ptype, COMMON_FOOD_ITEMS)
    return [
        {
            "item_id": row["id"],
            "label_ko": row["label_ko"],
            "required": bool(row["required"]),
            "applies_when_ko": row.get("applies_when_ko", ""),
            "example_ko": row.get("example_ko", ""),
            "legal_basis": dict(row["basis"]),
        }
        for row in rows
    ]


def _conditional_applies(item: Dict[str, Any], ptype: str, text: str, imported: bool) -> bool:
    """조건부 항목이 이 제품에 실제로 해당되는지 판단한다(모르면 False = 해당 없음으로 남김)."""
    key = item["id"]
    if key == "import_korean":
        return imported or bool(re.search(r"수입", text))
    if key == "functional_mark":
        return ptype == "functional_cosmetics"
    if key == "primary_package":
        return bool(re.search(r"1차\s*포장|본품", text))
    if key in ("nutrition", "allergen"):
        return True
    return True


def _status_for(item: Dict[str, Any], text: str, provided: Dict[str, Any]) -> str:
    """present / missing / unclear / not_checked."""
    key = item["id"]
    if key in provided:
        value = provided[key]
        if isinstance(value, bool):
            return "present" if value else "missing"
        if str(value).strip().lower() in ("yes", "y", "true", "1", "o", "있음"):
            return "present"
        if str(value).strip().lower() in ("no", "n", "false", "0", "x", "없음"):
            return "missing"
    if not text:
        return "not_checked"
    for pattern in item.get("detect") or []:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return "present"
    return "missing"


def check(product_type: str, *, label_text: str = "", provided: Optional[Dict[str, Any]] = None,
          imported: Any = None) -> Dict[str, Any]:
    """라벨 필수항목을 대조한다."""
    ptype = normalize_product_type(product_type, label_text)
    text = str(label_text or "")
    supplied = dict(provided or {})
    imported_flag = str(imported).strip().lower() in ("yes", "true", "1", "y", "수입")
    rows: List[Dict[str, Any]] = []
    for item in CHECKLISTS.get(ptype, COMMON_FOOD_ITEMS):
        applies = bool(item["required"]) or _conditional_applies(item, ptype, text, imported_flag)
        status = _status_for(item, text, supplied)
        if not applies and not item["required"]:
            status ="not_applicable"
        rows.append({
            "item_id": item["id"],
            "label_ko": item["label_ko"],
            "required": bool(item["required"]),
            "status": status,
            "applies_when_ko": item.get("applies_when_ko", ""),
            "example_ko": item.get("example_ko", ""),
            "legal_basis": dict(item["basis"]),
            "note_ko": (
                "입력한 라벨 텍스트에서 해당 항목을 찾지 못했습니다(실제 포장에 없다는 단정은 아닙니다)."
                if status == "missing" else ""
            ),
        })
        if imported_flag and item["id"] == "import_korean" and status == "not_checked":
            rows[-1]["status"] = "missing"
    present = [r["label_ko"] for r in rows if r["status"] == "present"]
    missing = [r["label_ko"] for r in rows if r["status"] == "missing" and r["required"]]
    conditional_missing = [r["label_ko"] for r in rows if r["status"] == "missing" and not r["required"]]
    not_checked = [r["label_ko"] for r in rows if r["status"] == "not_checked"]
    not_applicable = [r["label_ko"] for r in rows if r["status"] == "not_applicable"]
    required_rows = [r for r in rows if r["required"]]
    checked_required = [r for r in required_rows if r["status"] in ("present", "missing")]
    rate = (len([r for r in required_rows if r["status"] == "present"]) / len(required_rows)) if required_rows else 0.0

    if not text and not supplied:
        verdict = "info_needed"
        note = "라벨 문구나 항목 체크를 넣으면 누락 여부를 대조합니다."
    elif missing:
        verdict = "check_likely"
        note = f"필수 항목 {len(missing)}개를 찾지 못했습니다. 표시 누락은 판매 금지 사유가 될 수 있습니다(법 제4조제3항)."
    elif not_checked or conditional_missing:
        verdict = "info_needed"
        note = "필수 항목은 확인됐지만 조건부 항목ㆍ확인 불가 항목이 남아 있습니다."
    else:
        verdict = "low_risk"
        note = "입력한 범위에서 필수 표시항목이 모두 확인됐습니다. 세부 서식(글씨 크기ㆍ위치)은 별도 확인이 필요합니다."

    next_actions: List[str] = []
    if missing:
        next_actions.append("누락 항목을 라벨에 추가하고, 수입 전 한글표시사항 스티커·재포장 여부를 확인하세요.")
    if conditional_missing:
        next_actions.append("조건부 항목(" + ", ".join(conditional_missing[:4]) + ")이 해당 제품에 필요한지 확인하세요.")
    if ptype in ("general_food", "health_functional_food"):
        next_actions.append("세부 표시방법(글씨 크기ㆍ위치ㆍ알레르기 표시)은 「식품등의 표시기준」 최신본으로 확인하세요.")
    else:
        next_actions.append("1차 포장 기재와 한글 표시는 「화장품법 시행규칙」 및 식약처 안내서로 확인하세요.")

    return {
        "product_type": ptype,
        "product_type_label_ko": PRODUCT_TYPES[ptype]["label_ko"],
        "input_chars": len(text),
        "item_count": len(rows),
        "required_count": len(required_rows),
        "present_count": len(present),
        "missing_count": len(missing),
        "completion_rate": round(rate, 2),
        "present": present,
        "missing": missing,
        "conditional_missing": conditional_missing,
        "not_checked": not_checked,
        "not_applicable": not_applicable,
        "verdict": verdict,
        "verdict_note_ko": note,
        "checklist": rows,
        "next_actions": next_actions,
        "basis_sources": [
            {"name_ko": "식품등의 표시기준", "authority_ko": "식품의약품안전처 고시", "url": LABEL_STANDARD_URL,
             "note_ko": "글씨 크기ㆍ위치ㆍ알레르기 표시 등 세부 서식은 고시를 확인해야 합니다."},
        ] if ptype in ("general_food", "health_functional_food") else [
            {"name_ko": "화장품법 시행규칙", "authority_ko": "총리령",
             "url": "https://www.law.go.kr/법령/화장품법시행규칙",
             "note_ko": "표시기준ㆍ표시방법의 세부 사항은 시행규칙을 확인해야 합니다."},
        ],
        "coverage_ko": (
            "법령 조문으로 필수 항목을 정하고, 입력한 라벨 텍스트에서 항목 존재만 대조했습니다. "
            "라벨 사진 인식은 하지 않으며, '누락'은 입력에 그 항목이 없다는 뜻입니다."
        ),
        "checked_on": VERIFIED_ON,
    }


def summarize(result: Dict[str, Any], limit: int = 4) -> List[str]:
    lines: List[str] = []
    if result.get("missing"):
        lines.append("누락 가능 항목: " + ", ".join(result["missing"][:limit]))
    if result.get("conditional_missing"):
        lines.append("조건부 확인 항목: " + ", ".join(result["conditional_missing"][:limit]))
    if result.get("not_checked"):
        lines.append("아직 확인하지 못한 항목: " + ", ".join(result["not_checked"][:limit]))
    if not lines:
        lines.append("입력한 범위에서 필수 표시항목이 모두 확인됐습니다. 세부 서식은 고시로 확인하세요.")
    return lines
