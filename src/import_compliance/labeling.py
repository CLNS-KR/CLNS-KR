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

# --- 0.5.1 추가 품목군: 조문 근거 (2026-11-21 법제처 국가법령정보 OPEN API 실조회) ---
# 기존 식품ㆍ건강기능식품ㆍ화장품 조문은 2026-11-19 조회본을 그대로 쓴다.
VERIFIED_ON_GROUPS = "2026-11-21"
LAW_URL_ELECTRICAL = "https://www.law.go.kr/법령/전기용품및생활용품안전관리법"
LAW_URL_ELECTRICAL_RULE = "https://www.law.go.kr/법령/전기용품및생활용품안전관리법시행규칙"
LAW_URL_TRADE = "https://www.law.go.kr/법령/대외무역법"
LAW_URL_FEED = "https://www.law.go.kr/법령/사료관리법"
LAW_URL_FEED_RULE = "https://www.law.go.kr/법령/사료관리법시행규칙"
LAW_URL_ECOMMERCE = "https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률"
LAW_URL_COSMETICS_RULE = "https://www.law.go.kr/법령/화장품법시행규칙"


LEGAL_LABELS: Dict[str, str] = {
    "식품등의 표시ㆍ광고에 관한 법률": "식품등의 표시ㆍ광고에 관한 법률",
    "전기용품 및 생활용품 안전관리법": "전기용품 및 생활용품 안전관리법",
}


def _gb(law: str, article: str, effective_date: str, url: str, quote: str) -> Dict[str, str]:
    return {"law": law, "article": article, "effective_date": effective_date,
            "url": url, "quote": quote, "verified_on": VERIFIED_ON_GROUPS}


# 전기용품 및 생활용품 안전관리법 (법률, 시행 2025-10-01)
B_KC_9_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제9조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "안전인증대상제품의 제조업자 또는 수입업자는 산업통상부령으로 정하는 바에 따라 "
    "안전인증대상제품 또는 포장에 다음 각 호의 구분에 따른 표시(이하 \"안전인증표시등\"이라 "
    "한다)를 하여야 한다.",
)
B_KC_9_3 = _gb(
    "전기용품 및 생활용품 안전관리법", "제9조제3항", "2025-10-01", LAW_URL_ELECTRICAL,
    "다음 각 호의 어느 하나에 해당하는 자는 안전인증대상제품의 안전인증표시등을 임의로 "
    "변경하거나 제거해서는 아니 된다.",
)
B_KC_18_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제18조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "안전확인대상제품의 제조업자 또는 수입업자는 산업통상부령으로 정하는 바에 따라 "
    "안전확인대상제품 또는 포장에 다음 각 호의 구분에 따른 표시(이하 \"안전확인표시등\"이라 "
    "한다)를 하여야 한다.",
)
B_KC_25_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제25조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "공급자적합성확인대상제품의 제조업자 또는 수입업자는 산업통상부령으로 정하는 바에 따라 "
    "공급자적합성확인대상제품 또는 포장에 다음 각 호의 구분에 따른 표시(이하 "
    "\"공급자적합성확인표시등\"이라 한다)를 하여야 한다.",
)
B_KC_29_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제29조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "안전기준준수대상생활용품의 제조업자 또는 수입업자는 산업통상부령으로 정하는 바에 따라 "
    "안전기준준수대상생활용품 또는 포장에 제28조에 따른 안전기준에서 정하는 표시를 하여야 한다.",
)
B_KC_36_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제36조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "구매대행업자는 산업통상부령으로 정하는 바에 따라 다음 각 호의 사항(이하 \"구매대행 "
    "고지사항\"이라 한다)을 구매자에게 고지(인터넷을 통한 구매대행의 경우에는 인터넷 "
    "홈페이지에 게시하는 것을 말한다)하여야 한다. 1. 해당 제품이 구매대행을 통하여 유통되는 "
    "제품이라는 사항 2. 해당 제품이 이 법에 따른 안전관리대상제품이라는 사항 3. 해당 제품의 "
    "안전인증 표시 또는 안전확인신고 표시에 관한 사항",
)
B_KC_38_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제38조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "안전인증ㆍ안전확인신고ㆍ공급자적합성확인 또는 공급자적합성확인신고를 면제받은 제품을 "
    "병행수입하는 경우에는 다음 각 호의 사항을 제품 또는 포장에 표시(이하 \"병행수입 표시\"라 "
    "한다)하여야 하며, 해당 제품을 판매하는 경우에는 다음 각 호의 사항을 구매자에게 "
    "고지하여야 한다. 1. 해당 제품이 병행수입된 제품이라는 사항 2. 해당 제품이 이 법에 따른 "
    "안전관리대상제품이라는 사항",
)
B_KC_51_1 = _gb(
    "전기용품 및 생활용품 안전관리법", "제51조제1항", "2025-10-01", LAW_URL_ELECTRICAL,
    "다음 각 호의 어느 하나에 해당하는 자에게는 1천만원 이하의 과태료를 부과한다. … 2. "
    "제10조제1항을 위반하여 안전인증표시등이 없는 안전인증대상생활용품을 판매ㆍ대여하거나 "
    "판매ㆍ대여할 목적으로 수입ㆍ진열 또는 보관한 자 … 5. 제36조제1항을 위반하여 구매대행 "
    "고지사항을 고지하지 아니한 자 6. 제38조제1항을 위반하여 병행수입 표시 또는 고지를 하지 "
    "아니한 자",
)
B_KC_51_2 = _gb(
    "전기용품 및 생활용품 안전관리법", "제51조제2항", "2025-10-01", LAW_URL_ELECTRICAL,
    "다음 각 호의 어느 하나에 해당하는 자에게는 500만원 이하의 과태료를 부과한다. … 2. "
    "제9조제1항을 위반하여 안전인증표시등을 하지 아니한 자 … 7. 제18조제1항을 위반하여 "
    "안전확인표시등을 하지 아니한 자 … 13. 제25조제1항을 위반하여 공급자적합성확인표시등을 "
    "하지 아니한 자 … 18. 제29조제1항을 위반하여 안전기준준수대상생활용품의 표시를 하지 "
    "아니한 자",
)
# 전기용품 및 생활용품 안전관리법 시행규칙 별표 9 (시행 2026-11-09)
B_KC_RULE_DOAN = _gb(
    "전기용품 및 생활용품 안전관리법 시행규칙", "별표 9 제1호가목", "2026-11-09", LAW_URL_ELECTRICAL_RULE,
    "안전인증, 안전확인신고, 공급자적합성확인, 어린이보호포장 및 안전성검사의 표시방법 — "
    "가. 도안(안전인증번호: / 안전확인신고번호: / 어린이보호포장신고확인번호: / 안전성검사번호:)",
)
B_KC_RULE_METHOD = _gb(
    "전기용품 및 생활용품 안전관리법 시행규칙", "별표 9 제1호나목", "2026-11-09", LAW_URL_ELECTRICAL_RULE,
    "안전인증등의 표시방법은 해당 안전관리대상제품 또는 그 포장에 쉽게 알아볼 수 있도록 "
    "표시하고, 떨어지지 않도록 붙이거나 인쇄 또는 각인 등의 방법으로 표시하여야 한다. "
    "안전인증등의 표시방법 및 안전기준에 관한 사항, 국가기술표준원장이 정하는 사항은 한글로 "
    "표기하여야 한다. 다만, 전기용품의 경우에는 국문 또는 영문 등의 글자로 부기할 수 있다.",
)
B_KC_RULE_DETAIL = _gb(
    "전기용품 및 생활용품 안전관리법 시행규칙", "별표 9 제1호나목 6)", "2026-11-09", LAW_URL_ELECTRICAL_RULE,
    "세부표시사항은 국가기술표준원장이 고시하는 바에 따른다.",
)
B_KC_RULE_NET = _gb(
    "전기용품 및 생활용품 안전관리법 시행규칙", "제20조제3항", "2026-11-09", LAW_URL_ELECTRICAL_RULE,
    "법 제9조제3항 각 호의 어느 하나에 해당하는 자는 법 제9조제4항에 따라 다음 각 호의 "
    "안전인증 관련 정보를 인터넷 홈페이지에 게시하여야 한다. 1. 별표 9 제1호가목에 따른 도안 "
    "2. 안전인증번호, 제품명, 모델명(모델명이 있는 경우에 한정한다), 제조업자명 또는 수입업자명",
)

