"""화장품 배합금지 및 사용한도 지정 원료 대조 모듈.

근거: 식품의약품안전처 고시 「화장품 안전기준 등에 관한 규정」
- 별표 1: 배합금지 원료 (국내 제조·수입·판매 불가)
- 별표 2: 배합한도 지정 원료 (살균보존제·자외선차단제·기타 사용한도 준수 필요)

주의:
- 직구·수입 화장품 전성분표(한글 또는 INCI 영문)에서 자주 적발되는 핵심 성분을 우선 대조합니다.
- 이 목록에 없다고 해서 전 성분의 안전이 자동 보장되는 것은 아니며, 전체 고시 별표는 식약처에서 최종 확인해야 합니다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# 배합금지 원료(별표 1) — 직구·수입 적발 빈도가 높은 핵심 항목
PROHIBITED_INGREDIENTS: List[Dict[str, Any]] = [
    {
        "ko": "하이드로퀴논",
        "inci": ["hydroquinone"],
        "reason": "미백 연고 등에 쓰이는 전문·일반의약품 성분으로 화장품 배합금지 원료입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "트레티노인 / 레티노익애씨드",
        "inci": ["tretinoin", "retinoic acid", "all-trans-retinoic acid"],
        "reason": "여드름·광노화 의약품 성분으로 화장품 사용이 금지되어 있습니다(레티놀과 구분 필요).",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "비마토프로스트 / 라타노프로스트 (프로스타글란딘 유사체)",
        "inci": ["bimatoprost", "latanoprost", "travoprost", "isopropyl cloprostenate"],
        "reason": "해외 속눈썹 영양제에서 가장 많이 적발되는 의약품 성분(배합금지)입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1 / 식약처 직구 위해식품·화장품 차단 목록",
    },
    {
        "ko": "미녹시딜",
        "inci": ["minoxidil"],
        "reason": "탈모 치료 의약품 성분으로 화장품에 배합할 수 없습니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "스테로이드류 (베타메타손·클로베타솔·하이드로코르티손 등)",
        "inci": ["betamethasone", "clobetasol", "hydrocortisone", "triamcinolone", "dexamethasone", "fluocinolone"],
        "reason": "부신피질호르몬제(스테로이드)는 화장품 배합금지 원료입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "칸나비디올(CBD) / 테트라하이드로칸나비놀(THC) 등 대마 성분",
        "inci": ["cannabidiol", "cbd", "tetrahydrocannabinol", "thc", "cannabis sativa extract"],
        "reason": "대마 유래 칸나비노이드 성분은 마약류 관리법 및 화장품 배합금지 대상에 걸릴 수 있습니다(정제 햄프씨드오일과 구분 확인 필요).",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1 / 마약류 관리법",
    },
    {
        "ko": "포름알데히드",
        "inci": ["formaldehyde"],
        "reason": "발암성·자극성 물질로 화장품 배합금지 원료입니다(유리형 포름알데히드 주의).",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "프탈레이트류 (DEHP·DBP)",
        "inci": ["diethylhexyl phthalate", "dehp", "dibutyl phthalate", "dbp"],
        "reason": "내분비계 교란 우려 물질로 화장품 배합금지 원료입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "수은·납·비소·카드뮴 화합물",
        "inci": ["mercury", "lead acetate", "arsenic", "cadmium"],
        "reason": "중금속 성분은 화장품 배합금지 원료입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "하이드록시아이소헥실 3-사이클로헥센 카복스알데하이드(HICC / 라이랄)",
        "inci": ["hydroxyisohexyl 3-cyclohexene carboxaldehyde", "lyral", "hicc"],
        "reason": "고위험 알레르기 유발 향료로 국내 화장품 배합금지 원료입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
    {
        "ko": "부틸페닐메틸프로피오날(릴리알)",
        "inci": ["butylphenyl methylpropional", "lilial", "bmhca"],
        "reason": "생식독성 우려로 배합금지된 착향제 성분입니다.",
        "basis": "화장품 안전기준 등에 관한 규정 별표 1",
    },
]

# 배합한도 지정 원료(별표 2) — 함량(%)·유형 제한 확인이 필요한 핵심 성분
RESTRICTED_INGREDIENTS: List[Dict[str, Any]] = [
    {
        "ko": "살리실산 (바하/BHA)",
        "inci": ["salicylic acid"],
        "limit": "일반 화장품 0.5% 이하 (여드름성 피부 완화 기능성·두발용 씻어내는 제품 등 예외 한도 별도)",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "페녹시에탄올",
        "inci": ["phenoxyethanol"],
        "limit": "1.0% 이하 (살균보존제)",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "클로페네신",
        "inci": ["chlorphenesin"],
        "limit": "0.3% 이하 (살균보존제)",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "메칠파라벤 / 프로필파라벤 / 부틸파라벤",
        "inci": ["methylparaben", "ethylparaben", "propylparaben", "butylparaben"],
        "limit": "단일 0.4%(프로필/부틸 0.14%)·혼합 0.8% 이하, 만 3세 이하 영유아 기저귀 부위용 사용 금지 등 제한",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "벤조페논-3 (옥시벤존)",
        "inci": ["benzophenone-3", "oxybenzone"],
        "limit": "자외선차단제 5% 이하 (0.5% 초과 시 '벤조페논-3 함유' 주의문구 표시)",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "에칠헥실메톡시신나메이트 (옥티녹세이트)",
        "inci": ["ethylhexyl methoxycinnamate", "octinoxate"],
        "limit": "자외선차단제 7.5% 이하",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "징크옥사이드 / 티타늄디옥사이드",
        "inci": ["zinc oxide", "titanium dioxide"],
        "limit": "자외선차단제 각 25% 이하 (나노 원료 흡입 노출 스프레이형 주의)",
        "basis": "화장품 안전기준 등에 관한 규정 별표 2",
    },
    {
        "ko": "레티놀 / 레티닐팔미테이트",
        "inci": ["retinol", "retinyl palmitate"],
        "limit": "식약처 주름개선 기능성 고시 함량 기준(예: 레티놀 2,500 IU/g) 초과 여부 및 안정성 확인 필요",
        "basis": "기능성화장품 기준 및 시험방법 / 안전성 심사 대상 확인",
    },
    {
        "ko": "나이아신아마이드",
        "inci": ["niacinamide"],
        "limit": "일반 보습 배합 가능, 미백 기능성 표방 시 고시 함량(2~5%) 및 기능성 보고·심사 필요",
        "basis": "기능성화장품 기준 및 시험방법",
    },
    {
        "ko": "아젤라익애씨드",
        "inci": ["azelaic acid"],
        "limit": "고함량(10~20% 등) 제품은 국내에서 의약품으로 분류될 소지가 있어 함량·효능 표방 확인 필요",
        "basis": "약사법 / 화장품 원료 안전관리 기준",
    },
]


def _tokenize_ingredients(text: str) -> List[str]:
    parts = re.split(r"[,;\n/|]+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _matches(token_lower: str, ko_name: str, inci_list: List[str]) -> bool:
    for kw in [ko_name.split("(")[0].split("/")[0].strip().lower()] + [i.lower() for i in inci_list]:
        if not kw:
            continue
        if len(kw) <= 3:
            if re.search(rf"\b{re.escape(kw)}\b", token_lower):
                return True
        elif kw in token_lower:
            return True
    return False


def screen_cosmetic_ingredients(ingredients_text: str) -> Dict[str, Any]:
    """화장품 전성분 텍스트에서 배합금지 및 배합한도 성분을 대조한다."""
    raw = (ingredients_text or "").strip()
    tokens = _tokenize_ingredients(raw)
    if not tokens:
        return {
            "checked": False,
            "prohibited": [],
            "restricted": [],
            "verdict": "insufficient_info",
            "summary": "전성분이 입력되지 않아 배합금지·한도 대조를 건너뛰었습니다.",
        }

    prohibited_hits: List[Dict[str, Any]] = []
    restricted_hits: List[Dict[str, Any]] = []
    seen_p = set()
    seen_r = set()

    for tok in tokens:
        low = tok.lower()
        for item in PROHIBITED_INGREDIENTS:
            if item["ko"] not in seen_p and _matches(low, item["ko"], item["inci"]):
                seen_p.add(item["ko"])
                prohibited_hits.append({
                    "matched_input": tok,
                    "ingredient_ko": item["ko"],
                    "inci": item["inci"],
                    "reason": item["reason"],
                    "basis": item["basis"],
                })
        for item in RESTRICTED_INGREDIENTS:
            if item["ko"] not in seen_r and _matches(low, item["ko"], item["inci"]):
                seen_r.add(item["ko"])
                restricted_hits.append({
                    "matched_input": tok,
                    "ingredient_ko": item["ko"],
                    "inci": item["inci"],
                    "limit": item["limit"],
                    "basis": item["basis"],
                })

    if prohibited_hits:
        verdict = "blocked_risk"
        summary = f"배합금지 의심 성분 {len(prohibited_hits)}종이 검출되었습니다. 수입·판매 전 반드시 성분 제외 또는 제형 변경이 필요합니다."
    elif restricted_hits:
        verdict = "review_required"
        summary = f"배합한도 지정 성분 {len(restricted_hits)}종이 포함되어 있습니다. 제조사 성적서(COA)에서 배합 함량(%)이 국내 한도 이하인지 확인하세요."
    else:
        verdict = "no_major_hit"
        summary = f"입력된 {len(tokens)}개 성분 중 주요 직구 적발 배합금지·한도 성분이 발견되지 않았습니다(전체 고시 별표 대조는 식약처에서 최종 확인)."

    return {
        "checked": True,
        "token_count": len(tokens),
        "prohibited": prohibited_hits,
        "restricted": restricted_hits,
        "verdict": verdict,
        "summary": summary,
    }
