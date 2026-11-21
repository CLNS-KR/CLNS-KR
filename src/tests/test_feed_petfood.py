"""0.5.0 반려동물 사료·간식(사료관리법ㆍ동물검역) + 재배포 영속화 테스트(0.5.1에서 툴 15종).

검증 대상
---------
1. 사료관리법ㆍ가축전염병 예방법ㆍ고시 조문이 `feed-law-verification.json` 과 일치하는지
2. 확인 항목 13종이 대표 질의(강아지 간식ㆍ고양이 사료ㆍ단미사료ㆍ반려동물 영양제ㆍ펫푸드 직구)를
   판매/자가소비에 따라 다르게 짚는지, 오탐('참고 사료')을 피하는지
3. `check_feed_import` 툴 계약과 `assess_import_case` 원스톱 통합(TRAP-25)
4. 가이드 3종 렌더ㆍ근거 참조ㆍ문체, /p/ 사료 페이지의 "수입업 등록" 오답 교정
5. 저장소 시드로 재배포 후에도 스냅샷ㆍ익명 통계가 복원되는지(멱등)
6. DB 경로 환경변수 우선순위와 Postgres 미지원 안내

실행: python3 tests/test_feed_petfood.py   (네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import feed, guides, pseo, server, snapshots, usage, web_ui  # noqa: E402
from import_compliance.api import BILLABLE_TOOLS, TOOL_DEFS, TOOL_INDEX, call_tool  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.standards import CASE_REGULATION_TAGS, REGULATION_TAGS  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402

PERSONAL_PATTERNS = (
    r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}",
    r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com",
    r"(?:github|gitlab)\.com/[A-Za-z0-9-]+",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"010[-. ]?\d{4}[-. ]?\d{4}(?!\d)",   # 휴대전화 형태(URL·문서번호 오탐은 제외)
)

FEED_GUIDES = ("pet-food-import-registration", "pet-treat-direct-purchase-quarantine",
               "pet-supplement-feed-or-drug")


def assess(query: str = "", **kwargs):
    return feed.assess(query=query, **kwargs)


class VerifiedLawTest(unittest.TestCase):
    """조문 인용이 법제처 실조회 결과(feed-law-verification.json)와 어긋나지 않는지."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "feed-law-verification.json")
        with open(path, encoding="utf-8") as handle:
            cls.verification = json.load(handle)
        cls.verified = {}
        for law in cls.verification["laws"]:
            for article in law["articles"]:
                number = re.match(r"제[\d의]+조", article["article"])
                cls.verified[(law["law"], number.group(0) if number else article["article"])] = article

    def test_every_basis_article_was_verified(self):
        for check in feed.FEED_CHECKS:
            for basis in check["basis"]:
                if not basis["law"].endswith("수입위생조건") and not basis["law"].endswith("기준 및 규격"):
                    number = re.match(r"제[\d의]+조", basis["article"]).group(0)
                    with self.subTest(rule=check["rule_id"], article=basis["article"]):
                        self.assertIn((basis["law"], number), self.verified,
                                      f"{basis['law']} {basis['article']} 는 검증 파일에 없습니다")

    def test_effective_dates_match_verified_articles(self):
        for check in feed.FEED_CHECKS:
            for basis in check["basis"]:
                number = re.match(r"제[\d의]+조", basis["article"]).group(0)
                row = self.verified.get((basis["law"], number))
                if row is None:
                    continue
                with self.subTest(rule=check["rule_id"], article=basis["article"]):
                    self.assertEqual(basis["effective_date"], row["effective_from"])

    def test_quotes_are_excerpts_of_verified_text(self):
        """인용문은 '…' 로 이은 구간마다 검증된 조문 본문에 그대로 있어야 한다."""
        for check in feed.FEED_CHECKS:
            for basis in check["basis"]:
                number = re.match(r"제[\d의]+조", basis["article"]).group(0)
                row = self.verified.get((basis["law"], number))
                if row is None:
                    continue
                # 원문의 한자 병기(讓許表ㆍ單味飼料 등)는 인용에서 생략할 수 있으므로 비교 전에 뺀다.
                body = re.sub(r"\s+", "", row.get("text_full") or row.get("text") or "")
                body = re.sub(r"\([^)]*[\u4e00-\u9fff][^)]*\)", "", body)
                segments = [seg for seg in re.split(r"…", basis["quote"]) if len(seg.strip()) >= 10]
                self.assertTrue(segments)
                for segment in segments:
                    with self.subTest(rule=check["rule_id"], article=basis["article"],
                                      segment=segment[:24]):
                        self.assertIn(re.sub(r"\s+", "", segment), body)

    def test_no_import_business_registration_claim(self):
        """사료관리법에는 '수입업 등록'이 없다 — 제조업 등록(제8조)만 존재."""
        article = self.verified[("사료관리법", "제8조")]
        self.assertIn("제조업을 영위하려는 자", article["text_full"])
        self.assertNotIn("수입업을 영위하려는 자", article["text_full"])
        meta = feed.meta()
        self.assertIn("수입업 등록", meta["note_ko"])