# 대외무역법 (법률, 시행 2026-10-22)
B_TRADE_33_1 = _gb(
    "대외무역법", "제33조제1항", "2026-10-22", LAW_URL_TRADE,
    "산업통상부장관이 공정한 거래 질서의 확립과 생산자 및 소비자 보호를 위하여 원산지를 "
    "표시하여야 하는 대상으로 공고한 물품등(이하 \"원산지표시대상물품\"이라 한다)을 수출하거나 "
    "수입하려는 자는 그 물품등에 대하여 원산지를 표시하여야 한다.",
)
B_TRADE_33_2 = _gb(
    "대외무역법", "제33조제2항", "2026-10-22", LAW_URL_TRADE,
    "수입된 원산지표시대상물품에 대하여 대통령령으로 정하는 단순한 가공활동을 거침으로써 해당 "
    "물품등의 원산지 표시를 손상하거나 변형한 자는 그 단순 가공한 물품등에 당초의 원산지를 "
    "표시하여야 한다.",
)
B_TRADE_33_4 = _gb(
    "대외무역법", "제33조제4항", "2026-10-22", LAW_URL_TRADE,
    "무역거래자 또는 물품등의 판매업자는 수출 또는 수입 물품등 및 제35조에 따른 국내생산물품등에 "
    "대하여 다음 각 호의 어느 하나에 해당하는 행위를 하여서는 아니 된다. … 1. 원산지를 거짓으로 "
    "표시하거나 원산지를 오인하게 하는 표시를 하는 행위 2. 원산지의 표시를 손상하거나 변경하는 "
    "행위 3. 원산지표시대상물품에 대하여 원산지 표시를 하지 아니하는 행위 4. 제1호부터 제3호까지의 "
    "규정에 위반되는 원산지표시대상물품을 국내에서 거래하는 행위",
)
B_TRADE_33A_2 = _gb(
    "대외무역법", "제33조의2제2항", "2026-10-22", LAW_URL_TRADE,
    "산업통상부장관 또는 시ㆍ도지사는 제33조제2항부터 제4항까지의 규정(제33조제4항제4호는 "
    "제외한다)을 위반한 자에게 3억원 이하의 과징금을 부과할 수 있다.",
)

# 사료관리법 (법률 제19752호, 시행 2024-04-25) — 피드 엔진과 같은 조회본
B_FEED_LABEL_13_1 = _gb(
    "사료관리법", "제13조제1항", "2024-04-25", LAW_URL_FEED,
    "제조업자ㆍ수입업자 또는 판매업자는 제조 또는 수입한 사료를 판매하려는 경우에는 용기나 "
    "포장에 성분등록을 한 사항, 유통기한, 그 밖의 사용상 주의사항 등 농림축산식품부령으로 "
    "정하는 사항을 표시하여야 한다.",
)
B_FEED_LABEL_13_2 = _gb(
    "사료관리법", "제13조제2항", "2024-04-25", LAW_URL_FEED,
    "제조업자ㆍ수입업자 또는 판매업자는 제1항에 따른 표시사항을 거짓으로 표시하거나 과장하여 "
    "표시하여서는 아니 된다.",
)
B_FEED_RULE_4_1 = _gb(
    "사료관리법 시행규칙", "별표 4 제1호가목", "2024-12-05", LAW_URL_FEED_RULE,
    "배합사료의 표시사항과 표시방법 — 가. 표시사항 1) 사료의 성분등록번호 2) 사료의 명칭 및 "
    "형태 3) 등록성분량 4) 사용한 원료의 명칭 5) 동물용의약품 첨가 내용 6) 주의사항 7) 사료의 "
    "용도 8) 실제 중량(kg 또는 톤) 9) 제조(수입) 연월일 및 유통기간 또는 유통기한 10) "
    "제조(수입)업자의 상호(공장 명칭)ㆍ주소 및 전화번호 11) 재포장 내용 12) 사료공정에서 정하는 "
    "사항, 사료의 절감ㆍ품질관리 및 유통 개선을 위하여 농림축산식품부장관이 정하는 사항",
)
B_FEED_RULE_4_2 = _gb(
    "사료관리법 시행규칙", "별표 4 제2호가목", "2024-12-05", LAW_URL_FEED_RULE,
    "보조사료 및 단미사료의 표시사항과 표시방법 — 가. 표시사항 1) 사료의 성분등록번호 2) "
    "사료의 명칭 및 형태 3) 등록성분량 4) 사용한 원료의 명칭 5) 사료의 용도 6) 주의사항 7) "
    "실제 중량(kg 또는 톤) 8) 제조(수입) 연월일과 유통기간 또는 유통기한 9) 제조(수입)업자의 "
    "상호(공장 명칭)ㆍ주소 및 전화번호 10) 재포장 내용",
)
B_FEED_RULE_4_CAUTION = _gb(
    "사료관리법 시행규칙", "별표 4 제1호나목 6)", "2024-12-05", LAW_URL_FEED_RULE,
    "주의사항은 사료의 사용과 보관, 다른 사료와의 혼합 금지 등에 관하여 필요한 사항을 "
    "보증성분표 하단에 \"(주의):\" 형태로 붉은색 글씨 또는 눈에 잘 보이도록 표시하여야 하고, "
    "반추동물에서 유래한 동물성사료 또는 남은음식물사료가 포함된 배합사료에는 "
    "\"반추가축에게 먹이지 마십시오\"를 표시하여야 한다.",
)
B_FEED_RULE_20_1 = _gb(
    "사료관리법 시행규칙", "제20조제1항", "2024-12-05", LAW_URL_FEED_RULE,
    "법 제19조제1항에 따라 수입신고를 하려는 수입업자는 해당 사료의 통관 전까지 별지 "
    "제15호서식의 사료수입신고서에 다음 각 호의 서류를 첨부하여 … 제출하여야 한다. … 1. "
    "사료성분등록증 사본 … 3. 한글로 표시된 포장지 … 4. 상업송장(INVOICE)",
)
B_FEED_34 = _gb(
    "사료관리법", "제34조", "2024-04-25", LAW_URL_FEED,
    "다음 각 호의 어느 하나에 해당하는 자는 1년 이하의 징역 또는 1천만원 이하의 벌금에 "
    "처한다. … 7. 제13조제1항을 위반하여 표시사항을 표시하지 아니하고 사료를 판매한 자 8. "
    "제13조제2항을 위반하여 표시사항을 거짓으로 표시하거나 과장하여 표시한 자",
)

