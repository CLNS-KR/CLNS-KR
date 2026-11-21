"""0.5.5 — 질문형 가이드 10종 추가(90 → 100, 카탈로그 1.6.0) 회귀 테스트.

검증 항목
1. 카탈로그가 1.6.0(100종)이고, 새 10종이 근거 조문·규제 태그·툴·단정 금지 규칙을 지킨다.
2. 새 질문이 기존 90종과 검색 의도가 겹치지 않고, 서로 다른 카테고리에 흩어져 있다.
3. `/guides/{slug}`·sitemap·llms.txt·`/v1/meta` 가 새 카탈로그를 자동 반영한다.
4. 사입·구매대행 KC·펀딩 리워드·개별인정형 원료·단미사료·통관 반송 환불·부호 차용·
   책임판매업·영양표시·KC 표시 제거가 모두 페이지로 열린다.

실행: PYTHONPATH=src python3 -m unittest tests.test_v055_guides_100 -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import guides, pseo  # noqa: E402
from import_compliance.api import TOOL_INDEX, call_tool  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402

BASE = "https://clns-kr.onrender.com"

NEW_SLUGS = (
    "ali-temu-sourcing-import",
    "purchase-agency-kc-notice",
    "wadiz-reward-customs",
    "hff-individual-ingredient",
    "pet-treat-single-feed-registration",
    "overseas-shipping-customs-block-refund",
    "personal-id-lend",
    "cosmetics-responsible-seller-registration",
    "imported-food-nutrition-label",
    "kc-mark-removal-resale",
)


class GuideCatalog160Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = guides.items()
        cls.index = {item["slug"]: item for item in cls.items}

    def test_catalog_version_and_count(self):
        meta = guides.catalog_meta()
        self.assertEqual(meta["version"], "1.6.0")
        self.assertEqual(meta["verified_on"], "2026-11-21")
        self.assertEqual(meta["count"], 100)
        self.assertEqual(len(self.items), 100)
        self.assertEqual(len({item["slug"] for item in self.items}), len(self.items))

    def test_ten_new_slugs_are_present_and_indexable(self):
        self.assertEqual(len(NEW_SLUGS), 10)
        for slug in NEW_SLUGS:
            with self.subTest(slug=slug):
                item = self.index.get(slug)
                self.assertIsNotNone(item)
                self.assertTrue(guides.is_indexable(item))
                self.assertGreaterEqual(len(item["answer_ko"]), guides.THIN_MIN_ANSWER)
                self.assertGreaterEqual(len(item["summary_ko"]), 60)
                self.assertGreaterEqual(len(item["question_ko"]), 10)
                self.assertGreaterEqual(len(item["checkpoints_ko"]), guides.THIN_MIN_CHECKPOINTS)
                self.assertGreaterEqual(len(item.get("keywords") or []), 5)
                self.assertTrue(item["question_ko"].endswith("?"))

    def test_new_questions_are_distinct(self):
        questions = [item["question_ko"] for item in self.items]
        self.assertEqual(len(set(questions)), len(questions))
        joined = " ".join(self.index[slug]["question_ko"] for slug in NEW_SLUGS)
        for token in ("알리", "구매대행", "펀딩", "개별인정형", "단미사료", "통관에서 막히면",
                      "개인통관고유부호", "화장품책임판매업", "영양표시", "KC 인증 표시"):
            self.assertIn(token, joined, token)

    def test_new_questions_reference_verified_basis(self):
        for slug in NEW_SLUGS:
            item = self.index[slug]
            with self.subTest(slug=slug):
                self.assertIn(item["tool"], TOOL_INDEX)
                for tag in item["tags"]:
                    self.assertNotEqual(guides.authority_for(tag), "소관 기관 확인")
                    self.assertIn(guides.tool_for_tag(tag), TOOL_INDEX)
                basis = guides.legal_basis(item)
                self.assertTrue(basis, "근거 조문이 비어 있습니다")
                for row in basis:
                    self.assertTrue(row.get("law"))
                    self.assertTrue(row.get("article"))
                    self.assertRegex(str(row.get("effective_date") or ""), r"^\d{4}-\d{2}-\d{2}$")
                    self.assertTrue(str(row.get("quote") or "").strip())
                    self.assertTrue(str(row.get("url") or "").startswith("http"))

    def test_basis_keys_resolve_to_registry_only(self):
        registry = guides.basis_registry()
        for slug in NEW_SLUGS:
            item = self.index[slug]
            self.assertTrue(item.get("basis_keys") or item.get("cases"), slug)
            for key in item.get("basis_keys") or []:
                self.assertIn(key, registry, slug)

    def test_new_questions_avoid_conclusive_phrasing(self):
        for slug in NEW_SLUGS:
            item = self.index[slug]
            texts = [item["answer_ko"], item["summary_ko"], *item["checkpoints_ko"],
                     *(item.get("key_points_ko") or [])]
            for text in texts:
                with self.subTest(slug=slug):
                    self.assertEqual(find_conclusive_phrasing(text), [], text[:60])

    def test_new_questions_link_to_existing_pages(self):
        slugs = set(self.index)
        for slug in NEW_SLUGS:
            item = self.index[slug]
            with self.subTest(slug=slug):
                self.assertTrue(item.get("related_guides"))
                for related in item["related_guides"]:
                    self.assertIn(related, slugs)
                for product in item.get("related_items") or []:
                    self.assertIsNotNone(pseo.get_item(product), product)

    def test_new_questions_spread_across_categories(self):
        categories = {self.index[slug]["category"] for slug in NEW_SLUGS}
        self.assertGreaterEqual(len(categories), 6)


class GuideRender160Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()
        handler = make_handler(cls.store)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.status, response.read().decode("utf-8")

    def test_every_new_guide_renders_with_faq(self):
        for slug in NEW_SLUGS:
            with self.subTest(slug=slug):
                status, page = self.get(f"/guides/{slug}")
                self.assertEqual(status, 200)
                item = guides.get_item(slug)
                self.assertIn(item["question_ko"], page)
                self.assertIn(item["answer_ko"], page)
                self.assertIn("근거 법령", page)
                self.assertIn("자주 틀리는 답", page)
                block = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
                payload = json.loads(block.group(1))
                faq = next(node for node in payload["@graph"] if node["@type"] == "FAQPage")
                self.assertEqual(faq["mainEntity"][0]["name"], item["question_ko"])
                self.assertEqual(faq["mainEntity"][0]["acceptedAnswer"]["text"], item["answer_ko"])

    def test_guide_index_lists_one_hundred(self):
        status, page = self.get("/guides/")
        self.assertEqual(status, 200)
        self.assertIn("100개 질문", page)
        self.assertIn(f"수입 규제 질문 {len(guides.items())}선", page)
        for slug in NEW_SLUGS:
            self.assertIn(f"/guides/{slug}", page)

    def test_sitemap_and_llms_reflect_all_guides(self):
        status, raw = self.get("/sitemap.xml")
        self.assertEqual(status, 200)
        root = ET.fromstring(raw)
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(ns + "loc")]
        for slug in NEW_SLUGS:
            self.assertIn(f"{BASE}/guides/{slug}", locs)
        self.assertEqual(len(locs), 1 + len(pseo.indexable_paths()) + len(guides.indexable_paths()))
        self.assertEqual(len(locs), 138)
        status, body = self.get("/llms.txt")
        self.assertEqual(status, 200)
        self.assertIn(f"{len(guides.items())}개 질문", body)
        self.assertIn("FAQPage", body)

    def test_service_meta_reports_new_catalog(self):
        payload = call_tool("get_service_meta", {}, self.store)["result"]
        self.assertEqual(payload["guides"]["count"], 100)
        self.assertEqual(payload["guides"]["catalog_version"], "1.6.0")
        self.assertIn("FAQPage", payload["guides"]["structured_data"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
