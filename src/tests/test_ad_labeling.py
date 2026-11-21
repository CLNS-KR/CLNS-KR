"""0.2.0 과대광고·한글표시사항 검수 테스트.

검증 대상
---------
1. 같은 문구가 **품목 유형(일반식품/건기식/화장품/기능성화장품)** 에 따라 다르게 판정되는지
2. 위험도(높음/주의)와 근거 조문·대체 표현이 함께 오는지
3. 한글표시사항 체크리스트가 유형별로 다르고, 누락을 잡아내는지
4. MCP/HTTP/웹 UI에 툴이 등록되고 응답 스키마가 기존 계약(verdict·findings·evidence·면책)을
   유지하는지
5. 개인정보·시크릿·실명이 새로 들어가지 않았는지

실행: python3 tests/test_ad_labeling.py   (네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import advertising, labeling, web_ui  # noqa: E402
from import_compliance.api import TOOL_DEFS, call_tool, mcp_manifest  # noqa: E402
from import_compliance.live_api import SOURCE_DISPOSITION_MFG, SOURCE_DISPOSITION_SALES  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402


def review_once(text: str, product_type: str, **kwargs):
    return advertising.review(text, product_type, **kwargs)


class CategoryDifferenceTest(unittest.TestCase):
    """같은 문구라도 유형에 따라 허용/금지가 달라져야 한다."""

    PHRASE = "체지방 감소에 도움을 줄 수 있음"

    def test_weight_loss_claim_blocks_general_food(self):
        result = review_once(self.PHRASE, "general_food")
        ids = [f["rule_id"] for f in result["findings"]]
        self.assertIn("AD-03", ids)
        self.assertEqual(result["risk_high"], 1)
        self.assertEqual(result["verdict"], "check_likely")

    def test_weight_loss_claim_allowed_for_health_functional_food(self):
        result = review_once(self.PHRASE, "health_functional_food")
        ids = [f["rule_id"] for f in result["findings"]]
        self.assertNotIn("AD-03", ids, "건기식 인정 기능성 표현을 일반식품 기준으로 막으면 안 된다")
        self.assertEqual(result["verdict"], "low_risk")
        hints = [row["keyword"] for row in result["recognized_claim_hints"]]
        self.assertIn("체지방 감소", hints)

    def test_mi백_is_blocked_for_plain_cosmetics_but_allowed_for_functional(self):
        plain = review_once("피부 미백에 좋은 크림", "cosmetics")
        self.assertEqual(plain["risk_high"], 1)
        functional = review_once("피부 미백에 좋은 크림", "functional_cosmetics")
        self.assertEqual(functional["risk_high"], 0)
        entry = next(f for f in functional["findings"] if f["rule_id"] == "AD-09")
        self.assertEqual(entry["risk"], "caution")
        self.assertIn("기능성화장품", entry["category_note_ko"])

    def test_functional_flag_switches_cosmetics_category(self):
        result = advertising.review("주름개선 세럼", "cosmetics", functional="yes")
        self.assertEqual(result["product_type"], "functional_cosmetics")

    def test_disease_claim_stays_high_everywhere(self):
        for ptype in ("general_food", "health_functional_food", "cosmetics", "functional_cosmetics"):
            with self.subTest(product_type=ptype):
                result = review_once("아토피 치료에 효과", ptype)
                entry = next((f for f in result["findings"] if f["rule_id"] == "AD-01"), None)
                self.assertIsNotNone(entry)
                self.assertEqual(entry["risk"], "high")

    def test_category_comparison_has_four_rows(self):
        rows = advertising.compare_categories("체지방 감소, 미백, 아토피 치료")
        self.assertEqual(len(rows), 4)
        by_type = {row["product_type"]: row for row in rows}
        self.assertEqual(by_type["general_food"]["highest_risk"], "high")
        self.assertEqual(by_type["functional_cosmetics"]["highest_risk"], "high")
        self.assertLess(by_type["health_functional_food"]["finding_count"],
                        by_type["general_food"]["finding_count"])


class ClaimRuleTest(unittest.TestCase):
    CANONICAL = {
        "AD-01": "항암 효과", "AD-02": "부작용 없음", "AD-03": "면역력 증진",
        "AD-04": "100%", "AD-05": "먹어봤더니", "AD-06": "타사 대비",
        "AD-07": "짝퉁", "AD-08": "의사 추천", "AD-09": "미백",
        "AD-10": "다이어트", "AD-11": "디톡스", "AD-12": "피부 재생",
        "AD-13": "무첨가", "AD-14": "선정적", "AD-15": "기능성 표방",
        "AD-16": "정품과 동일",
    }

    def test_every_rule_matches_its_canonical_example(self):
        """정규식이 한국어 활용형에서 깨지지 않는지 고정한다(예: ‘먹어봤더니’)."""
        rules = {rule["id"]: rule for rule in advertising.CLAIM_RULES}
        self.assertEqual(set(rules), set(self.CANONICAL))
        for rule_id, sample in self.CANONICAL.items():
            with self.subTest(rule=rule_id):
                hit = any(re.search(pattern, sample) for pattern, _ in rules[rule_id]["patterns"])
                self.assertTrue(hit, f"{rule_id} 가 '{sample}' 를 탐지하지 못했습니다")

    def test_absolute_claims_are_high(self):
        result = review_once("100% 천연, 즉시 효과, 세계 최고", "general_food")
        entry = next(f for f in result["findings"] if f["rule_id"] == "AD-04")
        self.assertEqual(entry["risk"], "high")

    def test_testimonial_only_is_caution(self):
        result = review_once("먹어봤더니 4kg 감량했어요", "health_functional_food")
        self.assertEqual(result["risk_high"], 0)
        self.assertEqual(result["verdict"], "info_needed")
        self.assertEqual(result["findings"][0]["risk"], "caution")

    def test_context_exception_does_not_flag_medicine_disclaimer(self):
        result = review_once("이 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다", "health_functional_food")
        self.assertEqual(result["findings"], [])

    def test_every_finding_has_basis_and_safer_wording(self):
        result = review_once("항암 효과, 100% 다이어트", "general_food")
        self.assertTrue(result["findings"])
        for finding in result["findings"]:
            self.assertTrue(finding["legal_basis"])
            for basis in finding["legal_basis"]:
                for key in ("law", "article", "effective_date", "url", "quote", "verified_on"):
                    self.assertIn(key, basis)
            self.assertTrue(finding["safer_ko"])
            self.assertIn(finding["risk"], ("high", "caution"))

    def test_13_prohibited_hos_are_covered(self):
        """식품표시광고법 제8조제1항 1~9호 유형이 규칙에 매핑돼 있는지."""
        articles = {b["article"] for rule in advertising.CLAIM_RULES for b in rule["basis"]}
        for number in range(1, 10):
            with self.subTest(ho=number):
                self.assertIn(f"제8조제1항제{number}호", articles)
        self.assertIn("제9조제1항", articles)

    def test_cosmetics_ai_expert_rule_present(self):
        result = review_once("AI로 만든 피부과 전문의 추천 영상", "cosmetics")
        entry = next(f for f in result["findings"] if f["rule_id"] == "AD-08")
        articles = [b["article"] for b in entry["legal_basis"]]
        self.assertIn("제13조제1항제4호", articles)


class LabelingChecklistTest(unittest.TestCase):
    COMPLETE_FOOD = (
        "제품명 제주 감귤주스 / 내용량 500mL / 원재료명 감귤과즙 99% / "
        "영업소 (주)예시식품 인천광역시 / 식품유형 과채주스 / 품목보고번호 2019012345678 / "
        "소비기한 2027.03.15 / 보관방법 냉장보관 / 주의사항 개봉 후 빠르게 섭취 / "
        "영양정보 열량 120kcal 나트륨 30mg / 알레르기 없음"
    )

    def test_checklist_differs_by_type(self):
        food = {row["item_id"] for row in labeling.checklist("general_food")}
        hff = {row["item_id"] for row in labeling.checklist("health_functional_food")}
        cosmetics = {row["item_id"] for row in labeling.checklist("cosmetics")}
        self.assertIn("food_type", food)
        self.assertNotIn("food_type", hff)
        self.assertIn("hff_mark", hff)
        self.assertIn("not_medicine", hff)
        self.assertIn("manufacture_no", cosmetics)
        self.assertIn("price", cosmetics)

    def test_complete_food_label_is_low_risk(self):
        result = labeling.check("general_food", label_text=self.COMPLETE_FOOD)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["verdict"], "low_risk")
        self.assertGreaterEqual(result["completion_rate"], 0.9)

    def test_missing_expiry_is_caught(self):
        text = self.COMPLETE_FOOD.replace("소비기한 2027.03.15", "")
        result = labeling.check("general_food", label_text=text)
        self.assertIn("소비기한(또는 품질유지기한ㆍ제조연월일)", result["missing"])
        self.assertEqual(result["verdict"], "check_likely")

    def test_hff_requires_medicine_disclaimer(self):
        text = ("제품명 비타민D3 / 내용량 60정 / 원료명 비타민D3 / 영업소 (주)예시헬스 서울 / "
                "소비기한 2027.03.15 보관방법 서늘한 곳 / 섭취량 1일 1회 1정 섭취방법 물과 함께 / "
                "섭취 시 주의사항 / 건강기능식품 / 기능성 칼슘 흡수에 필요 / 비타민D 20μg 100% / "
                "원료의 함량 20μg / 소비자 안전을 위한 주의사항 / 영양정보")
        result = labeling.check("health_functional_food", label_text=text)
        self.assertIn("질병 예방ㆍ치료를 위한 의약품이 아니라는 표현", result["missing"])

    def test_hff_medicine_disclaimer_is_detected(self):
        text = "제품명 x / 의약품이 아닙니다"
        result = labeling.check("health_functional_food", label_text=text)
        row = next(r for r in result["checklist"] if r["item_id"] == "not_medicine")
        self.assertEqual(row["status"], "present")
        self.assertNotIn("질병 예방ㆍ치료를 위한 의약품이 아니라는 표현", result["missing"])

    def test_cosmetics_complete_label(self):
        text = ("명칭 수분 크림 / 상호 (주)예시코스메틱 주소 서울 / 전성분 정제수, 글리세린 / "
                "용량 50mL / 제조번호 A1B2 / 사용기한 2027.12.31 / 가격 29,000원 / "
                "주의사항 이상이 생기면 사용 중지")
        result = labeling.check("cosmetics", label_text=text)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["verdict"], "low_risk")

    def test_label_items_override_text_detection(self):
        result = labeling.check("general_food", label_text="제품명만 있음",
                                provided={"date_marking": False})
        self.assertIn("소비기한(또는 품질유지기한ㆍ제조연월일)", result["missing"])
        row = next(r for r in result["checklist"] if r["item_id"] == "date_marking")
        self.assertEqual(row["status"], "missing")

    def test_no_input_reports_info_needed(self):
        result = labeling.check("general_food")
        self.assertEqual(result["verdict"], "info_needed")
        self.assertEqual(result["missing"], [])


class AdLabelingToolTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _call(self, payload):
        return call_tool("check_ad_labeling", payload, self.store, client_id="ad-test")

    def test_tool_registered(self):
        names = [tool["name"] for tool in TOOL_DEFS]
        self.assertIn("check_ad_labeling", names)
        entry = next(t for t in mcp_manifest()["tools"] if t["name"] == "check_ad_labeling")
        props = entry["inputSchema"]["properties"]
        for key in ("product_type", "ad_copy", "label_text", "label_items", "imported", "functional"):
            self.assertIn(key, props)

    def test_high_risk_copy_returns_check_likely_and_blocks(self):
        out = self._call({"product_name": "다이어트 환", "product_type": "general_food",
                          "ad_copy": "먹기만 하면 100% 다이어트, 항암 효과 입증"})
        self.assertTrue(out["ok"])
        result = out["result"]
        self.assertEqual(result["verdict"]["code"], "check_likely")
        for key in ("ad_review", "labeling_check", "ad_labeling", "evidence", "disclaimer",
                    "data_provenance", "tier", "assessment_status"):
            self.assertIn(key, result)
        self.assertEqual(result["ad_review"]["product_type"], "general_food")
        self.assertGreaterEqual(result["ad_review"]["risk_high"], 2)
        tags = result["regulation_tags"]
        self.assertTrue({"FOOD_AD_CLAIM", "KOREAN_LABELING"} & set(tags))

    def test_hff_functional_claim_not_blocked(self):
        out = self._call({"product_type": "health_functional_food",
                          "ad_copy": "체지방 감소에 도움을 줄 수 있음"})
        result = out["result"]
        ids = [f["rule_id"] for f in result["ad_review"]["findings"]]
        self.assertNotIn("AD-03", ids)
        self.assertNotEqual(result["ad_review"]["verdict"], "check_likely")

    def test_cosmetics_claim_category(self):
        out = self._call({"product_type": "cosmetics",
                          "ad_copy": "미백 크림, 피부 재생, 여드름 치료"})
        result = out["result"]
        ids = [f["case_id"] for f in result["findings"]]
        self.assertIn("AD-09", ids)
        self.assertIn("AD-01", ids)
        self.assertIn("COSMETICS_AD_CLAIM", result["regulation_tags"])

    def test_label_only_request(self):
        out = self._call({"product_type": "cosmetics", "label_text": "명칭 크림 / 용량 50mL"})
        result = out["result"]
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertIn("가격", result["labeling_check"]["missing"])
        self.assertLess(result["labeling_check"]["completion_rate"], 1.0)
        self.assertTrue(result["next_actions"])

    def test_invalid_arguments(self):
        self.assertEqual(call_tool("check_ad_labeling", {}, self.store)["error"], "invalid_argument")
        self.assertEqual(call_tool("check_ad_labeling", {"ad_copy": "가나", "label_items": []},
                                   self.store)["error"], "invalid_argument")
        self.assertEqual(call_tool("check_ad_labeling", {"ad_copy": "가" * 4001},
                                   self.store)["error"], "invalid_argument")
        self.assertEqual(call_tool("check_ad_labeling", {"ad_copy": "x"},
                                   self.store)["error"], "invalid_argument")

    def test_guidance_avoids_conclusive_phrasing(self):
        out = self._call({"product_type": "general_food",
                          "ad_copy": "100% 천연, 100% 효과, 부작용 없음, 의사 추천"})
        joined = " ".join(out["result"]["answer"]["guidance"])
        self.assertEqual(find_conclusive_phrasing(joined), [], joined)

    def test_mcp_jsonrpc_call(self):
        from import_compliance import mcp_http
        store = Store(":memory:")
        self.addCleanup(store.close)
        listing = mcp_http.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                  store=store, client_id="mcp-ad")
        names = {tool["name"] for tool in listing["result"]["tools"]}
        self.assertIn("check_ad_labeling", names)
        called = mcp_http.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "check_ad_labeling",
                                             "arguments": {"product_type": "cosmetics",
                                                           "ad_copy": "여드름 치료 크림"}}},
                                 store=store, client_id="mcp-ad")
        self.assertFalse(called["result"].get("isError"))
        text = called["result"]["content"][0]["text"]
        self.assertIn("check_ad_labeling", text)

    def test_evidence_includes_cosmetics_law(self):
        out = self._call({"product_type": "cosmetics", "ad_copy": "주름 제거 크림"})
        laws = {row["law"] for row in out["result"]["evidence"]}
        self.assertIn("화장품법", laws)


class WebUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_ad_tab_and_form_exist(self):
        self.assertIn('id="ad-onestop-wrap"', self.page)
        self.assertIn('id="drug-fields-wrap"', self.page)
        for field in ("check-form", "ad-copy-onestop", "ad-label-onestop", "kind", "check-submit"):
            self.assertIn(f'id="{field}"', self.page)

    def test_tab_order_and_endpoints_listed(self):
        self.assertLess(self.page.index("CLNS Check"), self.page.index("CLNS Intelligence"))
        self.assertLess(self.page.index("CLNS Intelligence"), self.page.index("CLNS API &amp; MCP"))
        self.assertNotIn('data-tab="ad"', self.page)
        self.assertIn("/v1/tools/check_ad_labeling", self.page)
        self.assertIn("/v1/tools/lookup_mfds_disposition", self.page)

    def test_page_has_no_personal_data_markers(self):
        self.assertNotIn("대표자", self.page)
        self.assertNotRegex(self.page, r"01\d[- ]?\d{3,4}[- ]?\d{4}")
        self.assertNotRegex(self.page, r"[\w.+-]+@[\w-]+\.[\w.]+")


class ManifestAndAuditTest(unittest.TestCase):
    def test_version_and_manifest_agree(self):
        self.assertEqual(__version__, "0.5.4")
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["version"], __version__)
        self.assertLessEqual(len(manifest["description"]), 100)

    def test_new_sources_registered(self):
        from import_compliance.live_api import SOURCE_CATALOG
        ids = {row["source_id"] for row in SOURCE_CATALOG}
        self.assertIn(SOURCE_DISPOSITION_MFG, ids)
        self.assertIn(SOURCE_DISPOSITION_SALES, ids)

    def test_new_modules_have_no_secrets_or_personal_data(self):
        violations = [
            re.compile(r"DATA_GO_KR_SERVICE_KEY\s*=\s*[A-Za-z0-9%+/=]{20,}"),
            re.compile(r"LAW_GO_KR_OC\s*=\s*[A-Za-z0-9]{4,}"),
            re.compile(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)"),
            re.compile(r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com"),
        ]
        targets = [os.path.join(SRC, "import_compliance", name)
                   for name in ("advertising.py", "labeling.py", "mfds_dispositions.py")]
        targets += [os.path.join(ROOT, name) for name in
                    ("README.md", "09-ad-labeling-0.2.0.md", "01-api-sources-and-legal.md", "server.json")]
        for path in targets:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for pattern in violations:
                self.assertIsNone(pattern.search(text), f"{os.path.basename(path)}: {pattern.pattern}")

    def test_legal_quotes_have_urls(self):
        for rule in advertising.CLAIM_RULES:
            for basis in rule["basis"]:
                self.assertTrue(basis["url"].startswith("http"))
                self.assertTrue(basis["effective_date"])
                self.assertTrue(basis["quote"])
        for item in labeling.COMMON_FOOD_ITEMS + labeling.HFF_ITEMS + labeling.COSMETIC_ITEMS:
            self.assertTrue(item["basis"]["url"].startswith("http"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
