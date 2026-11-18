"""traps_20.json → 02-ai-trap-corpus-20.md 렌더러.

문서와 코퍼스가 어긋나지 않도록, 케이스 상세는 JSON에서 생성한다.
실행: python3 tools/build_corpus_doc.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
CORPUS = os.path.join(SRC, "traps_20.json")
OUT = os.path.join(ROOT, "02-ai-trap-corpus-20.md")

VERDICT_KO = {
    "check_likely": "확인 대상 가능성 높음",
    "info_needed": "추가 정보 필요",
    "low_risk": "현재 정보로는 가능성 낮음",
}

HEADER = """---
title: "02. 일반 AI가 틀리는 한국 수입·유통 함정 {count}선"
project: 수입·유통 컴플라이언스 검증 엔진
checked_on: {checked}
corpus_version: {version}
---

# 02. 일반 AI가 틀리는 한국 수입·유통 함정 {count}선

## 1. 이 문서의 목적과 검증 방법

이 코퍼스는 **"ChatGPT·Claude 같은 범용 AI나 단순 검색이 한국 수입 실무에서 자신 있게 틀리는 지점"** {count}개를 모은 것이다. 단순히 "AI가 틀린다"고 주장하지 않고, 각 케이스마다 ① 실제 법령·고시 조항, ② 시행일, ③ 원문 URL을 붙였다.

검증 방법:

- 법령·행정규칙은 **법제처 국가법령정보센터**(law.go.kr) 조문 또는 별표 원문을 기준으로 했다.
- 기관 안내·보도자료는 관세청, 식품의약품안전처, 국가기술표준원, 기후에너지환경부, 기획재정부 1차 자료를 우선했다.
- 확인일은 **{checked}** 이다. 법령은 그 뒤로도 개정되므로, 엔진은 모든 응답에 `effective_date`와 `checked_at`을 함께 반환한다.
- **확인하지 못한 것은 코퍼스에 넣지 않았다.** 세부 별표 품목 열거처럼 기관 확인이 필요한 부분은 "추가 정보 필요"로 남긴다.

## 2. 한눈에 보는 {count}개

| ID | 쟁점 | 흔한 AI 오답(요약) | 올바른 방향(요약) | 기본 판정 |
|---|---|---|---|---|
"""


def table_row(t: dict) -> str:
    issue = t["issue_ko"].replace("|", "／")
    wrong = t["common_ai_wrong"].replace("|", "／")
    if len(wrong) > 62:
        wrong = wrong[:60] + "…"
    right = t["correct_answer"].replace("|", "／")
    if len(right) > 78:
        right = right[:76] + "…"
    return f"| {t['id']} | {issue} | {wrong} | {right} | {VERDICT_KO[t['default_verdict']]} |\n"


def detail_block(t: dict) -> str:
    lines = [f"### {t['id']} · {t['issue_ko']}", ""]
    lines.append(f"**흔히 하는 오해**: {t['title']}")
    lines.append("")
    lines.append(f"- **상황**: {t['scenario']}")
    lines.append(f"- **일반 AI의 오답**: {t['common_ai_wrong']}")
    lines.append(f"- **실제 정답**: {t['correct_answer']}")
    lines.append("- **근거**:")
    for b in t["legal_basis"]:
        quote = b.get("quote", "").strip()
        if len(quote) > 190:
            quote = quote[:188] + "…"
        lines.append(f"  - {b['law']} {b['article']} (시행 {b['effective_date']}) — \"{quote}\"  ")
        lines.append(f"    {b['url']}")
    lines.append(f"- **엔진 판정 로직**: 신호 `{', '.join(t['engine']['signals'][:5])}` 감지 → 기본 판정 **{VERDICT_KO[t['default_verdict']]}**")
    req = t["engine"].get("required_inputs", [])
    if req:
        lines.append(f"  - 판정을 확정하려면 필요한 입력: {', '.join(r['field'] for r in req)} — 없으면 '추가 정보 필요'로 낮춤")
    if t["engine"].get("low_risk_conditions"):
        conds = []
        for c in t["engine"]["low_risk_conditions"]:
            conds.append(" + ".join(c.get("all_of", [])) + (" (단, " + ", ".join(c.get("none_of", [])) + " 제외)" if c.get("none_of") else ""))
        lines.append(f"  - '가능성 낮음'으로 내려가는 조건: {'; '.join(conds)}")
    if t.get("next_steps"):
        lines.append(f"- **사용자가 다음에 할 일**: {' → '.join(t['next_steps'])}")
    if t["engine"].get("notes"):
        lines.append(f"- **메모**: {t['engine']['notes']}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


PATTERNS = """
## 4. AI가 반복해서 틀리는 5가지 패턴

{count}개를 관통하는 오류 구조는 다섯 가지다. 이 다섯 개가 엔진의 룰 설계 근거이기도 하다.

