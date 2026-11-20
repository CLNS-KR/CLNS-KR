"""반려동물 사료·간식 수입 검수 엔진 (CLNS 0.5.0) — 사료관리법 · 동물검역.

무엇을 하는가
-------------
'강아지 간식', '고양이 사료', '단미사료', '반려동물 영양제', '펫푸드 직구'처럼 반려동물이
먹는 것을 수입·판매하려는 사람에게, **식품(수입식품안전관리 특별법)이 아니라 사료관리법**이
적용된다는 점과 그때 실제로 걸리는 4개 축을 사실관계 기준으로 정리한다.

1. **등록·신고** — 사료 성분등록(법 제12조), 사료 수입신고와 통관 전 검정(법 제19조),
   자가품질검사(법 제20조), (제조·재포장하는 경우) 사료 제조업 등록(법 제8조)
2. **표시** — 용기·포장 표시사항(법 제13조, 시행규칙 제14조·별표 4), 거짓·과장 표시 금지
3. **유해·금지** — 유해물질·동물용의약품 잔류 기준(법 제14조①, 「사료 등의 기준 및 규격」
   제11조), 성분등록·수입신고 없이 수입된 사료 판매 금지(같은 조 제5호·제6호), 유통기한
   경과 판매 금지(같은 조 ③), 특정 동물성사료(반추동물 유래) 사용 금지
4. **동물검역** — 지정검역물(가축전염병 예방법 제31조, 시행규칙 제31조 제13호), 검역증명서
   첨부(제34조)·수입검역(제36조)·우편물·탁송품 신고(제39조), 동물성 원료가 들어간
   반려동물 사료의 수입위생조건(「반려동물 사료 수입위생조건」)

왜 식품 축과 따로 두는가
------------------------
`advertising.py`·`labeling.py` 는 사람이 먹는 식품·건강기능식품의 표시·광고와 한글표시사항을
본다. 반려동물 사료는 소관 부처가 농림축산식품부이고, 근거 법령이 사료관리법이며, 판매 전에
**성분등록 → 수입신고 → 표시**가 순서대로 붙고 동물검역이 별도로 걸린다. 같은 '닭가슴살
동결건조'라도 사람이 먹으면 식품, 반려동물이 먹으면 사료다.

근거의 성격(정직하게)
--------------------
- 법률·시행령·시행규칙 조문은 **2026-11-20 법제처 국가법령정보 OPEN API로 조회해 조문시행일자가
  오늘 이하인 최신 버전**의 본문을 인용했다(`feed-law-verification.json`).
  - 사료관리법(법률 제19752호, 시행 2024-04-25): 제2조·제6조·제7조·제8조·제12조·제13조·
    제14조·제19조·제20조
  - 사료관리법 시행규칙(농림축산식품부령 제552호, 시행 2024-12-05): 제12조·제14조·제20조
  - 가축전염병 예방법(시행 2026-01-23 판본): 제31조·제32조·제34조·제36조·제39조
  - 가축전염병 예방법 시행규칙(시행 2026-09-29 판본): 제31조(지정검역물)
- 고시는 조문 단위가 아니라 본문 항목을 인용하고 원문 링크를 붙였다(수시 개정).
  - 「반려동물 사료 수입위생조건」(농림축산식품부고시 제2025-124호, 시행 2025-12-12)
  - 「사료 등의 기준 및 규격」(농림축산식품부고시 제2024-27호, 시행 2024-04-01)
- **사료관리법에 '수입업 등록' 제도는 없다.** 제8조는 제조업 등록만 정하고, 수입업자는
  성분등록(제12조)·수입신고(제19조)·표시(제13조) 의무를 진다. "사료 수입업 등록"을 안내하는
  설명은 조문과 맞지 않는다(이 모듈이 그 오답을 교정한다).
- 이 엔진은 **입력한 사실관계 대조**다. 제품 성분·원료의 실제 축종·가공도, 수출국 제조시설
  승인 여부, 실제 검역 결과는 보지 못한다. 결과는 "확인해야 할 항목 목록"이며 확정 판정이 아니다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERIFIED_ON = "2026-11-20"
AUTHORITY_KO = "농림축산식품부"
AUTHORITY_QUARANTINE_KO = "농림축산검역본부"

# ---------------------------------------------------------------------------
# 1. 근거 법령 원문 URL · 명칭
# ---------------------------------------------------------------------------
LAW_URL_FEED = "https://www.law.go.kr/법령/사료관리법"
LAW_URL_FEED_RULE = "https://www.law.go.kr/법령/사료관리법시행규칙"
LAW_URL_LIVESTOCK = "https://www.law.go.kr/법령/가축전염병예방법"
LAW_URL_LIVESTOCK_RULE = "https://www.law.go.kr/법령/가축전염병예방법시행규칙"
NOTICE_PETFOOD_URL = "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000269678"
NOTICE_FEED_STANDARD_URL = "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000238528"

FEED_NAME_KO = "사료관리법"
FEED_RULE_NAME_KO = "사료관리법 시행규칙"
LIVESTOCK_NAME_KO = "가축전염병 예방법"
LIVESTOCK_RULE_NAME_KO = "가축전염병 예방법 시행규칙"
NOTICE_PETFOOD_KO = "반려동물 사료 수입위생조건"
NOTICE_FEED_STANDARD_KO = "사료 등의 기준 및 규격"


def _basis(law: str, article: str, effective_date: str, url: str, quote: str) -> Dict[str, str]:
    return {"law": law, "article": article, "effective_date": effective_date,
            "url": url, "quote": quote, "verified_on": VERIFIED_ON}


# --- 사료관리법 (법률 제19752호, 시행 2024-04-25) ---------------------------
B_FEED_2_DEF = _basis(
    FEED_NAME_KO, "제2조제1호", "2024-04-25", LAW_URL_FEED,
    "\"사료\"란 「축산법」에 따른 가축이나 그 밖에 농림축산식품부장관이 정하여 고시하는 "
    "동물ㆍ어류 등(이하 \"동물등\"이라 한다)에 영양이 되거나 그 건강유지 또는 성장에 필요한 "
    "것으로서 단미사료ㆍ배합사료 및 보조사료를 말한다. 다만, 동물용의약으로서 섭취하는 것을 "
    "제외한다.",
)
B_FEED_2_IMPORTER = _basis(
    FEED_NAME_KO, "제2조제6호", "2024-04-25", LAW_URL_FEED,
    "\"수입업\"이란 사료를 수입하여 판매(단순히 재포장하는 경우를 포함한다. 이하 같다)하는 업을 "
    "말한다.",
)
B_FEED_6_RECOMMEND = _basis(
    FEED_NAME_KO, "제6조제1항", "2024-04-25", LAW_URL_FEED,
    "「세계무역기구 설립을 위한 마라케쉬 협정」에 따른 대한민국 양허표상의 시장접근물량에 "
    "적용되는 양허세율로 사료를 수입하려는 자는 농림축산식품부장관의 추천을 받아야 한다.",
)
B_FEED_7_PURPOSE = _basis(
    FEED_NAME_KO, "제7조제1항", "2024-04-25", LAW_URL_FEED,
    "누구든지 수입한 사료를 다른 사료의 원료용 또는 동물등의 먹이, 그 밖의 농림축산식품부령으로 "
    "정하는 용도 외로 판매하여서는 아니 된다.",
)
B_FEED_8_MANUFACTURE = _basis(
    FEED_NAME_KO, "제8조제1항", "2024-04-25", LAW_URL_FEED,
    "제조업을 영위하려는 자는 농림축산식품부령으로 정하는 바에 따라 특별시장ㆍ광역시장ㆍ"
    "특별자치시장ㆍ도지사 또는 특별자치도지사(이하 \"시ㆍ도지사\"라 한다)에게 등록하여야 한다.",
)
B_FEED_12_REGISTRATION = _basis(
    FEED_NAME_KO, "제12조제1항", "2024-04-25", LAW_URL_FEED,
    "제조업자 또는 수입업자는 시ㆍ도지사에게 제조 또는 수입하려는 사료의 종류ㆍ성분 및 "
    "성분량, 그 밖에 농림축산식품부장관이 정하는 사항을 등록(이하 \"성분등록\"이라 한다)하여야 "
    "한다.",
)
B_FEED_13_LABEL = _basis(
    FEED_NAME_KO, "제13조제1항", "2024-04-25", LAW_URL_FEED,
    "제조업자ㆍ수입업자 또는 판매업자는 제조 또는 수입한 사료를 판매하려는 경우에는 용기나 "
    "포장에 성분등록을 한 사항, 유통기한, 그 밖의 사용상 주의사항 등 농림축산식품부령으로 "
    "정하는 사항을 표시하여야 한다.",
)
B_FEED_13_FALSE_LABEL = _basis(
    FEED_NAME_KO, "제13조제2항", "2024-04-25", LAW_URL_FEED,
    "제조업자ㆍ수입업자 또는 판매업자는 제1항에 따른 표시사항을 거짓으로 표시하거나 과장하여 "
    "표시하여서는 아니 된다.",
)
B_FEED_14_HAZARD = _basis(
    FEED_NAME_KO, "제14조제1항제1호ㆍ제2호", "2024-04-25", LAW_URL_FEED,
    "1. 인체 또는 동물등에 해로운 유해물질이 허용기준 이상으로 포함되거나 잔류된 것 "
    "2. 동물용의약품이 허용기준 이상으로 잔류된 것",
)
B_FEED_14_UNREGISTERED = _basis(
    FEED_NAME_KO, "제14조제1항제5호ㆍ제6호", "2024-04-25", LAW_URL_FEED,
    "5. 성분등록을 하지 아니하고 제조 또는 수입된 것 6. 제19조제1항에 따른 수입신고를 하지 "
    "아니하고 수입된 것",
)
B_FEED_14_SPECIAL_RISK = _basis(
    FEED_NAME_KO, "제14조제1항제7호ㆍ제2항", "2024-04-25", LAW_URL_FEED,
    "7. 인체 또는 농림축산식품부장관이 정하여 고시한 동물등의 질병원인이 우려되어 사료로 "
    "사용하는 것을 금지한 동물등의 부산물ㆍ남은 음식물 등 농림축산식품부장관이 정하여 고시한 것 "
    "… ② 누구든지 동물등에게 제1항제7호의 사료를 사용하여서는 아니 된다.",
)
B_FEED_14_EXPIRY = _basis(
    FEED_NAME_KO, "제14조제3항", "2024-04-25", LAW_URL_FEED,
    "제조업자ㆍ수입업자 또는 판매업자는 유통기한이 경과한 사료를 판매하거나 판매할 목적으로 "
    "보관ㆍ진열하여서는 아니 된다.",
)
B_FEED_19_DECLARATION = _basis(
    FEED_NAME_KO, "제19조제1항ㆍ제2항", "2024-04-25", LAW_URL_FEED,
    "① 수입업자는 농림축산식품부장관이 정하여 고시하는 사료를 수입하려는 경우에는 "
    "농림축산식품부령으로 정하는 바에 따라 농림축산식품부장관에게 신고하여야 한다. … "
    "② 농림축산식품부장관은 사료의 안전성확보ㆍ수급안정 등 농림축산식품부령으로 정하는 사유가 "
    "있는 경우에는 제1항에 따라 신고된 사료에 대하여 통관절차 완료 전에 관계 공무원으로 하여금 "
    "필요한 검정을 하게 하여야 한다.",
)
B_FEED_20_SELF_INSPECTION = _basis(
    FEED_NAME_KO, "제20조제1항", "2024-04-25", LAW_URL_FEED,
    "① 제조업자 또는 수입업자는 사료의 품질관리 및 안전성 확보를 위하여 농림축산식품부령으로 "
    "정하는 시설을 갖추고 그가 제조 또는 수입하는 사료에 대하여 다음 각 호의 사항을 검사하여야 "
    "한다. … 1. 사료공정에 적합한지의 여부 2. 성분등록된 사항과 차이가 있는지의 여부 "
    "3. 제14조제1항제1호부터 제4호까지의 규정에 해당하는지의 여부",
)

# --- 사료관리법 시행규칙 (시행 2024-12-05) ---------------------------------
B_FEED_RULE_12 = _basis(
    FEED_RULE_NAME_KO, "제12조제1항", "2024-12-05", LAW_URL_FEED_RULE,
    "① 제조업자 또는 수입업자가 법 제12조제1항 본문에 따라 사료의 성분등록을 하려는 경우에는 "
    "별지 제6호서식 또는 별지 제7호서식의 사료성분등록신청서에 다음 각 호의 서류를 첨부하여 "
    "시ㆍ도지사에게 제출하여야 한다. … 1. 사용한 원료의 명칭을 적은 서류 … 3. 사료의 제조공정 "
    "설명서",
)
B_FEED_RULE_14 = _basis(
    FEED_RULE_NAME_KO, "제14조", "2024-12-05", LAW_URL_FEED_RULE,
    "제조업자ㆍ수입업자 또는 판매업자가 법 제13조제1항에 따라 용기나 포장에 표시하여야 할 "
    "사항 및 그 표시방법은 별표 4와 같다.",
)
B_FEED_RULE_20 = _basis(
    FEED_RULE_NAME_KO, "제20조제1항", "2024-12-05", LAW_URL_FEED_RULE,
    "① 법 제19조제1항에 따라 수입신고를 하려는 수입업자는 해당 사료의 통관 전까지 별지 "
    "제15호서식의 사료수입신고서에 다음 각 호의 서류를 첨부하여 … 신고단체\"라 한다)에 "
    "제출하여야 한다. … 1. 사료성분등록증 사본 … 3. 한글로 표시된 포장지 … 4. 상업송장(INVOICE)",
)

# --- 가축전염병 예방법 (시행 2026-01-23 판본) ------------------------------
B_LIVESTOCK_31 = _basis(
    LIVESTOCK_NAME_KO, "제31조제3호", "2026-01-23", LAW_URL_LIVESTOCK,
    "수출입 검역 대상 물건은 다음 각 호의 어느 하나에 해당하는 물건으로서 농림축산식품부령으로 "
    "정하는 물건(이하 \"지정검역물\"이라 한다)으로 한다. … 3. 그 밖에 가축 전염성 질병의 "
    "병원체를 퍼뜨릴 우려가 있는 사료, 사료원료, 기구, 건초, 깔짚, 그 밖에 이에 준하는 물건",
)
B_LIVESTOCK_RULE_31 = _basis(
    LIVESTOCK_RULE_NAME_KO, "제31조제1항제13호", "2026-09-29", LAW_URL_LIVESTOCK_RULE,
    "13. 가축전염성질병의 병원체를 퍼뜨릴 우려가 있는 것으로서 검역본부장이 정하여 고시하는 "
    "사료ㆍ사료원료ㆍ기구ㆍ건초ㆍ깔짚 그 밖에 이에 준하는 물건",
)
B_LIVESTOCK_32 = _basis(
    LIVESTOCK_NAME_KO, "제32조제1항", "2026-01-23", LAW_URL_LIVESTOCK,
    "① 다음 각 호의 어느 하나에 해당하는 물건은 수입하지 못한다. … 1. 농림축산식품부장관이 "
    "지정ㆍ고시하는 수입금지지역에서 생산 또는 발송되었거나 그 지역을 거친 지정검역물 "
    "2. 동물의 전염성 질병의 병원체 3. 소해면상뇌증이 발생한 날부터 5년이 지나지 아니한 국가산 "
    "30개월령 이상 쇠고기 및 쇠고기 제품 4. 특정위험물질",
)
B_LIVESTOCK_34 = _basis(
    LIVESTOCK_NAME_KO, "제34조제1항", "2026-01-23", LAW_URL_LIVESTOCK,
    "① 지정검역물을 수입하는 자는 다음 각 호의 구분에 따라 검역증명서를 첨부하여야 한다. … "
    "1. 제2항에 따라 위생조건이 정해진 경우: 수출국의 정부기관이 동물검역기관의 장과 협의한 "
    "서식에 따라 발급한 검역증명서",
)
B_LIVESTOCK_36 = _basis(
    LIVESTOCK_NAME_KO, "제36조제1항", "2026-01-23", LAW_URL_LIVESTOCK,
    "① 지정검역물을 수입한 자는 지체 없이 농림축산식품부령으로 정하는 바에 따라 동물검역기관의 "
    "장에게 검역을 신청하고 검역관의 검역을 받아야 한다. … 여행자 휴대품으로 지정검역물을 "
    "수입하는 자는 입국 즉시 … 신고하고 검역관의 검역을 받아야 한다.",
)
B_LIVESTOCK_39 = _basis(
    LIVESTOCK_NAME_KO, "제39조제1항", "2026-01-23", LAW_URL_LIVESTOCK,
    "① 지정검역물을 우편물 또는 탁송품으로 수입하는 자는 그 우편물 또는 탁송품을 받으면 지체 "
    "없이 그 우편물 또는 탁송품을 첨부하여 그 사실을 동물검역기관의 장에게 신고하고, "
    "농림축산식품부령으로 정하는 바에 따라 검역관의 검역을 받아야 한다.",
)

# --- 고시(조문 단위가 아닌 본문 항목 인용) ---------------------------------
B_NOTICE_PETFOOD_SCOPE = _basis(
    NOTICE_PETFOOD_KO, "제3조(적용 범위)", "2025-12-12", NOTICE_PETFOOD_URL,
    "이 고시는 「동물보호법 시행규칙」 제3조에 따른 반려동물 중 개ㆍ고양이ㆍ페럿ㆍ햄스터의 "
    "사료로 「가축전염병 예방법」 제31조 및 같은 법 시행규칙 제31조에 따른 동물성 원료 성분이 "
    "함유된 사료에 대하여 적용한다.",
)
B_NOTICE_PETFOOD_RAW = _basis(
    NOTICE_PETFOOD_KO, "제5조(사용할 수 있는 동물성 원료)제3항", "2025-12-12", NOTICE_PETFOOD_URL,
    "반려동물 사료에는 별표 제1호에 따라 사용이 허용된 원료 이외에 반추동물에서 유래된 단백질이 "
    "함유되지 않아야 한다.",
)
B_NOTICE_PETFOOD_PACKING = _basis(
    NOTICE_PETFOOD_KO, "제6조(생산조건)제3항", "2025-12-12", NOTICE_PETFOOD_URL,
    "반려동물 사료는 포장지에 제품명, 제조시설의 명칭, 원료명 등이 표시되어야 한다. 벌크 형태로 "
    "수입되는 사료의 경우 제품명, 제조시설의 명칭, 원료명 등이 인쇄 또는 기재된 스티커, "
    "라벨 또는 꼬리표를 사용할 수 있으나 떨어지지 아니하게 부착하여야 한다.",
)
B_NOTICE_PETFOOD_FACILITY = _basis(
    NOTICE_PETFOOD_KO, "제7조(제조시설)제2항", "2025-12-12", NOTICE_PETFOOD_URL,
    "제조시설은 수출국 정부가 점검하여 이 고시에 적합한 제조시설을 대한민국 정부(동물검역기관)에 "
    "통보하고, 그중 대한민국 정부가 현지점검을 통해 승인한 곳이어야 한다.",
)
B_NOTICE_PETFOOD_CERT = _basis(
    NOTICE_PETFOOD_KO, "제9조(수출검역증명서 기재사항)", "2025-12-12", NOTICE_PETFOOD_URL,
    "수출국 정부 수의관은 반려동물 사료 수출 선적 전 제품명ㆍ포장 형태ㆍ중량, 동물성 원료가 "
    "유래된 축종 및 원산지, 제조시설의 명칭ㆍ주소ㆍ등록번호, 선박명 또는 항공기 편명, 수출자ㆍ"
    "수입자, 컨테이너 번호 및 봉인 번호 등을 기재한 수출검역증명서를 발급하여야 한다.",
)
B_NOTICE_FEED_ANIMAL_SCOPE = _basis(
    NOTICE_FEED_STANDARD_KO, "제3조제2호(그 밖에 동물의 범위)", "2024-04-01", NOTICE_FEED_STANDARD_URL,
    "「사료관리법」 제2조제1호의 \"그 밖에 농림축산식품부장관이 정하여 고시하는 동물ㆍ어류 등\""
    "에는 애완용 동물(반려동물), 즉 「동물보호법 시행규칙」에 따른 반려의 목적으로 사육하는 "
    "동물(개ㆍ고양이ㆍ토끼ㆍ페럿ㆍ기니피그ㆍ햄스터) 등이 포함된다.",
)
B_NOTICE_FEED_SCOPE_LIMIT = _basis(
    NOTICE_FEED_STANDARD_KO, "제5조의2제1항", "2024-04-01", NOTICE_FEED_STANDARD_URL,
    "「사료관리법」 제14조에 따라 단미사료ㆍ보조사료의 범위에 해당하지 않는 물질은 사료로 "
    "제조ㆍ수입 또는 판매ㆍ공급하거나 사료의 원료로 사용하여서는 아니 된다.",
)
B_NOTICE_FEED_HAZARD = _basis(
    NOTICE_FEED_STANDARD_KO, "제11조제1항", "2024-04-01", NOTICE_FEED_STANDARD_URL,
    "「사료관리법」 제14조제1항제1호에 따른 사료 내 주요 유해물질의 범위 및 허용기준은 별표 16과 "
    "같다.",
)
B_NOTICE_FEED_BSE = _basis(
    NOTICE_FEED_STANDARD_KO, "제11조제4항ㆍ제5항", "2024-04-01", NOTICE_FEED_STANDARD_URL,
    "소해면상뇌증 등과 관련이 되는 소ㆍ사슴ㆍ양 등 반추동물, 조류인플루엔자와 관련이 되는 "
    "가금류에게는 사료로 사용하는 것을 금지한 동물등의 부산물ㆍ남은 음식물 등을 사용하여서는 "
    "아니 된다.",
)


# ---------------------------------------------------------------------------
# 2. 품목·동물·목적 분류
# ---------------------------------------------------------------------------
PRODUCT_TYPES: Dict[str, Dict[str, str]] = {
    "feed": {"label_ko": "사료(배합사료·단미사료)", "note_ko": "주식으로 급여하는 완제품 사료."},
    "treat": {"label_ko": "간식·트릿(동결건조·육포 등)", "note_ko": "간식도 사료관리법상 사료다."},
    "supplement": {"label_ko": "보조사료·영양제", "note_ko": "사료의 효용을 높이려고 첨가하는 것. 동물용의약품과 구분이 갈린다."},
    "raw_material": {"label_ko": "사료 원료(단미사료)", "note_ko": "배합사료의 원료로 쓰는 물질."},
    "unknown": {"label_ko": "미분류", "note_ko": "품목 유형을 알려주면 확인 항목이 좁혀진다."},
}

TYPE_ALIASES: Dict[str, str] = {
    "feed": "feed", "사료": "feed", "배합사료": "feed", "펫푸드": "feed", "petfood": "feed",
    "키블": "feed", "주식": "feed",
    "treat": "treat", "간식": "treat", "트릿": "treat", "껌": "treat", "동결건조": "treat",
    "육포": "treat", "snack": "treat",
    "supplement": "supplement", "영양제": "supplement", "보조사료": "supplement",
    "유산균": "supplement", "관절": "supplement", "오메가": "supplement",
    "raw_material": "raw_material", "단미사료": "raw_material", "원료": "raw_material",
    "unknown": "unknown",
}

ANIMALS: Dict[str, Dict[str, str]] = {
    "dog": {"label_ko": "개", "note_ko": "「사료 등의 기준 및 규격」이 반려동물로 포함한다."},
    "cat": {"label_ko": "고양이", "note_ko": "「사료 등의 기준 및 규격」이 반려동물로 포함한다."},
    "other": {"label_ko": "기타 반려동물(토끼·페럿·햄스터 등)", "note_ko": "수입위생조건 적용 대상은 개·고양이·페럿·햄스터다."},
    "unknown": {"label_ko": "미확인", "note_ko": "동물을 알려주면 검역 대상 여부가 좁혀진다."},
}

PURPOSES = {"resale": "판매·영업 목적", "self_use": "자가소비(직구·휴대)", "unknown": "미확인"}
CHANNELS = {
    "direct": "해외직구(직접 구매)", "agency": "구매대행", "carry": "휴대 반입",
    "unknown": "미확인",
}

PETFOOD_QUARANTINE_ANIMALS = ("dog", "cat", "other")  # 고시 대상: 개·고양이·페럿·햄스터


def normalize_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return TYPE_ALIASES.get(raw, "unknown")


def normalize_animal(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "dog": "dog", "개": "dog", "강아지": "dog", "반려견": "dog", "퍼피": "dog", "puppy": "dog",
        "cat": "cat", "고양이": "cat", "반려묘": "cat", "냥이": "cat", "캣": "cat", "cat ": "cat",
        "other": "other", "토끼": "other", "페럿": "other", "햄스터": "other", "기니피그": "other",
        "unknown": "unknown",
    }
    return aliases.get(raw, "unknown")


def normalize_purpose(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("resale", "sell", "sale", "판매", "영업"):
        return "resale"
    if raw in ("self_use", "selfuse", "personal", "자가소비", "자가사용", "직구"):
        return "self_use"
    return "unknown"


def normalize_channel(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("direct", "직구", "해외직구", "직접구매"):
        return "direct"
    if raw in ("agency", "구매대행", "배송대행"):
        return "agency"
    if raw in ("carry", "휴대", "휴대반입", "여행자"):
        return "carry"
    return "unknown"


def _yes_no(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("yes", "y", "true", "1", "예", "있음", "포함"):
        return "yes"
    if raw in ("no", "n", "false", "0", "아니오", "없음", "미포함"):
        return "no"
    return "unknown"


# ---------------------------------------------------------------------------
# 3. 확인 항목
# ---------------------------------------------------------------------------
# 필드 설명
# - check_id: 입력 측 확인 결과 키(checks 사전의 키)
# - purposes: 적용 목적(없으면 전체)
# - types: 적용 품목 유형(없으면 전체)
# - requires_animal_origin: "yes" 면 동물성 원료 포함일 때만 적용
# - risk: high = 위반 시 제조ㆍ수입ㆍ판매 금지ㆍ등록취소로 이어지는 의무,
#         caution = 근거ㆍ표시 방식에 따라 갈리는 항목
# - basis: 검증된 조문 상수
FEED_CHECKS: List[Dict[str, Any]] = [
    {
        "rule_id": "FE-01",
        "check_id": "ingredient_registration",
        "name_ko": "사료 성분등록",
        "axis_ko": "등록·신고",
        "risk": "high",
        "purposes": ["resale"],
        "why_ko": (
            "사료를 수입해 판매하려는 수입업자는 제조 또는 수입하려는 사료의 종류ㆍ성분 및 "
            "성분량을 시ㆍ도지사에게 성분등록해야 합니다. 성분등록 없이 수입한 사료는 판매할 수 "
            "없고, 등록 없이 수입하면 등록취소ㆍ영업정지 사유가 됩니다."
        ),
        "action_ko": (
            "사료성분등록신청서에 원료 명칭, 원료배합비율표, 제조공정 설명서를 붙여 관할 "
            "시ㆍ도지사에게 등록하고 사료성분등록증을 받으세요. 등록 대상이 아닌 사료인지도 "
            "「사료 등의 기준 및 규격」 별표 14에서 확인해야 합니다."
        ),
        "tags": ["FEED_INGREDIENT_REGISTRATION"],
        "basis": [B_FEED_12_REGISTRATION, B_FEED_RULE_12, B_NOTICE_FEED_ANIMAL_SCOPE],
    },
    {
        "rule_id": "FE-02",
        "check_id": "import_declaration",
        "name_ko": "사료 수입신고와 통관 전 검정",
        "axis_ko": "등록·신고",
        "risk": "high",
        "purposes": ["resale"],
        "why_ko": (
            "수입업자가 사료를 수입하려면 통관 전까지 사료수입신고를 하고, 필요하면 통관절차 "
            "완료 전에 검정을 받아야 합니다. 신고 없이 수입한 사료는 판매할 수 없습니다. "
            "세관장확인도 사료수입신고필증을 사후확인으로 요구합니다."
        ),
        "action_ko": (
            "사료수입신고서에 사료성분등록증 사본, 한글 표시 포장지(또는 한글 설명서), 상업송장을 "
            "붙여 신고단체(한국사료협회ㆍ한국단미사료협회 등)에 제출하고 사료수입신고필증을 "
            "받으세요. HS 2309(개ㆍ고양이 사료)로 세관장확인 요건을 함께 조회하세요."
        ),
        "tags": ["FEED_IMPORT_DECLARATION"],
        "basis": [B_FEED_19_DECLARATION, B_FEED_RULE_20, B_FEED_14_UNREGISTERED],
    },
    {
        "rule_id": "FE-03",
        "check_id": "korean_label",
        "name_ko": "용기·포장 표시사항(한글 표시)",
        "axis_ko": "표시",
        "risk": "high",
        "purposes": ["resale"],
        "why_ko": (
            "사료를 판매하려면 용기나 포장에 성분등록 사항, 유통기한, 사용상 주의사항 등 "
            "시행규칙 별표 4의 사항을 표시해야 합니다. 수입 사료는 한글로 표시된 포장지나 "
            "스티커 또는 한글 설명서를 수입신고 때 함께 내야 합니다."
        ),
        "action_ko": (
            "별표 4의 표시사항(성분등록번호, 명칭·형태, 등록성분량, 원료명, 용도, 실제 중량, "
            "제조·수입 연월일과 유통기간, 제조·수입업자 상호·주소·전화번호 등)을 한글로 갖추고, "
            "반추동물 유래 원료가 있으면 '반추가축에게 먹이지 마십시오'를 함께 표시하세요."
        ),
        "tags": ["FEED_LABELING"],
        "basis": [B_FEED_13_LABEL, B_FEED_RULE_14, B_NOTICE_PETFOOD_PACKING],
    },
    {
        "rule_id": "FE-04",
        "check_id": "label_truth",
        "name_ko": "표시 거짓·과장 금지",
        "axis_ko": "표시",
        "risk": "caution",
        "purposes": ["resale"],
        "why_ko": (
            "성분ㆍ원료ㆍ급여량 표시를 거짓으로 하거나 과장하면 판매할 수 없습니다. "
            "'인체에도 좋은 원료', '치료 효과' 같은 표현은 사료 표시 범위를 넘습니다."
        ),
        "action_ko": (
            "표시 문구는 성분등록증과 실제 배합 내용에 맞추고, 질병 치료ㆍ예방 효능 표현은 빼세요. "
            "반려동물의 건강 상태별 급여량은 수의사 상담 안내로 대체하세요."
        ),
        "tags": ["FEED_LABELING"],
        "basis": [B_FEED_13_FALSE_LABEL],
    },
    {
        "rule_id": "FE-05",
        "check_id": "hazard_standard",
        "name_ko": "유해물질·동물용의약품 잔류 기준과 유통기한",
        "axis_ko": "유해·금지",
        "risk": "high",
        "purposes": ["resale", "self_use"],
        "why_ko": (
            "유해물질이 허용기준 이상이거나 동물용의약품이 허용기준 이상 잔류한 사료, 유통기한이 "
            "지난 사료는 수입ㆍ판매할 수 없습니다. 허용기준은 「사료 등의 기준 및 규격」 별표 16ㆍ"
            "별표 17이 정합니다."
        ),
        "action_ko": (
            "수입 전 제조사의 성적서와 유통기간 설정 근거를 받고, 필요하면 사료시험검사기관의 "
            "검정증명서를 확보하세요. 유통기한이 지난 재고는 판매 목적 보관ㆍ진열 자체가 "
            "금지됩니다."
        ),
        "tags": ["FEED_HAZARD_STANDARD"],
        "basis": [B_FEED_14_HAZARD, B_FEED_14_EXPIRY, B_NOTICE_FEED_HAZARD],
    },
    {
        "rule_id": "FE-06",
        "check_id": "animal_quarantine",
        "name_ko": "동물검역(지정검역물)·검역증명서",
        "axis_ko": "동물검역",
        "risk": "high",
        "requires_animal_origin": "yes",
        "why_ko": (
            "가축전염병의 병원체를 퍼뜨릴 우려가 있는 사료ㆍ사료원료는 지정검역물입니다. "
            "동물성 원료가 들어간 사료를 수입하면 수출국 정부의 검역증명서를 첨부하고 수입검역을 "
            "받아야 하며, 우편물ㆍ탁송품(직구 포함)도 받은 뒤 지체 없이 신고하고 검역을 받아야 "
            "합니다."
        ),
        "action_ko": (
            "수출국 검역증명서를 준비하고, 도착 후 농림축산검역본부(동물검역기관)에 수입검역을 "
            "신청하세요. 수입금지지역산 원료인지, 특정위험물질이 섞였는지도 함께 확인합니다."
        ),
        "tags": ["ANIMAL_PRODUCT_QUARANTINE"],
        "basis": [B_LIVESTOCK_31, B_LIVESTOCK_RULE_31, B_LIVESTOCK_34,
                  B_LIVESTOCK_36, B_LIVESTOCK_39, B_LIVESTOCK_32],
    },
    {
        "rule_id": "FE-07",
        "check_id": "petfood_quarantine_condition",
        "name_ko": "반려동물 사료 수입위생조건(제조시설 승인·수출검역증명서)",
        "axis_ko": "동물검역",
        "risk": "high",
        "animals": ["dog", "cat", "other"],
        "requires_animal_origin": "yes",
        "why_ko": (
            "동물성 원료가 들어간 개ㆍ고양이ㆍ페럿ㆍ햄스터 사료는 「반려동물 사료 수입위생조건」"
            "이 적용됩니다. 원료는 고시 별표에서 허용된 것이어야 하고, 반추동물 유래 단백질이 "
            "들어가서는 안 되며, 제조시설은 대한민국 정부가 승인한 곳이어야 합니다."
        ),
        "action_ko": (
            "제조시설이 우리 정부 승인 목록에 있는지, 수출검역증명서에 축종ㆍ원산지ㆍ제조시설 "
            "등록번호ㆍ컨테이너ㆍ봉인 번호가 기재되는지 확인하세요. 반추동물 유래 단백질이 있으면 "
            "수입 전에 원료를 바꿔야 합니다."
        ),
        "tags": ["PET_FOOD_QUARANTINE", "ANIMAL_PRODUCT_QUARANTINE"],
        "basis": [B_NOTICE_PETFOOD_SCOPE, B_NOTICE_PETFOOD_RAW,
                  B_NOTICE_PETFOOD_FACILITY, B_NOTICE_PETFOOD_CERT],
    },
    {
        "rule_id": "FE-08",
        "check_id": "self_quality_inspection",
        "name_ko": "자가품질검사(시설·기록 2년)",
        "axis_ko": "등록·신고",
        "risk": "caution",
        "purposes": ["resale"],
        "why_ko": (
            "수입업자는 사료공정 적합 여부, 성분등록 사항과의 차이, 유해물질ㆍ동물용의약품 잔류 "
            "여부를 검사해야 하고, 검사 기록서를 2년간 보관해야 합니다. 검사를 하지 않으면 "
            "영업정지 사유가 됩니다."
        ),
        "action_ko": (
            "자가품질검사 시설을 갖추거나 다른 수입업자와 공동으로 갖추고, 사료시험검사기관에 "
            "검정을 의뢰해 검정증명서를 받아 두세요. 기록은 2년간 남깁니다."
        ),
        "tags": ["FEED_SELF_QUALITY_INSPECTION"],
        "basis": [B_FEED_20_SELF_INSPECTION],
    },
    {
        "rule_id": "FE-09",
        "check_id": "purpose_restriction",
        "name_ko": "수입 사료의 용도 외 판매 금지",
        "axis_ko": "유통",
        "risk": "caution",
        "purposes": ["resale"],
        "why_ko": (
            "수입한 사료는 다른 사료의 원료용, 동물의 먹이, 그 밖에 농림축산식품부령으로 정하는 "
            "용도 외로 판매할 수 없습니다. 사료로 수입한 것을 사람이 먹는 식품처럼 되파는 것도 "
            "여기에 걸립니다."
        ),
        "action_ko": (
            "수입신고한 용도와 판매 채널을 일치시키고, 사료가 아닌 용도로 전환하지 마세요. "
            "용도 전환이 필요하면 관할 기관에 먼저 확인합니다."
        ),
        "tags": ["FEED_IMPORT_DECLARATION"],
        "basis": [B_FEED_7_PURPOSE],
    },
    {
        "rule_id": "FE-10",
        "check_id": "import_recommendation",
        "name_ko": "수입추천(양허세율 적용 물량)",
        "axis_ko": "등록·신고",
        "risk": "caution",
        "purposes": ["resale"],
        "why_ko": (
            "WTO 양허표상 시장접근물량에 적용되는 양허세율로 사료를 수입하려면 농림축산식품부장관의 "
            "추천을 받아야 합니다. 추천이 필요한 경우는 양허세율이 적용되는 물량으로 한정됩니다."
        ),
        "action_ko": (
            "적용 세율이 양허세율(TRQ)인지 관세율표에서 확인하고, 해당되면 사료관련 단체를 통해 "
            "수입추천을 신청하세요."
        ),
        "tags": ["FEED_IMPORT_DECLARATION", "CUSTOMS_CHECKPOINT"],
        "basis": [B_FEED_6_RECOMMEND],
    },
    {
        "rule_id": "FE-11",
        "check_id": "manufacturer_registration",
        "name_ko": "사료 제조업 등록(제조·재포장·OEM)",
        "axis_ko": "등록·신고",
        "risk": "high",
        "needs_manufacture": True,
        "why_ko": (
            "사료를 제조(혼합ㆍ배합ㆍ가공, 단순 재포장 포함)해 판매ㆍ공급하려면 시ㆍ도지사에게 "
            "제조업 등록을 해야 합니다. 수입업과 달리 제조업은 등록제입니다."
        ),
        "action_ko": (
            "위탁 제조(OEM)든 국내 재포장이든 제조업 등록 대상인지 관할 시ㆍ도에 확인하고, "
            "시설기준을 갖춘 뒤 등록하세요. 단순 보관ㆍ배송만 하면 수입업 지위로 봅니다."
        ),
        "tags": ["FEED_BUSINESS_REGISTRATION"],
        "basis": [B_FEED_8_MANUFACTURE, B_FEED_2_IMPORTER],
    },
    {
        "rule_id": "FE-12",
        "check_id": "drug_boundary",
        "name_ko": "반려동물 영양제: 사료(보조사료)인가 동물용의약품인가",
        "axis_ko": "품목 구분",
        "risk": "caution",
        "types": ["supplement"],
        "why_ko": (
            "사료관리법의 '사료'는 동물용의약으로서 섭취하는 것을 제외합니다. 그래서 같은 영양제도 "
            "성분과 표방 목적에 따라 보조사료(사료)와 동물용의약품으로 갈리고, 어느 쪽인지에 따라 "
            "허가ㆍ등록 절차가 완전히 달라집니다. 보조사료 범위에 없는 물질은 사료로 수입ㆍ판매할 "
            "수 없습니다."
        ),
        "action_ko": (
            "성분이 「사료 등의 기준 및 규격」 별표 2(보조사료) 또는 별표 1(단미사료)에 있는지 "
            "확인하고, 질병의 치료ㆍ예방 효능을 표방하면 동물용의약품 소관인지 농림축산검역본부ㆍ"
            "식약처에 문의하세요. 범위에 없으면 사료로 수입할 수 없습니다."
        ),
        "tags": ["FEED_INGREDIENT_REGISTRATION", "FEED_HAZARD_STANDARD"],
        "basis": [B_FEED_2_DEF, B_NOTICE_FEED_SCOPE_LIMIT, B_NOTICE_FEED_ANIMAL_SCOPE],
    },
    {
        "rule_id": "FE-13",
        "check_id": "bse_control",
        "name_ko": "특정 동물성사료(반추동물 유래) 사용·교차오염 금지",
        "axis_ko": "유해·금지",
        "risk": "high",
        "requires_animal_origin": "yes",
        "types": ["feed", "treat", "raw_material"],
        "why_ko": (
            "소해면상뇌증(BSE) 등과 관련된 반추동물ㆍ가금류의 부산물과 남은 음식물은 사료로 "
            "사용할 수 없습니다. 반려동물 사료에도 반추동물 유래 단백질이 함유되지 않아야 합니다."
        ),
        "action_ko": (
            "원료의 축종과 부위를 서면으로 확인하고(소ㆍ사슴ㆍ양 유래 단백질 여부), 제조시설이 "
            "반추동물 유래 단백질 혼입 방지 관리를 하는지 확인하세요. 확인되지 않으면 수입하지 "
            "않는 쪽이 안전합니다."
        ),
        "tags": ["FEED_HAZARD_STANDARD", "PET_FOOD_QUARANTINE"],
        "basis": [B_FEED_14_SPECIAL_RISK, B_NOTICE_FEED_BSE, B_NOTICE_PETFOOD_RAW],
    },
]

CHECK_INDEX: Dict[str, Dict[str, Any]] = {row["check_id"]: row for row in FEED_CHECKS}

CHECK_LABELS_KO: Dict[str, str] = {row["check_id"]: row["name_ko"] for row in FEED_CHECKS}


# ---------------------------------------------------------------------------
# 4. 질의 분류(자연어 → 품목·동물·목적·원료)
# ---------------------------------------------------------------------------
_FEED_STRONG = (
    "강아지 사료", "고양이 사료", "반려견", "반려묘", "펫푸드", "petfood", "강아지 간식",
    "고양이 간식", "캣트릿", "애견", "단미사료", "보조사료", "배합사료", "사료관리법",
    "동결건조 간식", "펫 영양제", "반려동물 영양제", "개 사료", "고양이 모래", "사료 수입",
    "사료 직구", "펫푸드 수입",
)
_FEED_WEAK = ("사료", "간식", "트릿", "육포", "껌", "키블", "영양제")
_EXCLUDE = (r"참고\s*사료", r"역사\s*사료", r"통계\s*사료", r"사료(가|로)\s*되")

_TYPE_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("raw_material", ("단미사료", "사료 원료", "사료원료", "원료로 수입")),
    ("supplement", ("보조사료", "영양제", "유산균", "관절", "오메가", "비타민", "프로바이오틱스")),
    ("treat", ("간식", "트릿", "캣트릿", "육포", "껌", "동결건조")),
    ("feed", ("사료", "펫푸드", "키블", "주식")),
)

_ANIMAL_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("cat", ("고양이", "냥이", "반려묘", "캣", "cat")),
    ("dog", ("강아지", "반려견", "댕댕이", "퍼피", "dog", "puppy")),
    ("other", ("페럿", "햄스터", "기니피그", "토끼")),
)

_ANIMAL_ORIGIN_YES = (
    "동물성", "육포", "닭가슴살", "닭고기", "소고기", "돼지", "오리", "연어", "참치", "양고기",
    "곱창", "내장", "우유", "치즈", "계란", "어분", "육분", "육골분", "수산물", "생선", "고기",
)
_ANIMAL_ORIGIN_NO = ("식물성", "비건", "채식", "곡물", "현미", "감자", "고구마", "두부", "곤충")


def detect(query: str) -> Dict[str, Any]:
    """문장에서 반려동물 사료 여부와 품목·동물·원료 단서를 뽑는다(추측은 '미확인')."""
    text = str(query or "")
    norm = " ".join(text.lower().split())
    signals = [signal for signal in _FEED_STRONG if signal in norm]
    weak = [signal for signal in _FEED_WEAK if signal in norm]
    excluded = any(re.search(pattern, norm) for pattern in _EXCLUDE)
    has_animal = any(word in norm for _, words in _ANIMAL_PATTERNS for word in words)
    # '사료'는 '참고 사료'처럼 다른 뜻으로도 쓰이므로, 동물이 나오거나 수입·제조 맥락이 있을 때만
    # 사료 검수 대상으로 본다.
    feed_context = any(word in norm for word in
                       ("수입", "제조", "직구", "통관", "판매", "원료", "oem", "반입", "수출"))
    # '사료'만 수입ㆍ제조 맥락으로 보완한다(영양제ㆍ간식은 동물이 있어야 반려동물 것으로 본다).
    is_feed = bool(signals) or (bool(weak) and not excluded
                                and (has_animal or ("사료" in norm and feed_context)))
    if excluded and not signals:
        is_feed = False

    product_type = "unknown"
    for candidate, words in _TYPE_PATTERNS:
        if any(word in norm for word in words):
            product_type = candidate
            break

    animal = "unknown"
    for candidate, words in _ANIMAL_PATTERNS:
        if any(word in norm for word in words):
            animal = candidate
            break

    if any(word in norm for word in _ANIMAL_ORIGIN_NO) and not any(
            word in norm for word in _ANIMAL_ORIGIN_YES):
        animal_origin = "no"
    elif any(word in norm for word in _ANIMAL_ORIGIN_YES):
        animal_origin = "yes"
    else:
        animal_origin = "unknown"

    purpose = "unknown"
    if any(word in norm for word in ("판매", "되팔", "유통", "사업", "팔려")):
        purpose = "resale"
    elif any(word in norm for word in ("직구", "자가소비", "자가사용", "키우는", "우리 강아지",
                                      "우리 고양이", "내 반려")):
        purpose = "self_use"

    channel = "unknown"
    if "구매대행" in norm or "배송대행" in norm:
        channel = "agency"
    elif "휴대" in norm or "들고" in norm:
        channel = "carry"
    elif "직구" in norm:
        channel = "direct"

    return {
        "is_feed": is_feed,
        "product_type": product_type,
        "animal": animal,
        "animal_origin": animal_origin,
        "purpose": purpose,
        "channel": channel,
        "signals": signals + [word for word in weak if word not in signals],
        "manufacture": any(word in norm for word in ("제조", "가공", "재포장", "oem", "위탁생산")),
    }


# ---------------------------------------------------------------------------
# 5. 판정
# ---------------------------------------------------------------------------
SEVERITY = {"check_likely": 3, "info_needed": 2, "low_risk": 1}


def _applicable(check: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    purposes = check.get("purposes")
    if purposes and ctx["purpose"] not in purposes and ctx["purpose"] != "unknown":
        return False
    types = check.get("types")
    if types and ctx["product_type"] not in types and ctx["product_type"] != "unknown":
        return False
    animals = check.get("animals")
    if animals and ctx["animal"] not in animals and ctx["animal"] != "unknown":
        return False
    if check.get("requires_animal_origin") == "yes" and ctx["animal_origin"] == "no":
        return False
    if check.get("needs_manufacture") and not ctx.get("manufacture"):
        return False
    return True


def _status(check: Dict[str, Any], checks: Dict[str, Any]) -> str:
    key = check["check_id"]
    if key not in checks or checks.get(key) in (None, "", "unknown"):
        return "not_checked"
    return "present" if _yes_no(checks.get(key)) == "yes" else "missing"


def _finding(check: Dict[str, Any], status: str) -> Dict[str, Any]:
    risk = str(check["risk"])
    if status == "present":
        risk = "caution"
    return {
        "rule_id": check["rule_id"],
        "check_id": check["check_id"],
        "name_ko": check["name_ko"],
        "axis_ko": check["axis_ko"],
        "risk": risk,
        "risk_label_ko": "높음" if risk == "high" else "주의",
        "status": status,
        "status_label_ko": {"present": "확인됨", "missing": "갖추지 못함",
                            "not_checked": "확인 필요"}[status],
        "why_ko": check["why_ko"],
        "safer_ko": check["action_ko"],
        "regulation_tags": list(check["tags"]),
        "legal_basis": [dict(row) for row in check["basis"]],
    }


def assess(*, query: str = "", product_type: Any = "", purpose: Any = "",
           animal: Any = "", animal_origin: Any = "", channel: Any = "",
           checks: Optional[Dict[str, Any]] = None, manufacture: Any = None,
           limit: int = 13) -> Dict[str, Any]:
    """반려동물 사료·간식·영양제 수입의 확인 항목을 사실관계 기준으로 정리한다.

    - `checks` 에 확인 결과를 주면(present/missing) 항목별로 '갖추지 못함'을 짚는다.
      주지 않은 항목은 '확인 필요'로 남기고, 결과를 단정하지 않는다.
    """
    detected = detect(query)
    ctx = {
        "product_type": normalize_type(product_type) if product_type else detected["product_type"],
        "purpose": normalize_purpose(purpose) if purpose else detected["purpose"],
        "animal": normalize_animal(animal) if animal else detected["animal"],
        "animal_origin": (_yes_no(animal_origin) if animal_origin else detected["animal_origin"]),
        "channel": normalize_channel(channel) if channel else detected["channel"],
        "manufacture": (detected["manufacture"] if manufacture in (None, "")
                        else _yes_no(manufacture) == "yes"),
    }
    supplied = dict(checks or {})
    # 품목 유형을 '직접' 준 경우에만 사료로 본다. 문장에서 추론한 유형(예: '영양제')만으로
    # 사료 검수를 돌리면 사람용 영양제까지 반려동물 사료로 오인한다.
    explicit_type = bool(str(product_type or "").strip()) and ctx["product_type"] != "unknown"
    if not (detected["is_feed"] or explicit_type):
        return {
            "input": {
                "query_chars": len(str(query or "")),
                "product_type": ctx["product_type"],
                "product_type_label_ko": PRODUCT_TYPES[ctx["product_type"]]["label_ko"],
                "purpose": ctx["purpose"],
                "purpose_label_ko": PURPOSES[ctx["purpose"]],
                "animal": ctx["animal"],
                "animal_label_ko": ANIMALS[ctx["animal"]]["label_ko"],
                "animal_origin": ctx["animal_origin"],
                "channel": ctx["channel"],
                "channel_label_ko": CHANNELS[ctx["channel"]],
                "manufacture": ctx["manufacture"],
                "detected_signals": detected["signals"],
            },
            "is_feed": False,
            "verdict": "info_needed",
            "verdict_label_ko": "추가 정보 필요",
            "verdict_note_ko": (
                "입력에서 반려동물 사료·간식·영양제 신호를 찾지 못했습니다. 품목 유형"
                "(사료·간식·보조사료·단미사료)을 지정하면 확인 항목을 정리합니다."
            ),
            "check_count": 0,
            "present_count": 0,
            "missing_count": 0,
            "not_checked_count": 0,
            "risk_summary_ko": "해당 없음",
            "findings": [],
            "checklist": [],
            "regulation_tags": [],
            "next_steps_ko": ["품목명ㆍ품목 유형ㆍ동물ㆍ수입 목적을 함께 입력해 다시 확인"],
            "basis_sources": [
                {"name_ko": FEED_NAME_KO, "authority_ko": AUTHORITY_KO, "url": LAW_URL_FEED,
                 "note_ko": "성분등록ㆍ수입신고ㆍ표시ㆍ유해사료ㆍ제조업 등록의 근거 법률."},
                {"name_ko": LIVESTOCK_NAME_KO, "authority_ko": AUTHORITY_QUARANTINE_KO,
                 "url": LAW_URL_LIVESTOCK,
                 "note_ko": "지정검역물ㆍ검역증명서ㆍ수입검역ㆍ우편물 신고."},
            ],
            "coverage_ko": (
                "이 결과는 반려동물 사료·간식 수입 검수 대상이 아닌 입력에 대한 안내입니다."
            ),
            "checked_on": VERIFIED_ON,
            "authority_ko": AUTHORITY_KO,
        }
    applicable = [row for row in FEED_CHECKS if _applicable(row, ctx)]

    rows: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    for check in applicable:
        status = _status(check, supplied)
        rows.append({
            "check_id": check["check_id"],
            "rule_id": check["rule_id"],
            "name_ko": check["name_ko"],
            "axis_ko": check["axis_ko"],
            "risk": check["risk"],
            "status": status,
            "status_label_ko": {"present": "확인됨", "missing": "갖추지 못함",
                                "not_checked": "확인 필요"}[status],
            "safer_ko": check["action_ko"],
            "legal_basis": [dict(row) for row in check["basis"]],
        })
        if status != "present":
            findings.append(_finding(check, status))

    findings.sort(key=lambda row: (0 if row["status"] == "missing" else 1,
                                   0 if row["risk"] == "high" else 1, row["rule_id"]))
    findings = findings[:max(1, int(limit))]

    missing_high = sum(1 for row in rows if row["status"] == "missing" and row["risk"] == "high")
    missing = sum(1 for row in rows if row["status"] == "missing")
    not_checked = sum(1 for row in rows if row["status"] == "not_checked")
    present = sum(1 for row in rows if row["status"] == "present")

    if missing_high:
        verdict = "check_likely"
        note = ("갖추지 못했다고 답한 항목 중 판매 자체를 막는 의무가 있습니다. "
                "통관 전에 먼저 해결해야 합니다.")
    elif missing:
        verdict = "info_needed"
        note = "갖추지 못한 항목이 있습니다. 확인 후 진행하세요."
    elif ctx["purpose"] == "resale":
        verdict = "check_likely"
        note = ("판매 목적이면 성분등록ㆍ수입신고ㆍ표시 의무가 법으로 정해져 있습니다. "
                "확인 결과를 넣으면 갖춘 항목과 빠진 항목을 나눠 볼 수 있습니다.")
    elif not_checked:
        verdict = "info_needed"
        note = "확인하지 못한 항목이 남아 있습니다. 품목ㆍ원료ㆍ경로를 알려주면 좁혀집니다."
    else:
        verdict = "low_risk"
        note = "입력한 범위에서 확인 항목이 모두 갖추어진 것으로 답했습니다."

    tags: List[str] = []
    for row in rows:
        for tag in CHECK_INDEX[row["check_id"]]["tags"]:
            if tag not in tags:
                tags.append(tag)

    return {
        "input": {
            "query_chars": len(str(query or "")),
            "product_type": ctx["product_type"],
            "product_type_label_ko": PRODUCT_TYPES[ctx["product_type"]]["label_ko"],
            "purpose": ctx["purpose"],
            "purpose_label_ko": PURPOSES[ctx["purpose"]],
            "animal": ctx["animal"],
            "animal_label_ko": ANIMALS[ctx["animal"]]["label_ko"],
            "animal_origin": ctx["animal_origin"],
            "channel": ctx["channel"],
            "channel_label_ko": CHANNELS[ctx["channel"]],
            "manufacture": ctx["manufacture"],
            "detected_signals": detected["signals"],
        },
        "is_feed": bool(detected["is_feed"] or explicit_type),
        "verdict": verdict,
        "verdict_label_ko": {"check_likely": "확인 가능성 높음",
                             "info_needed": "추가 정보 필요",
                             "low_risk": "현재 정보상 가능성 낮음"}[verdict],
        "verdict_note_ko": note,
        "check_count": len(rows),
        "present_count": present,
        "missing_count": missing,
        "not_checked_count": not_checked,
        "risk_summary_ko": f"갖추지 못함 {missing}건 · 확인 필요 {not_checked}건",
        "findings": findings,
        "checklist": rows,
        "regulation_tags": tags,
        "next_steps_ko": _next_steps(ctx, rows),
        "basis_sources": [
            {"name_ko": FEED_NAME_KO, "authority_ko": AUTHORITY_KO, "url": LAW_URL_FEED,
             "note_ko": "성분등록ㆍ수입신고ㆍ표시ㆍ유해사료ㆍ제조업 등록의 근거 법률. 시행 2024-04-25 판본."},
            {"name_ko": FEED_RULE_NAME_KO, "authority_ko": AUTHORITY_KO, "url": LAW_URL_FEED_RULE,
             "note_ko": "성분등록 서류ㆍ표시사항(별표 4)ㆍ수입신고 첨부서류. 시행 2024-12-05 판본."},
            {"name_ko": LIVESTOCK_NAME_KO, "authority_ko": AUTHORITY_QUARANTINE_KO,
             "url": LAW_URL_LIVESTOCK,
             "note_ko": "지정검역물ㆍ검역증명서ㆍ수입검역ㆍ우편물 신고. 시행 2026-01-23 판본."},
            {"name_ko": NOTICE_PETFOOD_KO, "authority_ko": AUTHORITY_QUARANTINE_KO,
             "url": NOTICE_PETFOOD_URL,
             "note_ko": "동물성 원료가 든 반려동물 사료의 원료ㆍ제조시설ㆍ검역증명서 조건. 고시 제2025-124호."},
            {"name_ko": NOTICE_FEED_STANDARD_KO, "authority_ko": AUTHORITY_KO,
             "url": NOTICE_FEED_STANDARD_URL,
             "note_ko": "반려동물의 범위ㆍ단미/보조사료 범위ㆍ유해물질 허용기준. 고시 제2024-27호."},
        ],
        "coverage_ko": (
            "입력한 품목ㆍ동물ㆍ목적ㆍ동물성 원료 여부와 확인 결과를 사료관리법ㆍ시행규칙ㆍ"
            "가축전염병 예방법ㆍ고시(반려동물 사료 수입위생조건, 사료 등의 기준 및 규격)에 "
            "대조한 결과입니다. 실제 원료의 축종ㆍ가공도, 제조시설 승인 여부, 검역 결과는 보지 "
            "못하므로 최종 판단은 농림축산식품부ㆍ농림축산검역본부 확인을 따릅니다."
        ),
        "checked_on": VERIFIED_ON,
        "authority_ko": AUTHORITY_KO,
    }


def _next_steps(ctx: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> List[str]:
    """응답에 붙일 다음 행동(단정 표현 없이)."""
    steps: List[str] = []
    if ctx["purpose"] == "resale":
        steps.append("관할 시ㆍ도지사에 사료 성분등록을 신청하고 사료성분등록증을 확보")
        steps.append("통관 전 사료 수입신고(사료수입신고필증)와 검정 대상 여부 확인")
        steps.append("용기ㆍ포장에 시행규칙 별표 4 표시사항을 한글로 갖추기")
    else:
        steps.append("동물성 원료가 들어 있으면 지정검역물 해당 여부와 수입검역 절차 확인")
    if ctx["animal_origin"] in ("yes", "unknown") and ctx["animal"] in PETFOOD_QUARANTINE_ANIMALS:
        steps.append("수출국 제조시설이 우리 정부 승인 목록에 있는지, 수출검역증명서 기재사항 확인")
    if ctx["product_type"] == "supplement":
        steps.append("성분이 단미사료ㆍ보조사료 범위에 있는지, 동물용의약품 소관인지 구분")
    if ctx.get("manufacture"):
        steps.append("제조ㆍ재포장이면 사료 제조업 등록 대상인지 관할 시ㆍ도에 확인")
    if not steps:
        steps.append("품목 유형ㆍ동물ㆍ수입 목적ㆍ동물성 원료 여부를 넣어 다시 확인")
    return steps[:5]


def summarize(block: Dict[str, Any], limit: int = 3) -> List[str]:
    """응답 answer.guidance 에 넣을 문장(단정 표현 금지)."""
    lines: List[str] = []
    for finding in (block.get("findings") or [])[:limit]:
        lines.append(
            f"[{finding['status_label_ko']}] {finding['name_ko']} — {finding['safer_ko']}"
        )
    if not lines:
        lines.append(
            "반려동물 사료는 식품이 아니라 사료관리법이 적용됩니다. 성분등록ㆍ수입신고ㆍ표시와 "
            "동물검역(지정검역물) 요건을 함께 확인하세요."
        )
    return lines


def tags_for(block: Dict[str, Any]) -> List[str]:
    return list(block.get("regulation_tags") or [])


def check_ids() -> List[str]:
    return [row["check_id"] for row in FEED_CHECKS]


def rule_ids() -> List[str]:
    return [row["rule_id"] for row in FEED_CHECKS]


def meta() -> Dict[str, Any]:
    """`get_service_meta` 에 싣는 요약."""
    return {
        "checks": len(FEED_CHECKS),
        "rule_ids": rule_ids(),
        "product_types": [{"code": code, "label_ko": row["label_ko"]}
                          for code, row in PRODUCT_TYPES.items()],
        "animals": [{"code": code, "label_ko": row["label_ko"]}
                    for code, row in ANIMALS.items()],
        "authority_ko": AUTHORITY_KO,
        "quarantine_authority_ko": AUTHORITY_QUARANTINE_KO,
        "checked_on": VERIFIED_ON,
        "laws": [FEED_NAME_KO, FEED_RULE_NAME_KO, LIVESTOCK_NAME_KO,
                 LIVESTOCK_RULE_NAME_KO, NOTICE_PETFOOD_KO, NOTICE_FEED_STANDARD_KO],
        "note_ko": (
            "사료관리법에 '수입업 등록' 제도는 없습니다(제8조는 제조업 등록만 규정). 수입업자는 "
            "성분등록ㆍ수입신고ㆍ표시 의무를 지고, 동물성 원료가 있으면 동물검역이 별도로 붙습니다."
        ),
    }