# 화장품법 (시행 2026-10-20) — 0.5.1에서 추가 확인한 조문
B_COS_12 = _gb(
    "화장품법", "제12조", "2026-10-20", LAW_URL_COSMETICS,
    "제10조 및 제11조에 따른 기재ㆍ표시는 다른 문자 또는 문장보다 쉽게 볼 수 있는 곳에 "
    "하여야 하며, 총리령으로 정하는 바에 따라 읽기 쉽고 이해하기 쉬운 한글로 정확히 "
    "기재ㆍ표시하여야 하되, 한자 또는 외국어를 함께 기재할 수 있다.",
)
B_COS_38 = _gb(
    "화장품법", "제38조", "2026-10-20", LAW_URL_COSMETICS,
    "다음 각 호의 어느 하나에 해당하는 자는 200만원 이하의 벌금에 처한다. … 2. "
    "제10조제1항(같은 항 제7호는 제외한다)ㆍ제2항을 위반한 자",
)
B_COS_40 = _gb(
    "화장품법", "제40조제1항제5호의2", "2026-10-20", LAW_URL_COSMETICS,
    "다음 각 호의 어느 하나에 해당하는 자에게는 100만원 이하의 과태료를 부과한다. … 5의2. "
    "제10조제1항제7호 및 제11조를 위반하여 화장품의 판매 가격을 표시하지 아니한 자",
)

# 식품등의 표시ㆍ광고에 관한 법률 (시행 2025-09-19)
B_FOOD_28 = _gb(
    "식품등의 표시ㆍ광고에 관한 법률", "제28조제1호", "2025-09-19", LAW_URL_FOOD_AD,
    "다음 각 호의 어느 하나에 해당하는 자는 3년 이하의 징역 또는 3천만원 이하의 벌금에 "
    "처한다. 1. 제4조제3항을 위반하여 식품등(건강기능식품은 제외한다)을 판매하거나 판매할 "
    "목적으로 제조ㆍ가공ㆍ소분ㆍ수입ㆍ포장ㆍ보관ㆍ진열 또는 운반하거나 영업에 사용한 자",
)
B_FOOD_31 = _gb(
    "식품등의 표시ㆍ광고에 관한 법률", "제31조제1항제1호", "2025-09-19", LAW_URL_FOOD_AD,
    "다음 각 호의 어느 하나에 해당하는 자에게는 500만원 이하의 과태료를 부과한다. 1. "
    "제5조제3항을 위반하여 식품등을 판매하거나 판매할 목적으로 제조ㆍ가공ㆍ소분ㆍ수입ㆍ포장ㆍ"
    "보관ㆍ진열 또는 운반하거나 영업에 사용한 자",
)

# 전자상거래 등에서의 소비자보호에 관한 법률 (시행 2026-07-21)
B_EC_13_1 = _gb(
    "전자상거래 등에서의 소비자보호에 관한 법률", "제13조제1항", "2026-07-21", LAW_URL_ECOMMERCE,
    "통신판매업자가 재화등의 거래에 관한 청약을 받을 목적으로 표시ㆍ광고를 할 때에는 그 "
    "표시ㆍ광고에 다음 각 호의 사항을 포함하여야 한다. 1. 상호 및 대표자 성명 2. "
    "주소ㆍ전화번호ㆍ전자우편주소 3. 제12조에 따라 신고한 신고번호와 그 신고를 받은 기관의 "
    "이름 등 신고를 확인할 수 있는 사항",
)

# --- 추가 품목군 체크리스트 -------------------------------------------------
KC_ELECTRONICS_ITEMS: List[Dict[str, Any]] = [
    {"id": "kc_mark", "label_ko": "KC 표시(안전인증ㆍ안전확인ㆍ공급자적합성확인ㆍ안전기준준수 표시 도안)",
     "required": True, "basis": B_KC_9_1,
     "example_ko": "예: KC 마크 + 안전확인신고번호",
     "detect": [r"KC|K\.C|안전\s*인증|안전\s*확인|공급자\s*적합성|안전기준\s*준수"]},
    {"id": "cert_number", "label_ko": "인증ㆍ신고 번호(도안 안에 기재)",
     "required": True, "basis": B_KC_RULE_DOAN,
     "example_ko": "예: 안전확인신고번호 XU12345-20001",
     "detect": [r"인증\s*번호|신고\s*번호|확인\s*번호|\b[A-Z]{2,3}\d{2,6}-\d{2,6}\b"]},
    {"id": "detail_items", "label_ko": "세부표시사항(제품명ㆍ모델명ㆍ제조업자/수입업자명ㆍ정격 등 국표원 고시 항목)",
     "required": True, "basis": B_KC_RULE_DETAIL,
     "example_ko": "예: 모델명 ABC-100 / 제조업자 OOO / 정격 220V 60Hz 15W",
     "detect": [r"모델\s*(명|번호)|제조\s*업자|제조원|수입\s*업자|수입원|정격|소비\s*전력|제조\s*연월"]},
    {"id": "origin", "label_ko": "원산지 표시", "required": False, "basis": B_TRADE_33_1,
     "applies_when_ko": "원산지표시대상물품으로 공고된 품목인 경우(수입 공산품 대부분 포함)",
     "example_ko": "예: MADE IN CHINA", "detect": [r"원산지|MADE\s*IN|제조국"]},
    {"id": "purchase_agency_notice", "label_ko": "구매대행 고지(구매대행 제품ㆍ안전관리대상ㆍ인증 표시 사항)",
     "required": False, "basis": B_KC_36_1,
     "applies_when_ko": "구매대행으로 판매하는 경우(인터넷 홈페이지 게시 포함)",
     "example_ko": "예: 본 제품은 구매대행으로 유통되는 안전확인대상제품입니다",
     "detect": [r"구매\s*대행|안전관리대상"]},
    {"id": "parallel_import_mark", "label_ko": "병행수입 표시(병행수입 제품ㆍ안전관리대상제품)",
     "required": False, "basis": B_KC_38_1,
     "applies_when_ko": "병행수입한 제품인 경우",
     "example_ko": "예: 병행수입 제품 / 안전관리대상제품",
     "detect": [r"병행\s*수입"]},
]

