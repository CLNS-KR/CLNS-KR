"""0.1.5 회귀 테스트 — 의약품·영양제 반입 금지성분·제한성분 체크(CLNS 1번).

실행: python3 tests/test_drug_import.py   (표준 unittest, 네트워크 불필요)

검증 축
1. **성분 사전**(`drug_schedules.json`): 마약류 관리에 관한 법률 시행령 별표 1~8에서
   생성한 목록이 비어 있지 않고, 대표 성분이 정확한 별표·조문에 매핑되는지.
2. **법령 검증 산출물**(`drug-law-verification.json`): 인용 조문 시행일이 검증일 이하이고
   미해결 조문이 없는지, 코퍼스 카드의 인용과 일치하는지.
3. **스크리닝 로직**: 한글·영문 성분명, 제품명 매핑, 대마 표현, 수량·반입 경로 해석,
   6병 기준 상태, 과탐 방지.
4. **엔진·툴·웹 연결**: TRAP-23·24 자동 부착, `check_drug_import` MCP 툴, provenance,
   웹 UI 문구, 의약품 테스트셋(14건) 통과.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import drugs, pseo, web_ui  # noqa: E402
from import_compliance.api import TOOL_DEFS, call_tool, mcp_manifest  # noqa: E402
from import_compliance.corpus import load_corpus  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.policy import SCOPE_LIMITS_KO, find_conclusive_phrasing  # noqa: E402
from import_compliance.store import Store  # noqa: E402

SCHEDULES_PATH = os.path.join(SRC, "drug_schedules.json")
VERIFICATION_PATH = os.path.join(ROOT, "drug-law-verification.json")
DRUG_TESTSET_PATH = os.path.join(SRC, "drug_testset.json")
TODAY = "2026-11-18"


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _article_label(article: str) -> str:
    """'제6조의2제1항' → '제6조의2' (조문 번호만 남긴다)."""
    text = str(article).replace(" ", "")
    head = text.split("제")[1]
    main = head.split("조")[0]
    branch = ""
    if "의" in head:
        branch = "의" + head.split("의")[1].split("조")[0].split("항")[0]
    return f"제{main}조{branch}"


def assess_once(query, facts=None, live=None):
    store = Store(":memory:")
    try:
        return assess(query, facts, store=store, live=live)
    finally:
        store.close()


def tool_once(name, args):
    store = Store(":memory:")
    try:
        return call_tool(name, args, store)
    finally:
        store.close()


class ScheduleDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SCHEDULES_PATH):
            raise unittest.SkipTest("drug_schedules.json 없음 — 별표 사전을 먼저 생성해야 함")
        cls.data = load_json(SCHEDULES_PATH)
        cls.substances = cls.data["substances"]
        cls.precursors = cls.data["precursors"]

    def test_metadata_and_attribution(self):
        self.assertEqual(self.data["schedule_version"], "1.0.0")
        self.assertRegex(self.data["generated_on"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertLessEqual(self.data["generated_on"], TODAY)
        self.assertIn("마약류 관리에 관한 법률 시행령", self.data["decree"])
        self.assertIn("법제처", self.data["attribution_ko"])
        self.assertTrue(self.data["decree_mst"].isdigit())
        self.assertIn("단정할 수 없습니다", self.data["note_ko"])

    def test_every_entry_is_classified_and_sourced(self):
        known = set(drugs.CLASS_LABEL_KO)
        for entry in self.substances + self.precursors:
            with self.subTest(name=entry["name_ko"]):
                self.assertIn(entry["class"], known)
                self.assertTrue(entry["class_ko"])
                self.assertRegex(entry["reference"], r"법 제2조")
                self.assertRegex(entry["table"], r"^별표 \d")
                self.assertTrue(entry["name_ko"].strip())
                self.assertLessEqual(len(entry["name_ko"]), 60)
                self.assertNotIn("다만", entry["name_ko"])
                self.assertNotIn("유사체", entry["name_ko"])

    def test_classes_and_tables_are_populated(self):
        counts = {}
        for entry in self.substances:
            counts[entry["class"]] = counts.get(entry["class"], 0) + 1
        self.assertGreater(counts.get("NARCOTIC", 0), 100)
        self.assertGreater(counts.get("PSYCHOTROPIC", 0), 200)
        self.assertGreaterEqual(counts.get("CANNABIS_SYNTHETIC", 0), 3)
        self.assertGreater(len(self.precursors), 40)
        self.assertEqual(len(self.data["tables"]), 8)

    def test_representative_substances_are_mapped_to_right_schedule(self):
        by_name = {entry["name_ko"]: entry for entry in self.substances}
        expected = {
            "졸피뎀": "별표 6",
            "메틸페니데이트": "별표 4",
            "코데인": "별표 1",
            "디히드로코데인": "별표 1",
            "옥시코돈": "별표 1",
            "펜타닐": "별표 2",
            "알프라졸람": "별표 6",
            "칸나비디올": "별표 7",
            "테트라히드로칸나비놀": "별표 7",
        }
        for name, table in expected.items():
            with self.subTest(name=name):
                self.assertIn(name, by_name)
                self.assertEqual(by_name[name]["table"], table)
        self.assertEqual(by_name["졸피뎀"]["class"], "PSYCHOTROPIC")
        self.assertEqual(by_name["칸나비디올"]["class"], "CANNABIS_SYNTHETIC")

    def test_precursors_include_ephedrine_family(self):
        names = {entry["name_ko"] for entry in self.precursors}
        for name in ("에페드린", "슈도에페드린", "에르고타민", "에르고메트린"):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_unscheduled_substances_are_not_in_dictionary(self):
        """마약류가 아닌 성분(트라마돌·멜라토닌 등)을 마약류로 넣으면 오답이다."""
        names = {entry["name_ko"] for entry in self.substances + self.precursors}
        for name in ("트라마돌", "멜라토닌", "실데나필", "DHEA"):
            with self.subTest(name=name):
                self.assertNotIn(name, names)


class LawVerificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(VERIFICATION_PATH):
            raise unittest.SkipTest("drug-law-verification.json 없음 — 법령 대조는 로컬에서만 실행")
        cls.artifact = load_json(VERIFICATION_PATH)
        cls.by_law = {block["law"]: block for block in cls.artifact["laws"]}

    def test_artifact_covers_the_three_laws(self):
        self.assertEqual(self.artifact["checked_on"], TODAY)
        self.assertEqual(set(self.by_law), {"마약류 관리에 관한 법률", "약사법", "관세법"})
        for law, block in self.by_law.items():
            with self.subTest(law=law):
                self.assertEqual(block["unresolved"], [])
                self.assertTrue(block["articles"])

    def test_every_cited_article_is_already_in_force(self):
        checked = self.artifact["checked_on"]
        for law, block in self.by_law.items():
            for row in block["articles"]:
                with self.subTest(law=law, article=row["article"]):
                    self.assertLessEqual(row["effective_from"], checked)
                    self.assertTrue(row["text"].strip())
                    self.assertTrue(row["url"].startswith("https://www.law.go.kr/"))

    def test_corpus_cards_match_verified_dates(self):
        dates = {}
        for law, block in self.by_law.items():
            for row in block["articles"]:
                dates[(law, row["article"])] = row["effective_from"]
        self.assertEqual(dates[("마약류 관리에 관한 법률", "제2조")], "2026-11-12")
        self.assertEqual(dates[("마약류 관리에 관한 법률", "제4조")], "2026-11-12")
        self.assertEqual(dates[("마약류 관리에 관한 법률", "제18조")], "2026-11-12")
        self.assertEqual(dates[("약사법", "제42조")], "2026-11-12")
        self.assertEqual(dates[("관세법", "제226조")], "2026-10-02")

        corpus = load_corpus()
        for case_id in ("TRAP-23", "TRAP-24"):
            trap = corpus.by_id(case_id)
            self.assertIsNotNone(trap)
            for basis in trap.legal_basis:
                self.assertEqual(basis.verified_on, TODAY, case_id)
                if basis.law in self.by_law:
                    # '제6조의2제1항' 같은 인용에서 조문 번호(제6조의2)만 뽑아 대조한다.
                    label = _article_label(basis.article)
                    key = (basis.law, label)
                    self.assertIn(key, dates, f"{case_id} {basis.article}")
                    self.assertEqual(basis.effective_date, dates[key], f"{case_id} {basis.article}")

    def test_self_use_rule_quote_mentions_six_bottles_and_conditions(self):
        self_use = " ".join(row["quote"] for row in drugs.BASIS_SELF_USE)
        self.assertIn("6병", self_use)
        self.assertIn("3개월", self_use)
        precursor = " ".join(row["quote"] for row in drugs.BASIS_PRECURSOR)
        self.assertIn("에페드린", precursor)
        self.assertIn("요건확인", precursor)
        self.assertIn("admRulSeq=2100000269780", drugs.NOTICE_URL)


class ScreeningTest(unittest.TestCase):
    def test_korean_and_english_ingredient_names(self):
        for text in ("졸피뎀 30정", "Zolpidem", "zolpidem tartrate 10mg"):
            with self.subTest(text=text):
                result = drugs.assess(text)
                self.assertEqual(result["state"], "controlled_substance")
                self.assertEqual(result["matches"][0]["name_ko"], "졸피뎀")

    def test_cannabis_terms_and_cbd(self):
        for text in ("CBD 오일", "cannabidiol 25mg", "대마초 추출액", "THC 젤리"):
            with self.subTest(text=text):
                result = drugs.assess(text)
                self.assertIn("CANNABIS_SYNTHETIC",
                              {item["class"] for item in result["matches"]})

    def test_brand_names_map_to_ingredients(self):
        cases = {"Adderall 30정": "암페타민", "리탈린": "메틸페니데이트",
                 "Xanax": "알프라졸람", "Stilnox": "졸피뎀", "위고비": "세마글루타이드"}
        for text, ingredient in cases.items():
            with self.subTest(text=text):
                result = drugs.assess(text)
                self.assertIn(ingredient, [item["name_ko"] for item in result["matches"]])

    def test_precursor_state_and_note(self):
        result = drugs.assess("슈도에페드린 감기약")
        self.assertEqual(result["state"], "precursor_restricted")
        row = result["matches"][0]
        self.assertEqual(row["class"], "PRECURSOR")
        self.assertIn("원료물질", row["note_ko"])
        self.assertIn("요건확인", row["note_ko"])

    def test_kr_prescription_only_state(self):
        result = drugs.assess("멜라토닌 5mg")
        self.assertEqual(result["state"], "kr_prescription_only")
        self.assertIn("의약품", result["matches"][0]["note_ko"])

    def test_quantity_parsing_ignores_strength(self):
        self.assertEqual(drugs.detect_quantity("졸피뎀 30정"), {"value": 30, "unit": "정"})
        self.assertEqual(drugs.detect_quantity("2병 사려고"), {"value": 2, "unit": "병"})
        self.assertIsNone(drugs.detect_quantity("5mg 10mg 함량"))
        self.assertIsNone(drugs.detect_quantity("수량 미정"))

    def test_channel_detection(self):
        self.assertEqual(drugs.detect_channel("해외직구로 사려고"), "online")
        self.assertEqual(drugs.detect_channel("아이허브에서 주문"), "online")
        self.assertEqual(drugs.detect_channel("휴대 반입"), "carry")
        self.assertEqual(drugs.detect_channel("가방에 넣어"), "carry")
        self.assertEqual(drugs.detect_channel("얼마인가요"), "unknown")
        self.assertEqual(drugs.detect_channel("", {"channel": "carry"}), "carry")
        self.assertEqual(drugs.detect_channel("", {"channel": "online"}), "online")

    def test_self_use_status_matrix(self):
        self.assertEqual(drugs.assess("타이레놀 2병 휴대 반입")["self_use_status"],
                         "within_carry_allowance")
        self.assertEqual(drugs.assess("타이레놀 10병 휴대 반입")["self_use_status"],
                         "over_carry_allowance")
        self.assertEqual(drugs.assess("타이레놀 2병 직구")["self_use_status"], "online")
        self.assertEqual(drugs.assess("타이레놀 반입")["self_use_status"], "unknown")

    def test_generic_queries_do_not_trigger_drug_screening(self):
        for text in ("150달러 이하 보조배터리를 해외직구로 반입",
                     "중국산 블루투스 스피커를 수입해 판매",
                     "주방 세정제와 방향제를 수입해 판매",
                     "유아용 원목 완구 수입"):
            with self.subTest(text=text):
                self.assertFalse(drugs.looks_like_drug_query(text), text)
                self.assertEqual(drugs.assess(text)["match_count"], 0)

    def test_guidance_avoids_conclusive_phrasing(self):
        for text in ("졸피뎀 30정 직구", "멜라토닌 2병 휴대", "타이레놀 2병",
                     "슈도에페드린 감기약", "아무 성분이나"):
            with self.subTest(text=text):
                result = drugs.assess(text)
                joined = " ".join(result["guidance_ko"])
                self.assertEqual(find_conclusive_phrasing(joined), [], joined)

    def test_screening_is_deterministic(self):
        first = drugs.assess("졸피뎀 30정 직구")
        second = drugs.assess("졸피뎀 30정 직구")
        self.assertEqual([m["name_ko"] for m in first["matches"]],
                         [m["name_ko"] for m in second["matches"]])
        self.assertEqual(first["self_use_status"], second["self_use_status"])


class EngineIntegrationTest(unittest.TestCase):
    def test_narcotic_query_adds_card_and_screening(self):
        result = assess_once("미국에서 졸피뎀 30정을 자가용으로 직구하려고 해")
        self.assertEqual(result["verdict"]["code"], "check_likely")
        case_ids = [finding["case_id"] for finding in result["findings"]]
        self.assertIn("TRAP-23", case_ids)
        self.assertIn("NARCOTIC_IMPORT_BAN", result["regulation_tags"])
        screening = result["drug_screening"]
        self.assertEqual(screening["state"], "controlled_substance")
        self.assertEqual(screening["channel"], "online")
        self.assertEqual(result["query"]["facts_resolved"]["drug_class"], "yes")
        laws = {(row["law"], row["article"]) for row in result["evidence"]}
        self.assertIn(("마약류 관리에 관한 법률", "제4조제1항"), laws)
        self.assertIn(("마약류 관리에 관한 법률 시행령", "별표 7의2"), laws)

    def test_precursor_query_adds_restriction_card(self):
        result = assess_once("에페드린 함유 다이어트 보조제를 수입해 판매하려고 해")
        case_ids = [finding["case_id"] for finding in result["findings"]]
        self.assertIn("TRAP-24", case_ids)
        self.assertIn("DRUG_INGREDIENT_RESTRICTION", result["regulation_tags"])
        self.assertEqual(result["query"]["facts_resolved"].get("drug_class"), "no")

    def test_small_carry_quantity_is_not_overflagged(self):
        result = assess_once("타이레놀 2병을 휴대 반입하려고 해",
                             {"purpose": "self_use"})
        self.assertEqual(result["verdict"]["code"], "low_risk")
        self.assertEqual(result["drug_screening"]["self_use_status"], "within_carry_allowance")

    def test_over_allowance_carry_is_flagged(self):
        result = assess_once("타이레놀 10병을 휴대 반입하려고 해")
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertEqual(result["drug_screening"]["self_use_status"], "over_carry_allowance")

    def test_non_drug_query_has_no_drug_block(self):
        result = assess_once("150달러 이하 보조배터리를 해외직구로 반입",
                             {"price_usd": 150, "battery_type": "리튬이온",
                              "energy_density": "300Wh/L"})
        self.assertNotIn("drug_screening", result)
        self.assertNotIn("NARCOTIC_IMPORT_BAN", result["regulation_tags"])

    def test_provenance_reports_local_index_and_pending_apis(self):
        result = assess_once("졸피뎀 30정 직구")
        sources = {row.get("source_id"): row for row in result["data_provenance"]["sources"]}
        self.assertIn("mfds_drug_schedule", sources)
        entry = sources["mfds_drug_schedule"]
        self.assertEqual(entry["state"], "local_index")
        self.assertGreater(entry["substance_count"], 100)
        self.assertIn("활용승인", entry["note_ko"])
        pending = [row for row in entry["api_state"] if row["state"] == "approval_required"]
        self.assertGreaterEqual(len(pending), 5)


class DrugToolTest(unittest.TestCase):
    def test_tool_is_registered_with_schema(self):
        names = [tool["name"] for tool in TOOL_DEFS]
        self.assertIn("check_drug_import", names)
        manifest = mcp_manifest()
        entry = next(tool for tool in manifest["tools"] if tool["name"] == "check_drug_import")
        self.assertEqual(entry["inputSchema"]["required"], ["product_name"])
        self.assertIn("channel", entry["inputSchema"]["properties"])
        self.assertIn("quantity", entry["inputSchema"]["properties"])

    def test_tool_returns_screening_and_schedule_metadata(self):
        out = tool_once("check_drug_import", {"product_name": "졸피뎀", "channel": "online",
                                              "quantity": 30, "unit": "정",
                                              "prescription": "yes"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["tool"], "check_drug_import")
        result = out["result"]
        check = result["drug_import_check"]
        self.assertEqual(check["state"], "controlled_substance")
        self.assertEqual(check["self_use_status"], "online")
        self.assertEqual(check["self_use_rule"]["limit_bottles"], 6)
        self.assertTrue(check["schedule_version"])
        self.assertTrue(check["coverage_ko"])
        self.assertEqual({row["state"] for row in check["api_candidates"]}, {"approval_required"})
        self.assertEqual(result["drug_screening"]["prescription_status"], "yes")
        self.assertIn("확정하지 않습니다", " ".join(result["answer"]["guidance"]))
        for key in ("schema_version", "destination", "jurisdiction"):
            self.assertIn(key, result)

    def test_tool_accepts_english_ingredient(self):
        out = tool_once("check_drug_import", {"product_name": "Cannabidiol", "channel": "carry"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["drug_import_check"]["state"], "controlled_substance")

    def test_tool_rejects_bad_arguments(self):
        for args, code in (({"product_name": "a"}, "product_name_required"),
                           ({"product_name": "졸피뎀", "channel": "drone"},
                            "channel_must_be_carry_or_online"),
                           ({"product_name": "졸피뎀", "quantity": "many"},
                            "quantity_must_be_integer")):
            with self.subTest(args=args):
                out = tool_once("check_drug_import", args)
                self.assertFalse(out["ok"])
                self.assertEqual(out["error"], "invalid_argument")
                self.assertIn(code, out["message"])

    def test_meta_exposes_drug_schedules_and_testset(self):
        out = tool_once("get_service_meta", {})
        meta = out["result"]
        self.assertIn("drug_schedules", meta)
        self.assertGreater(meta["drug_schedules"]["controlled_substances"], 100)
        self.assertEqual(meta["drug_schedules"]["self_use_limit"]["limit_bottles"], 6)
        self.assertEqual(meta["drug_testset"]["cases"], 14)
        self.assertFalse(meta["live_sources"].get("mfds_drug_api", True) if meta.get("live_sources") else False)


class DrugTestsetTest(unittest.TestCase):
    def test_drug_testset_passes_without_forbidden_tags(self):
        if not os.path.exists(DRUG_TESTSET_PATH):
            raise unittest.SkipTest("drug_testset.json 없음")
        testset = load_json(DRUG_TESTSET_PATH)
        store = Store(":memory:")
        try:
            for case in testset["cases"]:
                with self.subTest(case=case["case_id"]):
                    result = assess(case["query"], case["facts"], store=store, limit=3)
                    tags = set()
                    for finding in result["findings"]:
                        tags.update(finding.get("regulation_tags") or [])
                    self.assertEqual(result["verdict"]["code"], case["expected_verdict"])
                    self.assertEqual(set(case["required_findings"]) - tags, set())
                    self.assertEqual(set(case.get("must_not_find") or []) & tags, set())
        finally:
            store.close()

    def test_reference_100_testset_is_unchanged(self):
        """의약품 기능을 더해도 대표 100개 테스트셋은 1.0.1·100건 그대로여야 한다."""
        testset = load_json(os.path.join(SRC, "testset_100.json"))
        self.assertEqual(testset["testset_version"], "1.0.1")
        self.assertEqual(len(testset["cases"]), 100)


class CorpusAndDocsTest(unittest.TestCase):
    def test_new_cards_are_in_corpus(self):
        corpus = load_corpus()
        self.assertGreaterEqual(len(corpus.traps), 24)
        trap = corpus.by_id("TRAP-23")
        self.assertEqual(trap.category, "drug")
        self.assertEqual(trap.default_verdict, "check_likely")
        joined = f"{trap.correct_answer} {trap.notes}"
        self.assertIn("처방전", trap.correct_answer)
        self.assertIn("별표", joined)
        self.assertEqual(corpus.by_id("TRAP-24").category, "drug")

    def test_scoring_scope_limits_mention_drugs(self):
        scope = " ".join(SCOPE_LIMITS_KO)
        self.assertIn("24개", scope)
        self.assertIn("마약류", scope)
        self.assertIn("활용승인", scope)
        self.assertIn("의약외품", scope)

    def test_web_ui_exposes_drug_check_both_languages(self):
        page = web_ui.render_page()
        self.assertIn("의약품·성분 체크", page)
        self.assertIn("check_drug_import", page)
        self.assertIn("Zolpidem", page)
        self.assertIn("졸피뎀", page)
        self.assertIn("6병", page)
        for word in ("CLNS Check", "CLNS Intelligence", "CLNS API &amp; MCP"):
            self.assertIn(word, page)

    def test_pseo_catalog_still_valid(self):
        self.assertEqual(len(pseo.slugs()), 35)

    def test_no_secret_or_personal_data_in_schedule_artifact(self):
        with open(SCHEDULES_PATH, encoding="utf-8") as handle:
            raw = handle.read()
        for token in ("serviceKey", "DATA_GO_KR", "LAW_GO_KR_OC", "OC="):
            self.assertNotIn(token, raw)
        import re

        self.assertNotRegex(raw, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertNotRegex(raw, r"01\d[- ]?\d{3,4}[- ]?\d{4}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
