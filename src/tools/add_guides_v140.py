"""가이드 카탈로그 1.4.0 — 롱테일 질문 17종 추가(68 → 85).

카탈로그는 조문 문안을 직접 갖지 않고 `guides.py` 의 `_basis_registry` 키와 함정 코퍼스
(`traps_20.json`) 케이스 ID 만 참조한다. 이 스크립트도 같은 계약을 지키며, 참조가 실제로
해석되는지·관련 링크가 카탈로그에 있는지 먼저 검증한 뒤에 쓴다(해석되지 않는 참조가 있으면
서버가 뜨지 않으므로, 쓰기 전에 막는다).

실행: PYTHONPATH=src python3 src/tools/add_guides_v140.py
"""
from __future__ import annotations

import json
import os
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(SRC, "guides_items.json")
sys.path.insert(0, SRC)

from import_compliance import guides, pseo  # noqa: E402
from import_compliance.corpus import load_corpus  # noqa: E402
from import_compliance.standards import REGULATION_TAGS  # noqa: E402

NEW_VERSION = "1.4.0"
VERIFIED_ON = "2026-11-21"

NEW_ITEMS = [
    {
        "slug": "perfume-60ml-direct-buy",
        "question_ko": "해외직구 향수는 60mL까지 면세로 살 수 있나요?",
        "title_ko": "향수 해외직구 — 60mL 기준의 출처와 직구 면세·표시",
        "category": "통관·면세",
        "summary_ko": "향수 60mL라는 숫자는 여행자 휴대품 면세 범위에서 나온 것이고, 해외직구(특송)에는 금액 기준과 목록통관 배제 여부가 따로 적용됩니다. 어느 기준이 내 주문에 걸리는지 정리했습니다.",
        "answer_ko": "60mL는 여행자가 휴대 반입할 때 향수의 면세 범위로 안내되는 수치입니다. 해외직구(특송)에는 이 수치가 아니라 물품가격과 현지 배송비를 합친 금액 기준(150달러, 미국발 200달러)이 먼저 적용되고, 화장품은 기능성화장품 등 일부가 목록통관 배제대상물품으로 열거되어 있어 향수가 그 목록에 드는지 확인해야 합니다. 판매를 목적으로 들여오면 화장품책임판매업 등록과 한글 기재사항, 품질검사 대상 여부가 함께 걸립니다.",
        "key_points_ko": [
            "여행자 휴대품 면세 범위와 해외직구 면세 한도는 서로 다른 기준입니다.",
            "화장품은 기능성 여부에 따라 목록통관 배제 대상이 갈릴 수 있습니다.",
            "판매 목적이면 통관 요건과 화장품 표시·등록 요건을 함께 봅니다.",
        ],
        "checkpoints_ko": [
            "반입 경로가 휴대 반입인지 특송 직구인지 확인합니다.",
            "물품가격과 현지 배송비를 합산한 금액을 확인합니다.",
            "향수가 목록통관 배제대상물품에 드는지 확인합니다.",
            "판매 목적이면 화장품책임판매업 등록과 한글 기재사항을 확인합니다.",
        ],
        "cases": ["TRAP-12", "TRAP-02"],
        "basis_keys": ["labeling:B_COS_10_1"],
        "tags": ["CUSTOMS_LOW_VALUE", "COSMETICS_RESPONSIBLE_SALES", "KOREAN_LABELING"],
        "tool": "assess_import_case",
        "tool_example": {"query": "향수 수입 판매", "facts": {"purpose": "resale"}},
        "keywords": ["향수 직구", "향수 60mL", "향수 면세", "화장품 목록통관", "향수 관세"],
        "related_guides": ["duty-free-150-200", "list-clearance-excluded-items", "direct-buy-cosmetics-resale"],
        "related_items": [],
    },
    {
        "slug": "wine-liquor-direct-buy",
        "question_ko": "해외직구 와인·위스키는 150달러 이하면 세금이 없나요?",
        "title_ko": "와인·주류 해외직구 — 목록통관 배제와 세금",
        "category": "통관·면세",
        "summary_ko": "주류는 금액이 낮아도 목록통관 배제대상물품으로 열거되어 있습니다. 와인·위스키를 개인적으로 들여올 때 확인할 절차와 세금 축을 정리했습니다.",
        "answer_ko": "주류는 특송물품 목록통관 배제대상물품에 '식품류·주류·담배류'로 함께 열거되어 있어, 물품가격이 150달러 이하라도 목록통관으로 처리되지 않고 수입신고와 세금 검토가 붙습니다. 주류는 관세와 함께 주세·부가가치세 등 별도 세목이 적용되는 품목이라, 결제 전에 총부담액을 확인해야 합니다. 판매를 목적으로 하면 수입식품 영업등록과 수입신고, 한글표시사항도 함께 확인해야 합니다.",
        "key_points_ko": [
            "금액 기준보다 품목 기준이 먼저 걸립니다.",
            "주류는 관세 외 세목이 붙어 실제 부담액이 커질 수 있습니다.",
            "판매 목적이면 식품 수입 절차가 함께 필요합니다.",
        ],
        "checkpoints_ko": [
            "주문 품목이 주류(발효주·증류주·리큐르)인지 확인합니다.",
            "목록통관 배제대상물품 해당 여부를 확인합니다.",
            "관세·주세·부가세를 포함한 총부담액을 확인합니다.",
            "판매 목적이면 수입식품 영업등록과 한글표시사항을 확인합니다.",
            "판매 목적이면 주류 판매에 필요한 면허·신고를 주세법 기준으로 함께 확인합니다.",
        ],
        "cases": ["TRAP-12", "TRAP-01"],
        "basis_keys": ["labeling:B_IMPORT_15", "labeling:B_FOOD_4_1_1"],
        "tags": ["CUSTOMS_LOW_VALUE", "FOOD_IMPORT_DECLARATION", "KOREAN_LABELING"],
        "tool": "assess_import_case",
        "tool_example": {"query": "주류 수입 판매", "facts": {"purpose": "resale"}},
        "keywords": ["와인 직구", "주류 직구", "주세", "주류 목록통관", "위스키 직구"],
        "related_guides": ["duty-free-150-200", "list-clearance-excluded-items", "food-business-registration"],
        "related_items": [],
    },
    {
        "slug": "order-multiple-aggregate",
        "question_ko": "직구를 여러 건으로 나눠 주문하면 세금이 합산되나요?",
        "title_ko": "직구 금액 합산과세 — 주문을 나눠도 기준이 피해지지 않는 이유",
        "category": "통관·면세",
        "summary_ko": "같은 날 여러 건으로 나눠 주문해도 금액 기준이 그대로 적용되지 않을 수 있습니다. 합산 판단이 이뤄지는 조건과 주문 전에 확인할 점을 정리했습니다.",
        "answer_ko": "면세·목록통관 기준은 주문 건별 결제 금액이 아니라 수입하는 사람과 물품, 입항 시점을 기준으로 판단됩니다. 같은 사람이 같은 날 같은 국가에서 받는 물품은 합산해 금액 요건을 보는 경우가 있어, 주문을 잘게 나누는 방식이 기준을 피하는 수단이 되기 어렵습니다. 물품가격에는 현지 배송비가 포함되고, 목록통관 배제대상물품이 한 건이라도 섞이면 화물 전체가 영향을 받을 수 있습니다.",
        "key_points_ko": [
            "기준은 결제 건이 아니라 수입자·물품·입항 시점입니다.",
            "현지 배송비도 과세가격에 포함됩니다.",
            "배제 대상이 섞이면 화물 전체가 목록통관에서 빠질 수 있습니다.",
        ],
        "checkpoints_ko": [
            "같은 날 도착 예정인 주문이 몇 건인지 확인합니다.",
            "각 주문의 물품가격과 현지 배송비 합계를 확인합니다.",
            "합산 판단 기준(수입자·발송국·입항일)을 관세청 안내로 확인합니다.",
            "배제 대상 품목이 섞였는지 확인합니다.",
        ],
        "cases": ["TRAP-12"],
        "basis_keys": [],
        "tags": ["CUSTOMS_LOW_VALUE", "CUSTOMS_PERSONAL_ID"],
        "tool": "lookup_hs_requirements",
        "tool_example": {"hs_code": "8518309000"},
        "keywords": ["합산과세", "직구 나눠 주문", "면세 한도 합산", "목록통관 합산", "직구 세금"],
        "related_guides": ["duty-free-150-200", "personal-customs-id", "list-clearance-excluded-items"],
        "related_items": ["bluetooth-earbuds"],
    },
    {
        "slug": "used-luxury-brand-ip",
        "question_ko": "해외직구 중고 명품, 정품이면 통관에 문제없나요?",
        "title_ko": "중고 명품 직구 — 상표권 신고와 세관 통관 보류",
        "category": "지재권·원산지",
        "summary_ko": "정품이라도 권리자 신고나 상표 사용 범위에 따라 통관이 보류될 수 있습니다. 중고·개인 간 거래에서 확인할 점을 정리했습니다.",
        "answer_ko": "세관은 지식재산권을 침해하는 물품의 통관을 보류하는 절차를 두고 있고, 지식재산권 위반 의심물품은 목록통관 배제대상물품으로도 열거되어 있습니다. 진정상품 병행수입은 국내외 상표권자가 동일인 관계 등 고시가 정한 요건을 갖출 때 상표권 침해로 보지 않지만, 중고품·개인 간 거래는 정품 증빙과 권리자 허락 여부가 따로 문제될 수 있습니다. 구매 전에 권리자 신고 이력과 정품 증빙 확보 가능성을 확인해야 합니다.",
        "key_points_ko": [
            "정품 여부와 통관 가능 여부는 같은 말이 아닙니다.",
            "권리자 신고가 있으면 통관이 보류될 수 있습니다.",
            "중고·개인 거래는 정품 증빙을 요구받을 수 있습니다.",
        ],
        "checkpoints_ko": [
            "물품이 지식재산권 위반 의심물품으로 신고되어 있는지 확인합니다.",
            "정품 증빙(구매 영수증·보증서·정품 인증)을 확보할 수 있는지 확인합니다.",
            "국내 상표권자와 해외 권리자의 관계를 확인합니다.",
            "판매 목적이면 상표 사용 허락 범위를 확인합니다.",
        ],
        "cases": ["TRAP-20", "TRAP-12"],
        "basis_keys": [],
        "tags": ["IP_PARALLEL_IMPORT", "CUSTOMS_CHECKPOINT"],
        "tool": "assess_import_case",
        "tool_example": {"query": "정품 명품 가방 병행수입 판매", "facts": {"purpose": "resale"}},
        "keywords": ["중고 명품 직구", "명품 통관", "상표권 신고", "세관 유치", "정품 증빙"],
        "related_guides": ["parallel-import", "smartstore-brand-logo-resale", "purchase-agency-vs-parallel-import"],
        "related_items": [],
    },
    {
        "slug": "contact-lens-medical-device",
        "question_ko": "해외직구 콘택트렌즈·미용렌즈도 의료기기 허가가 필요한가요?",
        "title_ko": "콘택트렌즈 직구 — 의료기기 등급과 수입 허가",
        "category": "기타 규제",
        "summary_ko": "컬러렌즈·미용렌즈는 패션 소품처럼 보이지만 의료기기로 관리됩니다. 수입업 허가와 품목 허가, 통관 요건을 정리했습니다.",
        "answer_ko": "콘택트렌즈는 시력 교정용이든 미용 목적이든 의료기기법의 관리 대상으로 안내되는 품목입니다. 판매를 업으로 수입하려면 식약처 수입업 허가와 품목별 수입허가·수입인증·수입신고가 각각 필요하고, 등급에 따라 절차가 갈립니다. 의료기기는 금액이 낮아도 목록통관 배제 검토 대상이므로, 자가사용으로 들여오는 경우에도 의료기기 해당 여부와 세관장확인 요건을 확인해야 합니다. 판매를 업으로 하면 판매업 신고와 용기·외장 기재사항도 함께 확인해야 합니다.",
        "key_points_ko": [
            "미용 목적 렌즈도 의료기기 관리 대상으로 안내됩니다.",
            "수입업 허가와 품목 허가는 별개 단계입니다.",
            "금액이 낮아도 목록통관 배제 여부를 함께 검토합니다.",
        ],
        "checkpoints_ko": [
            "렌즈의 등급과 품목 분류를 확인합니다.",
            "수입업 허가와 품목별 허가·인증·신고 중 어느 절차인지 확인합니다.",
            "판매업 신고와 용기·외장 기재사항을 확인합니다.",
            "HS 10자리로 세관장확인 요건을 함께 조회합니다.",
        ],
        "cases": ["TRAP-21", "TRAP-12"],
        "basis_keys": [],
        "tags": ["MEDICAL_DEVICE_IMPORT", "CUSTOMS_CHECKPOINT"],
        "tool": "assess_import_case",
        "tool_example": {"query": "해외직구 콘택트렌즈 자가사용", "facts": {"purpose": "self_use"}},
        "keywords": ["콘택트렌즈 직구", "미용렌즈 수입", "컬러렌즈 의료기기", "의료기기 수입업 허가", "렌즈 통관"],
        "related_guides": ["medical-device-fda-ce", "list-clearance-excluded-items", "customs-checkpoint-zero"],
        "related_items": [],
    },
    {
        "slug": "vape-device-import",
        "question_ko": "전자담배 기기만 직구하면 담배 규제를 피할 수 있나요?",
        "title_ko": "전자담배 기기·액상 반입 — 기기와 액상을 나눠 보는 기준",
        "category": "기타 규제",
        "summary_ko": "기기와 액상은 적용 법령이 다르고, 액상에 니코틴이 있으면 담배로 관리됩니다. 나눠서 확인할 지점을 정리했습니다.",
        "answer_ko": "담배사업법상 담배는 연초나 니코틴(천연·합성 포함)을 원료로 한 것으로 확대되어, 니코틴 액상은 기기와 별개로 담배 규제가 적용됩니다. 수입·판매하려면 수입판매업 등록과 제세부담금 납부, 경고문구·성분 표시, 유해성분 검사가 따릅니다. 니코틴이 없는 향료 액상이라도 사용 목적과 구성에 따라 다른 법령이 걸릴 수 있고, 기기의 충전·전원부는 전기용품 안전관리와 전파 요건을 따로 확인해야 합니다. 기기만 따로 사는 방식이라도 결합해 사용하는 목적을 함께 봅니다.",
        "key_points_ko": [
            "액상의 니코틴 유무가 담배 해당 여부를 가릅니다.",
            "기기와 액상은 확인 축이 다릅니다.",
            "충전·전원부는 전기용품·전파 요건을 따로 봅니다.",
        ],
        "checkpoints_ko": [
            "액상 성분에 니코틴이 있는지 확인합니다.",
            "제품이 담배사업법상 담배에 해당하는지 확인합니다.",
            "수입판매업 등록과 제세부담금 절차를 확인합니다.",
            "기기의 충전 방식과 무선 기능을 확인합니다.",
        ],
        "cases": ["TRAP-15", "TRAP-16"],
        "basis_keys": [],
        "tags": ["TOBACCO_VAPE", "ELECTRICAL_KC", "CUSTOMS_CHECKPOINT"],
        "tool": "assess_import_case",
        "tool_example": {"query": "전자담배 기기와 니코틴 액상 수입 판매", "facts": {"purpose": "resale"}},
        "keywords": ["전자담배 기기 직구", "전자담배 액상", "니코틴 액상 반입", "담배사업법", "전자담배 수입"],
        "related_guides": ["nicotine-liquid-tobacco", "household-chemical-safety", "kc-low-voltage"],
        "related_items": [],
    },
    {
        "slug": "quarantine-meat-dairy",
        "question_ko": "해외직구 육포·치즈·육가공품은 동물검역 신고를 해야 하나요?",
        "title_ko": "육포·치즈 직구 — 지정검역물과 목록통관 배제",
        "category": "기타 규제",
        "summary_ko": "축산물·유제품은 식품이면서 검역 대상 물건이 될 수 있습니다. 검역 대상 여부와 신고 절차, 목록통관 배제 여부를 정리했습니다.",
        "answer_ko": "가축전염병 예방법은 수출입 검역 대상 물건을 정하고, 지정검역물을 수입한 자는 동물검역기관에 검역을 신청해 검역관의 검역을 받도록 하고 있습니다. 여행자 휴대품으로 지정검역물을 들여오는 경우에는 입국 즉시 신고해야 합니다. 목록통관 배제대상물품에도 농림축수산물등 검역대상물품이 들어 있어, 금액이 낮아도 수입신고와 검역이 함께 걸릴 수 있습니다. 육포·육가공품·유제품이 지정검역물에 드는지가 첫 확인 지점입니다.",
        "key_points_ko": [
            "식품 요건과 검역 요건은 별개로 걸립니다.",
            "여행자 휴대품도 입국 즉시 신고 대상이 될 수 있습니다.",
            "검역대상물품은 목록통관 배제 대상으로 열거되어 있습니다.",
        ],
        "checkpoints_ko": [
            "물품이 지정검역물에 드는지 확인합니다.",
            "동물검역기관 검역 신청 절차를 확인합니다.",
            "휴대 반입이면 입국 즉시 신고 대상인지 확인합니다.",
            "식품 수입신고와 한글표시사항을 함께 확인합니다.",
        ],
        "cases": ["TRAP-12"],
        "basis_keys": ["feed:B_LIVESTOCK_31", "feed:B_LIVESTOCK_34",
                       "feed:B_LIVESTOCK_36", "feed:B_LIVESTOCK_39"],
        "tags": ["ANIMAL_PRODUCT_QUARANTINE", "CUSTOMS_LOW_VALUE", "KOREAN_LABELING"],
        "tool": "assess_import_case",
        "tool_example": {"query": "수입 축산물 가공식품 판매", "facts": {"purpose": "resale"}},
        "keywords": ["육포 직구", "치즈 반입", "동물검역", "지정검역물", "축산물 직구"],
        "related_guides": ["pet-treat-direct-purchase-quarantine", "list-clearance-excluded-items", "food-import-declaration"],
        "related_items": [],
    },
    {
        "slug": "stroller-carseat-kc",
        "question_ko": "해외직구 유모차·카시트는 KC 안전인증 없이 들여올 수 있나요?",
        "title_ko": "유모차·카시트 직구 — 어린이제품 안전인증과 면제 범위",
        "category": "어린이제품",
        "summary_ko": "유모차·카시트는 어린이제품 안전관리 대상으로 분류되는 대표 품목입니다. 인증 유형과 면제 사유, 직구 반입 시 확인할 점을 정리했습니다.",
        "answer_ko": "유모차와 카시트는 어린이제품 안전관리 대상으로 분류되는 대표 품목이고, 어린이제품은 안전인증·안전확인·공급자적합성확인 3유형으로 나뉘어 품목과 대상 연령에 따라 유형이 정해집니다. 안전인증 면제는 연구·개발, 수출, 전시회 출품 등 법이 정한 사유에 한정되므로, 자가사용 직구라고 해서 당연히 빠지는 것은 아닙니다. 대상 연령 표기와 사용 기간이 유형 판단에 직접 영향을 주니 제품 표시를 함께 확인해야 합니다.",
        "key_points_ko": [
            "유모차·카시트는 안전인증 대상으로 분류되는 대표 품목입니다.",
            "면제는 법이 정한 사유에 한정됩니다.",
            "대상 연령 표기가 유형 판단에 영향을 줍니다.",
        ],
        "checkpoints_ko": [
            "제품의 대상 연령과 사용 목적을 확인합니다.",
            "안전인증·안전확인·공급자적합성 중 어느 유형인지 확인합니다.",
            "면제 사유에 해당하는지 확인합니다.",
            "KC 인증·신고번호를 조회해 표시와 대조합니다.",
        ],
        "cases": ["TRAP-03"],
        "basis_keys": [],
        "tags": ["CHILDREN_PRODUCT_SAFETY", "CUSTOMS_CHECKPOINT"],
        "tool": "check_kc_certification",
        "tool_example": {"product_name": "유모차", "target_age": "만 0~3세"},
        "keywords": ["유모차 직구", "카시트 직구", "어린이제품 안전인증", "KC 인증 유모차", "카시트 수입"],
        "related_guides": ["children-product-types", "children-product-exemption", "children-kc-13-safety-confirm"],
        "related_items": [],
    },
    {
        "slug": "led-multitap-kc",
        "question_ko": "LED 조명·멀티탭도 KC 인증 대상인가요?",
        "title_ko": "LED 조명·멀티탭 — 전기용품 안전인증 대상 범위",
        "category": "전기·전파·KC",
        "summary_ko": "조명기구와 멀티탭은 전기용품 안전관리 대상 중에서도 확인이 자주 빠지는 품목입니다. 대상 범위와 확인 순서를 정리했습니다.",
        "answer_ko": "안전인증대상전기용품은 1천볼트 이하의 교류·직류 전원을 사용하는 제품 중 전기용품 및 생활용품 안전관리법 시행규칙 별표 3이 정한 것입니다. LED 조명기구와 멀티탭(콘센트·배선기구류)은 이 표의 품목 분류 안에서 검토되는 품목이라, 완제품 유형과 정격을 기준으로 어느 절차(안전인증·안전확인·공급자적합성확인)가 걸리는지 확인해야 합니다. 해외 인증(CE·UL)은 국내 절차를 대신하지 않습니다.",
        "key_points_ko": [
            "입력 전원과 정격이 대상 판단의 출발점입니다.",
            "조명기구·배선기구류는 별표 3의 품목 분류로 확인합니다.",
            "해외 인증은 국내 절차를 대체하지 않습니다.",
        ],
        "checkpoints_ko": [
            "제품의 정격 입력(AC/DC)과 정격출력을 라벨에서 확인합니다.",
            "시행규칙 별표 3의 품목 분류 중 어디에 드는지 확인합니다.",
            "KC 인증번호·신고번호를 조회해 표시와 대조합니다.",
            "어린이 방에 쓰는 제품이면 어린이제품 요건을 함께 확인합니다.",
        ],
        "cases": ["TRAP-04"],
        "basis_keys": [],
        "tags": ["ELECTRICAL_KC", "CUSTOMS_CHECKPOINT"],
        "tool": "check_kc_certification",
        "tool_example": {"product_name": "LED 스탠드 조명", "ac_plug": "yes", "battery": "none"},
        "keywords": ["LED 조명 KC", "멀티탭 인증", "조명기구 안전인증", "전기용품 KC", "콘센트 수입"],
        "related_guides": ["kc-low-voltage", "battery-separate-cert", "kc-cert-number-verify"],
        "related_items": ["led-mood-light", "camping-lantern"],
    },
    {
        "slug": "kitchen-appliance-110v-kc",
        "question_ko": "미국 직구 에어프라이어·커피머신, 110V 전압은 어떻게 봐야 하나요?",
        "title_ko": "주방 전기제품 직구 — 110V·플러그와 KC 안전인증",
        "category": "전기·전파·KC",
        "summary_ko": "전압과 플러그가 다른 제품을 들여올 때 KC 요건과 실제 사용 조건을 함께 봐야 합니다. 확인 순서를 정리했습니다.",
        "answer_ko": "주방 전기제품은 1천볼트 이하 전원을 쓰는 제품 중 시행규칙 별표 3이 정한 범위에서 안전인증·안전확인 등 KC 절차를 검토합니다. 미국·일본향 제품은 정격 110V와 플러그 형식이 국내 220V 환경과 달라, 변압기 사용을 전제로 한 사용 조건과 제조사 보증 범위를 별도로 확인해야 합니다. 전압·주파수 표기와 정격출력, 접지 여부를 라벨에서 확인하고, 인증번호가 있다면 조회해 표시와 대조하는 순서로 보면 됩니다.",
        "key_points_ko": [
            "KC 대상 여부와 국내 사용 가능 여부는 별개 문제입니다.",
            "110V·플러그 형식은 사용 조건과 보증에 영향을 줍니다.",
            "인증번호는 조회해 표시와 대조합니다.",
        ],
        "checkpoints_ko": [
            "정격 전압·주파수와 플러그 형식을 확인합니다.",
            "정격출력과 접지 여부를 확인합니다.",
            "시행규칙 별표 3의 품목 분류를 확인합니다.",
            "변압기 사용 조건과 제조사 보증 범위를 확인합니다.",
        ],
        "cases": ["TRAP-04"],
        "basis_keys": [],
        "tags": ["ELECTRICAL_KC", "CUSTOMS_CHECKPOINT"],
        "tool": "check_kc_certification",
        "tool_example": {"product_name": "에어프라이어", "ac_plug": "yes", "battery": "none"},
        "keywords": ["110V 직구", "에어프라이어 직구", "커피머신 수입", "변압기 KC", "주방 전기제품"],
        "related_guides": ["kc-low-voltage", "led-multitap-kc", "kc-cert-number-verify"],
        "related_items": ["air-fryer", "coffee-machine", "electric-kettle"],
    },
    {
        "slug": "wearable-health-device",
        "question_ko": "혈압·심전도를 재는 스마트워치는 의료기기인가요, 전파인증 대상인가요?",
        "title_ko": "웨어러블 건강 측정기 — 의료기기와 전파 적합성평가",
        "category": "전기·전파·KC",
        "summary_ko": "같은 웨어러블이라도 측정 기능의 용도와 무선 송신 여부에 따라 확인 축이 달라집니다. 두 축을 나눠 정리했습니다.",
        "answer_ko": "스마트워치가 혈압·심전도 같은 측정값을 의료 목적으로 제공하면 의료기기 해당 여부를 먼저 확인해야 하고, 의료기기로 관리되면 수입업 허가와 품목별 허가·인증·신고가 각각 필요합니다. 무선으로 데이터를 보내는 제품은 전파법상 적합성평가 대상이 되어 적합인증·적합등록 등 해당 절차를 확인해야 하며, 개인이 사용할 목적으로 반입하는 기자재는 모델별 1대에 적합성평가 면제가 적용되는 경우가 있습니다. 건강관리 목적 표시와 의료 목적 표시는 판단이 갈리는 지점이므로 제품 설명과 표시를 함께 봐야 합니다.",
        "key_points_ko": [
            "측정 기능의 용도 표시가 의료기기 판단의 출발점입니다.",
            "무선 송신이 있으면 전파 적합성평가 축이 붙습니다.",
            "개인 사용 1대 면제는 모델·수량 조건을 함께 봅니다.",
        ],
        "checkpoints_ko": [
            "제품이 의료 목적 측정 기능을 표시하는지 확인합니다.",
            "무선 송신 방식과 주파수를 확인합니다.",
            "적합성평가 유형(적합인증·적합등록·자기적합확인)을 확인합니다.",
            "개인 사용 1대 면제 조건에 드는지 확인합니다.",
        ],
        "cases": ["TRAP-21", "TRAP-06"],
        "basis_keys": [],
        "tags": ["MEDICAL_DEVICE_IMPORT", "RF_CONFORMITY"],
        "tool": "assess_import_case",
        "tool_example": {"query": "심전도 측정 스마트워치 직구", "facts": {"purpose": "self_use", "rf_tx": "yes"}},
        "keywords": ["스마트워치 의료기기", "심전도 워치", "전파 적합성평가", "웨어러블 인증", "스마트워치 직구"],
        "related_guides": ["medical-device-fda-ce", "rf-conformity-overseas", "rf-exemption-personal"],
        "related_items": [],
    },
    {
        "slug": "roasted-coffee-tea-import",
        "question_ko": "해외직구 원두커피·차는 식약처 수입신고를 해야 하나요?",
        "title_ko": "원두·차 수입 — 식품 수입신고와 검사 순서",
        "category": "식품·화장품",
        "summary_ko": "커피·차는 가공식품이라 수입신고와 검사, 한글표시사항이 함께 걸립니다. 소량 직구와 판매 목적의 차이를 정리했습니다.",
        "answer_ko": "원두커피와 차는 식품으로, 판매를 목적으로 수입하는 영업자는 수입식품등 수입·판매업 영업등록 후 매 수입 건마다 수입신고와 검사를 거쳐야 합니다. 자가소비용 국제우편·특송 면제는 자가소비에 한정되고, 식품등 인터넷 구매대행업 영업등록을 한 자에게 요청해 수입하는 경우는 제외됩니다. 제품에는 제품명·원재료명·소비기한 등 한글표시사항이 필요하고, 로스팅 원산지와 소비기한 표기 오류는 통관 지연으로 이어지기 쉽습니다.",
        "key_points_ko": [
            "식품은 금액과 무관하게 수입신고·검사를 함께 검토합니다.",
            "자가소비 면제는 판매 목적에 적용되지 않습니다.",
            "한글표시사항과 소비기한 표기가 통관에 직접 영향을 줍니다.",
        ],
        "checkpoints_ko": [
            "판매 목적인지 자가소비인지 확인합니다.",
            "수입식품 영업등록과 수입신고 절차를 확인합니다.",
            "한글표시사항(제품명·원재료명·소비기한)을 확인합니다.",
            "목록통관 배제대상물품 해당 여부를 확인합니다.",
        ],
        "cases": ["TRAP-01", "TRAP-12"],
        "basis_keys": ["labeling:B_IMPORT_15", "labeling:B_FOOD_4_1_1"],
        "tags": ["FOOD_IMPORT_DECLARATION", "FOOD_BUSINESS_REGISTRATION", "KOREAN_LABELING"],
        "tool": "check_food_cosmetics",
        "tool_example": {"product_name": "원두커피", "kind": "food"},
        "keywords": ["원두 직구", "커피 수입신고", "차 수입", "수입식품 검사", "원두 관세"],
        "related_guides": ["food-import-declaration", "korean-labeling-items", "food-business-registration"],
        "related_items": ["roasted-coffee"],
    },
    {
        "slug": "tumbler-food-contact",
        "question_ko": "스테인리스 텀블러·보온병도 식품용 기구 수입신고 대상인가요?",
        "title_ko": "텀블러·보온병 수입 — 식품용 기구 검사와 표시",
        "category": "식품·화장품",
        "summary_ko": "식품에 닿는 용기라면 재질 기준과 표시 요건이 붙습니다. 스테인리스 텀블러·보온병에서 확인할 항목과 수입 절차를 정리했습니다.",
        "answer_ko": "식품용 기구 및 용기·포장은 수입식품안전관리 특별법상 수입식품등에 포함되어 수입신고·검사 대상이 될 수 있고, 재질별 기준·규격과 표시(재질, 영업소 명칭 및 소재지, 주의사항)를 지켜야 합니다. 스테인리스 텀블러·보온병은 식품 접촉부의 재질과 용출 기준이 핵심이고, 같은 제품이라도 식품 접촉 용도로 판매하면 이 요건이 추가됩니다. 판매 목적이면 수입식품 영업등록과 수입신고 순서를 먼저 확인해야 합니다.",
        "key_points_ko": [
            "식품 접촉 용도인지가 적용 법령을 가릅니다.",
            "재질별 기준·규격과 시험성적서가 필요합니다.",
            "표시 항목(재질·영업소·주의사항)을 함께 봅니다.",
        ],
        "checkpoints_ko": [
            "제품의 사용 용도(식품 접촉 여부)를 확인합니다.",
            "재질과 식품용 적합 표시를 확인합니다.",
            "재질별 기준·규격 시험성적서를 확인합니다.",
            "수입식품 영업등록·수입신고 절차를 확인합니다.",
        ],
        "cases": ["TRAP-11"],
        "basis_keys": [],
        "tags": ["FOOD_CONTACT_MATERIAL", "FOOD_IMPORT_DECLARATION", "KOREAN_LABELING"],
        "tool": "check_food_cosmetics",
        "tool_example": {"product_name": "스테인리스 텀블러", "kind": "food_contact"},
        "keywords": ["텀블러 수입", "보온병 수입", "식품용 기구", "스테인리스 용기 검사", "기구용기 표시"],
        "related_guides": ["food-contact-material", "food-import-declaration", "baby-product-import"],
        "related_items": ["stainless-tumbler"],
    },
    {
        "slug": "cosmetics-quality-inspection",
        "question_ko": "수입 화장품 품질검사는 어떤 경우에 면제되나요?",
        "title_ko": "수입 화장품 품질검사 — 대상과 면제 확인 순서",
        "category": "식품·화장품",
        "summary_ko": "수입 화장품은 품질검사 대상 여부와 면제 사유를 먼저 확인해야 합니다. 확인 순서와 함께 볼 요건을 정리했습니다.",
        "answer_ko": "수입 화장품은 품질검사 대상 여부를 확인해야 하고, 면제는 수입화장품 품질검사 면제에 관한 규정이 정한 대상·절차에 따라 판단합니다. 자가소비 목적의 직접구매 해외화장품은 별도 정의와 검사 대상으로 다뤄지며, 판매·유통하려면 화장품책임판매업 등록과 품질관리, 수입실적 보고가 필요합니다. 검사 대상·면제 여부는 제품 유형과 수입 형태에 따라 갈리므로, 통관 전에 검사기관과 면제 요건을 함께 확인하는 순서가 안전합니다.",
        "key_points_ko": [
            "검사 대상 여부와 면제 사유를 따로 확인합니다.",
            "직접구매 해외화장품은 별도 정의로 다뤄집니다.",
            "판매 목적이면 책임판매업 등록이 선행됩니다.",
        ],
        "checkpoints_ko": [
            "제품이 기능성화장품인지 확인합니다.",
            "품질검사 대상·면제 요건을 확인합니다.",
            "화장품책임판매업 등록 여부를 확인합니다.",
            "한글 기재사항과 사용기한 표시를 확인합니다.",
        ],
        "cases": ["TRAP-02"],
        "basis_keys": ["labeling:B_COS_10_1"],
        "tags": ["COSMETICS_RESPONSIBLE_SALES", "KOREAN_LABELING"],
        "tool": "check_food_cosmetics",
        "tool_example": {"product_name": "수딩 크림", "kind": "cosmetics"},
        "keywords": ["수입 화장품 품질검사", "화장품 검사 면제", "화장품책임판매업", "직접구매 해외화장품", "화장품 수입"],
        "related_guides": ["direct-buy-cosmetics-resale", "cosmetics-labeling-items", "cosmetics-import-labeling-sticker"],
        "related_items": ["soothing-cream", "sunscreen"],
    },
    {
        "slug": "food-purchase-agency-registration",
        "question_ko": "수입식품 구매대행을 하려면 어떤 영업등록이 필요한가요?",
        "title_ko": "수입식품 구매대행업 — 영업등록과 수입신고 순서",
        "category": "식품·화장품",
        "summary_ko": "구매대행으로 식품을 들여와 판매하면 개인 자가소비 면제가 적용되지 않습니다. 필요한 등록과 신고 순서를 정리했습니다.",
        "answer_ko": "식품등 인터넷 구매대행업은 수입식품안전관리 특별법상 영업등록 대상 업종이고, 판매를 목적으로 수입하는 영업자는 수입식품등 수입·판매업 영업등록 후 매 수입 건마다 수입신고와 검사를 거쳐야 합니다. 자가소비용 국제우편·특송 면제는 구매대행업 영업등록을 한 자에게 요청해 수입하는 경우에 적용되지 않도록 명시되어 있어, 구매대행을 하면서 개인 면세·면제 범위를 그대로 적용하기는 어렵습니다. 영업등록 없이 수입한 식품은 판매할 수 없으므로, 판매 계획이 있으면 등록을 먼저 끝내는 순서가 필요합니다.",
        "key_points_ko": [
            "구매대행은 자가소비 면제의 예외로 명시되어 있습니다.",
            "영업등록과 건별 수입신고가 모두 필요합니다.",
            "등록 없이 수입한 식품은 판매할 수 없습니다.",
        ],
        "checkpoints_ko": [
            "업태가 수입식품등 인터넷 구매대행업에 드는지 확인합니다.",
            "영업등록 요건(시설·서류)을 확인합니다.",
            "건별 수입신고와 검사 절차를 확인합니다.",
            "한글표시사항과 표시 의무자를 확인합니다.",
        ],
        "cases": ["TRAP-01", "TRAP-07"],
        "basis_keys": ["labeling:B_IMPORT_15", "labeling:B_IMPORT_20"],
        "tags": ["FOOD_BUSINESS_REGISTRATION", "FOOD_IMPORT_DECLARATION", "KOREAN_LABELING"],
        "tool": "check_food_cosmetics",
        "tool_example": {"product_name": "수입 과자 구매대행", "kind": "food", "purpose": "resale"},
        "keywords": ["수입식품 구매대행", "구매대행 영업등록", "인터넷 구매대행업", "수입식품 영업등록", "구매대행 수입신고"],
        "related_guides": ["food-business-registration", "purchase-agency-vs-parallel-import",
                           "food-import-registration-order", "resale-after-direct-buy"],
        "related_items": [],
    },
    {
        "slug": "food-expiry-labeling",
        "question_ko": "해외직구 식품을 원포장 그대로 팔 때 한글 소비기한 표시는 어떻게 하나요?",
        "title_ko": "원포장 수입식품 — 한글 소비기한·표시사항 부착",
        "category": "표시·광고",
        "summary_ko": "원포장을 그대로 유통해도 한글 표시 의무는 사라지지 않습니다. 소비기한을 포함해 붙여야 할 표시 항목과 표시 방법을 정리했습니다.",
        "answer_ko": "수입한 식품을 재가공·재포장 없이 원래 포장 상태로 유통하는 경우에도 제품명, 식품의 유형, 업소명 및 소재지, 제조연월일, 소비기한, 내용량, 원재료명, 영양성분 등을 한글로 표시해야 합니다. 표시가 없거나 표시방법을 위반한 식품등은 판매하거나 판매 목적으로 수입·보관·진열할 수 없습니다. 한글 표시가 원칙이고 한자·외국어 병기는 글씨 크기 기준을 지켜야 하므로, 스티커로 붙이는 경우에도 소비기한과 주의사항 항목이 빠지지 않게 확인해야 합니다.",
        "key_points_ko": [
            "원포장 유통도 한글 표시 의무가 적용됩니다.",
            "소비기한은 필수 표시 항목입니다.",
            "표시 방법(글씨 크기·병기)도 함께 확인합니다.",
        ],
        "checkpoints_ko": [
            "제품명·식품유형·업소명·소비기한 항목이 모두 있는지 확인합니다.",
            "원재료명과 영양성분 표시를 확인합니다.",
            "한글·외국어 병기 시 글씨 크기 기준을 확인합니다.",
            "스티커 부착 위치와 훼손 가능성을 확인합니다.",
        ],
        "cases": ["TRAP-10", "TRAP-01"],
        "basis_keys": ["labeling:B_FOOD_4_1_1", "labeling:B_FOOD_4_3", "labeling:B_FOOD_RULE_3_1"],
        "tags": ["KOREAN_LABELING", "FOOD_IMPORT_DECLARATION"],
        "tool": "check_ad_labeling",
        "tool_example": {"label_text": "제품명 유기농 그래놀라 / 내용량 300g / 소비기한 2027.03.15",
                         "product_type": "general_food"},
        "keywords": ["한글 소비기한", "수입식품 한글표시", "원포장 유통", "소비기한 스티커", "한글표시사항"],
        "related_guides": ["korean-labeling-items", "food-allergen-labeling", "cosmetics-import-labeling-sticker"],
        "related_items": ["roasted-coffee"],
    },
    {
        "slug": "purchase-agency-withdrawal",
        "question_ko": "해외 구매대행 상품도 청약철회·반품이 되나요?",
        "title_ko": "구매대행 청약철회 — 7일 기간과 반품비·고지 의무",
        "category": "국내 이커머스·공정위",
        "summary_ko": "구매대행도 통신판매에 해당해 청약철회 규정이 적용됩니다. 기간, 반품비 범위, 미리 고지할 내용을 정리했습니다.",
        "answer_ko": "구매대행으로 판매하는 경우에도 통신판매에 해당하면 전자상거래법상 청약철회 규정이 적용됩니다. 소비자는 계약내용에 관한 서면을 받은 날부터 7일 이내에 청약철회를 할 수 있고, 재화등의 내용이 표시·광고의 내용과 다르거나 계약내용과 다르게 이행되면 공급받은 날부터 3개월, 그 사실을 안 날부터 30일 이내에 청약철회를 할 수 있습니다. 반환에 필요한 비용은 소비자가 부담하지만 사업자는 위약금이나 손해배상을 청구할 수 없고, 청약철회가 불가능한 상품은 그 사유를 포장이나 소비자가 쉽게 알 수 있는 곳에 명확히 표시해야 합니다. 해외 발주 뒤 취소·반품 조건은 주문 전에 고지해야 분쟁을 줄일 수 있습니다.",
        "key_points_ko": [
            "구매대행도 통신판매라 청약철회 규정이 적용됩니다.",
            "기간은 7일이고, 표시·광고와 다른 경우 3개월·30일 기준이 함께 있습니다.",
            "반품비 외 위약금·추가 비용은 청구할 수 없습니다.",
        ],
        "checkpoints_ko": [
            "청약철회 기간과 기산점을 확인합니다.",
            "청약철회 제한 사유와 고지 방법을 확인합니다.",
            "반품비 범위와 부담 주체를 확인합니다.",
            "해외 발주·취소 조건을 주문 전에 고지하는지 확인합니다.",
        ],
        "cases": [],
        "basis_keys": ["ecommerce:B_EC_17_1", "ecommerce:B_EC_17_3", "ecommerce:B_EC_17_6",
                       "ecommerce:B_EC_18_9", "ecommerce:B_NOTICE_GUIDE_EXTRA_FEE",
                       "ecommerce:B_NOTICE_PRODUCT_INFO"],
        "tags": ["WITHDRAWAL_REFUND", "SELLER_DISCLOSURE", "DELIVERY_FULFILLMENT"],
        "tool": "check_ecommerce_compliance",
        "tool_example": {"detail_copy": "해외 구매대행 상품으로 단순변심 반품 불가, 취소 시 수수료 30% 부과",
                         "channel": "smartstore"},
        "keywords": ["구매대행 청약철회", "구매대행 반품", "해외 구매대행 환불", "청약철회 7일", "반품비"],
        "related_guides": ["refund-policy-wording", "return-fee-charge", "purchase-agency-vs-parallel-import"],
        "related_items": [],
    },
]