PET_FOOD_ITEMS: List[Dict[str, Any]] = [
    {"id": "ingredient_registration_no", "label_ko": "사료 성분등록번호", "required": True,
     "basis": B_FEED_RULE_4_1, "example_ko": "예: 성분등록번호 제00-000호",
     "detect": [r"성분\s*등록\s*번호|등록\s*번호"]},
    {"id": "product_name_form", "label_ko": "사료의 명칭 및 형태", "required": True,
     "basis": B_FEED_RULE_4_1, "example_ko": "예: 닭고기 함유 배합사료 / 펠릿",
     "detect": [r"명칭|제품명|품명|형태|펠릿|크럼블|후레이크|가루|액상"]},
    {"id": "registered_components", "label_ko": "등록성분량(조단백질ㆍ조지방 등, % 이상/이하)",
     "required": True, "basis": B_FEED_RULE_4_1,
     "example_ko": "예: 조단백질 26% 이상 / 조지방 12% 이상",
     "detect": [r"등록\s*성분량|조단백|조지방|조섬유|조회분|칼슘|인\b|%"]},
    {"id": "raw_material_names", "label_ko": "사용한 원료의 명칭(배합비율 큰 순서)", "required": True,
     "basis": B_FEED_RULE_4_1, "example_ko": "예: 원료명 — 닭고기, 옥수수, 대두박",
     "detect": [r"원료\s*(명)?|원재료"]},
    {"id": "medicated_feed", "label_ko": "동물용의약품 첨가 내용(첨가한 경우)", "required": False,
     "basis": B_FEED_RULE_4_1, "applies_when_ko": "동물용의약품을 첨가한 사료인 경우",
     "example_ko": "예: 동물용의약품 첨가사료 — OOO 00mg(성장 촉진), 휴약기간 5일",
     "detect": [r"동물용\s*의약품|휴약"]},
    {"id": "usage", "label_ko": "사료의 용도", "required": True, "basis": B_FEED_RULE_4_1,
     "example_ko": "예: 성견용 / 고양이 전연령", "detect": [r"용도|급여\s*대상|성견|자견|전연령|고양이"]},
    {"id": "caution", "label_ko": "주의사항", "required": True, "basis": B_FEED_RULE_4_CAUTION,
     "example_ko": "예: (주의) 개봉 후 냉장보관, 다른 사료와 혼합 금지",
     "detect": [r"주의\s*사항|주의\s*[:：]|보관\s*방법"]},
    {"id": "net_weight", "label_ko": "실제 중량(kg 또는 톤)", "required": True, "basis": B_FEED_RULE_4_1,
     "example_ko": "예: 2kg", "detect": [r"중량|내용량|\d+\s*(kg|g|톤|t)\b"]},
    {"id": "dates", "label_ko": "제조(수입) 연월일 및 유통기간 또는 유통기한", "required": True,
     "basis": B_FEED_RULE_4_1, "example_ko": "예: 제조일 2026.05.01 / 유통기한 2027.05.01",
     "detect": [r"유통\s*기한|유통\s*기간|제조\s*연월일|제조일|수입일"]},
    {"id": "seller_info", "label_ko": "제조(수입)업자의 상호(공장 명칭)ㆍ주소 및 전화번호", "required": True,
     "basis": B_FEED_RULE_4_1, "example_ko": "예: (주)예시펫푸드 / 인천 … / 000-0000-0000",
     "detect": [r"제조\s*업자|수입\s*업자|상호|주소|전화"]},
    {"id": "repackage_info", "label_ko": "재포장 내용(재포장한 경우)", "required": False,
     "basis": B_FEED_RULE_4_1, "applies_when_ko": "재포장한 사료인 경우",
     "example_ko": "예: 재포장 사유ㆍ날짜ㆍ중량, 재포장자 상호ㆍ주소",
     "detect": [r"재포장"]},
    {"id": "korean_package", "label_ko": "한글로 표시된 포장지(수입신고 첨부)", "required": False,
     "basis": B_FEED_RULE_20_1, "applies_when_ko": "수입 사료인 경우(수입신고 첨부서류)",
     "example_ko": "예: 한글 표시 포장지 또는 한글 설명서",
     "detect": [r"한글\s*표시|한글\s*포장지"]},
    {"id": "ruminant_warning", "label_ko": "\"반추가축에게 먹이지 마십시오\" 표시(반추동물 유래 원료 포함 시)",
     "required": False, "basis": B_FEED_RULE_4_CAUTION,
     "applies_when_ko": "반추동물에서 유래한 동물성 원료가 포함된 경우",
     "example_ko": "예: 반추가축에게 먹이지 마십시오",
     "detect": [r"반추"]},
]

GENERAL_GOODS_ITEMS: List[Dict[str, Any]] = [
    {"id": "origin", "label_ko": "원산지 표시", "required": False, "basis": B_TRADE_33_1,
     "applies_when_ko": "원산지표시대상물품으로 공고된 품목인 경우(수입 공산품 대부분 포함, 세부 대상은 고시 확인)",
     "example_ko": "예: MADE IN CHINA / 원산지: 중국", "detect": [r"원산지|MADE\s*IN|제조국"]},
    {"id": "kc_or_safety", "label_ko": "KC 표시 또는 안전기준준수 표시(전기ㆍ생활용품인 경우)",
     "required": False, "basis": B_KC_29_1,
     "applies_when_ko": "안전관리대상 전기용품ㆍ생활용품인 경우",
     "example_ko": "예: KC 마크 + 인증번호", "detect": [r"KC|안전\s*인증|안전\s*확인|공급자\s*적합성|안전기준\s*준수"]},
    {"id": "seller_info", "label_ko": "판매자 정보(상호ㆍ대표자ㆍ주소ㆍ연락처ㆍ통신판매업 신고번호)",
     "required": False, "basis": B_EC_13_1, "applies_when_ko": "온라인에서 판매하는 경우(표시ㆍ광고에 포함)",
     "example_ko": "예: 상호 (주)예시 / 주소 … / 전화 … / 통신판매업 신고번호 …",
     "detect": [r"상호|사업자\s*등록|통신판매|대표자|주소|전화"]},
]

CHECKLISTS: Dict[str, List[Dict[str, Any]]] = {
    "general_food": COMMON_FOOD_ITEMS,
    "health_functional_food": HFF_ITEMS,
    "cosmetics": COSMETIC_ITEMS,
    "functional_cosmetics": COSMETIC_ITEMS,
    "kc_electronics": KC_ELECTRONICS_ITEMS,
    "pet_food": PET_FOOD_ITEMS,
    "general_goods": GENERAL_GOODS_ITEMS,
}

