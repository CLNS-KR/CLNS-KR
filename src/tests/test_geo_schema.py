"""AI 검색(GEO)·검색엔진용 출력 검사 — JSON-LD·robots·sitemap·llms.txt.

검증하는 것
-----------
1. 홈의 WebApplication · Organization · WebSite 가 `@id` 로 이어지는지
2. 품목(`/p/`)·가이드(`/guides/`) 페이지의 JSON-LD 가 모두 **유효한 JSON** 이고
   FAQPage·BreadcrumbList·ItemList 숫자가 화면의 건수와 맞는지
3. robots.txt 가 주요 AI 크롤러를 빠뜨리지 않았는지, sitemap 이 XML 로 읽히는지
4. llms.txt 링크가 전부 절대 주소인지, 구조화 데이터 안내가 있는지
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ElementTree

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import guides, pseo, static_files, web_ui  # noqa: E402

LD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
AI_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ClaudeBot", "Claude-SearchBot", "PerplexityBot",
               "Google-Extended", "CCBot", "Applebot-Extended", "Bingbot")


def _blocks(page: str):
    return [json.loads(body) for body in LD_PATTERN.findall(page)]


class HomeJsonLdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_app_website_org_are_linked(self):
        blocks = _blocks(self.page)
        self.assertGreaterEqual(len(blocks), 1)
        app = blocks[0]
        self.assertEqual(app["@type"], "WebApplication")
        self.assertEqual(app["name"], "CLNS")
        self.assertTrue(app["isAccessibleForFree"])
        self.assertEqual(app["offers"]["price"], "0")
        graph = blocks[1]["@graph"]
        self.assertEqual([node["@type"] for node in graph], ["Organization", "WebSite"])
        ids = {node["@id"] for node in graph}
        self.assertIn(app["publisher"]["@id"], ids)
        self.assertIn(app["isPartOf"]["@id"], ids)
        self.assertEqual(graph[1]["potentialAction"]["@type"], "SearchAction")
        self.assertIn("?q=", graph[1]["potentialAction"]["target"]["urlTemplate"])

    def test_no_org_handle_in_structured_data(self):
        # 익명 운영 — 구조화 데이터에 개인/조직 계정 핸들을 넣지 않는다.
        for body in LD_PATTERN.findall(self.page):
            self.assertNotRegex(body, r"(?:github|gitlab)\.com/[A-Za-z0-9-]+")

    def test_first_block_is_still_web_application(self):
        # 기존 회귀 테스트가 첫 블록을 WebApplication 으로 읽는다.
        start = self.page.index('<script type="application/ld+json">')
        body = self.page[start:].split(">", 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(body)["@type"], "WebApplication")


class PageJsonLdTest(unittest.TestCase):
    def test_pseo_index_has_item_list(self):
        page = pseo.render_index()
        blocks = _blocks(page)
        collection = blocks[0]
        self.assertEqual(collection["@type"], "CollectionPage")
        items = collection["mainEntity"]
        self.assertEqual(items["@type"], "ItemList")
        self.assertEqual(items["numberOfItems"], len(pseo.items()))
        self.assertEqual([row["position"] for row in items["itemListElement"]],
                         list(range(1, len(pseo.items()) + 1)))
        for row in items["itemListElement"]:
            self.assertTrue(row["url"].startswith("http"))
            self.assertTrue(row["name"])

    def test_pseo_item_graph(self):
        slug = pseo.items()[0]["slug"]
        page = pseo.render_item(slug)
        graph = _blocks(page)[0]["@graph"]
        types = [node["@type"] for node in graph]
        self.assertIn("Article", types)
        self.assertIn("FAQPage", types)
        self.assertIn("BreadcrumbList", types)
        faq = next(node for node in graph if node["@type"] == "FAQPage")
        for question in faq["mainEntity"]:
            self.assertEqual(question["@type"], "Question")
            self.assertTrue(question["acceptedAnswer"]["text"])

    def test_guides_faq_and_crumb(self):
        slug = guides.slugs()[0]
        page = guides.render_guide(slug)
        nodes = []
        for block in _blocks(page):
            nodes.extend(block.get("@graph") or [block])
        types = [node.get("@type") for node in nodes]
        self.assertIn("FAQPage", types)
        self.assertIn("BreadcrumbList", types)
        faq = next(node for node in nodes if node.get("@type") == "FAQPage")
        self.assertTrue(faq["mainEntity"])
        for question in faq["mainEntity"]:
            self.assertTrue(question["name"])
            self.assertTrue(question["acceptedAnswer"]["text"])

    def test_no_unescaped_closing_tag(self):
        for page in (web_ui.render_page(), pseo.render_index(),
                     pseo.render_item(pseo.items()[0]["slug"]),
                     guides.render_guide(guides.slugs()[0])):
            for body in LD_PATTERN.findall(page):
                self.assertNotIn("</", body.replace("<\\/", ""))


class CrawlerFilesTest(unittest.TestCase):
    def test_robots_allows_ai_crawlers(self):
        text = static_files.robots_txt("https://example.test")
        self.assertIn("Disallow: /v1/", text)
        self.assertIn("Sitemap: https://example.test/sitemap.xml", text)
        self.assertIn("llms.txt", text)
        for crawler in AI_CRAWLERS:
            self.assertIn(f"User-agent: {crawler}", text, crawler)
            block = text.split(f"User-agent: {crawler}", 1)[1].split("\n\n", 1)[0]
            self.assertIn("Allow: /", block, crawler)

    def test_sitemap_is_valid_xml(self):
        xml = static_files.sitemap_xml("https://example.test")
        root = ElementTree.fromstring(xml)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(f"{namespace}loc")]
        self.assertTrue(locs)
        self.assertEqual(len(locs), len(set(locs)))
        for loc in locs:
            self.assertTrue(loc.startswith("https://example.test/"), loc)
        for path in ("/", "/p/", "/guides/", "/about", "/privacy", "/terms"):
            self.assertIn("https://example.test" + path, locs, path)
        for node in root.iter(f"{namespace}lastmod"):
            self.assertRegex(node.text, r"^\d{4}-\d{2}-\d{2}$")

    def test_llms_links_are_absolute(self):
        text = static_files.llms_txt()
        links = re.findall(r"\]\(([^)]+)\)", text)
        self.assertTrue(links)
        for link in links:
            self.assertTrue(link.startswith("http"), link)
        self.assertIn("## 구조화 데이터(JSON-LD)", text)
        self.assertIn("WebApplication", text)
        self.assertIn("CollectionPage", text)
        for marker in ("## 사람용", "## 기계용 (MCP · JSON-RPC 2.0)", "## 기계용 (REST JSON)",
                       "check_likely", "info_needed", "low_risk"):
            self.assertIn(marker, text, marker)


if __name__ == "__main__":
    unittest.main(verbosity=2)