### 패턴 1. "자가사용"과 "판매"를 같은 것으로 본다
TRAP-01·02·07·10·12가 여기에 걸린다. AI는 "소량", "자가소비", "개인 직구"라는 단어를 보면 규제가 없다고 결론내린다. 그러나 한국 제도에서 **자가소비 예외는 '판매·영업 목적이 아닐 것'을 전제**로 하고, 구매대행을 끼우면 그 예외 자체가 사라진다(수입식품법 시행규칙 별표 8의2 제2호). 화장품도 자가소비 직구와 판매용 유통은 등록 요건이 완전히 다르다.

### 패턴 2. 해외 인증 = 한국 인증으로 등치한다
TRAP-06이 대표적이다. CE·FCC는 한국 전파법상 적합성평가를 대체하지 않는다. TRAP-03(어린이제품)·TRAP-04(전기용품)도 "해외에서 안전성 검사를 받았으니 KC도 자동"이라고 답하는 경우가 많다. 상호인정협정·MRA 같은 예외는 **별도 확인 사항**이지 기본값이 아니다.

### 패턴 3. 금액 기준만 보고 품목 배제를 놓친다
TRAP-12. "150달러 이하면 목록통관·면세"는 절반만 맞다. 의약품·건강기능식품·식품류·일부 화장품·방송통신기자재는 **금액과 무관하게 목록통관 배제**다. AI는 금액 계산은 잘하지만 배제대상 표를 먼저 보지 않는다.

### 패턴 4. 법령 이름은 알지만 시행일·개정을 반영하지 않는다
TRAP-15(2026-04-24 담배 정의 확대), TRAP-14(2026-11-12 의약품 휴대 반입 확대, 직구는 여전히 불인정), TRAP-02(직접구매 해외화장품 정의 신설)가 여기 해당한다. 학습 시점이 오래된 모델일수록 "작년 기준 정답"을 자신 있게 말한다. 그래서 엔진은 **조항+시행일을 함께** 반환하고, 시행일이 확인 시점과 멀면 별도 표시한다.

### 패턴 5. "정품·승인·등록"을 "요건 충족"으로 착각한다
TRAP-20(정품이면 병행수입 항상 가능), TRAP-08(FDA 승인 첨가물이면 국내 사용 가능), TRAP-17(국내 가공이면 한국산). 각각 ① 상표권자 관계, ② 국내 공전 등재·사용기준, ③ 협정별 원산지결정기준이라는 **별개의 판정 체계**가 있다. "정품/승인/가공"은 그 체계의 입력값이지 결론이 아니다.

## 5. 코퍼스 운영 규칙

1. **조항이 바뀌면 케이스를 고친다.** 법령 개정 공포를 감지하면(Phase 2 웹훅) 해당 `legal_basis.effective_date`를 갱신하고, 구 시행일 기준 답변은 이력으로 남긴다.
2. **판정 언어는 3단계만 쓴다.** `check_likely` / `info_needed` / `low_risk`. "대상입니다", "면제됩니다", "확정"은 생성 문장에서 금지하며 테스트로 강제한다(`find_conclusive_phrasing`).
3. **케이스를 늘릴 때는 근거 3개 이상**을 요구한다. 조항·시행일·URL이 없으면 코퍼스에 넣지 않는다.
4. **AI 오답은 실제로 관찰된 것만 쓴다.** 그럴듯한 허수아비를 만들지 않는다. 새 케이스는 실제 상담·커뮤니티 질문·기존 모델 답변에서 수집한다.

## 6. 한계

- 조문·별표의 **대표 항목**까지만 인용했다. 개별 모델·성분·공정의 최종 판정은 인증기관·관세사 확인이 필요하다.
- HS 분류는 코퍼스가 직접 판정하지 않는다. HS 10자리는 관세청 품목분류 확인이 선행되어야 한다.
- 지방세·부가세·개별소비세 계산은 다루지 않는다(Phase 2 후보).
- TRAP-14의 2026-11-12 제도 변경은 시행 초기라 세부 운영 기준이 추가로 나올 수 있다. 분기마다 재확인한다.
"""


def main() -> None:
    with open(CORPUS, encoding="utf-8") as handle:
        data = json.load(handle)
    traps = data["traps"]
    count = len(traps)
    parts = [HEADER.format(checked=data["verified_on"], version=data["corpus_version"], count=count)]
    parts.extend(table_row(t) for t in traps)
    parts.append("\n## 3. 케이스 상세\n\n")
    for trap in traps:
        parts.append(detail_block(trap))
    parts.append(PATTERNS.replace("{count}", str(count)))
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write("".join(parts))
    print(f"wrote {OUT} ({len(traps)} cases)")


if __name__ == "__main__":
    main()
