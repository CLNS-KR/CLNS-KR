"""성장 1단계 회귀 테스트 — pSEO 35개 페이지·동적 sitemap·익명 카운터·stdio MCP·MIT 라이선스·CI.

검증 항목
- `/p/` 인덱스와 35개 `/p/{slug}` 페이지가 200 + H1 + 면책 + 근거 + `/?q=` 링크로 렌더된다(JS 없음).
- 존재하지 않는 slug 는 404, 얆은 데이터는 `noindex`(색인·사이트맵에서 제외).
- `sitemap.xml` 이 `/` + `/p/` + 전체 품목 URL 을 절대 주소로 동적 반환하고, `llms.txt` 가 pSEO·stats 경로를 안내한다.
- `GET /v1/stats` 가 IP·User-Agent·쿠키 없이 일별 경로/툴/판정/0건/오류만 집계한다(원문 미저장 검증 포함).
- `python -m import_compliance.mcp_stdio` 가 줄 단위 JSON-RPC 로 initialize/tools/list/tools/call 을 처리한다.
- `LICENSE`(MIT · CLNS-KR), `.github/workflows/test.yml`, README·버전 갱신, 개인정보·시크릿 미포함.

실행: python3 tests/test_pseo_stats.py   (네트워크 불필요)
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
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import pseo, static_files, usage  # noqa: E402
from import_compliance.api import TOOL_INDEX  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402

BASE = "https://clns-kr.onrender.com"

# 개인정보 패턴(값이 아니라 모양으로 잗는다 — 테스트 파일 자체가 개인정보를 담지 않게).
PERSONAL_PATTERNS = (
    r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}",                     # 휴대전화 번호
    r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com",   # 개인 메일
    r"(?:github|gitlab)\.com/[A-Za-z0-9-]+",                      # 개인 코드 호스팅 계정
)


def anonymous_violations():
    return [re.compile(pattern, re.MULTILINE) for pattern in PERSONAL_PATTERNS]


# 개인정보·시크릿이 새어 나가면 안 되는 자리표시자(테스트용 가짜 값)
SENTINEL_UA = "SentinelAgent/9.9 (+test)"
SENTINEL_IP = "203.0.113.77"
SENTINEL_COOKIE = "sid=sentinel-cookie-value"
SENTINEL_REF = "https://sentinel.example/referrer"
SENTINEL_CLIENT = "sentinel-client-0001"


class ServerCase(unittest.TestCase):
    """실제 소켓 HTTP 계약 하네스(파일 DB — 원문 미저장 검증을 위해)."""

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

    def raw(self, path, *, method="GET", body=None, headers=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body,
            headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def get_text(self, path, **kwargs):
        status, headers, raw = self.raw(path, **kwargs)
        return status, headers, raw.decode("utf-8")


class PseoPageTest(ServerCase):
    def test_catalog_has_at_least_thirty_items(self):
        items = pseo.items()
        self.assertGreaterEqual(len(items), 30)
        self.assertLessEqual(len(items), 40)
        slugs = [item["slug"] for item in items]
        self.assertEqual(len(slugs), len(set(slugs)))
        for item in items:
            self.assertRegex(item["hs_code"], r"^\d{10}$")
            self.assertTrue(item["requirements_ko"])
            self.assertTrue(item["summary_ko"])

    def test_every_item_page_renders_for_crawlers(self):
        for item in pseo.items():
            with self.subTest(slug=item["slug"]):
                status, headers, html = self.get_text(f"/p/{item['slug']}")
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["Content-Type"])
                self.assertIn("<h1>", html)
                self.assertIn(item["name_ko"], html)
                # 본문이 서버에서 렌더된다(크롤러가 JS 없이 읽는다).
                self.assertIn("<script", html)  # JSON-LD 만 있고 실행 코드는 없다
                self.assertNotIn("<script src=", html)
                self.assertIn("관세청", html)
                self.assertIn("면책", html)
                # 법적 근거 + 면책 + 실시간 조회 링크
                self.assertIn("법적 근거", html)
                self.assertIn(f"/?q={item['name_ko']}", html)
                self.assertIn(f'<link rel="canonical" href="{BASE}/p/{item["slug"]}">', html)
                self.assertIn("본 서비스는 관세사법상", html)
                # 외부 CDN·트래커 없음
                for token in ("cdn.", "jsdelivr", "unpkg", "googletagmanager"):
                    self.assertNotIn(token, html.lower())

    def test_item_page_shows_requirement_rows_and_zero_note(self):
        status, _, html = self.get_text("/p/usb-mini-fan")
        self.assertEqual(status, 200)
        self.assertIn("8414519000", html)
        self.assertIn("전기용품 및 생활용품 요건확인서", html)
        self.assertIn("전파법", html)
        # 요건 0건 품목은 '0건은 요건 없음이 아니다' 문구를 반드시 보여준다.
        status, _, zero_html = self.get_text("/p/childrens-toy")
        self.assertEqual(status, 200)
        self.assertIn("0건은", zero_html)
        self.assertIn("조회되지 않음", zero_html)

    def test_unknown_slug_is_404(self):
        for path in ("/p/no-such-item", "/p/....", "/p/" + "a" * 80):
            with self.subTest(path=path):
                status, _, _ = self.raw(path)
                self.assertEqual(status, 404)

    def test_index_page_links_every_item(self):
        status, _, html = self.get_text("/p/")
        self.assertEqual(status, 200)
        self.assertIn("품목별 수입 요건", html)
        for item in pseo.items():
            self.assertIn(f'/p/{item["slug"]}"', html)

    def test_home_page_links_to_pseo_index(self):
        status, _, html = self.get_text("/")
        self.assertEqual(status, 200)
        self.assertIn('href="/p/"', html)

    def test_head_requests_supported(self):
        for path in ("/p/", "/p/usb-mini-fan", "/v1/stats"):
            with self.subTest(path=path):
                status, headers, raw = self.raw(path, method="HEAD")
                self.assertEqual(status, 200)
                self.assertEqual(raw, b"")

    def test_thin_page_is_noindex_and_kept_out_of_sitemap(self):
        thin = {
            "slug": "thin-sample", "name_ko": "얇은 예시", "hs_code": "0000000000",
            "hs_name_ko": "", "category": "기타", "summary_ko": "짧음",
            "key_points_ko": [], "requirements_ko": [], "certifications_ko": [],
            "traps": [], "hs_requirements": [], "hs_checked_at": "",
        }
        self.assertFalse(pseo.is_indexable(thin))
        for item in pseo.items():
            self.assertTrue(pseo.is_indexable(item), item["slug"])

        original = pseo.item_index
        pseo.item_index = lambda: {**original(), thin["slug"]: thin}
        try:
            paths = pseo.indexable_paths()
            self.assertIn("/p/", paths)
            self.assertNotIn("/p/thin-sample", paths)
            html = pseo.render_item("thin-sample")
            self.assertIsNotNone(html)
            self.assertIn('content="noindex,follow"', html)
            self.assertIn("0건은", html)
        finally:
            pseo.item_index = original


class SitemapAndLlmsTest(unittest.TestCase):
    def test_sitemap_lists_every_indexable_page(self):
        root = ET.fromstring(static_files.sitemap_xml())
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(ns + "loc")]
        self.assertEqual(locs[0], f"{BASE}/")
        self.assertEqual(locs[1], f"{BASE}/p/")
        for slug in pseo.slugs():
            self.assertIn(f"{BASE}/p/{slug}", locs)
        self.assertEqual(len(locs), len(set(locs)))
        self.assertGreaterEqual(len(locs), 31)

    def test_sitemap_uses_public_base_url(self):
        xml = static_files.sitemap_xml("https://example.test/")
        self.assertIn("<loc>https://example.test/p/</loc>", xml)
        self.assertNotIn("clns-kr.onrender.com", xml)

    def test_llms_txt_points_at_pseo_and_stats(self):
        text = static_files.llms_txt()
        self.assertIn(f"{BASE}/p/", text)
        self.assertIn(f"{BASE}/p/<slug>", text)
        self.assertIn(f"{BASE}/v1/stats", text)
        self.assertIn("35", text)
        # 기존 계약 유지
        self.assertTrue(text.startswith("# CLNS"))
        self.assertIn("/mcp", text)


class StatsTest(ServerCase):
    def test_stats_shape_and_privacy_flags(self):
        status, headers, payload = self.get_text("/v1/stats")
        self.assertEqual(status, 200)
        data = json.loads(payload)
        self.assertTrue(data["ok"])
        self.assertEqual(data["timezone"], "Asia/Seoul")
        self.assertEqual(data["window_days"], usage.DEFAULT_DAYS)
        self.assertEqual(data["privacy"]["stores_ip"], False)
        self.assertEqual(data["privacy"]["stores_user_agent"], False)
        self.assertEqual(data["privacy"]["stores_cookies"], False)
        self.assertEqual(data["privacy"]["stores_identifiers"], False)
        self.assertEqual(len(data["days"]), usage.DEFAULT_DAYS)
        self.assertRegex(data["days"][-1]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("paths", data["totals"])
        self.assertIn("tools", data["totals"])
        for forbidden in ("ip", "user_agent", "ua", "cookie", "client_id", "query"):
            self.assertNotIn(forbidden, data["days"][-1])
            self.assertNotIn(forbidden, data["totals"])

    def test_window_is_clamped(self):
        data = json.loads(self.get_text("/v1/stats?days=999")[2])
        self.assertEqual(data["window_days"], usage.MAX_DAYS)
        data = json.loads(self.get_text("/v1/stats?days=abc")[2])
        self.assertEqual(data["window_days"], usage.DEFAULT_DAYS)

    def test_requests_tools_and_verdicts_are_counted(self):
        self.get_text("/p/usb-mini-fan")
        self.get_text("/no-such-path-" + "z" * 10)
        body = json.dumps({"product_name": "오메가3", "kind": "health_functional"}).encode()
        self.raw("/v1/tools/check_food_cosmetics", method="POST", body=body,
                 headers={"Content-Type": "application/json"})
        self.raw("/mcp", method="POST",
                 body=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "get_service_meta",
                                             "arguments": {}}}).encode(),
                 headers={"Content-Type": "application/json"})
        data = json.loads(self.get_text("/v1/stats")[2])
        today = data["days"][-1]
        self.assertGreaterEqual(today["paths"].get("/p/usb-mini-fan", 0), 1)
        self.assertGreaterEqual(today["paths"].get("/404", 0), 1)
        self.assertGreaterEqual(today["tools"].get("check_food_cosmetics", 0), 1)
        self.assertGreaterEqual(today["tools"].get("get_service_meta", 0), 1)
        self.assertTrue(set(today["verdicts"]) <= set(usage.VERDICT_CODES))

    def test_raw_identifiers_are_never_persisted(self):
        headers = {
            "User-Agent": SENTINEL_UA,
            "X-Forwarded-For": SENTINEL_IP,
            "X-Real-IP": SENTINEL_IP,
            "Cookie": SENTINEL_COOKIE,
            "Referer": SENTINEL_REF,
            "X-Client-Id": SENTINEL_CLIENT,
        }
        self.raw("/", headers=headers)
        self.raw("/p/omega3", headers=headers)
        self.raw("/v1/tools/lookup_recall",
                 method="POST", body=json.dumps({"brand": "센티넬브랜드"}).encode(),
                 headers={**headers, "Content-Type": "application/json"})
        self.raw("/mcp", method="POST",
                 body=json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                  "params": {"name": "lookup_recall",
                                             "arguments": {"brand": "센티넬브랜드"}}}).encode(),
                 headers={**headers, "Content-Type": "application/json"})

        # 1) 카운터 테이블의 집계 행 자체에 원문이 없어야 한다(클라이언트ID 포함).
        rows = self.store.usage_rows("0000-00-00", "9999-99-99")
        self.assertTrue(rows)
        joined = json.dumps(rows, ensure_ascii=False)
        for sentinel in (SENTINEL_UA, SENTINEL_IP, SENTINEL_COOKIE, SENTINEL_REF,
                         SENTINEL_CLIENT, "센티넬브랜드"):
            self.assertNotIn(sentinel, joined)

        # 2) DB 파일 바이트에도 IP·UA·쿠키·Referer 원문이 없어야 한다.
        #    (X-Client-Id 는 기존 무료 쿼터 기능이 브라우저별 카운트에 쓰는 가명 값으로,
        #     카운터와 무관한 테이블에만 남는다 — 아래 3)에서 카운터에는 없음을 확인한다.)
        self.store.conn.execute("PRAGMA wal_checkpoint(FULL)")
        blobs = b""
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                with open(path, "rb") as handle:
                    blobs += handle.read()
        self.assertTrue(blobs)
        for sentinel in (SENTINEL_UA, SENTINEL_IP, SENTINEL_COOKIE, SENTINEL_REF):
            self.assertNotIn(sentinel.encode(), blobs)

        # 3) 통계 응답에도 헤더 유래 값이 없고, 모르는 경로는 `/404` 한 칸으로 뭉갠다.
        data = json.loads(self.get_text("/v1/stats")[2])
        stats_text = json.dumps(data, ensure_ascii=False)
        for sentinel in (SENTINEL_UA, SENTINEL_IP, SENTINEL_COOKIE, SENTINEL_REF,
                         SENTINEL_CLIENT):
            self.assertNotIn(sentinel, stats_text)
        for key in data["totals"]["paths"]:
            self.assertNotIn("sentinel", key.lower())

    def test_catalog_paths_are_counted_one_bucket_per_page(self):
        self.assertEqual(usage.path_key("/p/omega3"), "/p/omega3")
        self.assertEqual(usage.path_key("/p/omega3?x=1"), "/p/omega3")
        self.assertEqual(usage.path_key("/p/omega3/"), "/p/omega3")
        self.assertEqual(usage.path_key("/p/unknown-slug"), "/404")
        self.assertEqual(usage.path_key("/v1/tools/assess_import_case"), "/v1/tools")
        self.assertEqual(usage.path_key("/"), "/")
        self.assertEqual(usage.path_key("/p/"), "/p/")


class ZeroAndErrorFlagTest(unittest.TestCase):
    def test_zero_result_flags_are_recorded(self):
        store = Store(":memory:")
        try:
            result = {"ok": True, "result": {
                "lookup": {"hs_code": "8507609000"},
                "hs_requirements_live": {"state": "live", "requirement_count": 0}}}
            usage.record_tool(store, "lookup_hs_requirements", result, day="2026-11-18")
            recall = {"ok": True, "result": {"recall": {"match_count": 0}}}
            usage.record_tool(store, "lookup_recall", recall, day="2026-11-18")
            error = {"ok": False, "error": "invalid_argument"}
            usage.record_tool(store, "assess_import_case", error, day="2026-11-18")
            payload = usage.stats_payload(store, days=1, today="2026-11-18")
            day = payload["days"][0]
            self.assertEqual(day["tools"].get("lookup_hs_requirements"), 1)
            self.assertEqual(day["flags"].get(usage.FLAG_ZERO), 2)
            self.assertEqual(day["flags"].get(usage.FLAG_ERROR), 1)
        finally:
            store.close()

    def test_quota_error_is_flagged(self):
        store = Store(":memory:")
        try:
            usage.record_tool(store, "assess_import_case",
                              {"ok": False, "error": "quota_exceeded"}, day="2026-11-18")
            payload = usage.stats_payload(store, days=1, today="2026-11-18")
            self.assertEqual(payload["days"][0]["flags"].get(usage.FLAG_QUOTA), 1)
        finally:
            store.close()


class StdioMcpTest(unittest.TestCase):
    def run_stdio(self, lines, env_extra=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC
        env.pop("IMPORT_COMPLIANCE_LIVE", None)
        env.pop("IMPORT_COMPLIANCE_DB", None)
        env.update(env_extra or {})
        proc = subprocess.run(
            [sys.executable, "-m", "import_compliance.mcp_stdio"],
            input="\n".join(lines) + "\n", capture_output=True, text=True,
            cwd=SRC, env=env, timeout=60)
        out_lines = [line for line in proc.stdout.splitlines() if line.strip()]
        replies = [json.loads(line) for line in out_lines]
        return proc, replies

    def test_initialize_list_and_call_over_pipe(self):
        proc, replies = self.run_stdio([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18",
                                   "clientInfo": {"name": "test"}}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "get_service_meta", "arguments": {}}}),
            json.dumps({"jsonrpc": "2.0", "id": 4, "method": "nope"}),
            "{not json",
        ])
        self.assertEqual(proc.returncode, 0)
        # stdout 에는 JSON-RPC 응답만 있어야 한다(로그는 stderr).
        self.assertEqual(len(replies), 5)
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "clns")
        self.assertEqual(len(replies[1]["result"]["tools"]), len(TOOL_INDEX))
        structured = replies[2]["result"]["structuredContent"]
        self.assertEqual(structured["tool"], "get_service_meta")
        self.assertEqual(replies[3]["error"]["code"], -32601)
        self.assertEqual(replies[4]["error"]["code"], -32700)
        self.assertIn("CLNS stdio MCP ready", proc.stderr)

    def test_stdio_records_usage_into_given_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "stdio.sqlite")
            self.run_stdio([
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "get_service_meta", "arguments": {}}}),
            ], env_extra={"IMPORT_COMPLIANCE_DB": db_path})
            store = Store(db_path)
            try:
                payload = usage.stats_payload(store, days=1)
                self.assertGreaterEqual(payload["days"][0]["tools"].get("get_service_meta", 0), 1)
            finally:
                store.close()


class LicenseAndCiTest(unittest.TestCase):
    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_mit_license_is_anonymous(self):
        text = self.read("LICENSE")
        self.assertIn("MIT License", text)
        self.assertIn("Copyright (c) 2026 CLNS-KR", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn("THE SOFTWARE IS PROVIDED \"AS IS\"", text)
        # 저작권자 줄은 CLNS-KR 한 곳만 — 실명·개인 연락처가 붙으면 실패한다.
        holders = [line for line in text.splitlines() if line.startswith("Copyright")]
        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0].strip(), "Copyright (c) 2026 CLNS-KR")
        for pattern in anonymous_violations():
            self.assertIsNone(pattern.search(text), pattern.pattern)

    def test_github_actions_workflow(self):
        text = self.read(".github", "workflows", "test.yml")
        self.assertIn("python-version", text)
        self.assertRegex(text, r"3\.1[12]")
        self.assertIn("--check-corpus", text)
        self.assertIn("tests", text)
        self.assertIn("on:", text)
        self.assertNotIn("DATA_GO_KR_SERVICE_KEY=", text)
        self.assertNotIn("LAW_GO_KR_OC=", text)

    def test_readme_documents_growth_stage_one(self):
        text = self.read("README.md")
        self.assertIn(BASE, text)
        self.assertIn("/p/", text)
        self.assertIn("/v1/stats", text)
        self.assertIn("mcp_stdio", text)
        self.assertIn("MIT", text)
        self.assertIn("CLNS-KR", text)
        self.assertIn(".github/workflows/test.yml", text)
        for pattern in anonymous_violations():
            self.assertIsNone(pattern.search(text), pattern.pattern)

    def test_version_bumped_to_0_2_0(self):
        # 0.3.0: 질문형 가이드(/guides/) + 일일 시계열 스냅샷·추이
        version_text = self.read("src", "import_compliance", "version.py")
        self.assertIn('__version__ = "0.5.6"', version_text)
        docker = self.read("Dockerfile")
        self.assertIn('org.opencontainers.image.version="0.5.6"', docker)
        from import_compliance import web_ui

        self.assertEqual(web_ui.SERVICE_VERSION, "0.5.6")

    def test_committed_files_have_no_secrets_or_personal_data(self):
        patterns = [
            re.compile(r"DATA_GO_KR_SERVICE_KEY\s*=\s*[A-Za-z0-9%+/=]{20,}"),
            re.compile(r"LAW_GO_KR_OC\s*=\s*[A-Za-z0-9]{6,}"),
            re.compile(r"ghp_[A-Za-z0-9]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        ] + anonymous_violations()
        targets = ["README.md", "LICENSE", "Dockerfile", "render.yaml",
                   os.path.join("src", "pseo_items.json"),
                   os.path.join("src", "import_compliance", "pseo.py"),
                   os.path.join("src", "import_compliance", "usage.py"),
                   os.path.join("src", "import_compliance", "mcp_stdio.py"),
                   os.path.join("src", "import_compliance", "static_files.py"),
                   os.path.join(".github", "workflows", "test.yml")]
        for relative in targets:
            text = self.read(relative)
            for pattern in patterns:
                with self.subTest(file=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