class RuleCatalogTest(unittest.TestCase):
    def test_check_count_and_unique_ids(self):
        self.assertEqual(len(feed.FEED_CHECKS), 13)
        rule_ids = [row["rule_id"] for row in feed.FEED_CHECKS]
        check_ids = [row["check_id"] for row in feed.FEED_CHECKS]
        self.assertEqual(len(set(rule_ids)), len(rule_ids))
        self.assertEqual(len(set(check_ids)), len(check_ids))
        self.assertEqual(rule_ids[0], "FE-01")

    def test_every_check_has_basis_and_answer(self):
        for check in feed.FEED_CHECKS:
            with self.subTest(rule=check["rule_id"]):
                self.assertTrue(check["basis"])
                self.assertGreater(len(check["why_ko"]), 40)
                self.assertGreater(len(check["action_ko"]), 40)
                self.assertIn(check["risk"], ("high", "caution"))
                for tag in check["tags"]:
                    self.assertIn(tag, REGULATION_TAGS)

    def test_check_text_has_no_conclusive_phrasing(self):
        for check in feed.FEED_CHECKS:
            for field in ("why_ko", "action_ko", "name_ko"):
                with self.subTest(rule=check["rule_id"], field=field):
                    self.assertEqual(find_conclusive_phrasing(check[field]), [])

    def test_all_feed_tags_exist_and_map_to_tool(self):
        for check in feed.FEED_CHECKS:
            for tag in check["tags"]:
                with self.subTest(tag=tag):
                    self.assertIn(tag, REGULATION_TAGS)
                    if tag.startswith(("FEED_", "ANIMAL_", "PET_")):
                        self.assertEqual(guides.tool_for_tag(tag), "check_feed_import")
                    self.assertNotEqual(guides.authority_for(tag), "소관 기관 확인")


class DetectTest(unittest.TestCase):
    def test_detects_pet_food_queries(self):
        cases = {
            "강아지 간식 직구": ("treat", "dog", "self_use"),
            "고양이 사료를 수입해서 판매": ("feed", "cat", "resale"),
            "단미사료 수입": ("raw_material", None, None),
            "반려동물 영양제 수입": ("supplement", None, None),
            "펫푸드 수입 판매": ("feed", None, "resale"),
            "강아지 사료 2309101000 수입": ("feed", "dog", None),
        }
        for query, (product_type, animal, purpose) in cases.items():
            with self.subTest(query=query):
                found = feed.detect(query)
                self.assertTrue(found["is_feed"])
                self.assertEqual(found["product_type"], product_type)
                if animal:
                    self.assertEqual(found["animal"], animal)
                if purpose:
                    self.assertEqual(found["purpose"], purpose)

    def test_ignores_unrelated_uses_of_the_word(self):
        for query in ("참고 사료를 보면", "역사 사료 조사", "통계 사료 정리", "블루투스 스피커 수입"):
            with self.subTest(query=query):
                self.assertFalse(feed.detect(query)["is_feed"])

    def test_pet_supplement_needs_an_animal_or_import_context(self):
        """'강아지 영양제'는 사료 축, 사람용 '영양제'는 아니다."""
        pet = feed.detect("강아지 영양제")
        self.assertTrue(pet["is_feed"])
        self.assertEqual(pet["product_type"], "supplement")
        self.assertEqual(pet["animal"], "dog")
        self.assertFalse(feed.detect("수입 영양제 비타민")["is_feed"])
        # '사료'만으로는 뜻이 갈리므로 수입ㆍ제조 맥락이 있어야 사료로 본다.
        self.assertTrue(feed.detect("사료 OEM 제조 수입")["is_feed"])
        self.assertFalse(feed.detect("사료")["is_feed"])
        self.assertFalse(assess(query="수입 영양제 비타민")["is_feed"])

    def test_detects_animal_origin_and_channel(self):
        found = feed.detect("미국산 닭가슴살 육포 간식을 구매대행으로 들여와 판매")
        self.assertEqual(found["animal_origin"], "yes")
        self.assertEqual(found["channel"], "agency")
        plant = feed.detect("식물성 강아지 간식 수입")
        self.assertEqual(plant["animal_origin"], "no")


