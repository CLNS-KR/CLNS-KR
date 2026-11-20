"""0.3.0 회귀 테스트 — 질문형 가이드 36종 + 일일 시계열 스냅샷·추이.

검증 항목
- `/guides/` 인덱스와 모든 `/guides/{slug}` 페이지가 200 + 질문 H1 + 한 줄 답변 +
  체크포인트 + 근거 조문(시행일·원문 URL) + `/?q=`·`/mcp` 링크로 렌더된다(JS 없음).
- `FAQPage` 구조화 데이터가 페이지의 질문·답변과 일치하고, 얇은 페이지는 `noindex` 로
  색인·사이트맵에서 빠진다.
- 카탈로그의 모든 참조(케이스 ID·근거 키·규제 태그·툴 이름)가 실제로 해석되고,
  답변 문장에 단정 표현·개인정보가 없다.
- `sitemap.xml`·`llms.txt` 가 가이드 경로와 개수를 자동 노출한다.
- `take_snapshot` 이 멱등이고, 신규/변경/삭제를 정확히 세며, `backfill_from_history` 는
  관측 스냅샷을 덮지 않는다.
- `trends` 가 최근 창·직전 창 급증 표를 내고, 이벤트가 0건이면 데이터 기준일 참고 창을
  따로 돌려준다(0건을 '급증 없음'으로 단정하지 않는다).
- `get_compliance_trends` 툴과 `GET /v1/trends` 가 같은 계약으로 응답한다.

실행: python3 tests/test_guides_trends.py   (네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html import escape
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import (  # noqa: E402
    guides, mfds_dispositions, pseo, recall_index, snapshots, static_files, usage,
)
from import_compliance.api import TOOL_INDEX, call_tool  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.standards import REGULATION_TAGS  # noqa: E402
from import_compliance.store import Store  # noqa: E402

BASE = "https://clns-kr.onrender.com"

# 개인정보·시크릿 모양(값이 아니라 모양으로 잡는다 — 테스트 파일 자체가 개인정보를 담지 않게).
PERSONAL_PATTERNS = (
    r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}",
    r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com",
    r"(?:github|gitlab)\.com/[A-Za-z0-9-]+",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
)

PHONE_SAMPLE = "010" + "-1234" + "-5678"

RECALL_CSV_HEADER = (
    "인증번호,모델명,제품명,브랜드명,사업자구분,법정제품분류,리콜종류,리콜사업자명,"
    "제조국가명,제조사명,제조사국가명,리콜방법,위해유형,안전성조사명,등록일"
)


def recall_csv(*rows: str) -> str:
    return "\n".join([RECALL_CSV_HEADER, *rows]) + "\n"


def disposition_row(seq: str, *, confirmed: str, law: str, violation: str,
                    industry: str = "식품제조가공업") -> dict:
    return {
        "DSPSDTLS_SEQ": seq,
        "INDUTY_CD_NM": industry,
        "DSPS_TYPECD_NM": "영업정지",
        "DSPS_DCSNDT": confirmed,
        "DSPS_BGNDT": confirmed,
        "DSPS_ENDDT": confirmed,
        "VILTCN": violation,
        "LAWORD_CD_NM": law,
        "DSPSCN": "영업정지 15일",
        "DSPS_INSTTCD_NM": "식품의약품안전처",
        "LAST_UPDT_DTM": "2026-11-20",
    }


def empty_catalogs() -> dict:
    return {"prohibited": {}, "restricted": {}}


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmpdir.name, "app.sqlite")
        cls.store = Store(cls.db_path)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()
        cls.tmpdir.cleanup()

    def raw(self, path, *, method="GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def get_text(self, path, **kwargs):
        status, headers, raw = self.raw(path, **kwargs)
        return status, headers, raw.decode("utf-8")


def json_ld_blocks(html: str) -> list:
    out = []
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        out.append(json.loads(match.group(1)))
    return out


class GuideCatalogTest(unittest.TestCase):
    def test_catalog_has_at_least_thirty_guides(self):
        items = guides.items()
        self.assertGreaterEqual(len(items), 30)
        slugs = [item["slug"] for item in items]
        self.assertEqual(len(slugs), len(set(slugs)))
        for item in items:
            self.assertGreaterEqual(len(item["question_ko"]), 10, item["slug"])
            self.assertGreaterEqual(len(item["answer_ko"]), 80, item["slug"])
            self.assertGreaterEqual(len(item["checkpoints_ko"]), 3, item["slug"])
            self.assertGreaterEqual(len(item["summary_ko"]), 60, item["slug"])

    def test_catalog_references_resolve(self):
        for item in guides.items():
            with self.subTest(slug=item["slug"]):
                self.assertIn(item["tool"], TOOL_INDEX)
                for tag in item["tags"]:
                    self.assertIn(tag, REGULATION_TAGS)
                basis = guides.legal_basis(item)
                self.assertTrue(basis, "근거 조문이 비어 있습니다")
                for row in basis:
                    self.assertTrue(row.get("law"))
                    self.assertTrue(row.get("article"))
                    self.assertRegex(str(row.get("effective_date") or ""), r"^\d{4}-\d{2}-\d{2}$")
                    self.assertTrue(str(row.get("quote") or "").strip())

    def test_answers_avoid_conclusive_phrasing_and_personal_data(self):
        patterns = [re.compile(pattern) for pattern in PERSONAL_PATTERNS]
        for item in guides.items():
            texts = [item["answer_ko"], item["summary_ko"], *item["checkpoints_ko"],
                     *(item.get("key_points_ko") or [])]
            for text in texts:
                with self.subTest(slug=item["slug"]):
                    self.assertEqual(find_conclusive_phrasing(text), [], text[:60])
                    for pattern in patterns:
                        self.assertIsNone(pattern.search(text), pattern.pattern)

    def test_every_tag_has_authority_and_tool(self):
        for item in guides.items():
            for tag in item["tags"]:
                with self.subTest(slug=item["slug"], tag=tag):
                    self.assertNotEqual(guides.authority_for(tag), "소관 기관 확인")
                    self.assertIn(guides.tool_for_tag(tag), TOOL_INDEX)

    def test_related_guides_exist(self):
        slugs = set(guides.slugs())
        for item in guides.items():
            for slug in item.get("related_guides") or []:
                self.assertIn(slug, slugs, item["slug"])
            for slug in item.get("related_items") or []:
                self.assertIsNotNone(pseo.get_item(slug), item["slug"])


class GuidePageTest(ServerCase):
    def test_every_guide_renders_for_crawlers(self):
        for item in guides.items():
            with self.subTest(slug=item["slug"]):
                status, headers, html = self.get_text(f"/guides/{item['slug']}")
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["Content-Type"])
                # 질문에 따옴표가 들어가면 H1 은 HTML 이스케이프된 형태로 렌더된다.
                self.assertIn(f"<h1>{escape(item['question_ko'])}</h1>", html)
                self.assertIn("한 줄 답변", html)
                self.assertIn("대표 체크포인트", html)
                self.assertIn("근거 법령", html)
                self.assertIn("시행", html)
                self.assertIn("면책", html)
                self.assertIn(f'<link rel="canonical" href="{BASE}/guides/{item["slug"]}">', html)
                # 웹 체크·MCP 연결 링크가 모든 페이지에 있다.
                self.assertIn("/?q=", html)
                self.assertIn('href="/mcp"', html)
                self.assertIn("python -m import_compliance.mcp_stdio", html)
                # JS 없이 읽힌다(외부 CDN·트래커·script src 없음).
                self.assertIn("<script", html)
                self.assertNotIn("<script src=", html)
                for token in ("cdn.", "jsdelivr", "unpkg", "googletagmanager"):
                    self.assertNotIn(token, html.lower())

    def test_faq_json_ld_matches_question_and_answer(self):
        item = guides.get_item("duty-free-150-200")
        _, _, html = self.get_text("/guides/duty-free-150-200")
        blocks = json_ld_blocks(html)
        self.assertTrue(blocks)
        graph = blocks[0]["@graph"]
        faq = next(node for node in graph if node["@type"] == "FAQPage")
        entity = faq["mainEntity"][0]
        self.assertEqual(entity["name"], item["question_ko"])
        self.assertEqual(entity["acceptedAnswer"]["text"], item["answer_ko"])
        types = {node["@type"] for node in graph}
        self.assertIn("WebPage", types)
        self.assertIn("BreadcrumbList", types)

    def test_unknown_guide_is_404(self):
        for path in ("/guides/no-such-guide", "/guides/....", "/guides/" + "a" * 80):
            with self.subTest(path=path):
                status, _, _ = self.raw(path)
                self.assertEqual(status, 404)

    def test_index_lists_every_guide_and_links_sections(self):
        status, _, html = self.get_text("/guides/")
        self.assertEqual(status, 200)
        self.assertIn("수입 규제 질문 가이드", html)
        self.assertIn('href="/p/"', html)
        for item in guides.items():
            self.assertIn(f'/guides/{item["slug"]}"', html)

    def test_thin_guide_is_noindex_and_kept_out_of_sitemap(self):
        thin = {
            "slug": "thin-guide", "question_ko": "짧은 질문인가요?", "title_ko": "얇은 가이드",
            "category": "기타", "summary_ko": "짧은 요약입니다. 그래도 최소 길이는 넘겨야 합니다. " * 2,
            "answer_ko": "짧음", "checkpoints_ko": ["하나", "둘", "셋"], "tags": ["KOREAN_LABELING"],
            "tool": "assess_import_case", "cases": ["TRAP-10"], "basis_keys": [],
            "keywords": [], "related_guides": [], "related_items": [],
        }
        self.assertFalse(guides.is_indexable(thin))
        for item in guides.items():
            self.assertTrue(guides.is_indexable(item), item["slug"])

        original = guides.item_index
        guides.item_index = lambda: {**original(), thin["slug"]: thin}
        try:
            paths = guides.indexable_paths()
            self.assertIn("/guides/", paths)
            self.assertNotIn("/guides/thin-guide", paths)
            html = guides.render_guide("thin-guide")
            self.assertIsNotNone(html)
            self.assertIn('content="noindex,follow"', html)
        finally:
            guides.item_index = original

    def test_service_meta_exposes_guides_and_trends(self):
        status, _, html = self.get_text("/guides/")
        self.assertEqual(status, 200)
        self.assertIn(f"가이드 v{guides.catalog_meta()['version']}", html)

    def test_product_pages_link_to_related_guides(self):
        status, _, html = self.get_text("/p/omega3")
        self.assertEqual(status, 200)
        self.assertIn("이 품목과 함께 보는 질문", html)
        self.assertIn('/guides/supplement-6-bottle"', html)
        self.assertIn('href="/guides/"', html)

    def test_home_page_links_to_guides(self):
        status, _, html = self.get_text("/")
        self.assertEqual(status, 200)
        self.assertIn('href="/guides/"', html)

    def test_head_requests_supported(self):
        for path in ("/guides/", "/guides/supplement-6-bottle", "/v1/trends"):
            with self.subTest(path=path):
                status, _, raw = self.raw(path, method="HEAD")
                self.assertEqual(status, 200)
                self.assertEqual(raw, b"")


class ServiceMetaTest(unittest.TestCase):
    def test_meta_lists_guides_and_trends(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        payload = call_tool("get_service_meta", {}, store)["result"]
        self.assertEqual(payload["guides"]["count"], len(guides.items()))
        self.assertEqual(payload["guides"]["page_pattern"], "/guides/{slug}")
        self.assertIn("FAQPage", payload["guides"]["structured_data"])
        self.assertEqual(payload["trends"]["tool"], "get_compliance_trends")
        self.assertIn("recall", payload["trends"]["snapshot_sources"])
        self.assertEqual(payload["trends"]["snapshot_available_days"], 0)


class GuidesDiscoveryTest(unittest.TestCase):
    def test_sitemap_lists_guides_after_product_pages(self):
        root = ET.fromstring(static_files.sitemap_xml())
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(ns + "loc")]
        self.assertEqual(locs[0], f"{BASE}/")
        self.assertEqual(locs[1], f"{BASE}/p/")
        self.assertIn(f"{BASE}/guides/", locs)
        for slug in guides.slugs():
            self.assertIn(f"{BASE}/guides/{slug}", locs)
        self.assertEqual(len(locs), len(set(locs)))
        self.assertGreaterEqual(len(locs), 65)
        self.assertGreater(locs.index(f"{BASE}/guides/"), locs.index(f"{BASE}/p/"))

    def test_sitemap_priority_for_guides(self):
        xml = static_files.sitemap_xml("https://example.test")
        self.assertIn("<loc>https://example.test/guides/</loc>", xml)
        self.assertIn("<priority>0.8</priority>", xml)

    def test_llms_txt_lists_guides_trends_and_counts(self):
        text = static_files.llms_txt()
        self.assertIn(f"{BASE}/guides/", text)
        self.assertIn(f"{BASE}/guides/<slug>", text)
        self.assertIn(f"{len(guides.items())}", text)
        self.assertIn(f"{BASE}/v1/trends", text)
        self.assertIn("get_compliance_trends", text)
        # 기존 계약(품목 페이지·MCP)은 그대로 유지된다.
        self.assertIn(f"{BASE}/p/", text)
        self.assertIn(f"{len(pseo.items())}", text)
        self.assertIn("/mcp", text)


class SnapshotTest(unittest.TestCase):
    def make_store(self) -> Store:
        store = Store(":memory:")
        self.addCleanup(store.close)
        return store

    def seed_day1(self, store: Store) -> None:
        recall_index.load_items(store, recall_csv(
            "C1,M-OLD,완구 자동차,토이브랜드,제조업,완구>기타완구>기타,리콜명령,토이브랜드,중국,토이제조,중국,회수,유해물질,어린이완구,2026-11-09",
            "C2,M-FAN,미니 선풍기,팬브랜드,제조업,전기용품>선풍기,리콜명령,팬브랜드,중국,팬제조,중국,회수,감전,선풍기,2026-11-10",
        ))
        store.save_dispositions([mfds_dispositions.normalize_item(
            disposition_row("D1", confirmed="20261109", law="식품위생법 제36조(시설기준)",
                            violation="시설기준 미비 (연락처 " + PHONE_SAMPLE + ")"), "manufacturing")])

    def test_take_snapshot_counts_and_first_observation(self):
        store = self.make_store()
        self.seed_day1(store)
        result = snapshots.take_snapshot(store, "2026-11-10",
                                         cosmetic_catalog={"prohibited": {"성분A": {
                                             "label": "성분A", "category": "배합금지",
                                             "event_date": "", "payload": {},
                                             "fingerprint": "fp-1"}}, "restricted": {}},
                                         drug_catalog={"substance:성분B": {
                                             "label": "성분B", "category": "마약", "event_date": "",
                                             "payload": {}, "fingerprint": "fp-2"}})
        self.assertEqual(result["counts"]["recall"], 2)
        self.assertEqual(result["counts"]["disposition"], 1)
        self.assertEqual(result["counts"]["cosmetic_prohibited"], 1)
        self.assertEqual(result["counts"]["drug_schedule"], 1)
        self.assertTrue(result["first_observation"])
        self.assertIsNone(result["previous_day"])
        self.assertEqual(result["diff"]["new"], 5)

    def test_take_snapshot_is_idempotent(self):
        store = self.make_store()
        self.seed_day1(store)
        kwargs = {"cosmetic_catalog": empty_catalogs(), "drug_catalog": {}}
        first = snapshots.take_snapshot(store, "2026-11-10", **kwargs)
        second = snapshots.take_snapshot(store, "2026-11-10", **kwargs)
        self.assertEqual(first["counts"], second["counts"])
        self.assertEqual(len(snapshots.days(store)), 1)
        rows = store.conn.execute(
            "SELECT COUNT(*) AS n FROM compliance_snapshots WHERE day = ?",
            ("2026-11-10",)).fetchone()
        self.assertEqual(int(rows["n"]), sum(first["counts"].values()))

    def test_diff_detects_new_changed_and_removed(self):
        store = self.make_store()
        self.seed_day1(store)
        kwargs = {"cosmetic_catalog": empty_catalogs(), "drug_catalog": {}}
        snapshots.take_snapshot(store, "2026-11-10", **kwargs)

        # 다음 날: 신규 C3, 기존 C2 위해유형 변경, C1 삭제.
        recall_index.load_items(store, recall_csv(
            "C2,M-FAN,미니 선풍기,팬브랜드,제조업,전기용품>선풍기,리콜명령,팬브랜드,중국,팬제조,중국,회수,화재및화상,선풍기,2026-11-10",
            "C3,M-LAMP,LED 무드등,램프브랜드,제조업,조명기기>일반조명기구,리콜명령,램프브랜드,중국,램프제조,중국,회수,감전,무드등,2026-11-11",
        ))
        result = snapshots.take_snapshot(store, "2026-11-11", **kwargs)
        self.assertEqual(result["previous_day"], "2026-11-10")
        self.assertEqual(result["counts"]["recall"], 2)
        self.assertEqual(result["diff"]["new"], 1)
        self.assertEqual(result["diff"]["changed"], 1)
        self.assertEqual(result["diff"]["removed"], 1)
        self.assertEqual(result["diff"]["new_by_source"], {"recall": 1})
        changed_labels = {row["label"] for row in result["diff"]["changed_samples"]}
        self.assertEqual(changed_labels, {"미니 선풍기"})

        diff = snapshots.daily_diff(store, "2026-11-11")
        self.assertEqual((diff["new"], diff["changed"], diff["removed"]), (1, 1, 1))
        self.assertEqual(diff["previous_day"], "2026-11-10")
        self.assertEqual(diff["removed_samples"][0]["label"], "완구 자동차")

    def test_disposition_pii_is_not_kept_in_snapshots(self):
        store = self.make_store()
        self.seed_day1(store)
        result = snapshots.take_snapshot(store, "2026-11-10",
                                         cosmetic_catalog=empty_catalogs(), drug_catalog={})
        self.assertEqual(result["counts"]["disposition"], 1)
        rows = store.conn.execute("SELECT * FROM compliance_snapshots").fetchall()
        dump = json.dumps([dict(row) for row in rows], ensure_ascii=False)
        self.assertNotIn(PHONE_SAMPLE, dump)
        self.assertIn("[연락처]", dump)  # 마스킹된 형태로만 남는다

    def test_export_writes_daily_json(self):
        store = self.make_store()
        self.seed_day1(store)
        with tempfile.TemporaryDirectory() as tmp:
            result = snapshots.take_snapshot(store, "2026-11-10", export_dir=tmp,
                                             cosmetic_catalog=empty_catalogs(),
                                             drug_catalog={})
            path = result["export_path"]
            self.assertTrue(path.endswith("2026-11-10.json"))
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["schema"], snapshots.SNAPSHOT_SCHEMA)
            self.assertEqual(payload["day"], "2026-11-10")
            self.assertIn("counts", payload)
            self.assertNotIn("items", payload)  # 기본은 요약만

    def test_backfill_reconstructs_history_and_skips_observed_days(self):
        store = self.make_store()
        self.seed_day1(store)
        observed = snapshots.take_snapshot(store, "2026-11-10",
                                           cosmetic_catalog=empty_catalogs(), drug_catalog={})
        self.assertEqual(observed["counts"]["recall"], 2)
        result = snapshots.backfill_from_history(store, 3, end_day="2026-11-10")
        self.assertEqual(result["days"], 2)  # 11-08, 11-09 (11-10 은 관측분 유지)
        self.assertEqual(result["skipped_observed_days"], ["2026-11-10"])
        day8 = snapshots.items_for(store, "2026-11-08")
        day9 = snapshots.items_for(store, "2026-11-09")
        self.assertEqual(sum(1 for key in day8 if key.startswith("recall:")), 0)
        self.assertEqual(sum(1 for key in day9 if key.startswith("recall:")), 1)
        run = store.conn.execute(
            "SELECT origin FROM snapshot_runs WHERE day = ?", ("2026-11-09",)).fetchone()
        self.assertEqual(run["origin"], snapshots.ORIGIN_BACKFILLED)

    def test_trends_windows_and_spikes(self):
        store = self.make_store()
        self.seed_day1(store)
        kwargs = {"cosmetic_catalog": empty_catalogs(), "drug_catalog": {}}
        for day in ("2026-11-09", "2026-11-10"):
            snapshots.take_snapshot(store, day, **kwargs)
        payload = snapshots.trends(store, days=7, today="2026-11-10")
        window = payload["current_window"]
        self.assertEqual(payload["window_days"], 7)
        self.assertEqual(window["start"], "2026-11-04")
        self.assertEqual(window["end"], "2026-11-10")
        self.assertEqual(window["recall_total"], 2)
        self.assertEqual(window["disposition_total"], 1)
        top = window["by_category"][0]
        self.assertIn(top["key"], {"완구", "전기용품"})
        self.assertGreaterEqual(top["count"], 1)
        self.assertEqual(window["by_law"][0]["key"], "식품위생법 제36조")
        self.assertEqual(len(payload["series"]), 2)
        self.assertEqual(payload["last_observed_diff"]["day"], "2026-11-10")
        self.assertIn("note_ko", payload["coverage"])

    def test_trends_reference_window_when_no_recent_events(self):
        store = self.make_store()
        self.seed_day1(store)
        snapshots.take_snapshot(store, "2026-11-10", cosmetic_catalog=empty_catalogs(),
                                drug_catalog={})
        payload = snapshots.trends(store, days=3, today="2026-11-20")
        self.assertEqual(payload["current_window"]["recall_total"], 0)
        self.assertIsNotNone(payload["reference"])
        self.assertEqual(payload["reference"]["as_of"], "2026-11-10")
        self.assertEqual(payload["reference"]["recall_total"], 2)

    def test_trends_without_data_reports_no_snapshot(self):
        store = self.make_store()
        payload = snapshots.trends(store, days=7, today="2026-11-20")
        self.assertEqual(payload["series"], [])
        self.assertIsNone(payload["reference"])
        self.assertEqual(payload["coverage"]["snapshot_available_days"], 0)


class TrendsToolTest(unittest.TestCase):
    def make_store(self) -> Store:
        store = Store(":memory:")
        self.addCleanup(store.close)
        return store

    def test_tool_returns_envelope_and_status(self):
        store = self.make_store()
        out = call_tool("get_compliance_trends", {"days": 7}, store)
        self.assertTrue(out["ok"])
        payload = out["result"]
        self.assertEqual(payload["trends"]["schema"], snapshots.TRENDS_SCHEMA)
        self.assertIn("assessment_status", payload)
        self.assertIn(payload["assessment_status"], ("UNKNOWN", "REVIEW_REQUIRED"))
        self.assertEqual(payload["missing_information"], ["snapshot"])
        self.assertIn("disclaimer", payload)
        self.assertIn("data_provenance", payload)
        joined = " ".join(payload["answer"]["guidance"])
        self.assertEqual(find_conclusive_phrasing(joined), [], joined)

    def test_tool_clamps_days_and_validates_source(self):
        store = self.make_store()
        self.assertEqual(
            call_tool("get_compliance_trends", {"days": 999}, store)["result"]["trends"]["window_days"],
            snapshots.MAX_TREND_DAYS)
        bad = call_tool("get_compliance_trends", {"source": "naver"}, store)
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error"], "invalid_argument")
        bad_days = call_tool("get_compliance_trends", {"days": "많이"}, store)
        self.assertFalse(bad_days["ok"])

    def test_tool_reports_diff_after_two_snapshots(self):
        store = self.make_store()
        recall_index.load_items(store, recall_csv(
            "C1,M1,완구 자동차,브랜드,제조업,완구>기타완구,리콜명령,브랜드,중국,제조사,중국,회수,유해물질,완구,2026-11-09",
        ))
        snapshots.take_snapshot(store, "2026-11-19", cosmetic_catalog=empty_catalogs(),
                                drug_catalog={})
        snapshots.take_snapshot(store, "2026-11-20", cosmetic_catalog=empty_catalogs(),
                                drug_catalog={})
        out = call_tool("get_compliance_trends", {"days": 7}, store)
        payload = out["result"]
        self.assertEqual(payload["trends"]["last_observed_diff"]["new"], 0)
        self.assertIn("전일 대비", payload["answer"]["guidance"][1])
        self.assertEqual(payload["missing_information"], [])


class TrendsEndpointTest(ServerCase):
    def test_v1_trends_returns_contract(self):
        status, headers, raw = self.raw("/v1/trends?days=7")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        data = json.loads(raw.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["tool"], "get_compliance_trends")
        self.assertEqual(data["result"]["trends"]["window_days"], 7)
        self.assertIn("coverage", data["result"]["trends"])

    def test_v1_trends_clamps_and_defaults(self):
        data = json.loads(self.raw("/v1/trends?days=999")[2].decode("utf-8"))
        self.assertEqual(data["result"]["trends"]["window_days"], snapshots.MAX_TREND_DAYS)
        data = json.loads(self.raw("/v1/trends?days=abc")[2].decode("utf-8"))
        self.assertEqual(data["result"]["trends"]["window_days"], snapshots.DEFAULT_TREND_DAYS)

    def test_usage_counts_guides_and_trends_paths(self):
        self.assertEqual(usage.path_key("/guides/supplement-6-bottle"),
                         "/guides/supplement-6-bottle")
        self.assertEqual(usage.path_key("/guides/unknown-slug"), "/404")
        self.assertEqual(usage.path_key("/v1/trends?days=7"), "/v1/trends")
        self.get_text("/guides/duty-free-150-200")
        self.get_text("/v1/trends")
        rows = self.store.usage_rows("0000-00-00", "9999-99-99")
        keys = {(row["kind"], row["key"]) for row in rows}
        self.assertIn(("path", "/guides/duty-free-150-200"), keys)
        self.assertIn(("path", "/v1/trends"), keys)


class SnapshotCliTest(unittest.TestCase):
    def test_cli_take_and_trends(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "cli.sqlite")
            env = dict(os.environ)
            env["PYTHONPATH"] = SRC
            proc = subprocess.run(
                [sys.executable, "-m", "import_compliance.snapshots",
                 "--db", db_path, "--take", "--day", "2026-11-20", "--trends", "7"],
                capture_output=True, text=True, cwd=SRC, env=env, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(snapshots.SNAPSHOT_SCHEMA, proc.stdout)
            self.assertIn(snapshots.TRENDS_SCHEMA, proc.stdout)
            self.assertTrue(os.path.exists(db_path))


class AnonymousSourceTest(unittest.TestCase):
    def test_new_files_have_no_personal_data_or_secrets(self):
        patterns = [re.compile(pattern) for pattern in PERSONAL_PATTERNS]
        targets = [
            os.path.join("src", "import_compliance", "guides.py"),
            os.path.join("src", "import_compliance", "snapshots.py"),
            os.path.join("src", "import_compliance", "api.py"),
            os.path.join("src", "import_compliance", "static_files.py"),
            os.path.join("src", "guides_items.json"),
            os.path.join("src", "tests", "test_guides_trends.py"),
        ]
        for relative in targets:
            with open(os.path.join(ROOT, relative), encoding="utf-8") as handle:
                text = handle.read()
            for pattern in patterns:
                with self.subTest(file=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
