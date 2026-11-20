"""0.5.1 수입품 한글표시사항(라벨링) 1초 체크 — 엔진·MCP 툴·API·웹 UI·가이드 회귀 테스트.

검증 항목
1. 5개 품목군(화장품/식품·건기식/전기·생활용품 KC/반려동물 사료/일반 공산품)의 체크리스트가
   서로 다르고, 근거 조문에 시행일·원문 URL·인용문이 붙어 있다.
2. 라벨 문구를 넣으면 누락을 잡고, 비우면 체크리스트와 흔한 과태료 사례를 돌려준다.
3. `check_korean_labeling` MCP 툴(15종)ㆍ`POST /v1/tools/check_korean_labeling`ㆍ웹 UI 탭.
4. 새 가이드 5종이 근거 상수·규제 태그·단정 금지 규칙을 지키고 sitemap/llms 에 자동 반영된다.
5. 0.5.1 버전 동기화와 익명성(전화번호ㆍ이메일ㆍ키) 스캔.

실행: PYTHONPATH=src python3 -m unittest tests.test_labeling_korean_0_5_1 -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import guides, labeling, web_ui  # noqa: E402
from import_compliance.api import BILLABLE_TOOLS, TOOL_DEFS, TOOL_INDEX, call_tool, mcp_manifest  # noqa: E402
from import_compliance.mcp_http import handle as mcp_handle  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.standards import REGULATION_TAGS  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402

GROUPS = ("cosmetics", "general_food", "health_functional_food", "kc_electronics", "pet_food",
          "general_goods")
NEW_GUIDES = ("kc-korean-labeling-items", "pet-food-labeling-items", "all-imports-korean-label",
              "label-sticker-fell-off", "label-missing-penalty-cases")

COMPLETE_KC = ("KC 마크 / 안전확인신고번호 XU12345-20001 / 모델명 ABC-100 / "
               "제조업자 (주)예시전자 / 정격 220V 60Hz 15W / MADE IN CHINA")
COMPLETE_PET = ("성분등록번호 제00-000호 / 제품명 닭고기 함유 배합사료 펠릿 / "
                "등록성분량 조단백질 26% 이상 조지방 12% 이상 / 원료명 닭고기, 옥수수 / "
                "용도 성견용 / 주의사항 개봉 후 냉장보관 / 실제 중량 2kg / "
                "제조일 2026.05.01 유통기한 2027.05.01 / "
                "제조업자 (주)예시펫푸드 인천광역시 전화 000-0000-0000")
COMPLETE_COSMETICS = ("명칭 수분 크림 / 상호 (주)예시코스메틱 주소 서울 / 전성분 정제수, 글리세린 / "
                      "용량 50mL / 제조번호 A1B2 / 사용기한 2027.12.31 / 가격 29,000원 / "
                      "주의사항 이상이 생기면 사용 중지")


class GroupChecklistTest(unittest.TestCase):
    def test_five_groups_have_distinct_checklists(self):
        sets = {group: {row["item_id"] for row in labeling.checklist(group)} for group in GROUPS}
        self.assertIn("kc_mark", sets["kc_electronics"])
        self.assertIn("cert_number", sets["kc_electronics"])
        self.assertIn("ingredient_registration_no", sets["pet_food"])
        self.assertIn("ruminant_warning", sets["pet_food"])
        self.assertIn("origin", sets["general_goods"])
        self.assertNotIn("kc_mark", sets["pet_food"])
        self.assertNotIn("ingredient_registration_no", sets["general_goods"])

    def test_group_meta_covers_every_group(self):
        for group in GROUPS:
            meta = labeling.GROUP_META[group]
            for key in ("label_ko", "governing_law_ko", "authority_ko", "note_ko"):
                self.assertTrue(meta[key].strip(), (group, key))

    def test_every_basis_has_verified_fields(self):
        rows = []
        for group in GROUPS:
            rows.extend(labeling.CHECKLISTS[group])
            rows.extend(labeling.FINE_CASES[group])
        bases = []
        for row in rows:
            if "basis" in row:
                bases.extend(row["basis"] if isinstance(row["basis"], list) else [row["basis"]])
        self.assertGreaterEqual(len(bases), 20)
        for basis in bases:
            self.assertTrue(str(basis.get("law") or "").strip())
            self.assertTrue(str(basis.get("article") or "").strip())
            self.assertRegex(str(basis.get("effective_date") or ""), r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(str(basis.get("quote") or "").strip())
            self.assertTrue(str(basis.get("url") or "").startswith("http"))
            self.assertTrue(str(basis.get("verified_on") or "").strip())

    def test_fine_cases_cover_the_common_mistakes(self):
        food_cases = " ".join(case["case_ko"] for case in labeling.FINE_CASES["general_food"])
        cosmetic_cases = " ".join(case["case_ko"] for case in labeling.FINE_CASES["cosmetics"])
        kc_cases = " ".join(case["case_ko"] for case in labeling.FINE_CASES["kc_electronics"])
        self.assertIn("소비기한", food_cases)
        self.assertIn("스티커", food_cases)
        self.assertIn("전성분", cosmetic_cases)
        self.assertIn("KC", kc_cases)
        self.assertTrue(any("스티커" in case["case_ko"] for case in labeling.FINE_CASES["general_goods"]))

    def test_method_checks_exist_for_every_group(self):
        for group in GROUPS:
            self.assertGreaterEqual(len(labeling.METHOD_CHECKS[group]), 1, group)

    def test_group_tags_are_known_regulation_tags(self):
        for group, tags in labeling.GROUP_TAGS.items():
            for tag in tags:
                self.assertIn(tag, REGULATION_TAGS, (group, tag))


class NormalizeGroupTest(unittest.TestCase):
    def test_aliases(self):
        cases = {
            "화장품": "cosmetics", "cosmetic": "cosmetics", "건기식": "health_functional_food",
            "kc": "kc_electronics", "전기용품": "kc_electronics", "사료": "pet_food",
            "pet_food": "pet_food", "general": "general_goods", "공산품": "general_goods",
            "food": "general_food",
        }
        for raw, expected in cases.items():
            self.assertEqual(labeling.normalize_group(raw), expected, raw)

    def test_infers_from_text_when_value_missing(self):
        self.assertEqual(labeling.normalize_group("", "강아지 동결건조 간식 라벨"), "pet_food")
        self.assertEqual(labeling.normalize_group("", "KC 안전확인 표시"), "kc_electronics")
        self.assertEqual(labeling.normalize_group("", "수분 크림 전성분"), "cosmetics")
        self.assertEqual(labeling.normalize_group("", "비타민D3 영양제"), "health_functional_food")

    def test_unknown_falls_back_to_general_goods(self):
        self.assertEqual(labeling.normalize_group("", "텀블러"), "general_goods")
        self.assertEqual(labeling.normalize_group("", ""), "general_goods")


class LabelingCheckTest(unittest.TestCase):
    def test_complete_cosmetics_label_is_low_risk(self):
        result = labeling.check("cosmetics", label_text=COMPLETE_COSMETICS)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["verdict"], "low_risk")
        self.assertGreaterEqual(result["completion_rate"], 0.9)

    def test_cosmetics_missing_ingredients_is_caught(self):
        text = COMPLETE_COSMETICS.replace("전성분 정제수, 글리세린", "")
        result = labeling.check("cosmetics", label_text=text)
        self.assertIn("사용된 모든 성분(전성분)", result["missing"])
        self.assertEqual(result["verdict"], "check_likely")

    def test_complete_kc_label_is_low_risk(self):
        result = labeling.check("kc_electronics", label_text=COMPLETE_KC)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["verdict"], "low_risk")

    def test_kc_missing_mark_or_number_is_caught(self):
        result = labeling.check("kc_electronics", label_text="모델명 ABC-100 / 제조업자 (주)예시")
        self.assertIn("KC 표시(안전인증ㆍ안전확인ㆍ공급자적합성확인ㆍ안전기준준수 표시 도안)",
                      result["missing"])
        self.assertIn("인증ㆍ신고 번호(도안 안에 기재)", result["missing"])

    def test_kc_purchase_agency_notice_is_conditional(self):
        without = labeling.check("kc_electronics", label_text=COMPLETE_KC)
        agency = labeling.check("kc_electronics", label_text=COMPLETE_KC, channel="agency")
        row = next(r for r in agency["checklist"] if r["item_id"] == "purchase_agency_notice")
        self.assertEqual(row["status"], "missing")
        self.assertIn("구매대행 고지(구매대행 제품ㆍ안전관리대상ㆍ인증 표시 사항)",
                      agency["conditional_missing"])
        plain = next(r for r in without["checklist"] if r["item_id"] == "purchase_agency_notice")
        self.assertEqual(plain["status"], "not_applicable")

    def test_kc_parallel_import_mark(self):
        result = labeling.check("kc_electronics", label_text=COMPLETE_KC, channel="parallel_import")
        row = next(r for r in result["checklist"] if r["item_id"] == "parallel_import_mark")
        self.assertEqual(row["status"], "missing")

    def test_complete_pet_label_is_low_risk_and_import_needs_korean_package(self):
        local = labeling.check("pet_food", label_text=COMPLETE_PET)
        self.assertEqual(local["missing"], [])
        self.assertEqual(local["verdict"], "low_risk")
        imported = labeling.check("pet_food", label_text=COMPLETE_PET, imported="yes")
        self.assertIn("한글로 표시된 포장지(수입신고 첨부)", imported["conditional_missing"])

    def test_pet_ruminant_warning_applies(self):
        result = labeling.check("pet_food", label_text=COMPLETE_PET, animal_origin="yes")
        row = next(r for r in result["checklist"] if r["item_id"] == "ruminant_warning")
        self.assertEqual(row["status"], "missing")

    def test_pet_missing_registration_number_is_caught(self):
        text = COMPLETE_PET.replace("성분등록번호 제00-000호", "")
        result = labeling.check("pet_food", label_text=text)
        self.assertIn("사료 성분등록번호", result["missing"])

    def test_general_goods_has_no_required_items(self):
        result = labeling.check("general_goods", label_text="원산지 중국")
        self.assertEqual(result["required_count"], 0)
        self.assertEqual(result["verdict"], "info_needed")
        self.assertIn("통일된", result["group_note_ko"])
        origin = next(r for r in result["checklist"] if r["item_id"] == "origin")
        self.assertEqual(origin["status"], "present")

    def test_no_label_text_returns_checklist_and_fine_cases(self):
        for group in GROUPS:
            result = labeling.check(group)
            self.assertEqual(result["verdict"], "info_needed")
            self.assertEqual(result["missing"], [])
            self.assertGreaterEqual(len(result["checklist"]), 3)
            self.assertGreaterEqual(len(result["fine_cases"]), 2, group)

    def test_coverage_note_never_claims_legality(self):
        for group in GROUPS:
            result = labeling.check(group, label_text="제품명 예시")
            self.assertIn("확정하지 않습니다", result["coverage_ko"])
            self.assertNotEqual(result["verdict"], "low_risk" if not result["missing"] else "low_risk")


class LabelingToolTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _call(self, payload):
        return call_tool("check_korean_labeling", payload, self.store, client_id="label-test")

    def test_tool_registered_as_15th(self):
        names = [tool["name"] for tool in TOOL_DEFS]
        self.assertIn("check_korean_labeling", names)
        self.assertEqual(len(TOOL_DEFS), 15)
        self.assertEqual(len(BILLABLE_TOOLS), 14)
        self.assertIn("check_korean_labeling", BILLABLE_TOOLS)
        entry = next(t for t in mcp_manifest()["tools"] if t["name"] == "check_korean_labeling")
        enum = entry["inputSchema"]["properties"]["product_type"]["enum"]
        for group in ("cosmetics", "general_food", "health_functional_food", "kc_electronics",
                      "pet_food", "general_goods"):
            self.assertIn(group, enum)

    def test_tool_returns_labeling_block(self):
        out = self._call({"product_type": "cosmetics", "label_text": COMPLETE_COSMETICS})
        self.assertTrue(out["ok"])
        result = out["result"]
        for key in ("korean_labeling", "checklist", "fine_cases", "method_checks_ko",
                    "next_actions", "verdict", "assessment_status", "evidence", "disclaimer",
                    "data_provenance", "coverage_ko", "regulation_tags"):
            self.assertIn(key, result)
        self.assertEqual(result["korean_labeling"]["group"], "cosmetics")
        self.assertEqual(result["verdict"]["code"], "low_risk")
        self.assertTrue(result["evidence"])
        for row in result["evidence"]:
            self.assertTrue(row["url"].startswith("http"))

    def test_tool_flags_missing_item_with_finding_basis(self):
        out = self._call({"product_type": "kc_electronics", "label_text": "모델명 ABC-100"})
        result = out["result"]
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertGreaterEqual(result["korean_labeling"]["missing_count"], 2)
        self.assertTrue(result["findings"])
        self.assertTrue(result["findings"][0]["legal_basis"])

    def test_tool_infers_group_from_label_text(self):
        out = self._call({"label_text": "강아지 사료 성분등록번호 제00-000호"})
        self.assertEqual(out["result"]["group"], "pet_food")

    def test_tool_limit_truncates_fine_cases(self):
        out = self._call({"product_type": "general_food", "limit": 2})
        self.assertEqual(len(out["result"]["fine_cases"]), 2)

    def test_tool_validates_inputs(self):
        self.assertEqual(self._call({})["error"], "invalid_argument")
        self.assertEqual(self._call({"product_type": "cosmetics", "label_text": "x"})["error"],
                         "invalid_argument")
        self.assertEqual(self._call({"product_type": "cosmetics", "label_text": "가" * 4001})["error"],
                         "invalid_argument")
        self.assertEqual(self._call({"product_type": "cosmetics", "label_items": []})["error"],
                         "invalid_argument")
        self.assertEqual(self._call({"product_type": "cosmetics",
                                     "label_items": {"not_an_item": True}})["error"],
                         "invalid_argument")

    def test_tool_accepts_label_items_checkbox(self):
        out = self._call({"product_type": "cosmetics", "label_items": {"manufacture_no": False}})
        self.assertIn("제조번호", out["result"]["missing"])

    def test_outputs_avoid_conclusive_phrasing(self):
        for group in GROUPS:
            out = self._call({"product_type": group})
            result = out["result"]
            texts = [result["answer"]["headline"], *result["answer"]["guidance"],
                     result["verdict"]["note_ko"], result["group_note_ko"], result["coverage_ko"],
                     *result["next_actions"], *result["method_checks_ko"]]
            for case in result["fine_cases"]:
                texts.extend([case["case_ko"], case["why_ko"], case["fix_ko"]])
            for text in texts:
                self.assertEqual(find_conclusive_phrasing(text), [], (group, text[:60]))

    def test_mcp_tools_call(self):
        response = mcp_handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                               "params": {"name": "check_korean_labeling",
                                          "arguments": {"product_type": "pet_food",
                                                        "label_text": COMPLETE_PET}}},
                              store=self.store)
        self.assertEqual(response["id"], 7)
        text = json.dumps(response, ensure_ascii=False)
        self.assertIn("korean_labeling", text)
        self.assertIn("pet_food", text)


class HttpEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store(":memory:")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()

    def _post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as response:
            return response.read().decode("utf-8")

    def test_post_endpoint_returns_result(self):
        payload = self._post("/v1/tools/check_korean_labeling",
                             {"product_type": "general_food", "label_text": "제품명 감귤주스"})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool"], "check_korean_labeling")
        self.assertEqual(payload["result"]["group"], "general_food")
        self.assertTrue(payload["result"]["missing"])

    def test_sitemap_and_llms_include_new_guides(self):
        sitemap = self._get("/sitemap.xml")
        for slug in NEW_GUIDES:
            self.assertIn(f"/guides/{slug}", sitemap)
        llms = self._get("/llms.txt")
        self.assertIn(f"{len(guides.items())}개 질문", llms)

    def test_home_page_has_label_tab_and_presets(self):
        page = self._get("/")
        for marker in ('id="tabbtn-label"', 'id="tab-label"', 'id="label-form"',
                       'id="label-text"', "/v1/tools/check_korean_labeling"):
            self.assertIn(marker, page)
        self.assertEqual(page.count("data-label-preset="), 4)


class VersionAndAnonymityTest(unittest.TestCase):
    def test_version_sync(self):
        self.assertEqual(__version__, "0.5.1")
        self.assertEqual(web_ui.SERVICE_VERSION, __version__)
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["version"], __version__)
        with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as handle:
            docker = handle.read()
        self.assertIn('org.opencontainers.image.version="0.5.1"', docker)
        self.assertEqual(TOOL_INDEX["check_korean_labeling"]["name"], "check_korean_labeling")

    def test_new_files_have_no_personal_data_or_secrets(self):
        patterns = [
            re.compile(r"DATA_GO_KR_SERVICE_KEY\s*=\s*[A-Za-z0-9%+/=]{20,}"),
            re.compile(r"LAW_GO_KR_OC\s*=\s*[A-Za-z0-9]{4,}"),
            re.compile(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)"),
            re.compile(r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com"),
        ]
        targets = [
            os.path.join(SRC, "import_compliance", name)
            for name in ("labeling.py", "api.py", "web_ui.py")
        ] + [os.path.join(SRC, "guides_items.json"), os.path.join(ROOT, "README.md"),
             os.path.join(ROOT, "14-labeling-korean-0.5.1.md")]
        for path in targets:
            if not os.path.exists(path):
                continue
            text = open(path, encoding="utf-8").read()
            for pattern in patterns:
                self.assertIsNone(pattern.search(text), f"{os.path.basename(path)}: {pattern.pattern}")

    def test_new_guides_follow_catalog_rules(self):
        index = {item["slug"]: item for item in guides.items()}
        registry = guides.basis_registry()
        for slug in NEW_GUIDES:
            item = index[slug]
            with self.subTest(slug=slug):
                self.assertTrue(guides.is_indexable(item))
                self.assertGreaterEqual(len(item["answer_ko"]), guides.THIN_MIN_ANSWER)
                self.assertGreaterEqual(len(item["checkpoints_ko"]), guides.THIN_MIN_CHECKPOINTS)
                self.assertGreaterEqual(len(item["keywords"]), 5)
                self.assertTrue(item["question_ko"].endswith("?"))
                self.assertEqual(item["tool"], "check_korean_labeling")
                self.assertIn(item["tool"], TOOL_INDEX)
                for tag in item["tags"]:
                    self.assertIn(tag, REGULATION_TAGS)
                    self.assertNotEqual(guides.authority_for(tag), "소관 기관 확인")
                    self.assertIn(guides.tool_for_tag(tag), TOOL_INDEX)
                self.assertTrue(item["basis_keys"])
                for key in item["basis_keys"]:
                    self.assertIn(key, registry)
                for related in item["related_guides"]:
                    self.assertIn(related, index)
                for text in [item["answer_ko"], item["summary_ko"], *item["checkpoints_ko"],
                             *(item.get("key_points_ko") or [])]:
                    self.assertEqual(find_conclusive_phrasing(text), [], text[:60])


if __name__ == "__main__":
    unittest.main(verbosity=2)