class AssessTest(unittest.TestCase):
    def test_resale_gets_registration_declaration_labeling(self):
        block = assess(query="고양이 사료를 수입해서 판매")
        check_ids = [row["check_id"] for row in block["checklist"]]
        for expected in ("ingredient_registration", "import_declaration", "korean_label",
                         "self_quality_inspection", "purpose_restriction"):
            self.assertIn(expected, check_ids)
        self.assertEqual(block["verdict"], "check_likely")
        self.assertIn("FEED_INGREDIENT_REGISTRATION", block["regulation_tags"])

    def test_self_use_skips_business_registration_duties(self):
        block = assess(query="강아지 간식 직구", purpose="self_use")
        check_ids = [row["check_id"] for row in block["checklist"]]
        self.assertNotIn("ingredient_registration", check_ids)
        self.assertNotIn("korean_label", check_ids)
        self.assertIn("animal_quarantine", check_ids)
        self.assertEqual(block["verdict"], "info_needed")

    def test_plant_based_skips_quarantine_checks(self):
        block = assess(query="식물성 강아지 간식 수입", animal_origin="no", purpose="resale")
        check_ids = [row["check_id"] for row in block["checklist"]]
        self.assertNotIn("animal_quarantine", check_ids)
        self.assertNotIn("petfood_quarantine_condition", check_ids)
        self.assertIn("ingredient_registration", check_ids)

    def test_animal_origin_adds_petfood_condition(self):
        block = assess(query="강아지 동결건조 간식 수입 판매", animal="dog", animal_origin="yes")
        check_ids = [row["check_id"] for row in block["checklist"]]
        self.assertIn("petfood_quarantine_condition", check_ids)
        self.assertIn("bse_control", check_ids)
        self.assertIn("PET_FOOD_QUARANTINE", block["regulation_tags"])

    def test_checks_missing_and_present_change_findings(self):
        block = assess(query="강아지 사료 수입 판매",
                       checks={"ingredient_registration": "no", "import_declaration": "yes",
                               "korean_label": "yes"})
        self.assertEqual(block["missing_count"], 1)
        first = block["findings"][0]
        self.assertEqual(first["check_id"], "ingredient_registration")
        self.assertEqual(first["status"], "missing")
        self.assertEqual(block["verdict"], "check_likely")
        present = [row["check_id"] for row in block["checklist"] if row["status"] == "present"]
        self.assertIn("import_declaration", present)
        self.assertIn("korean_label", present)
        self.assertNotIn("ingredient_registration", present)

    def test_supplement_adds_drug_boundary_check(self):
        block = assess(query="반려동물 영양제 수입", product_type="supplement", purpose="resale")
        check_ids = [row["check_id"] for row in block["checklist"]]
        self.assertIn("drug_boundary", check_ids)

    def test_manufacture_adds_manufacturer_registration(self):
        without = assess(query="사료 수입", manufacture="no")
        with_oem = assess(query="사료 OEM 제조 수입", manufacture="yes")
        self.assertNotIn("manufacturer_registration",
                         [row["check_id"] for row in without["checklist"]])
        self.assertIn("manufacturer_registration",
                      [row["check_id"] for row in with_oem["checklist"]])

    def test_non_feed_input_returns_empty_block(self):
        block = assess(query="블루투스 스피커 수입")
        self.assertFalse(block["is_feed"])
        self.assertEqual(block["checklist"], [])
        self.assertEqual(block["verdict"], "info_needed")

    def test_block_text_has_no_conclusive_phrasing(self):
        blocks = [assess(query=q) for q in
                  ("강아지 간식 직구", "고양이 사료 수입 판매", "반려동물 영양제 수입", "단미사료 수입")]
        for block in blocks:
            text = " ".join([block["verdict_note_ko"], block["coverage_ko"]] + block["next_steps_ko"]
                            + [row["why_ko"] + " " + row["safer_ko"] for row in block["findings"]])
            with self.subTest(query=block["input"]["detected_signals"]):
                self.assertEqual(find_conclusive_phrasing(text), [])


class ToolContractTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_tool_is_registered_and_billable(self):
        self.assertIn("check_feed_import", TOOL_INDEX)
        self.assertIn("check_feed_import", BILLABLE_TOOLS)
        definition = TOOL_INDEX["check_feed_import"]
        self.assertEqual(definition["input_schema"]["required"], ["product_name"])

    def test_tool_requires_product_name(self):
        out = call_tool("check_feed_import", {}, self.store)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "invalid_argument")

    def test_tool_rejects_unknown_check_id(self):
        out = call_tool("check_feed_import", {"product_name": "강아지 사료", "checks": {"nope": True}},
                        self.store)
        self.assertFalse(out["ok"])
        self.assertIn("unknown_check_id", out["message"])

    def test_tool_response_shape(self):
        out = call_tool("check_feed_import",
                        {"product_name": "강아지 동결건조 간식", "product_type": "treat",
                         "animal": "dog", "purpose": "resale", "animal_origin": "yes",
                         "checks": {"import_declaration": "no"}}, self.store)
        self.assertTrue(out["ok"])
        result = out["result"]
        for key in ("feed_check", "verdict", "answer", "evidence", "missing_information",
                    "next_actions", "data_provenance", "disclaimer", "schema_version",
                    "destination", "jurisdiction", "origin", "assessment_status"):
            self.assertIn(key, result)
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertTrue(result["evidence"])
        self.assertTrue(result["missing_information"])
        self.assertTrue(any("사료" in name for name in result["missing_information"]))

    def test_assess_import_case_attaches_feed_check(self):
        out = call_tool("assess_import_case",
                        {"query": "미국산 강아지 사료를 수입해서 판매하려고 합니다"}, self.store)
        result = out["result"]
        case_ids = [finding["case_id"] for finding in result["findings"]]
        self.assertIn("TRAP-25", case_ids)
        self.assertTrue(result["feed_check"]["is_feed"])
        for tag in ("FEED_INGREDIENT_REGISTRATION", "ANIMAL_PRODUCT_QUARANTINE"):
            self.assertIn(tag, result["regulation_tags"])
        self.assertTrue(any("사료" in line for line in result["answer"]["guidance"]))

    def test_pet_supplement_does_not_pull_health_food_card(self):
        """반려동물 영양제는 건강기능식품 광고 카드(TRAP-09)가 아니라 사료 카드로 본다."""
        pet = call_tool("assess_import_case", {"query": "반려동물 영양제 수입"}, self.store)["result"]
        case_ids = [finding["case_id"] for finding in pet["findings"]]
        self.assertIn("TRAP-25", case_ids)
        self.assertNotIn("TRAP-09", case_ids)
        human = call_tool("assess_import_case", {"query": "수입 건강기능식품 비타민 광고"}, self.store)["result"]
        self.assertIn("TRAP-09", [finding["case_id"] for finding in human["findings"]])
        self.assertNotIn("feed_check", human)

    def test_assess_import_case_skips_feed_for_other_products(self):
        out = call_tool("assess_import_case", {"query": "중국산 블루투스 스피커 수입"}, self.store)
        self.assertNotIn("feed_check", out["result"])
        self.assertNotIn("TRAP-25", [f["case_id"] for f in out["result"]["findings"]])

    def test_service_meta_reports_feed_and_persistence(self):
        payload = call_tool("get_service_meta", {}, self.store)["result"]
        self.assertEqual(payload["feed"]["checks"], 13)
        self.assertEqual(payload["feed"]["rule_ids"][0], "FE-01")
        self.assertIn("mode", payload["persistence"])
        self.assertTrue(payload["persistence"]["note_ko"])

    def test_trap_25_is_explainable(self):
        out = call_tool("explain_trap", {"case_id": "TRAP-25"}, self.store)
        self.assertTrue(out["ok"])
        self.assertIn("사료", json.dumps(out["result"], ensure_ascii=False))
        self.assertEqual(CASE_REGULATION_TAGS["TRAP-25"][0], "FEED_INGREDIENT_REGISTRATION")