GROUP_META: Dict[str, Dict[str, str]] = {
    "general_food": {
        "label_ko": PRODUCT_TYPES["general_food"]["label_ko"],
        "governing_law_ko": "식품등의 표시ㆍ광고에 관한 법률",
        "authority_ko": "식품의약품안전처",
        "note_ko": "수입식품은 수입신고 전에 한글표시사항을 갖추어야 하며, 표시가 없거나 표시방법을 위반한 식품은 판매할 수 없습니다(법 제4조제3항).",
    },
    "health_functional_food": {
        "label_ko": PRODUCT_TYPES["health_functional_food"]["label_ko"],
        "governing_law_ko": "식품등의 표시ㆍ광고에 관한 법률",
        "authority_ko": "식품의약품안전처",
        "note_ko": "건강기능식품은 일반식품 표시사항에 더해 '건강기능식품' 문자ㆍ도안, 기능성 정보, 섭취방법, 의약품 아님 표현이 필요합니다(법 제4조제1항제3호).",
    },
    "cosmetics": {
        "label_ko": PRODUCT_TYPES["cosmetics"]["label_ko"],
        "governing_law_ko": "화장품법",
        "authority_ko": "식품의약품안전처",
        "note_ko": "화장품은 2차 포장에 기재사항 전체를, 1차 포장에는 명칭ㆍ상호ㆍ제조번호ㆍ사용기한을 표시하고, 한글로 정확히 기재해야 합니다(제10조ㆍ제12조).",
    },
    "functional_cosmetics": {
        "label_ko": PRODUCT_TYPES["functional_cosmetics"]["label_ko"],
        "governing_law_ko": "화장품법",
        "authority_ko": "식품의약품안전처",
        "note_ko": "기능성화장품은 기재사항에 더해 '기능성화장품' 글자 또는 도안과 심사ㆍ보고받은 기능성 내용을 표시해야 합니다(제10조제1항).",
    },
    "kc_electronics": {
        "label_ko": "전기용품ㆍ생활용품(KC)",
        "governing_law_ko": "전기용품 및 생활용품 안전관리법",
        "authority_ko": "산업통상부 국가기술표준원",
        "note_ko": "제품 유형에 따라 안전인증(제9조)ㆍ안전확인(제18조)ㆍ공급자적합성확인(제25조)ㆍ안전기준준수(제29조) 중 하나의 표시를 제품 또는 포장에 해야 하고, 세부 항목은 국가기술표준원 고시를 따릅니다.",
    },
    "pet_food": {
        "label_ko": "반려동물 사료ㆍ간식(사료관리법)",
        "governing_law_ko": "사료관리법",
        "authority_ko": "농림축산식품부",
        "note_ko": "사료는 사람이 먹는 식품이 아니라 사료관리법이 적용됩니다. 용기ㆍ포장에 별표 4 표시사항을 갖추고, 수입 사료는 통관 전 수입신고에 한글로 표시된 포장지를 첨부해야 합니다.",
    },
    "general_goods": {
        "label_ko": "일반 공산품",
        "governing_law_ko": "품목별 개별 법령(공통 한글표시 법 없음)",
        "authority_ko": "품목별 소관 기관",
        "note_ko": "일반 공산품에는 모든 수입품에 적용되는 통일된 '법정 한글표시사항' 목록이 없습니다. 원산지 표시(대외무역법), KCㆍ안전기준(전기용품 및 생활용품 안전관리법), 온라인 판매자 정보(전자상거래법)와 품목별 개별법(식품ㆍ화장품ㆍ사료ㆍ의료기기ㆍ어린이제품 등)이 각각 적용됩니다.",
    },
}

