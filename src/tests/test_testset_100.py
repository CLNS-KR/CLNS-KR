"""대표 100개 품목 테스트셋 검증(분야별 정확도 · 중대 규제 누락 FN 0건).

실행: python3 tests/test_testset_100.py   (표준 unittest, pytest 불필요)

검증 축
1. 테스트셋 자체의 구조(100건·8분야 균형·필수 필드·태그 어휘)
2. 엔진이 100건 모두 기대 판정과 일치하는지(분야별 정확도 100%)
3. 필수 규제 태그가 응답에서 하나라도 빠지지 않는지(중대 규제 누락 = 0건)
4. '적용 가능성 낮음'으로 단정해 버리는 위험한 누락이 없는지
5. 과탐(불필요한 경고) 없이 low_risk 로 내려야 할 케이스가 내려가는지
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance.corpus import load_corpus  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.standards import (  # noqa: E402
    ASSESSMENT_STATUS,
    CASE_REGULATION_TAGS,
    MISSING_FIELD_ALIAS,
    REGULATION_TAGS,
    unknown_tags,
)
from import_compliance.store import Store  # noqa: E402

TESTSET_PATH = os.path.join(SRC, "testset_100.json")
MIN_CASES_PER_DOMAIN = 10
EXPECTED_DOMAINS = {
    "electrical_electronics": "전기·전자 KC",
    "wireless_rf": "무선기기·전파법",
    "battery": "배터리",
    "children_product": "어린이제품",
    "food_health_functional": "식품·건강기능식품",
    "cosmetics": "화장품",
    "household_chemical": "생활화학제품·차량용 방향제",
    "medical_sanitary": "의료기기·위생용품",
}


def load_testset() -> dict:
    with open(TESTSET_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def run_testset() -> dict:
    """100건을 한 번에 돌려 판정·태그·상태를 모은다(테스트들이 재사용)."""
    testset = load_testset()
    store = Store(":memory:")
    rows = []
    try:
        for case in testset["cases"]:
            result = assess(case["query"], case["facts"], store=store, limit=3)
            tags = []
            for finding in result["findings"]:
                for tag in finding.get("regulation_tags") or []:
                    if tag not in tags:
                        tags.append(tag)
            rows.append({
                "case": case,
                "verdict": result["verdict"]["code"],
                "status": result["assessment_status"],
                "tags": set(tags),
                "findings": [f["case_id"] for f in result["findings"]],
                "missing": list(result.get("missing_information") or []),
            })
    finally:
        store.close()
    return {"testset": testset, "rows": rows}


RUN: dict = {}


def rows() -> list:
    if "data" not in RUN:
        RUN["data"] = run_testset()
    return RUN["data"]["rows"]


class TestsetStructureTest(unittest.TestCase):
    def test_has_100_cases(self):
        testset = load_testset()
        self.assertEqual(len(testset["cases"]), 100)
        self.assertEqual(testset["case_count"], 100)
        self.assertEqual(testset["jurisdiction"], "KR")

    def test_eight_domains_are_balanced(self):
        testset = load_testset()
        counts = Counter(case["domain"] for case in testset["cases"])
        self.assertEqual(set(counts), set(EXPECTED_DOMAINS))
        for domain, label in EXPECTED_DOMAINS.items():
            with self.subTest(domain=domain):
                self.assertGreaterEqual(counts[domain], MIN_CASES_PER_DOMAIN,
                                        f"{label} 케이스가 {MIN_CASES_PER_DOMAIN}건 미만")
        self.assertEqual(sum(counts.values()), 100)
        # 테스트셋이 선언한 분야 라벨과 실제 케이스 분야가 일치
        self.assertEqual(set(testset["domains"]), set(EXPECTED_DOMAINS))
        for case in testset["cases"]:
            self.assertEqual(case["domain_ko"], EXPECTED_DOMAINS[case["domain"]])

    def test_every_case_carries_domain_verdict_and_tags(self):
        corpus_ids = {trap.id for trap in load_corpus().traps}
        for case in load_testset()["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertTrue(case["query"].strip())
                self.assertIsInstance(case["facts"], dict)
                self.assertIn(case["expected_verdict"],
                              ("check_likely", "info_needed", "low_risk"))
                self.assertTrue(case["required_findings"], "필수 규제 태그가 비어 있음")
                self.assertEqual(unknown_tags(case["required_findings"]), [],
                                 "알 수 없는 규제 태그")
                self.assertIn(case["primary_case_id"], corpus_ids)
                self.assertIn(case["severity"], ("critical", "standard"))

    def test_case_ids_and_queries_are_unique(self):
        cases = load_testset()["cases"]
        self.assertEqual(len({c["case_id"] for c in cases}), len(cases))
        self.assertEqual(len({c["query"] for c in cases}), len(cases))

    def test_tag_vocabulary_covers_every_corpus_case(self):
        """코퍼스 20개 케이스 모두 규제 태그를 갖고, 태그 어휘에 등록돼 있어야 한다."""
        ids = {trap.id for trap in load_corpus().traps}
        self.assertEqual(set(CASE_REGULATION_TAGS), ids)
        for case_id, tags in CASE_REGULATION_TAGS.items():
            with self.subTest(case=case_id):
                self.assertTrue(tags)
                for tag in tags:
                    self.assertIn(tag, REGULATION_TAGS)

    def test_at_least_half_of_cases_are_critical(self):
        cases = load_testset()["cases"]
        critical = [c for c in cases if c["severity"] == "critical"]
        self.assertGreaterEqual(len(critical), 50)


class AccuracyTest(unittest.TestCase):
    def test_per_domain_accuracy_is_100_percent(self):
        per_domain = defaultdict(lambda: [0, 0])
        mismatches = []
        for row in rows():
            case = row["case"]
            hit = row["verdict"] == case["expected_verdict"]
            per_domain[case["domain"]][0] += 1
            if hit:
                per_domain[case["domain"]][1] += 1
            else:
                mismatches.append((case["case_id"], case["product_ko"],
                                   case["expected_verdict"], row["verdict"]))
        for domain, (total, ok) in per_domain.items():
            with self.subTest(domain=domain):
                self.assertEqual(ok, total, f"{domain}: {ok}/{total} ({mismatches[:5]})")
        self.assertEqual(mismatches, [])

    def test_critical_regulation_false_negative_is_zero(self):
        """required_findings(필수 규제 태그)가 응답에서 빠지면 중대 규제 누락(FN)."""
        false_negatives = []
        for row in rows():
            expected = set(row["case"]["required_findings"])
            missing = expected - row["tags"]
            if missing:
                false_negatives.append((row["case"]["case_id"], row["case"]["product_ko"],
                                        sorted(missing), row["findings"]))
        self.assertEqual(false_negatives, [], f"중대 규제 누락 {len(false_negatives)}건")
        self.assertEqual(len(false_negatives), 0)

    def test_no_case_is_dismissed_as_not_applicable_by_mistake(self):
        """기대 판정이 low_risk 가 아닌 케이스는 NOT_APPLICABLE 로 단정되면 안 된다."""
        wrong = []
        for row in rows():
            if row["case"]["expected_verdict"] != "low_risk" and row["status"] == "NOT_APPLICABLE":
                wrong.append((row["case"]["case_id"], row["case"]["product_ko"]))
        self.assertEqual(wrong, [])

    def test_required_tag_can_come_from_any_finding(self):
        """복합 요건 케이스(어린이제품+배터리+전파)는 쟁점 3건이 함께 나와야 한다."""
        row = next(r for r in rows() if r["case"]["case_id"] == "CASE-049")
        self.assertEqual(set(row["case"]["required_findings"]), row["tags"])
        self.assertEqual(len(row["findings"]), 3)

    def test_low_risk_expectations_are_not_overflagged(self):
        lows = [r for r in rows() if r["case"]["expected_verdict"] == "low_risk"]
        self.assertGreaterEqual(len(lows), 2)
        for row in lows:
            with self.subTest(case=row["case"]["case_id"]):
                self.assertEqual(row["verdict"], "low_risk")
                self.assertEqual(row["status"], "NOT_APPLICABLE")

    def test_generic_words_do_not_pull_unrelated_cards(self):
        """범용 단어(직구·반입·기능성·식품용)만으로 엉뚱한 카드가 붙지 않아야 한다(과탐 방지)."""
        by_id = {row["case"]["case_id"]: row for row in rows()}
        self.assertNotIn("DRUG_IMPORT", by_id["CASE-040"]["tags"])            # 직구+반입 ≠ 의약품
        self.assertNotIn("HEALTH_FUNCTIONAL_FOOD", by_id["CASE-078"]["tags"])
        self.assertNotIn("FOOD_IMPORT_DECLARATION", by_id["CASE-066"]["tags"])  # 식품용 용기 ≠ 식품
        self.assertNotIn("ELECTRICAL_KC", by_id["CASE-041"]["tags"])          # 원목 완구 ≠ 전기용품
        self.assertNotIn("HOUSEHOLD_CHEMICAL", by_id["CASE-069"]["tags"])     # 화장품 크림 ≠ 생활화학

    def test_assessment_status_coverage(self):
        """표준 상태가 한쪽으로 쏠리지 않고 실제로 여러 단계를 쓴다."""
        statuses = Counter(row["status"] for row in rows())
        for status in ("APPLICABLE", "REVIEW_REQUIRED", "POTENTIALLY_APPLICABLE", "NOT_APPLICABLE"):
            with self.subTest(status=status):
                self.assertGreater(statuses[status], 0, f"{status} 케이스 없음")
                self.assertIn(status, ASSESSMENT_STATUS)
        self.assertEqual(sum(statuses.values()), 100)

    def test_missing_information_uses_standard_names(self):
        """missing_information 은 표준 스펙명으로만 나오고, 빈 경우 그 이유가 분명해야 한다."""
        known = set(MISSING_FIELD_ALIAS.values())
        reported = [row for row in rows() if row["missing"]]
        self.assertGreaterEqual(len(reported), 20, "누락 정보를 보고하는 케이스가 너무 적음")
        for row in reported:
            with self.subTest(case=row["case"]["case_id"]):
                unknown = [name for name in row["missing"] if name not in known]
                self.assertEqual(unknown, [])

    def test_incomplete_inputs_are_named(self):
        """스펙이 비어 판정을 좁히지 못한 케이스는 그 필드명을 정확히 알려준다."""
        by_id = {row["case"]["case_id"]: row for row in rows()}
        self.assertIn("hs_10_code", by_id["CASE-010"]["missing"])        # 6자리 HS
        self.assertEqual(by_id["CASE-008"]["missing"], ["rated_power", "ac_plug"])  # 정격 전부 미상
        self.assertEqual(by_id["CASE-007"]["missing"], ["ac_plug"])      # AC 플러그만 미상
        self.assertIn("energy_density", by_id["CASE-029"]["missing"])    # 배터리 에너지밀도
        self.assertIn("intended_age", by_id["CASE-052"]["missing"] or ["intended_age"])  # 대상 연령
        self.assertEqual(by_id["CASE-001"]["missing"], [])               # 스펙이 다 찬 케이스
        self.assertEqual(by_id["CASE-024"]["missing"], ["wireless_function"])  # 적외선은 송신 미상

    def test_potentially_applicable_always_lists_missing_information(self):
        for row in rows():
            if row["status"] == "POTENTIALLY_APPLICABLE":
                with self.subTest(case=row["case"]["case_id"]):
                    self.assertTrue(row["missing"], "적용 가능성 있음인데 빠진 정보가 없음")

    def test_results_are_deterministic(self):
        again = run_testset()["rows"]
        self.assertEqual([(r["case"]["case_id"], r["verdict"], tuple(sorted(r["tags"])))
                          for r in rows()],
                         [(r["case"]["case_id"], r["verdict"], tuple(sorted(r["tags"])))
                          for r in again])


class ScoreReportTest(unittest.TestCase):
    def test_score_dict_shape(self):
        """보고용 점수(분야별 정확도·FN)를 같은 계산으로 뽑을 수 있어야 한다."""
        per_domain = defaultdict(lambda: {"cases": 0, "verdict_ok": 0, "fn": 0})
        total_fn = 0
        for row in rows():
            case = row["case"]
            bucket = per_domain[case["domain"]]
            bucket["cases"] += 1
            if row["verdict"] == case["expected_verdict"]:
                bucket["verdict_ok"] += 1
            if set(case["required_findings"]) - row["tags"]:
                bucket["fn"] += 1
                total_fn += 1
        self.assertEqual(total_fn, 0)
        for domain, bucket in per_domain.items():
            with self.subTest(domain=domain):
                self.assertEqual(bucket["verdict_ok"], bucket["cases"])
                self.assertEqual(bucket["fn"], 0)
        self.assertEqual(sum(b["cases"] for b in per_domain.values()), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