class GuideTest(unittest.TestCase):
    def test_three_feed_guides_exist_and_render(self):
        for slug in FEED_GUIDES:
            with self.subTest(slug=slug):
                item = guides.get_item(slug)
                self.assertIsNotNone(item)
                self.assertEqual(item["category"], "반려동물 사료·간식")
                self.assertEqual(item["tool"], "check_feed_import")
                self.assertTrue(guides.is_indexable(item))
                html = guides.render_guide(slug)
                self.assertIn("check_feed_import", html)
                self.assertIn("사료관리법", html)
                self.assertIn("FAQPage", html)

    def test_feed_guides_are_in_sitemap_and_llms(self):
        from import_compliance import static_files

        sitemap = static_files.sitemap_xml()
        for slug in FEED_GUIDES:
            self.assertIn(f"/guides/{slug}", sitemap)
        self.assertIn("check_feed_import", static_files.llms_txt())

    def test_feed_guides_reference_verified_basis(self):
        registry = guides.basis_registry()
        for slug in FEED_GUIDES:
            item = guides.get_item(slug)
            self.assertTrue(item["basis_keys"])
            for key in item["basis_keys"]:
                with self.subTest(slug=slug, key=key):
                    self.assertIn(key, registry)

    def test_feed_guide_text_has_no_conclusive_phrasing(self):
        for slug in FEED_GUIDES:
            item = guides.get_item(slug)
            text = " ".join([item["answer_ko"], item["summary_ko"]]
                            + item["checkpoints_ko"] + item["key_points_ko"])
            with self.subTest(slug=slug):
                self.assertEqual(find_conclusive_phrasing(text), [])

    def test_pseo_pet_pages_correct_the_registration_myth(self):
        for slug in ("dog-food", "cat-treat"):
            item = pseo.get_item(slug)
            with self.subTest(slug=slug):
                joined = " ".join(item["key_points_ko"] + item["requirements_ko"])
                self.assertNotIn("사료 제조·수입업 등록", joined)
                self.assertIn("'수입업 등록' 제도는 없습니다", joined)
                self.assertIn("TRAP-25", item["traps"])

    def test_web_ui_exposes_feed_example_and_block(self):
        page = web_ui.render_page()
        self.assertIn('id="check-demo-feed"', page)
        self.assertIn('value="feed"', page)
        self.assertIn("feedCheckBlock", page)
        self.assertIn("반려동물 사료·간식 검수", page)


