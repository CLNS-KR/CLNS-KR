"""데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class LegalBasis:
    law: str
    article: str
    effective_date: str
    url: str
    quote: str = ""
    verified_on: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "law": self.law,
            "article": self.article,
            "effective_date": self.effective_date,
            "url": self.url,
            "quote": self.quote,
            "verified_on": self.verified_on,
        }


@dataclass(frozen=True)
class RequiredInput:
    field: str
    prompt: str
    values: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Trap:
    id: str
    title: str
    issue_ko: str
    category: str
    scenario: str
    common_ai_wrong: str
    correct_answer: str
    default_verdict: str
    legal_basis: List[LegalBasis]
    signals: List[str]
    required_inputs: List[RequiredInput]
    low_risk_conditions: List[Dict[str, List[str]]]
    next_steps: List[str]
    notes: str = ""
    fact_rules: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Trap":
        engine = raw.get("engine", {})
        return cls(
            id=raw["id"],
            title=raw["title"],
            issue_ko=raw.get("issue_ko", raw["title"]),
            category=raw["category"],
            scenario=raw["scenario"],
            common_ai_wrong=raw["common_ai_wrong"],
            correct_answer=raw["correct_answer"],
            default_verdict=raw["default_verdict"],
            legal_basis=[
                LegalBasis(
                    law=b["law"],
                    article=b["article"],
                    effective_date=b.get("effective_date", ""),
                    url=b["url"],
                    quote=b.get("quote", ""),
                    verified_on=b.get("verified_on", ""),
                )
                for b in raw.get("legal_basis", [])
            ],
            signals=list(engine.get("signals", [])),
            required_inputs=[
                RequiredInput(
                    field=r["field"],
                    prompt=r.get("prompt", ""),
                    values=list(r.get("values", [])),
                )
                for r in engine.get("required_inputs", [])
            ],
            low_risk_conditions=list(engine.get("low_risk_conditions", [])),
            next_steps=list(raw.get("next_steps", [])),
            notes=engine.get("notes", ""),
            fact_rules=list(engine.get("fact_rules", [])),
        )


@dataclass
class Finding:
    trap: Trap
    verdict: str
    confidence: float
    matched_signals: List[str]
    missing_inputs: List[RequiredInput]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.trap.id,
            "title": self.trap.title,
            "issue_ko": self.trap.issue_ko,
            "category": self.trap.category,
            "verdict": self.verdict,
            "verdict_label_ko": VERDICT_LABEL_KO[self.verdict],
            "verdict_label_en": VERDICT_LABEL_EN[self.verdict],
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "matched_signals": self.matched_signals,
            "missing_inputs": [
                {"field": m.field, "prompt": m.prompt, "allowed_values": m.values}
                for m in self.missing_inputs
            ],
            "misconception": self.trap.common_ai_wrong,
            "explanation": self.trap.correct_answer,
            "scenario": self.trap.scenario,
            "next_steps": self.trap.next_steps,
            "notes": self.trap.notes,
            "legal_basis": [b.to_dict() for b in self.trap.legal_basis],
        }


VERDICT_LABEL_KO: Dict[str, str] = {
    "check_likely": "확인 대상 가능성 높음",
    "info_needed": "추가 정보 필요",
    "low_risk": "현재 정보로는 가능성 낮음",
}

VERDICT_LABEL_EN: Dict[str, str] = {
    "check_likely": "Likely requires review",
    "info_needed": "More information needed",
    "low_risk": "Low likelihood on current information",
}

VERDICT_SEVERITY: Dict[str, int] = {"low_risk": 0, "info_needed": 1, "check_likely": 2}
