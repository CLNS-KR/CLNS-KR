"""면책·표현 가드·서비스 경계 정의."""
from __future__ import annotations

import re
from typing import Dict, List

DISCLAIMER_KO = (
    "본 결과는 사전 참고용입니다. 법적 효력이 없으며, 최종 법적 판단과 통관·인증 가능 여부는 "
    "관세사, 관세청, 국가기술표준원·인증기관, 식품의약품안전처 등 소관 기관의 확인이 필요합니다. "
    "본 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않습니다."
)

DISCLAIMER_EN = (
    "This output is preliminary reference information only. It has no legal effect and is not "
    "customs advice. Final determinations on classification, clearance, certification and "
    "labeling must be confirmed with a licensed customs broker and the competent Korean "
    "authorities (Korea Customs Service, KATS/certification bodies, MFDS)."
)

# 우리가 생성하는 문장(판정 요약·안내·다음 단계)에 등장하면 안 되는 단정 표현.
CONCLUSIVE_PATTERNS: List[str] = [
    "확정",
    "면제됩니다",
    "면제입니다",
    "면제이다",
    "대상입니다",
    "대상이다",
    "대상이 아닙니다",
    "대상이 아니다",
    "필요 없습니다",
    "필요없",
    "보장합니다",
    "100%",
]

NEGATION_HINTS = ("확정하지", "확정할 수 없", "단정", "아니", "않습니다", "금지", "제외", "불가", "어렵")

SENTENCE_SPLIT = re.compile(r"[.。!?\n]")


def find_conclusive_phrasing(text: str) -> List[str]:
    """단정 표현을 찾는다. 단, 부정·한정 문맥('확정하지 않습니다' 등)은 허용한다."""
    hits: List[str] = []
    for sentence in SENTENCE_SPLIT.split(text or ""):
        if not sentence.strip():
            continue
        if any(hint in sentence for hint in NEGATION_HINTS):
            continue
        for pattern in CONCLUSIVE_PATTERNS:
            if pattern in sentence:
                hits.append(pattern)
    return hits


TIER_BOUNDARIES: Dict[str, Dict[str, object]] = {
    "free": {
        "price_krw": 0,
        "monthly_calls": 250,
        "bulk_check": False,
        "pdf_report": False,
        "webhook_alerts": False,
        "api_key_required": False,
        "payment_wall": False,
    },
    "pro_waitlist": {
        "price_krw": None,
        "status": "오픈 예정 · 대기자 등록만",
        "bulk_check": True,
        "pdf_report": True,
        "webhook_alerts": True,
        "api_key_required": True,
        "payment_wall": True,
    },
}

PAID_TIER_NOTICE_KO = (
    "유료 티어는 아직 판매하지 않습니다. 결제창을 열지 않고 '오픈 예정 · 대기자 등록'으로만 "
    "수요를 측정하며, 대기자 등록에는 이메일 외 개인정보를 받지 않습니다."
)

SCOPE_LIMITS_KO = [
    "품목분류(HS) 확정, 인증 대행, 통관 대리, 법률 자문을 수행하지 않습니다.",
    "공공데이터 원본을 그대로 중계하지 않고, 결합·정규화한 판정 결과만 제공합니다.",
    "API 장애·개정 지연 시 캐시 시점을 명시하고 판정을 '추가 정보 필요'로 낮춥니다.",
    "확인되지 않은 고시·별표는 추정으로 채우지 않습니다.",
    "규제 카드는 식품·화장품·전기용품·전파·생활화학·통관·원산지·지재권 20개 쟁점 기준입니다. "
    "의료기기·위생용품·의약외품은 통관(세관장확인·목록통관) 축만 확인하며, 해당 법령의 "
    "허가·신고 요건은 식품의약품안전처 등 소관 기관에서 별도로 확인해야 합니다.",
]
