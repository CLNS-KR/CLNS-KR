"""관세율·FTA 원산지 요건 및 자가사용 면세 기준 참고 모듈.

주의:
- 정확한 HS 10자리별 양허세율·세번별 원산지결정기준(PSR)은 관세청 관세법령정보포털(UNIPASS)
  또는 관세사 확인이 최종 기준입니다.
- 이 모듈은 셀러가 수입 전 마진·서류 리스크를 빠르게 가늠할 수 있도록
  품목군별 대표 기본세율·부가세(10%), 원산지별 협정 적용 가능 여부, 원산지증명서(CO) 유형,
  자가소비 면세한도를 제공합니다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 원산지 국가별 한국과의 FTA 협정 현황
FTA_BY_ORIGIN: Dict[str, Dict[str, Any]] = {
    "중국": {
        "has_fta": True,
        "agreements": ["한·중 FTA", "RCEP"],
        "co_type": "기관발급 원산지증명서(중국 해관총서 또는 CCPIT 발급)",
        "small_exemption": "과세가격 미화 700달러 이하라도 한·중 FTA 특혜 신청 시 원산지증명서 원칙 필요",
        "tip": "알리·1688 도매 구매는 판매자가 기관발급 CO를 안 해 주는 경우가 많아 기본세율(8% 등) 기준으로 원가를 잡는 편이 안전합니다.",
    },
    "미국": {
        "has_fta": True,
        "agreements": ["한·미 FTA"],
        "co_type": "자율발급 원산지증명서(수출자·생산자·수입자 서명, 미화 1,000달러 이하 서류 면제 가능)",
        "self_use_limit_usd": 200,
        "tip": "목록통관 일반 물품은 $200까지 면세지만, 건강기능식품·의약품·화장품(기능성 등)·식품류는 목록통관 배제 대상이라 $150 기준이 적용됩니다.",
    },
    "일본": {
        "has_fta": False,
        "agreements": ["RCEP (일부 품목 단계적 양허 — 한·일 양자 FTA 없음)"],
        "co_type": "RCEP 적용 품목에 한해 기관발급/인증수출자 원산지증명서",
        "tip": "한·일 양자 FTA가 없어 상당수 공산품·식품에 기본관세율(보통 8%, 의류 13% 등)이 그대로 부과됩니다. RCEP 양허 여부를 HS 10자리로 꼭 확인하세요.",
    },
    "베트남": {
        "has_fta": True,
        "agreements": ["한·베트남 FTA", "한·아세안 FTA", "RCEP"],
        "co_type": "기관발급 원산지증명서(Form VK 또는 Form AK)",
        "tip": "의류·신발·가방·생활용품은 한·베트남 FTA 적용 시 관세 0%인 경우가 많으나, 중국산 원단을 썼다면 원산지결정기준(역내가공 등) 미충족에 유의하세요.",
    },
    "독일": {
        "has_fta": True,
        "agreements": ["한·EU FTA"],
        "co_type": "원산지신고서(송장·인보이스 문구 기재; 건당 6,000유로 초과 시 EU 인증수출자 번호 필수)",
        "tip": "EU 역내(독일·프랑스·이탈리아 등) 산지 제품은 6,000유로 이하라도 정확한 원산지신고 문구가 인보이스에 들어가야 0% 협정세율을 받습니다.",
    },
    "대만": {
        "has_fta": False,
        "agreements": [],
        "co_type": "FTA 미체결 — 기본관세율 적용",
        "tip": "한국과 FTA가 체결되어 있지 않아 기본관세율(대부분 8% 전후) + 부가세 10%가 부과됩니다.",
    },
    "태국": {
        "has_fta": True,
        "agreements": ["한·아세안 FTA", "RCEP"],
        "co_type": "기관발급 원산지증명서(Form AK 또는 RCEP CO)",
        "tip": "가공식품·화장품·생활용품은 원산지결정기준 충족 및 Form AK 구비 시 관세 절감 폭이 큽니다.",
    },
    "인도네시아": {
        "has_fta": True,
        "agreements": ["한·인니 CEPA", "한·아세안 FTA", "RCEP"],
        "co_type": "기관발급 원산지증명서(Form AK / CEPA CO)",
        "tip": "한·인니 CEPA 발효로 다수 품목이 0% 또는 저세율 적용 대상입니다.",
    },
    "인도": {
        "has_fta": True,
        "agreements": ["한·인도 CEPA"],
        "co_type": "기관발급 원산지증명서(인도 수출검사위원회 등 발급)",
        "tip": "CEPA 적용 대상 품목과 양허세율을 HS 코드 기준으로 확인하세요.",
    },
    "멕시코": {
        "has_fta": False,
        "agreements": [],
        "co_type": "FTA 미체결 — 기본관세율 적용",
        "tip": "FTA 미체결국으로 기본관세율이 적용됩니다.",
    },
}

# 품목 키워드 / HS 2자리 기반 대표 기본관세율 참고표 (실무 마진 가늠용)
CATEGORY_TARIFF_HINTS: List[Dict[str, Any]] = [
    {
        "id": "electronics_bt",
        "label": "전자·블루투스·IT기기 (HS 85류 등)",
        "keywords": ("스피커", "이어폰", "헤드폰", "블루투스", "충전기", "케이블", "마우스", "키보드", "전자", "모니터", "카메라"),
        "hs2": ("84", "85"),
        "base_rate": "0% ~ 8% (ITA 대상 IT기기 다수 0%, 일반 가전·스피커류 8%)",
        "vat_rate": "10%",
        "fta_note": "기본세율이 이미 0%인 ITA 품목도 많으나, 일반 소형가전·스피커(8%)는 FTA 적용 시 0% 가능.",
    },
    {
        "id": "cosmetics",
        "label": "화장품·향수·스킨케어 (HS 3304 등)",
        "keywords": ("화장품", "크림", "세럼", "로션", "선크림", "토너", "마스크팩", "향수", "립스틱", "샴푸"),
        "hs2": ("33",),
        "base_rate": "6.5% ~ 8% (기초·색조 대부분 6.5%)",
        "vat_rate": "10%",
        "fta_note": "한·미/한·EU FTA는 0% 적용 사례가 많고, 한·중/RCEP은 품목·연차별 단계 양허 확인 필요.",
    },
    {
        "id": "health_food",
        "label": "건강기능식품·영양제 (HS 2106 등)",
        "keywords": ("비타민", "영양제", "오메가", "루테인", "유산균", "프로바이오", "건강기능식품", "콜라겐", "홍삼", "마그네슘"),
        "hs2": ("21",),
        "base_rate": "8% (조제식료품·건기식 대부분 8%)",
        "vat_rate": "10%",
        "fta_note": "한·미 FTA 등은 원산지증명서 구비 시 0% 가능. 단, 자가사용은 6병 초과 시 정식 수입신고 필요.",
    },
    {
        "id": "apparel_shoes",
        "label": "의류·신발·가방 (HS 61·62·64·42류)",
        "keywords": ("의류", "티셔츠", "자켓", "바지", "원피스", "신발", "운동화", "가방", "백팩", "모자", "양말"),
        "hs2": ("42", "61", "62", "64"),
        "base_rate": "8% ~ 13% (의류·신발 대부분 13%, 가방 8%)",
        "vat_rate": "10%",
        "fta_note": "세율 비중이 커서 FTA 유무가 마진에 직접 영향(예: 베트남산 0% vs 일본·대만산 13%).",
    },
    {
        "id": "toys_kids",
        "label": "완구·어린이제품 (HS 9503 등)",
        "keywords": ("완구", "장난감", "인형", "블록", "유아", "어린이"),
        "hs2": ("95",),
        "base_rate": "0% ~ 8% (일반 완구류 다수 0% 또는 8%)",
        "vat_rate": "10%",
        "fta_note": "관세율보다 KC 어린이제품 안전인증(공급자적합성·안전확인) 비용이 더 큰 변수입니다.",
    },
    {
        "id": "kitchen_living",
        "label": "주방용품·식품용기·생활잡화 (HS 39·73·69류)",
        "keywords": ("텀블러", "컵", "접시", "그릇", "프라이팬", "주방", "수납", "생활용품", "거치대"),
        "hs2": ("39", "69", "73"),
        "base_rate": "6.5% ~ 8%",
        "vat_rate": "10%",
        "fta_note": "스테인리스·플라스틱·도자기 식품용기는 관세 외 식약처 기구·용기·포장 정밀검사 비용을 함께 잡아야 합니다.",
    },
]


def assess_tariff_fta(
    *,
    product: str = "",
    hs_code: str = "",
    origin: str = "",
    purpose: str = "resale",
    cif_krw: Optional[float] = None,
) -> Dict[str, Any]:
    """품목·HS·원산지 기반 관세율 범위, FTA 가능 여부, 원산지증명서 요건을 정리한다."""
    clean_hs = re.sub(r"[^0-9]", "", hs_code or "")
    hs2 = clean_hs[:2] if len(clean_hs) >= 2 else ""
    text = (product or "").strip()

    matched_cat: Optional[Dict[str, Any]] = None
    for cat in CATEGORY_TARIFF_HINTS:
        if hs2 and hs2 in cat["hs2"]:
            matched_cat = cat
            break
    if matched_cat is None and text:
        for cat in CATEGORY_TARIFF_HINTS:
            if any(kw in text for kw in cat["keywords"]):
                matched_cat = cat
                break

    origin_clean = (origin or "").strip()
    fta_info = FTA_BY_ORIGIN.get(origin_clean)

    # 자가소비 면세한도 안내
    if purpose == "self_use":
        limit_usd = (fta_info or {}).get("self_use_limit_usd", 150)
        duty_free_note = (
            f"자가소비 개인 직구는 물품가격+현지배송비 합산 미화 ${limit_usd} 이하일 때 관·부가세 면세 대상입니다"
            " (단, 건강기능식품·화장품 일부·식품 등 목록통관 배제 품목은 $150 기준 적용, 6병·자가사용 한도 초과 시 과세)."
        )
    else:
        duty_free_note = (
            "판매·유통 목적(사업자 통관)은 소액 면세가 적용되지 않으며, 1원부터 과세가격(CIF = 물품대+국제운임+보험료) 기준으로 관세 + 부가세 10%가 부과됩니다."
        )

    return {
        "origin": origin_clean or "미지정",
        "hs_code": clean_hs or None,
        "category_label": matched_cat["label"] if matched_cat else "일반 공산품·기타 (HS 10자리 확인 필요)",
        "base_rate_hint": matched_cat["base_rate"] if matched_cat else "일반 기본세율 보통 8% 내외 (HS 10자리에 따라 0~13%+ 상이)",
        "vat_rate": "10% (과세가격 + 관세 합산액의 10%)",
        "category_fta_note": matched_cat["fta_note"] if matched_cat else "원산지·HS 10자리에 따라 FTA 협정세율 0% 적용 가능 여부가 달라집니다.",
        "fta": fta_info if fta_info else {
            "has_fta": None,
            "agreements": [],
            "co_type": "원산지를 선택하면 체결된 FTA와 원산지증명서(CO) 발급 방식을 안내합니다.",
            "tip": "원산지에 따라 관세 0% vs 8~13% 차이가 크므로 발주 전 꼭 확인하세요.",
        },
        "duty_free_note": duty_free_note,
        "cif_krw": cif_krw,
        "unipass_url": "https://unipass.customs.go.kr/clip/index.do",
        "disclaimer": "참고용 예상 범위이며, 최종 세율과 원산지결정기준(PSR)은 관세법령정보포털(UNIPASS) 또는 관세사 확인이 기준입니다.",
    }