FINE_CASES: Dict[str, List[Dict[str, Any]]] = {
    "general_food": [
        {"case_ko": "한글표시사항 없이 수입식품을 판매",
         "why_ko": "표시가 없거나 표시방법을 위반한 식품등은 판매하거나 판매 목적으로 수입ㆍ보관ㆍ진열할 수 없습니다.",
         "fix_ko": "수입 전에 한글표시사항 스티커ㆍ재포장으로 제품명ㆍ원재료명ㆍ소비기한 등을 갖추고, 원포장 표시를 가리지 않게 부착하세요.",
         "basis": [B_FOOD_4_3, B_FOOD_28]},
        {"case_ko": "영양표시 누락",
         "why_ko": "영양표시 대상 식품을 영양표시 없이 판매하면 과태료가 부과될 수 있습니다.",
         "fix_ko": "대상 여부를 「식품등의 표시기준」으로 확인하고 열량ㆍ나트륨ㆍ탄수화물 등을 표시하세요.",
         "basis": [B_FOOD_5_NUTRITION, B_FOOD_31]},
        {"case_ko": "소비기한과 제조일자를 혼동",
         "why_ko": "법은 소비기한ㆍ품질유지기한 또는 제조연월일을 구분해 표시하도록 정하고 있습니다.",
         "fix_ko": "소비기한(또는 품질유지기한)을 명확히 적고, 제조일자는 별도 항목으로 표시하세요.",
         "basis": [B_FOOD_4_1_1, B_FOOD_28]},
        {"case_ko": "한글 스티커가 원포장 표시를 가리거나 떨어짐",
         "why_ko": "표시방법은 총리령으로 정하며, 표시가 없거나 방법을 위반하면 판매 금지 사유가 됩니다.",
         "fix_ko": "원포장의 원재료명ㆍ소비기한을 가리지 않는 위치에 붙이고, 떨어지지 않도록 부착하세요(세부 기준은 「식품등의 표시기준」).",
         "basis": [B_FOOD_4_2, B_FOOD_4_3]},
        {"case_ko": "알레르기 유발물질 미표시",
         "why_ko": "알레르기 유발물질을 원재료로 사용한 경우 소비자 안전을 위한 표시가 필요합니다.",
         "fix_ko": "원재료명에 사용 여부를 적고, 대상 물질과 표시 방법은 「식품등의 표시기준」으로 확인하세요.",
         "basis": [B_FOOD_4_1_1, B_FOOD_28]},
    ],
    "health_functional_food": [
        {"case_ko": "'건강기능식품' 문자ㆍ도안 누락",
         "why_ko": "건강기능식품에는 '건강기능식품'이라는 문자 또는 도안과 의약품이 아니라는 표현이 필요합니다.",
         "fix_ko": "도안과 문구를 함께 넣고, 기능성 내용은 인정받은 범위로 적으세요.",
         "basis": [B_FOOD_4_1_3, B_FOOD_28]},
        {"case_ko": "섭취량ㆍ섭취방법 미표시",
         "why_ko": "섭취량ㆍ섭취방법과 섭취 시 주의사항은 법정 표시사항입니다.",
         "fix_ko": "1일 섭취량과 방법, 임산부ㆍ수유부 등 주의 대상을 표시하세요.",
         "basis": [B_FOOD_4_1_3, B_FOOD_28]},
        {"case_ko": "기능성 성분 함유량 미표시",
         "why_ko": "기능성을 나타내는 성분의 함유량과 원료의 함량을 표시해야 합니다.",
         "fix_ko": "성분명과 함량(1일 섭취량 기준)을 함께 적으세요.",
         "basis": [B_FOOD_4_1_3, B_FOOD_RULE_3_3]},
    ],
    "cosmetics": [
        {"case_ko": "전성분(사용된 모든 성분) 누락",
         "why_ko": "화장품법 제10조는 사용된 모든 성분을 기재하도록 정하고, 이를 위반하면 벌금이 부과될 수 있습니다.",
         "fix_ko": "전성분을 한글(또는 한글+외국어)로 빠짐없이 적고, 함량 순서와 표기 기준은 시행규칙을 확인하세요.",
         "basis": [B_COS_10_1, B_COS_38]},
        {"case_ko": "가격 미표시",
         "why_ko": "소비자에게 직접 판매하는 자는 판매 가격을 표시해야 하며, 위반 시 과태료가 부과될 수 있습니다.",
         "fix_ko": "판매 가격을 소비자가 쉽게 볼 수 있는 곳에 표시하세요.",
         "basis": [B_COS_10_1, B_COS_40]},
        {"case_ko": "사용기한 대신 제조일자만 표시",
         "why_ko": "사용기한 또는 개봉 후 사용기간을 기재해야 합니다.",
         "fix_ko": "사용기한(또는 개봉 후 사용기간)을 명확히 적고, 제조번호와 함께 표시하세요.",
         "basis": [B_COS_10_1, B_COS_38]},
        {"case_ko": "외국어만 표시(한글 미표기)",
         "why_ko": "기재ㆍ표시는 읽기 쉽고 이해하기 쉬운 한글로 정확히 해야 합니다.",
         "fix_ko": "한글을 기본으로 적고 한자ㆍ외국어를 함께 표기하세요.",
         "basis": [B_COS_12, B_COS_38]},
        {"case_ko": "한글 스티커 훼손ㆍ미부착",
         "why_ko": "기재사항이 없는 화장품은 표시 의무 위반이 되고, 수입 화장품은 한글 표시가 특히 문제됩니다.",
         "fix_ko": "훼손되지 않는 재질로 부착하고, 1차 포장에도 명칭ㆍ상호ㆍ제조번호ㆍ사용기한을 표시하세요.",
         "basis": [B_COS_10_1, B_COS_10_2, B_COS_38]},
    ],
    "functional_cosmetics": [
        {"case_ko": "'기능성화장품' 표시 누락",
         "why_ko": "기능성화장품은 심사ㆍ보고받은 기능성 내용과 '기능성화장품' 표시가 필요합니다.",
         "fix_ko": "심사ㆍ보고 결과에 맞는 기능성 문구와 도안을 표시하세요.",
         "basis": [B_COS_10_1, B_COS_38]},
        {"case_ko": "전성분 누락", "why_ko": "사용된 모든 성분을 기재해야 합니다.",
         "fix_ko": "전성분을 빠짐없이 한글로 적으세요.", "basis": [B_COS_10_1, B_COS_38]},
    ],
    "kc_electronics": [
        {"case_ko": "KC 표시 없이 판매",
         "why_ko": "표시가 없는 안전관리대상생활용품을 판매ㆍ대여하거나 판매 목적으로 수입ㆍ진열ㆍ보관하면 과태료가 부과될 수 있습니다.",
         "fix_ko": "통관 전에 제품 또는 포장에 KC 표시와 인증번호를 표시하세요.",
         "basis": [B_KC_9_1, B_KC_51_1]},
        {"case_ko": "제조ㆍ수입업자가 KC 표시를 하지 않음",
         "why_ko": "안전인증ㆍ안전확인ㆍ공급자적합성확인ㆍ안전기준준수 표시를 하지 않으면 500만원 이하 과태료가 부과될 수 있습니다.",
         "fix_ko": "유형별 표시(도안+번호)를 제품 또는 포장에 하고, 수입품은 통관 전에 마치세요.",
         "basis": [B_KC_9_1, B_KC_51_2]},
        {"case_ko": "표시가 떨어지거나 훼손됨",
         "why_ko": "표시는 쉽게 알아볼 수 있고 떨어지지 않도록 붙이거나 인쇄ㆍ각인해야 하며, 임의로 변경ㆍ제거할 수 없습니다.",
         "fix_ko": "스티커가 아닌 인쇄ㆍ각인을 우선하고, 스티커를 쓰면 떨어지지 않게 부착하세요.",
         "basis": [B_KC_RULE_METHOD, B_KC_9_3]},
        {"case_ko": "한글 미표기",
         "why_ko": "표시방법ㆍ안전기준ㆍ국표원 고시 사항은 한글로 표기해야 합니다(전기용품은 국문 또는 영문 부기 가능).",
         "fix_ko": "한글 표시를 기본으로 하고 외국어를 함께 적으세요.",
         "basis": [B_KC_RULE_METHOD]},
        {"case_ko": "온라인 판매 시 인증정보 미게시",
         "why_ko": "인터넷으로 판매ㆍ대여ㆍ판매중개ㆍ수입대행을 하면 도안ㆍ인증번호ㆍ제품명ㆍ모델명ㆍ제조/수입업자명을 홈페이지에 게시해야 합니다.",
         "fix_ko": "상세페이지에 인증 도안과 인증번호를 게시하세요.",
         "basis": [B_KC_RULE_NET, B_KC_51_2]},
        {"case_ko": "구매대행 고지 누락",
         "why_ko": "구매대행업자는 구매대행 제품임, 안전관리대상제품임, 인증ㆍ신고 표시 사항을 고지해야 합니다.",
         "fix_ko": "상품 페이지와 고지문에 세 가지를 모두 적으세요.",
         "basis": [B_KC_36_1, B_KC_51_1]},
    ],
    "pet_food": [
        {"case_ko": "표시 없이 사료 판매",
         "why_ko": "표시사항을 표시하지 않고 사료를 판매하면 1년 이하 징역 또는 1천만원 이하 벌금이 부과될 수 있습니다.",
         "fix_ko": "별표 4 표시사항을 용기ㆍ포장에 갖추세요.",
         "basis": [B_FEED_LABEL_13_1, B_FEED_34]},
        {"case_ko": "성분등록번호ㆍ원료명 누락",
         "why_ko": "성분등록번호와 사용한 원료의 명칭은 별표 4의 필수 표시사항입니다.",
         "fix_ko": "성분등록증과 표시가 일치하는지 대조하고, 원료명을 배합비율 큰 순서로 적으세요.",
         "basis": [B_FEED_RULE_4_1, B_FEED_34]},
        {"case_ko": "한글 포장지 없이 수입신고",
         "why_ko": "사료 수입신고에는 한글로 표시된 포장지(또는 한글 설명서)가 첨부서류입니다.",
         "fix_ko": "통관 전에 한글 표시 포장지를 준비해 신고에 첨부하세요.",
         "basis": [B_FEED_RULE_20_1]},
        {"case_ko": "거짓ㆍ과장 표시",
         "why_ko": "표시사항을 거짓으로 표시하거나 과장하면 처벌될 수 있습니다.",
         "fix_ko": "성분ㆍ원료ㆍ급여량 표시를 성분등록 내용과 일치시키고, 질병 치료ㆍ예방 표현은 빼세요.",
         "basis": [B_FEED_LABEL_13_2, B_FEED_34]},
        {"case_ko": "반추동물 원료 경고 미표시",
         "why_ko": "반추동물 유래 동물성사료가 포함되면 '반추가축에게 먹이지 마십시오'를 표시해야 합니다.",
         "fix_ko": "주의사항에 해당 문구를 함께 표시하세요.",
         "basis": [B_FEED_RULE_4_CAUTION]},
    ],
    "general_goods": [
        {"case_ko": "원산지 미표시",
         "why_ko": "원산지표시대상물품에 원산지를 표시하지 않으면 시정명령ㆍ과징금 대상이 될 수 있습니다.",
         "fix_ko": "수입 전에 원산지를 표시하고, 표시 방법은 「원산지표시제도 운영에 관한 고시」로 확인하세요.",
         "basis": [B_TRADE_33_1, B_TRADE_33_4, B_TRADE_33A_2]},
        {"case_ko": "원산지 표시 손상ㆍ변경",
         "why_ko": "원산지 표시를 손상ㆍ변경하거나 거짓 표시하는 행위는 금지됩니다.",
         "fix_ko": "원산지 스티커를 덧붙이거나 떼지 말고, 원래 표시가 유지되게 하세요.",
         "basis": [B_TRADE_33_4, B_TRADE_33A_2]},
        {"case_ko": "원산지 스티커가 떨어져 알아보기 어려움",
         "why_ko": "원산지를 알아보기 어려우면 미표시로 문제될 수 있습니다.",
         "fix_ko": "떨어지지 않는 방법으로 표시하고, 유통 중 훼손 여부를 확인하세요.",
         "basis": [B_TRADE_33_4, B_TRADE_33A_2]},
        {"case_ko": "'모든 수입품에 한글표시사항이 필수'라는 오해",
         "why_ko": "일반 공산품 전체에 적용되는 통일된 법정 한글표시 목록은 없습니다. 품목별 개별법이 정한 표시만 의무입니다.",
         "fix_ko": "품목이 식품ㆍ화장품ㆍ사료ㆍ전기용품ㆍ어린이제품ㆍ의료기기 중 어디에 속하는지 먼저 확인하고, 해당 법령의 표시사항을 적용하세요.",
         "basis": [B_TRADE_33_1]},
    ],
}