def main() -> int:
    with open(PATH, encoding="utf-8") as handle:
        catalog = json.load(handle)
    existing = {item["slug"] for item in catalog["items"]}
    known_guides = set(existing) | {item["slug"] for item in NEW_ITEMS}
    corpus_ids = {trap.id for trap in load_corpus().traps}
    registry = guides.basis_registry()

    if len(NEW_ITEMS) != 17:
        raise SystemExit(f"기대한 신규 항목 수(17)와 다릅니다: {len(NEW_ITEMS)}")
    if len({item["slug"] for item in NEW_ITEMS}) != len(NEW_ITEMS):
        raise SystemExit("신규 항목에 중복 슬러그가 있습니다")

    for item in NEW_ITEMS:
        slug = item["slug"]
        if slug in existing:
            print(f"skip existing {slug}")
            continue
        for key in item["basis_keys"]:
            if key not in registry:
                raise SystemExit(f"{slug}: unknown basis key {key}")
        for case_id in item["cases"]:
            if case_id not in corpus_ids:
                raise SystemExit(f"{slug}: unknown case {case_id}")
        for tag in item["tags"]:
            if tag not in REGULATION_TAGS:
                raise SystemExit(f"{slug}: unknown regulation tag {tag}")
        for related in item["related_guides"]:
            if related not in known_guides:
                raise SystemExit(f"{slug}: unknown related guide {related}")
        for product in item["related_items"]:
            if pseo.get_item(product) is None:
                raise SystemExit(f"{slug}: unknown related item {product}")
        if not item["cases"] and not item["basis_keys"]:
            raise SystemExit(f"{slug}: 근거(케이스 또는 조문 키)가 비어 있습니다")
        if len(item["checkpoints_ko"]) < 3:
            raise SystemExit(f"{slug}: 체크포인트가 3개 미만입니다")

    catalog["items"].extend(item for item in NEW_ITEMS if item["slug"] not in existing)
    catalog["catalog_version"] = NEW_VERSION
    catalog["verified_on"] = VERIFIED_ON
    with open(PATH, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    guides.load_catalog.cache_clear()
    guides.item_index.cache_clear()
    total = len(catalog["items"])
    indexed = 1 + len(pseo.indexable_paths()) + len(guides.indexable_paths())
    print(f"catalog {NEW_VERSION}: {total} items, sitemap urls ~{indexed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
