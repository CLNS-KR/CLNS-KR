"""회귀 테스트: 함정 22케이스 판정 + 리스크 가드 + 쿼터/캐시 폴백.

실행: python3 tests/test_engine.py   (pytest 불필요, 표준 unittest)
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance.api import BILLABLE_TOOLS, TOOL_DEFS, call_tool, mcp_manifest  # noqa: E402
from import_compliance.corpus import load_corpus, normalize  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.policy import (  # noqa: E402
    DISCLAIMER_EN,
    DISCLAIMER_KO,
    TIER_BOUNDARIES,
    find_conclusive_phrasing,
)
from import_compliance.store import KST, QuotaExceeded, SourceGateway, Store  # noqa: E402

# (case_id, query, facts, 기대하는 해당 케이스의 판정)
CASES = [
    ("TRAP-01", "중국에서 과자랑 소스를 구매대행으로 들여와 오픈마켓에서 판매하려고 해", {}, "check_likely"),
    ("TRAP-02", "해외 직구로 산 화장품 크림을 중고거래로 판매하려고 해", {"functional": "no"}, "check_likely"),
    ("TRAP-03", "유아용 원목 완구를 수입해서 팔려고 해", {}, "info_needed"),
    ("TRAP-04", "USB-C 충전기를 중국에서 수입해 판매하려고 해", {"rated_power": "65W", "ac_plug": "yes"}, "check_likely"),
    ("TRAP-05", "리튬이온 배터리가 내장된 블루투스 이어폰을 수입해 판매", {"battery_type": "리튬이온 팩", "energy_density": "700Wh/L 이상"}, "check_likely"),
    ("TRAP-06", "블루투스 스피커를 중국에서 수입해 판매하려고 해", {}, "check_likely"),
    ("TRAP-07", "식품을 수입해서 판매하려는데 영업등록이 필요한가요", {"business_type": "수입판매업"}, "check_likely"),
    ("TRAP-08", "미국 FDA에서 GRAS 인정받은 색소를 식품에 사용하려고 해", {"additive_names": ["황색4호"], "food_type": "과자류"}, "check_likely"),
    ("TRAP-09", "해외 건강기능식품 비타민을 수입해 상세페이지에 기능성 광고를 하려고 해", {"claim_type": "기능성", "ingredient": "비타민C"}, "check_likely"),
    ("TRAP-10", "수입 식품을 원포장 그대로 한글표시 없이 유통하려고 해", {}, "check_likely"),
    ("TRAP-11", "식품용 밀폐용기를 수입해 판매하려고 해", {"food_contact": "yes", "material": "PP"}, "check_likely"),
    ("TRAP-12", "150달러 이하 건강기능식품을 목록통관으로 들여오려고 해", {"item": "건강기능식품", "price_usd": 150}, "check_likely"),
    ("TRAP-13", "개인통관고유부호 없이 생년월일로 해외직구 주문을 하려고 해", {"has_pccc": "no"}, "check_likely"),
    ("TRAP-14", "위고비를 해외 사이트에서 직구로 사려고 해", {"drug_class": "yes"}, "check_likely"),
    ("TRAP-15", "합성니코틴 액상형 전자담배를 수입해 판매하려고 해", {}, "check_likely"),
    ("TRAP-16", "주방 세정제와 방향제를 수입해 판매하려고 해", {"product_type": "세정제", "has_cert": "no"}, "check_likely"),
    ("TRAP-17", "중국산 원재료로 한국에서 가공해 한미 FTA 원산지증명서를 발급하려고 해", {}, "info_needed"),
    ("TRAP-18", "중국 부품을 국내에서 조립해 Made in Korea 표시를 하려고 해", {"process": "단순 조립", "material_origin": "중국"}, "check_likely"),
    ("TRAP-19", "HS 850760 품목의 수입요건을 확인하려고 해", {}, "info_needed"),
    ("TRAP-20", "정품 병행수입을 하려는데 상표권 문제가 없을까", {}, "info_needed"),
    ("TRAP-21", "해외에서 산 전자혈압계를 국내 오픈마켓에서 판매하려고 해", {}, "check_likely"),
    ("TRAP-22", "기저귀와 칫솔을 수입해 판매하려고 해", {}, "check_likely"),
]


class CorpusTest(unittest.TestCase):
    def test_corpus_has_22_cases_with_evidence(self):
        corpus = load_corpus()
        self.assertEqual(len(corpus.traps), 22)
        for trap in corpus.traps:
            self.assertTrue(trap.legal_basis, trap.id)
            for basis in trap.legal_basis:
                self.assertTrue(basis.url.startswith("http"), (trap.id, basis.url))
                self.assertRegex(basis.effective_date, r"^\d{4}-\d{2}-\d{2}$", trap.id)
            self.assertIn(trap.default_verdict, ("check_likely", "info_needed", "low_risk"))
            self.assertEqual(find_conclusive_phrasing(trap.correct_answer), [], trap.id)

    def test_no_duplicate_ids(self):
        corpus = load_corpus()
        self.assertEqual(len({t.id for t in corpus.traps}), 22)

    def test_customs_law_effective_dates_match_legal_api(self):
        """법제처 현행 조문 시행일자(2026-11-18 확인)와 코퍼스 인용이 어긋나지 않게 고정한다."""
        expected = {
            ("TRAP-19", "관세법", "제226조"): "2026-10-02",
            ("TRAP-20", "관세법", "제235조"): "2026-10-02",
            ("TRAP-12", "관세법", "제94조제4호"): "2026-10-02",
            ("TRAP-12", "관세법 시행규칙", "제45조제2항제1호"): "2026-07-31",
            ("TRAP-06", "전파법", "제58조의2"): "2026-10-22",
        }
        corpus = load_corpus()
        seen = {}
        for trap in corpus.traps:
            for basis in trap.legal_basis:
                seen[(trap.id, basis.law, basis.article)] = basis.effective_date
        for key, want in expected.items():
            with self.subTest(key=key):
                self.assertIn(key, seen)
                self.assertEqual(seen[key], want)


class TrapVerdictTest(unittest.TestCase):
    def test_all_22_cases(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        for case_id, query, facts, expected in CASES:
            with self.subTest(case=case_id):
                result = assess(query, facts, store=store)
                by_id = {f["case_id"]: f for f in result["findings"]}
                self.assertIn(case_id, by_id, f"{case_id} not matched for query: {query}")
                self.assertEqual(by_id[case_id]["verdict"], expected,
                                 f"{case_id}: {by_id[case_id]['verdict']} != {expected} ({by_id[case_id]['reason']})")

    def test_low_risk_path_and_overall(self):
        result = assess("150달러 이하 의류 목록통관", store=Store(":memory:"))
        self.assertEqual(result["verdict"]["code"], "low_risk")
        self.assertEqual(result["findings"][0]["case_id"], "TRAP-12")

    def test_missing_inputs_downgrade_to_info_needed(self):
        result = assess("유아용 원목 완구 수입 판매", store=Store(":memory:"))
        self.assertEqual(result["verdict"]["code"], "info_needed")
        missing = [m["field"] for f in result["findings"] for m in f["missing_inputs"]]
        self.assertIn("target_age", missing)

    def test_unknown_query_returns_info_needed_without_fabrication(self):
        result = assess("우주선 부품 수입", store=Store(":memory:"))
        self.assertEqual(result["verdict"]["code"], "info_needed")
        self.assertEqual(result["findings"], [])
        self.assertIn("특정하지 못했습니다", result["answer"]["headline"])

    def test_hs_10_digit_satisfies_input(self):
        six = assess("HS 850760 수입요건", store=Store(":memory:"))
        ten = assess("HS 8507609000 수입요건", store=Store(":memory:"))
        six_case = {f["case_id"]: f for f in six["findings"]}.get("TRAP-19")
        ten_case = {f["case_id"]: f for f in ten["findings"]}.get("TRAP-19")
        self.assertIsNotNone(six_case)
        self.assertIsNotNone(ten_case)
        self.assertIn("hs_code", [m["field"] for m in six_case["missing_inputs"]])
        self.assertNotIn("hs_code", [m["field"] for m in ten_case["missing_inputs"]])

    def test_national_suffix_does_not_trigger_origin_trap(self):
        """'미국산·중국산'의 '국산' 부분일치로 원산지 함정(TRAP-18)이 오탐되지 않는다."""
        result = assess("미국산 수딩크림 화장품을 수입해 판매하려고 해", store=Store(":memory:"))
        self.assertNotIn("TRAP-18", [f["case_id"] for f in result["findings"]])
        still = assess("중국 부품을 국내에서 조립해 Made in Korea 표시를 하려고 해",
                       {"process": "단순 조립", "material_origin": "중국"}, store=Store(":memory:"))
        self.assertIn("TRAP-18", [f["case_id"] for f in still["findings"]])

    def test_fact_rule_downgrades_rf_trap(self):
        """rf_tx=no 사실을 주면 전파법 쟁점(TRAP-06)은 low_risk로 내려간다."""
        with_fact = assess("무선 미니 선풍기 수입 판매", {"rf_tx": "no"}, store=Store(":memory:"))
        without = assess("무선 미니 선풍기 수입 판매", {}, store=Store(":memory:"))
        by_id = {f["case_id"]: f for f in with_fact["findings"]}
        by_id_no = {f["case_id"]: f for f in without["findings"]}
        self.assertIn("TRAP-06", by_id)
        self.assertEqual(by_id["TRAP-06"]["verdict"], "low_risk")
        self.assertEqual(by_id_no["TRAP-06"]["verdict"], "check_likely")


class RiskGuardTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_disclaimer_and_no_conclusive_phrasing(self):
        for case_id, query, facts, _ in CASES:
            with self.subTest(case=case_id):
                result = assess(query, facts, store=self.store)
                self.assertIn("사전 참고용", result["disclaimer"]["ko"])
                self.assertIn("preliminary reference", result["disclaimer"]["en"])
                self.assertIn("관세사", result["disclaimer"]["ko"])
                generated = result["answer"]["headline"] + " " + " ".join(result["answer"]["guidance"])
                generated += " " + " ".join(result["next_actions"])
                self.assertEqual(find_conclusive_phrasing(generated), [], generated)
                for finding in result["findings"]:
                    self.assertNotIn("확정", finding["verdict_label_ko"])

    def test_every_finding_carries_law_article_date_url(self):
        result = assess("블루투스 스피커 수입 판매", store=self.store)
        self.assertTrue(result["evidence"])
        for item in result["evidence"]:
            self.assertTrue(item["law"])
            self.assertTrue(item["article"])
            self.assertRegex(item["effective_date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(item["url"].startswith("http"))

    def test_no_raw_api_passthrough(self):
        result = assess("식품용 밀폐용기 수입", {"food_contact": "yes"}, store=self.store)
        blob = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("payload_json", blob)
        for source in result["data_provenance"]["sources"]:
            self.assertNotIn("data", source)

    def test_determinative_flag_false(self):
        result = assess("블루투스 스피커 수입 판매", store=self.store)
        self.assertFalse(result["verdict"]["determinative"])


class CacheFallbackTest(unittest.TestCase):
    def test_stale_snapshot_downgrades_verdict(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.upsert_source("customs_requirements", "관세청 세관장확인대상물품", "관세청",
                            "이용허락범위 제한 없음", "https://apis.data.go.kr", "realtime")
        query = "HS 8507609000 수입요건"
        store.put_snapshot("customs_requirements", normalize(query)[:60], {"items": [{"law": "전기용품및생활용품안전관리법"}]})
        old = (datetime.now(KST) - timedelta(days=5)).isoformat(timespec="seconds")
        store.conn.execute("UPDATE api_snapshots SET fetched_at=?", (old,))
        store.conn.commit()

        gateway = SourceGateway(store, stale_hours=72)
        snapshot = gateway.get("customs_requirements", normalize(query)[:60])
        self.assertEqual(snapshot["state"], "cached_fallback")
        self.assertFalse(snapshot["fresh"])
        self.assertGreater(snapshot["age_hours"], 72)

        result = assess(query, store=store)
        self.assertEqual(result["verdict"]["code"], "info_needed")

    def test_fresh_snapshot_keeps_verdict(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.upsert_source("customs_requirements", "관세청 세관장확인대상물품", "관세청",
                            "이용허락범위 제한 없음", "https://apis.data.go.kr", "realtime")
        query = "HS 8507609000 수입요건"
        store.put_snapshot("customs_requirements", normalize(query)[:60], {"items": []})
        gateway = SourceGateway(store, stale_hours=72)
        snapshot = gateway.get("customs_requirements", normalize(query)[:60])
        self.assertTrue(snapshot["fresh"])

    def test_missing_source_reports_unavailable(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        out = call_tool("lookup_recall", {"brand": "테스트", "model": "X1"}, store)
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["recall"]["state"], "source_unavailable")
        self.assertEqual(out["result"]["verdict"]["code"], "info_needed")


class QuotaAndTierTest(unittest.TestCase):
    def test_free_tier_250_calls(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        for _ in range(250):
            store.consume_quota("c1")
        out = call_tool("assess_import_case", {"query": "블루투스 스피커 수입"}, store, client_id="c1")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "quota_exceeded")
        meta = call_tool("get_service_meta", {}, store, client_id="c1")
        self.assertTrue(meta["ok"])  # 메타 조회는 과금/한도 미적용

    def test_billable_tools_exclude_meta(self):
        self.assertEqual(len(TOOL_DEFS), 8)
        self.assertEqual(len(BILLABLE_TOOLS), 7)
        self.assertNotIn("get_service_meta", BILLABLE_TOOLS)

    def test_mcp_manifest_lists_8_tools(self):
        manifest = mcp_manifest()
        self.assertEqual(len(manifest["tools"]), 8)
        names = {t["name"] for t in manifest["tools"]}
        self.assertIn("assess_import_case", names)
        self.assertIn("get_legal_basis", names)

    def test_paid_tier_is_waitlist_only(self):
        self.assertEqual(TIER_BOUNDARIES["free"]["price_krw"], 0)
        self.assertFalse(TIER_BOUNDARIES["free"]["payment_wall"])
        self.assertEqual(TIER_BOUNDARIES["pro_waitlist"]["status"], "오픈 예정 · 대기자 등록만")

    def test_server_has_no_payment_route(self):
        server_path = os.path.join(SRC, "import_compliance", "server.py")
        with open(server_path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("/v1/pay", source)
        self.assertNotIn("checkout", source)


class ToolContractTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_unknown_tool_and_bad_args(self):
        self.assertEqual(call_tool("nope", {}, self.store)["error"], "unknown_tool")
        self.assertEqual(call_tool("lookup_hs_requirements", {"hs_code": "ABC"}, self.store)["error"], "invalid_argument")
        self.assertEqual(call_tool("explain_trap", {"case_id": "TRAP-99"}, self.store)["error"], "invalid_argument")

    def test_explain_trap_shape(self):
        out = call_tool("explain_trap", {"case_id": "trap-06"}, self.store)
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["case_id"], "TRAP-06")
        self.assertTrue(out["result"]["legal_basis"])

    def test_get_legal_basis_filters(self):
        out = call_tool("get_legal_basis", {"law": "전파법"}, self.store)
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["result"]["match_count"], 1)
        for item in out["result"]["basis"]:
            self.assertIn("전파법", item["law"])
            self.assertTrue(item["url"].startswith("http"))

    def test_hs_tool_marks_6_digit_insufficient(self):
        out = call_tool("lookup_hs_requirements", {"hs_code": "850760"}, self.store)
        self.assertTrue(out["ok"])
        self.assertFalse(out["result"]["hs_lookup"]["sufficient_for_checkpoint"])
        self.assertEqual(out["result"]["verdict"]["code"], "info_needed")

    def test_every_response_has_verdict_and_disclaimer(self):
        out = call_tool("assess_import_case", {"query": "세정제 수입 판매"}, self.store)
        result = out["result"]
        for key in ("verdict", "answer", "evidence", "disclaimer", "data_provenance", "tier"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