METHOD_CHECKS: Dict[str, List[str]] = {
    "general_food": [
        "한글 표시가 원포장의 원재료명ㆍ소비기한을 가리지 않는지 실물로 확인하세요.",
        "글씨 크기ㆍ표시 위치ㆍ알레르기 표시 방법은 「식품등의 표시기준」으로 확인하세요.",
    ],
    "health_functional_food": [
        "'건강기능식품' 도안의 크기ㆍ색상과 기능성 문구의 위치는 「건강기능식품의 기준 및 규격」으로 확인하세요.",
    ],
    "cosmetics": [
        "1차 포장에도 명칭ㆍ상호ㆍ제조번호ㆍ사용기한이 있는지 실물로 확인하세요.",
        "한글 표시의 글씨 크기ㆍ위치는 「화장품법 시행규칙」으로 확인하세요.",
    ],
    "functional_cosmetics": [
        "기능성화장품 도안과 심사ㆍ보고받은 기능성 내용이 일치하는지 확인하세요.",
    ],
    "kc_electronics": [
        "KC 표시가 쉽게 알아보이고 떨어지지 않게 부착ㆍ인쇄ㆍ각인되었는지 실물로 확인하세요(별표 9).",
        "한글 표기 여부와 세부표시사항(제품명ㆍ모델명ㆍ정격 등)은 국가기술표준원 고시로 확인하세요.",
        "수입품은 통관 전에 표시를 마쳐야 하며, 온라인 판매 시 인증정보를 홈페이지에 게시해야 합니다.",
    ],
    "pet_food": [
        "한글 표시 포장지가 수입신고 첨부서류로 준비되었는지 확인하세요(시행규칙 제20조).",
        "벌크로 수입해 스티커ㆍ라벨ㆍ꼬리표를 쓰는 경우 떨어지지 않게 부착해야 합니다(수입위생조건 제6조).",
    ],
    "general_goods": [
        "원산지 표시가 유통 중 훼손되지 않는 방법인지 확인하세요.",
        "품목별 개별법(식품ㆍ화장품ㆍ사료ㆍ전기용품ㆍ어린이제품ㆍ의료기기) 대상인지 먼저 확인하세요.",
    ],
}

LABEL_GROUP_ALIASES: Dict[str, str] = {
    "general_food": "general_food", "food": "general_food", "식품": "general_food",
    "일반식품": "general_food", "가공식품": "general_food", "수입식품": "general_food",
    "health_functional_food": "health_functional_food", "hff": "health_functional_food",
    "health_functional": "health_functional_food", "건강기능식품": "health_functional_food",
    "건기식": "health_functional_food", "supplement": "health_functional_food",
    "cosmetics": "cosmetics", "cosmetic": "cosmetics", "화장품": "cosmetics",
    "functional_cosmetics": "functional_cosmetics", "기능성화장품": "functional_cosmetics",
    "kc_electronics": "kc_electronics", "kc": "kc_electronics", "electronics": "kc_electronics",
    "electrical": "kc_electronics", "전기용품": "kc_electronics", "생활용품": "kc_electronics",
    "가전": "kc_electronics", "전자제품": "kc_electronics",
    "pet_food": "pet_food", "pet": "pet_food", "feed": "pet_food", "사료": "pet_food",
    "반려동물": "pet_food", "펫푸드": "pet_food", "petfood": "pet_food",
    "general_goods": "general_goods", "general": "general_goods", "공산품": "general_goods",
    "general_product": "general_goods", "goods": "general_goods", "일반공산품": "general_goods",
}

GROUP_TAGS: Dict[str, List[str]] = {
    "general_food": ["KOREAN_LABELING", "FOOD_IMPORT_DECLARATION"],
    "health_functional_food": ["KOREAN_LABELING", "HEALTH_FUNCTIONAL_FOOD"],
    "cosmetics": ["KOREAN_LABELING"],
    "functional_cosmetics": ["KOREAN_LABELING"],
    "kc_electronics": ["ELECTRICAL_KC", "KOREAN_LABELING"],
    "pet_food": ["FEED_LABELING"],
    "general_goods": ["ORIGIN_MARKING", "KOREAN_LABELING"],
}

GROUP_ORDER: List[str] = [
    "cosmetics", "functional_cosmetics", "general_food", "health_functional_food",
    "kc_electronics", "pet_food", "general_goods",
]


def normalize_group(value: Any, text: str = "") -> str:
    """품목군을 정한다. 명시값이 없으면 문구에서 찾고, 끝까지 모르면 일반 공산품으로 둔다."""
    raw = str(value or "").strip().lower()
    if raw in LABEL_GROUP_ALIASES:
        return LABEL_GROUP_ALIASES[raw]
    probe = str(text or "")
    if any(key in probe for key in ("사료", "간식", "반려동물", "펫푸드", "강아지", "고양이")):
        return "pet_food"
    if any(key in probe for key in ("KC", "안전인증", "안전확인", "공급자적합성", "전기용품", "생활용품")):
        return "kc_electronics"
    if any(key in probe for key in ("화장품", "크림", "세럼", "앰플", "로션", "토너", "마스크팩", "에센스")):
        return "cosmetics"
    if any(key in probe for key in ("건강기능식품", "건기식", "비타민", "영양제", "유산균", "오메가")):
        return "health_functional_food"
    if any(key in probe for key in ("식품", "음료", "주스", "과자", "소스", "차", "커피", "분말")):
        return "general_food"
    return "general_goods"


def checklist(product_type: str) -> List[Dict[str, Any]]:
    ptype = normalize_group(product_type)
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


def _truthy_flag(value: Any) -> Optional[bool]:
    token = str(value or "").strip().lower()
    if token in ("yes", "y", "true", "1", "o", "있음", "수입"):
        return True
    if token in ("no", "n", "false", "0", "x", "없음"):
        return False
    return None


def _conditional_applies(item: Dict[str, Any], ptype: str, text: str, imported: bool,
                         channel: str, animal_origin: Optional[bool]) -> bool:
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
    if key == "purchase_agency_notice":
        return channel in ("agency",) or bool(re.search(r"구매\s*대행", text))
    if key == "parallel_import_mark":
        return channel == "parallel_import" or bool(re.search(r"병행\s*수입", text))
    if key == "medicated_feed":
        return bool(re.search(r"동물용\s*의약품|휴약", text))
    if key == "repackage_info":
        return bool(re.search(r"재포장", text))
    if key == "korean_package":
        return imported or bool(re.search(r"수입|한글\s*표시", text))
    if key == "ruminant_warning":
        return animal_origin is True or bool(re.search(r"반추", text))
    if key == "seller_info" and ptype == "general_goods":
        return channel == "online" or bool(
            re.search(r"온라인|상세\s*페이지|스마트스토어|쿠팡|자사몰", text))
    if key == "origin":
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


