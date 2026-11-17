"""CLNS — Korea Import Compliance MCP & API · PRODUCT COMPLIANCE INTELLIGENCE · KOREA.

Clearance, simplified.
복잡한 한국 수입 규제를 10초 만에 확인 (Phase 1, 무료 베타).

설계 원칙
1. 판정은 3단계(check_likely / info_needed / low_risk)만 사용하고, '면제·대상 확정' 표현을 쓰지 않는다.
2. 모든 응답은 근거 법령·조항·시행일·원문 URL과 국/영문 면책을 구조적으로 포함한다.
3. 공공 API 원본을 1:1로 중계하지 않는다. 여러 기관 데이터를 결합·정규화한 2차 판정 결과만 반환한다.
4. 외부 API 장애 시 로컬 스냅샷으로 폴백하고, 증거가 오래되면 판정을 info_needed로 낮춘다.
"""

from .version import __version__

__all__ = ["__version__"]