class PersistenceTest(unittest.TestCase):
    def _store(self):
        path = os.path.join(tempfile.mkdtemp(prefix="clns-seed-"), "app.sqlite")
        store = Store(path)
        self.addCleanup(store.close)
        return store

    def _write_snapshot(self, folder: str, day: str = "2026-11-19") -> str:
        payload = {
            "schema": snapshots.SNAPSHOT_SCHEMA,
            "day": day,
            "taken_at": f"{day}T04:00:00+09:00",
            "origin": "observed",
            "counts": {"recall": 2},
            "diff": {"new": 1, "changed": 0, "removed": 0},
            "items": {"recall": [
                {"key": "r1", "label": "완구", "category": "어린이",
                 "event_date": "2020-09-22", "fingerprint": "abc123"},
                {"key": "r2", "label": "전지", "category": "전기",
                 "event_date": "2020-09-23", "fingerprint": "def456"},
            ]},
        }
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{day}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        return path

    def test_seed_restores_snapshot_days(self):
        store = self._store()
        folder = tempfile.mkdtemp(prefix="clns-snap-")
        self._write_snapshot(folder)
        result = snapshots.seed_snapshots(store, folder)
        self.assertEqual(result["days"], ["2026-11-19"])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(snapshots.days(store), ["2026-11-19"])
        rows = store.conn.execute(
            "SELECT origin FROM compliance_snapshots WHERE day = ?", ("2026-11-19",)).fetchall()
        self.assertEqual({row["origin"] for row in rows}, {"observed"})

    def test_seed_is_idempotent_and_keeps_existing_day(self):
        store = self._store()
        folder = tempfile.mkdtemp(prefix="clns-snap-")
        self._write_snapshot(folder)
        snapshots.seed_snapshots(store, folder)
        second = snapshots.seed_snapshots(store, folder)
        self.assertEqual(second["days"], [])
        self.assertEqual(second["skipped"], ["2026-11-19"])
        count = store.conn.execute("SELECT COUNT(*) AS n FROM compliance_snapshots").fetchone()["n"]
        self.assertEqual(count, 2)

    def test_seed_skips_summary_only_exports(self):
        store = self._store()
        folder = tempfile.mkdtemp(prefix="clns-snap-")
        path = os.path.join(folder, "2026-11-18.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"day": "2026-11-18", "counts": {"recall": 1}}, handle)
        result = snapshots.seed_snapshots(store, folder)
        self.assertEqual(result["days"], [])
        self.assertEqual(result["unreadable"], ["2026-11-18.json"])

    def test_missing_seed_dir_is_not_an_error(self):
        store = self._store()
        result = snapshots.seed_snapshots(store, os.path.join(tempfile.mkdtemp(), "nope"))
        self.assertEqual(result["days"], [])

    def test_usage_seed_restores_and_keeps_the_larger_value(self):
        store = self._store()
        folder = tempfile.mkdtemp(prefix="clns-usage-")
        path = os.path.join(folder, "stats.json")
        payload = {"days": [
            {"date": "2026-11-19", "paths": {"/": 5}, "tools": {"assess_import_case": 3},
             "verdicts": {"check_likely": 2}, "flags": {"zero_results": 1}},
            {"date": "2026-11-20", "paths": {"/": 4}},
        ]}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        restored = snapshots.seed_snapshot_usage(store, path)
        self.assertEqual(restored["days"], 2)
        self.assertGreaterEqual(restored["rows"], 5)
        store.bump_usage("2026-11-19", usage.KIND_PATH, "/", 1)  # 복원값 위에 증가
        stats = usage.stats_payload(store, 7, today="2026-11-20")
        day = next(row for row in stats["days"] if row["date"] == "2026-11-19")
        self.assertEqual(day["paths"]["/"], 6)
        snapshots.seed_snapshot_usage(store, path)  # 다시 복원해도 줄지 않는다(MAX)
        stats = usage.stats_payload(store, 7, today="2026-11-20")
        day = next(row for row in stats["days"] if row["date"] == "2026-11-19")
        self.assertEqual(day["paths"]["/"], 6)

    def test_seed_persistence_reports_status(self):
        store = self._store()
        folder = tempfile.mkdtemp(prefix="clns-snap-")
        self._write_snapshot(folder)
        summary = snapshots.seed_persistence(store, folder, os.path.join(folder, "missing.json"))
        self.assertEqual(summary["seeded_days"], ["2026-11-19"])
        status = snapshots.persistence_status()
        self.assertEqual(status["mode"], "repo_seed + sqlite")
        self.assertTrue(status["seed_present"])
        self.assertEqual(status["snapshot_days_skipped"], [])

    def test_db_path_precedence(self):
        self.assertEqual(server.resolve_db_path({"CLNS_DB_PATH": "/data/clns.sqlite"})["db_source"],
                         "CLNS_DB_PATH")
        both = server.resolve_db_path({"CLNS_DB_PATH": "/a.sqlite",
                                       "IMPORT_COMPLIANCE_DB": "/b.sqlite"})
        self.assertEqual(both["db_path"], "/a.sqlite")
        legacy = server.resolve_db_path({"IMPORT_COMPLIANCE_DB": "/b.sqlite"})
        self.assertEqual(legacy["db_path"], "/b.sqlite")
        sqlite_url = server.resolve_db_path({"DATABASE_URL": "sqlite:///srv/app.sqlite"})
        self.assertEqual(sqlite_url["db_path"], "srv/app.sqlite")
        self.assertIn("sqlite", sqlite_url["db_source"])

    def test_postgres_url_falls_back_with_notice(self):
        resolved = server.resolve_db_path({"DATABASE_URL": "postgres://user:pw@host/db"})
        self.assertTrue(resolved["db_path"].endswith(os.path.join("data", "app.sqlite")))
        self.assertIn("unsupported", resolved["db_source"])
        self.assertTrue(any("Postgres" in note for note in resolved["notes"]))

    def test_config_from_env_exposes_seed_paths(self):
        cfg = server.config_from_env({"CLNS_SEED_DIR": "/srv/seed", "CLNS_USAGE_SEED": "/srv/u.json"})
        self.assertEqual(cfg["seed_dir"], "/srv/seed")
        self.assertEqual(cfg["usage_seed"], "/srv/u.json")
        self.assertIn(cfg["db_source"], ("default", "IMPORT_COMPLIANCE_DB", "CLNS_DB_PATH"))

    def test_committed_seed_files_are_valid(self):
        seed_dir = os.path.join(ROOT, "data", "snapshots")
        self.assertTrue(os.path.isdir(seed_dir))
        files = [name for name in os.listdir(seed_dir) if name.endswith(".json")]
        self.assertTrue(files)
        for name in files:
            with open(os.path.join(seed_dir, name), encoding="utf-8") as handle:
                payload = json.load(handle)
            with self.subTest(file=name):
                self.assertRegex(payload["day"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(payload.get("items") or payload.get("counts"))
                if payload.get("items"):
                    self.assertIn("recall", payload["items"])

    def test_usage_seed_shape(self):
        path = os.path.join(ROOT, "data", "usage", "stats.json")
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertIn("days", payload)
        rows = snapshots.usage_rows_from_payload(payload)
        self.assertTrue(all(row["count"] > 0 for row in rows))
        self.assertTrue(all(row["kind"] in ("path", "tool", "verdict", "flag") for row in rows))

    def test_workflow_schedule_and_commit_step(self):
        path = os.path.join(ROOT, ".github", "workflows", "daily-snapshot.yml")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('cron: "0 19 * * *"', text)   # 04:00 KST
        self.assertIn("data/snapshots", text)
        self.assertIn("data/usage", text)
        self.assertIn("git push", text)
        self.assertIn("--include-items", text)


class VersionAndAnonymityTest(unittest.TestCase):
    def test_version_is_0_5_1(self):
        self.assertEqual(__version__, "0.5.7")
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["version"], __version__)
        self.assertEqual(web_ui.SERVICE_VERSION, __version__)
        with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as handle:
            self.assertIn('org.opencontainers.image.version="0.5.7"', handle.read())

    def test_trap_25_entry_has_no_personal_data(self):
        from import_compliance.corpus import load_corpus

        trap = next(row for row in load_corpus().traps if row.id == "TRAP-25")
        text = json.dumps(trap.to_dict() if hasattr(trap, "to_dict") else trap.__dict__,
                          ensure_ascii=False, default=str)
        for pattern in PERSONAL_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text))

    def test_tool_count_is_15(self):
        self.assertEqual(len(TOOL_DEFS), 15)
        self.assertEqual(len(BILLABLE_TOOLS), 14)

    def test_new_files_have_no_personal_data_or_secrets(self):
        patterns = [re.compile(pattern) for pattern in PERSONAL_PATTERNS]
        targets = [
            os.path.join("src", "import_compliance", "feed.py"),
            os.path.join("src", "import_compliance", "snapshots.py"),
            os.path.join("src", "import_compliance", "server.py"),
            os.path.join("src", "import_compliance", "api.py"),
            os.path.join("src", "guides_items.json"),
            os.path.join("src", "import_compliance", "policy.py"),
            os.path.join(".github", "workflows", "daily-snapshot.yml"),
            "12-petfood-feed-0.5.0.md",
        ]
        for relative in targets:
            path = os.path.join(ROOT, relative)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for pattern in patterns:
                with self.subTest(file=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