def _basis_sources(ptype: str) -> List[Dict[str, str]]:
    if ptype in ("general_food", "health_functional_food"):
        return [{"name_ko": "식품등의 표시기준", "authority_ko": "식품의약품안전처 고시",
                 "url": LABEL_STANDARD_URL,
                 "note_ko": "글씨 크기ㆍ위치ㆍ알레르기 표시 등 세부 서식은 고시를 확인해야 합니다."}]
    if ptype in ("cosmetics", "functional_cosmetics"):
        return [{"name_ko": "화장품법 시행규칙", "authority_ko": "총리령", "url": LAW_URL_COSMETICS_RULE,
                 "note_ko": "표시기준ㆍ표시방법의 세부 사항은 시행규칙을 확인해야 합니다."}]
    if ptype == "kc_electronics":
        return [{"name_ko": "전기용품 및 생활용품 안전관리법 시행규칙 별표 9(표시방법)",
                 "authority_ko": "산업통상부령", "url": LAW_URL_ELECTRICAL_RULE,
                 "note_ko": "세부표시사항은 국가기술표준원장이 고시하는 바에 따릅니다(별표 9 제1호나목 6)."}]
    if ptype == "pet_food":
        return [{"name_ko": "사료관리법 시행규칙 별표 4(용기ㆍ포장 표시사항)",
                 "authority_ko": "농림축산식품부령", "url": LAW_URL_FEED_RULE,
                 "note_ko": "사료 수입신고에는 한글로 표시된 포장지가 첨부서류입니다(시행규칙 제20조)."},
                {"name_ko": "반려동물 사료 수입위생조건", "authority_ko": "농림축산식품부고시",
                 "url": "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000269678",
                 "note_ko": "벌크 수입 시 스티커ㆍ라벨ㆍ꼬리표는 떨어지지 않게 부착해야 합니다."}]
    return [{"name_ko": "원산지표시제도 운영에 관한 고시", "authority_ko": "산업통상부 고시",
             "url": "https://www.law.go.kr/행정규칙/원산지표시제도운영에관한고시",
             "note_ko": "원산지표시대상물품과 표시 방법은 고시로 확인해야 합니다."}]


def check(product_type: str, *, label_text: str = "", provided: Optional[Dict[str, Any]] = None,
          imported: Any = None, channel: Any = None, animal_origin: Any = None) -> Dict[str, Any]:
    """라벨 필수항목을 대조한다."""
    ptype = normalize_group(product_type, label_text)
    meta = GROUP_META[ptype]
    text = str(label_text or "")
    supplied = dict(provided or {})
    imported_flag = bool(_truthy_flag(imported))
    channel_token = str(channel or "").strip().lower()
    if channel_token in ("buy_for_me", "purchase_agency", "구매대행"):
        channel_token = "agency"
    if channel_token in ("parallel", "병행수입"):
        channel_token = "parallel_import"
    animal_flag = _truthy_flag(animal_origin)
    rows: List[Dict[str, Any]] = []
    for item in CHECKLISTS.get(ptype, COMMON_FOOD_ITEMS):
        applies = bool(item["required"]) or _conditional_applies(
            item, ptype, text, imported_flag, channel_token, animal_flag)
        status = _status_for(item, text, supplied)
        if not applies and not item["required"]:
            status = "not_applicable"
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
    rate = (len([r for r in required_rows if r["status"] == "present"]) / len(required_rows)) if required_rows else 0.0
    fine_cases = [dict(case) for case in FINE_CASES.get(ptype, [])]
    method_checks = list(METHOD_CHECKS.get(ptype, []))

    if not text and not supplied:
        verdict = "info_needed"
        note = "라벨 문구나 항목 체크를 넣으면 누락 여부를 대조합니다. 지금은 필수 항목 체크리스트와 흔한 과태료 사례를 보여 줍니다."
    elif missing:
        verdict = "check_likely"
        note = f"필수 항목 {len(missing)}개를 찾지 못했습니다. 표시 누락은 판매 금지ㆍ과태료 사유가 될 수 있습니다."
    elif not_checked or conditional_missing:
        verdict = "info_needed"
        note = "필수 항목은 확인됐지만 조건부 항목ㆍ확인 불가 항목이 남아 있습니다."
    elif not required_rows:
        verdict = "info_needed"
        note = "이 품목군에는 법정 공통 필수 항목이 없습니다. 원산지ㆍKCㆍ판매자 정보와 품목별 개별법 확인이 필요합니다."
    else:
        verdict = "low_risk"
        note = "입력한 범위에서 필수 표시항목이 모두 확인됐습니다. 세부 서식(글씨 크기ㆍ위치)과 표시 방법은 별도 확인이 필요합니다."

    next_actions: List[str] = []
    if missing:
        next_actions.append("누락 항목을 라벨에 추가하고, 수입 전 한글표시사항 스티커ㆍ재포장 여부를 확인하세요.")
    if conditional_missing:
        next_actions.append("조건부 항목(" + ", ".join(conditional_missing[:4]) + ")이 해당 제품에 필요한지 확인하세요.")
    if ptype in ("general_food", "health_functional_food"):
        next_actions.append("세부 표시방법(글씨 크기ㆍ위치ㆍ알레르기 표시)은 「식품등의 표시기준」 최신본으로 확인하세요.")
    elif ptype in ("cosmetics", "functional_cosmetics"):
        next_actions.append("1차 포장 기재와 한글 표시는 「화장품법 시행규칙」 및 식약처 안내서로 확인하세요.")
    elif ptype == "kc_electronics":
        next_actions.append("KC 유형(안전인증/안전확인/공급자적합성확인/안전기준준수)은 CLNS Check의 ‘적합성평가 번호’ 항목으로 먼저 확인하세요.")
        next_actions.append("세부표시사항은 국가기술표준원 고시를 확인하세요(별표 9 제1호나목 6).")
    elif ptype == "pet_food":
        next_actions.append("사료 성분등록ㆍ수입신고ㆍ동물검역은 CLNS Check의 ‘반려동물 사료·간식’ 점검으로 함께 확인하세요.")
    else:
        next_actions.append("품목별 개별법(식품ㆍ화장품ㆍ사료ㆍ전기용품ㆍ어린이제품ㆍ의료기기) 대상인지 먼저 확인하세요.")

    return {
        "product_type": ptype,
        "product_type_label_ko": meta["label_ko"],
        "governing_law_ko": meta["governing_law_ko"],
        "authority_ko": meta["authority_ko"],
        "group_note_ko": meta["note_ko"],
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
        "fine_cases": fine_cases,
        "method_checks_ko": method_checks,
        "next_actions": next_actions,
        "basis_sources": _basis_sources(ptype),
        "coverage_ko": (
            "법령 조문으로 필수 항목을 정하고, 입력한 라벨 텍스트에서 항목 존재만 대조했습니다. "
            "라벨 사진 인식은 하지 않으며, '누락'은 입력에 그 항목이 없다는 뜻입니다. "
            "0건·전항목 확인이 라벨의 적법성을 확정하지 않습니다."
        ),
        "checked_on": VERIFIED_ON_GROUPS if ptype in ("kc_electronics", "pet_food", "general_goods") else VERIFIED_ON,
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
