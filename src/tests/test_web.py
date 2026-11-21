"""웹 UI(`GET /`)·배포 설정·보안 회귀 테스트.

- `GET /`가 외부 CDN 없는 단일 HTML을 200으로 돌려주는지
- 툴 별칭(`assess_import_risk` → `assess_import_case`)이 동작하는지
- 환경변수(PORT·HOST·IMPORT_COMPLIANCE_DB·IMPORT_COMPLIANCE_LIVE) 해석이 맞는지
- 모듈 엔트리포인트(`python -m import_compliance.server`)로 실제 기동되는지
- API 키가 페이지·응답·에러 어디에도 새지 않는지

실행: python3 tests/test_web.py   (표준 unittest, 네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import web_ui  # noqa: E402
from import_compliance.api import TOOL_DEFS  # noqa: E402
from import_compliance.live_api import LiveApiClient  # noqa: E402
from import_compliance.server import (  # noqa: E402
    DEFAULT_PORT,
    config_from_env,
    default_db_path,
    make_handler,
)
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402

FAKE_KEY = "FAKE_SERVICE_KEY_9f3c1d7b"
FAKE_OC = "fakeoc"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def url_get(port: int, path: str, headers=None, timeout: float = 5.0):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers), response.read()


class PageTest(unittest.TestCase):
    """정적 HTML 계약(외부 의존 0·익명·접근성/구조 일관성)."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_single_page_without_external_assets(self):
        self.assertIn("<!doctype html>", self.page.lower())
        self.assertIn("lang=\"ko\"", self.page)
        self.assertIn("width=device-width", self.page)
        # 페이지가 실제로 불러오는 외부 자원(스크립트·스타일시트·이미지)은 없어야 한다.
        self.assertNotRegex(self.page, r'src="(?:https?:)?//')
        self.assertNotRegex(self.page, r"<link[^>]+stylesheet")
        self.assertNotRegex(self.page, r"<script[^>]+src=")
        # canonical·og:url 같은 메타데이터 링크는 자원이 아니므로 허용한다(중복 색인 방지 목적).
        self.assertRegex(self.page, r'<link rel="canonical" href="https://')
        for token in ("cdn.", "jsdelivr", "unpkg", "googleapis", "googletagmanager"):
            self.assertNotIn(token, self.page.lower())

    def test_risk_check_form_fields(self):
        for field_id in ("product", "hs", "origin", "kind", "check-form", "hs-form"):
            self.assertIn(f'id="{field_id}"', self.page)
        for name in ("wire", "child", "purpose"):
            self.assertIn(f'name="{name}"', self.page)
        self.assertIn("모름", self.page)
        self.assertIn("있음", self.page)
        self.assertIn("없음", self.page)

    def test_required_sections_present(self):
        for text in ("리스크 체크", "HS 10자리", "MCP", "무료 베타",
                     "관세사", "참고용", "면책", "식약처", "리콜", "세관장확인"):
            self.assertIn(text, self.page)

    OLD_BRANDS = ("trade" + "check", "kl" + "air")

    def test_brand_name_and_subtitles(self):
        self.assertIn("<h1>CLNS</h1>", self.page)
        self.assertIn("PRODUCT COMPLIANCE INTELLIGENCE · KOREA", self.page)
        self.assertIn("Clearance, simplified.", self.page)
        self.assertIn("<title>CLNS · PRODUCT COMPLIANCE INTELLIGENCE · KOREA</title>", self.page)
        for old in self.OLD_BRANDS:
            self.assertNotIn(old, self.page.lower())

    def test_brand_lines_are_not_grouped(self):
        """브랜드명·서브타이틀·슬로건은 각각 다른 요소로 줄을 나눠 표기한다."""
        self.assertNotRegex(self.page, r"CLNS\s*\(")
        self.assertNotIn("CLNS — PRODUCT", self.page)
        self.assertIn('<p class="sub-en">PRODUCT COMPLIANCE INTELLIGENCE · KOREA</p>', self.page)
        self.assertIn('<p class="slogan">Clearance, simplified.</p>', self.page)

    def test_three_axis_tab_names(self):
        for label in ("CLNS Check", "CLNS Intelligence", "CLNS API &amp; MCP"):
            self.assertIn(label, self.page)
        self.assertLess(self.page.index("CLNS Check"), self.page.index("CLNS Intelligence"))
        self.assertLess(self.page.index("CLNS Intelligence"), self.page.index("CLNS API &amp; MCP"))

    def test_anonymous_service_name_only(self):
        self.assertIn("CLNS", self.page)
        self.assertNotRegex(self.page, r"[\w.+-]+@[\w-]+\.[\w.]+")            # 이메일 없음
        self.assertNotRegex(self.page, r"01\d[- ]?\d{3,4}[- ]?\d{4}")         # 휴대폰 번호 없음
        for word in ("사업자등록번호", "대표자", "주민등록", "통신판매업"):
            self.assertNotIn(word, self.page)

    def test_javascript_references_existing_ids(self):
        ids = set(re.findall(r'id="([^"]+)"', self.page))
        refs = set(re.findall(r'getElementById\("([^"]+)"\)', self.page))
        self.assertTrue(refs, "스크립트가 참조하는 id가 없습니다")
        self.assertEqual(sorted(refs - ids), [], "HTML에 없는 id를 참조합니다")
        self.assertIn('data-tab="check"', self.page)
        self.assertIn('aria-controls="tab-check"', self.page)

    def test_no_conclusive_or_personal_claims(self):
        self.assertNotIn("확정입니다", self.page)
        self.assertIn("확정 판정이 아니라", self.page)
        self.assertIn("법적 효력이 없", self.page)

    def test_page_constant_avoids_escaped_double_quotes(self):
        """PAGE_HTML 안에서 \" 이스케이프를 쓰지 않는다.

        이스케이프된 따옴표는 렌더된 HTML에서는 그냥 " 가 되어, JS 문자열 안의
        HTML 속성(class="...")이 문자열을 조기 종료해 스크립트 전체가 문법 오류로
        죽는다(실제로 한 번 발생한 버그). 안쪽 따옴표는 ' 를 쓴다.
        """
        import pathlib

        source = pathlib.Path(web_ui.__file__).read_text(encoding="utf-8")
        marker = 'PAGE_HTML = """'
        start = source.index(marker)
        end = source.index('"""', start + len(marker))
        self.assertNotIn('\\"', source[start:end],
                         "PAGE_HTML 안에 이스케이프된 따옴표가 있습니다 : JS 문자열이 깨집니다")


class HttpTest(unittest.TestCase):
    """실제 소켓으로 GET / · 별칭 · 오류 응답을 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="clns-web-")
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

    def _post(self, path, payload, headers=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")

    def test_index_returns_html(self):
        status, headers, body = url_get(self.port, "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        html = body.decode("utf-8")
        self.assertIn("CLNS", html)
        self.assertIn('id="check-form"', html)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'none'", headers.get("Content-Security-Policy", ""))

    def test_head_request_has_no_body(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/", method="HEAD")
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"")

    def test_tool_alias_assess_import_risk(self):
        status, _, body = self._post("/v1/tools/assess_import_risk",
                                     {"query": "중국산 블루투스 스피커를 수입해 판매"})
        out = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(out["ok"])
        self.assertEqual(out["tool"], "assess_import_case")
        self.assertIn("disclaimer", out["result"])

    def test_index_and_meta_never_contain_keys(self):
        live = LiveApiClient(service_key=FAKE_KEY, law_oc=FAKE_OC,
                             transport=lambda url, timeout: (500, "down", "application/json"),
                             sleep=lambda seconds: None)
        store = Store(":memory:")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, live=live))
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            _, _, page = url_get(port, "/")
            _, _, meta = url_get(port, "/v1/meta")
            status, _, assess = self._post_to(port, "/v1/tools/assess_import_case",
                                              {"query": "중국산 유아용 완구를 수입해 판매",
                                               "facts": {"hs_code": "9503009000"}})
            self.assertEqual(status, 200)
            for payload in (page, meta, assess):
                text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
                self.assertNotIn(FAKE_KEY, text)
                self.assertNotIn(FAKE_OC, text)
            self.assertIn('"customs_checkpoint": true', meta.decode("utf-8"))
        finally:
            httpd.shutdown()
            httpd.server_close()
            store.close()

    @staticmethod
    def _post_to(port, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Client-Id": "web-test0001"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, dict(response.headers), response.read()

    def test_meta_and_manifest_use_clns_branding(self):
        _, _, meta = url_get(self.port, "/v1/meta")
        meta_json = json.loads(meta.decode("utf-8"))["result"]
        self.assertEqual(meta_json["service"], "CLNS")
        self.assertEqual(meta_json["service_subtitle_en"], "PRODUCT COMPLIANCE INTELLIGENCE · KOREA")
        self.assertEqual(meta_json["service_slogan"], "Clearance, simplified.")
        self.assertEqual(meta_json["service_axes"],
                         ["CLNS Check", "CLNS Label", "CLNS Intelligence", "CLNS API & MCP"])

        _, _, manifest = url_get(self.port, "/v1/mcp")
        mcp = json.loads(manifest.decode("utf-8"))
        self.assertEqual(mcp["name"], "clns")
        self.assertEqual(mcp["version"], "clns/" + __version__)
        self.assertIn("CLNS — Korea Import Compliance MCP & API", mcp["description"])
        self.assertEqual(mcp["serverInfo"],
                         {"name": "clns", "version": "clns/" + __version__,
                          "description": "CLNS — Korea Import Compliance MCP & API · PRODUCT COMPLIANCE INTELLIGENCE · KOREA"})
        self.assertEqual(len(mcp["tools"]), len(TOOL_DEFS))

    def test_healthz_reports_clns_service(self):
        _, _, body = url_get(self.port, "/healthz")
        self.assertEqual(json.loads(body)["service"], "clns-kr")

    def test_invalid_body_returns_400(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/tools/assess_import_case",
            data=b"{not json", headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(json.loads(ctx.exception.read())["error"], "invalid_json")

    def test_non_object_body_returns_400(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/tools/assess_import_case",
            data=b"[1,2,3]", headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_payload_too_large_returns_413(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/tools/assess_import_case",
            data=b"{}", headers={"Content-Type": "application/json",
                                 "Content-Length": str(1024 * 1024)}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 413)

    def test_client_id_is_sanitized(self):
        self._post("/v1/tools/assess_import_case", {"query": "중국산 유아용 완구를 수입해 판매"},
                   headers={"X-Client-Id": "bad id<script>"})
        row = self.store.conn.execute(
            "SELECT client_id FROM assessments ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row)
        self.assertNotIn("<", row["client_id"])
        self.assertNotIn(" ", row["client_id"])


class UiContractTest(unittest.TestCase):
    """웹 UI 렌더러가 읽는 필드가 응답에 실제로 있는지 고정한다.

    `web_ui.py`의 `esc()`로 그리는 키 이름이 바뀌면 화면이 빈 채로 나가므로,
    여기서 계약을 끊어 잠근다.
    """

    @classmethod
    def setUpClass(cls):
        from import_compliance import recall_index
        from import_compliance.api import call_tool
        cls.store = Store(":memory:")
        recall_index.load_from_index(cls.store)  # 서버와 같이 리콜 인덱스를 올린 상태로 본다
        cls.call = staticmethod(call_tool)
        cls.assess = call_tool(
            "assess_import_case",
            {"query": "중국산 블루투스 스피커를 수입해서 판매",
             "facts": {"purpose": "resale", "rf_tx": "yes", "target_age": "성인",
                       "hs_code": "8518220000"}},
            cls.store, client_id="web-contract")["result"]
        cls.hs = call_tool("lookup_hs_requirements", {"hs_code": "8518220000"},
                           cls.store, client_id="web-contract")["result"]
        cls.recall = call_tool("lookup_recall", {"product_name": "전지", "brand": "", "limit": 3},
                               cls.store, client_id="web-contract")["result"]

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_assess_fields_used_by_page(self):
        r = self.assess
        for key in ("assessment_id", "engine", "query", "verdict", "answer", "findings",
                    "evidence", "data_provenance", "disclaimer", "scope_limits_ko", "next_actions"):
            self.assertIn(key, r)
        for key in ("code", "label_ko", "label_en", "note_ko"):
            self.assertIn(key, r["verdict"])
        self.assertIn("guidance", r["answer"])
        self.assertIn("text", r["query"])
        self.assertIn("checked_at", r["data_provenance"])
        self.assertIn("ko", r["disclaimer"])
        finding = r["findings"][0]
        for key in ("case_id", "title", "issue_ko", "verdict", "verdict_label_ko", "confidence",
                    "reason", "missing_inputs", "misconception", "explanation", "notes"):
            self.assertIn(key, finding)
        for basis in r["evidence"]:
            for key in ("law", "article", "effective_date", "url"):
                self.assertIn(key, basis)

    def test_hs_and_recall_fields_used_by_page(self):
        self.assertIn("hs_lookup", self.hs)
        self.assertIn("note_ko", self.hs["hs_lookup"])
        self.assertIn("findings", self.hs)
        self.assertIn("evidence", self.hs)
        recall = self.recall["recall"]
        for key in ("state", "match_count", "matches", "coverage", "note_ko", "official_url"):
            self.assertIn(key, recall)
        self.assertIn("items", recall["coverage"])
        self.assertTrue(recall["matches"], "로컬 인덱스에서 '전지' 검색 결과가 비었습니다")
        for key in ("product_name", "model", "brand", "recall_type", "hazard_type", "registered_on"):
            self.assertIn(key, recall["matches"][0])

    def test_live_blocks_shape_when_keys_present(self):
        """live 모드에서 UI가 그리는 블록(세관장확인·식약처)의 필드 형태."""
        sys.path.insert(0, HERE)
        import test_live_api as live_fixtures  # 같은 tests/ 폴더의 고정 응답 재사용

        live = LiveApiClient(
            service_key=live_fixtures.FAKE_KEY, law_oc=live_fixtures.FAKE_OC,
            transport=live_fixtures.fake_transport({
                "retrieveCcctLworCd": (200, live_fixtures.CUSTOMS_XML),
                "getImrtsCnfirmList05": (200, live_fixtures.MFDS_PERMIT_JSON),
                "getInspctImproptList05": (200, live_fixtures.MFDS_IMPROPER_JSON),
                "IprtFoodPrdtDBService02": (200, live_fixtures.MFDS_PRODUCT_JSON),
            }), sleep=lambda seconds: None)
        store = Store(":memory:")
        self.addCleanup(store.close)
        hs = self.call("lookup_hs_requirements", {"hs_code": "8518220000"}, store,
                       client_id="web-live", live=live)["result"]["hs_requirements_live"]
        self.assertEqual(hs["state"], "live")
        for key in ("hs_code", "checked_at", "requirement_count", "requirements",
                    "note_ko", "zero_note_ko"):
            self.assertIn(key, hs)
        for key in ("requirement_law", "requirement_agency", "requirement_document",
                    "applies_from", "timing"):
            self.assertIn(key, hs["requirements"][0])
        food = self.call("check_food_cosmetics", {"product_name": "비타민", "kind": "health_functional"},
                         store, client_id="web-live", live=live)["result"]["food_import_live"]
        for key in ("product_db", "import_permit_history", "improper_history", "note_ko"):
            self.assertIn(key, food)
        self.assertIn("product_name", food["product_db"]["samples"][0])
        self.assertIn("product_name_ko", food["import_permit_history"]["samples"][0])
        self.assertIn("fail_reason", food["improper_history"]["samples"][0])


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = config_from_env({})
        self.assertEqual(cfg["host"], "0.0.0.0")
        self.assertEqual(cfg["port"], DEFAULT_PORT)
        self.assertTrue(cfg["db_path"].endswith(os.path.join("data", "app.sqlite")))
        self.assertFalse(cfg["live_mode"])

    def test_overrides_from_environment(self):
        cfg = config_from_env({
            "HOST": "127.0.0.1",
            "PORT": "5000",
            "IMPORT_COMPLIANCE_DB": "/data/custom.sqlite",
            "IMPORT_COMPLIANCE_LIVE": "1",
        })
        self.assertEqual(cfg["host"], "127.0.0.1")
        self.assertEqual(cfg["port"], 5000)
        self.assertEqual(cfg["db_path"], "/data/custom.sqlite")
        self.assertTrue(cfg["live_mode"])

    def test_bad_port_falls_back(self):
        self.assertEqual(config_from_env({"PORT": "abc"})["port"], DEFAULT_PORT)
        self.assertEqual(config_from_env({"PORT": "99999"})["port"], DEFAULT_PORT)

    def test_default_db_path_points_to_workspace_data(self):
        self.assertEqual(os.path.dirname(default_db_path()),
                         os.path.join(os.path.dirname(SRC), "data"))


class EntryPointTest(unittest.TestCase):
    """`python -m import_compliance.server` / CLI `--serve` 실제 기동."""

    def _base_env(self, db_path):
        env = dict(os.environ)
        env.update({
            "PYTHONPATH": SRC,
            "HOST": "127.0.0.1",
            "PORT": str(free_port()),
            "IMPORT_COMPLIANCE_DB": db_path,
        })
        for key in ("IMPORT_COMPLIANCE_LIVE", "DATA_GO_KR_SERVICE_KEY", "LAW_GO_KR_OC"):
            env.pop(key, None)
        return env

    def _wait_ready(self, port, proc, timeout=20.0):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError("서버가 조기 종료되었습니다: " + (proc.stdout.read() or ""))
            try:
                status, _, body = url_get(port, "/healthz", timeout=1.0)
                if status == 200 and json.loads(body)["ok"]:
                    return
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last_error = exc
                time.sleep(0.2)
        raise AssertionError(f"서버가 {timeout}초 안에 응답하지 않았습니다: {last_error}")

    def _run_and_check(self, args):
        db_path = os.path.join(tempfile.mkdtemp(prefix="clns-entry-"), "app.sqlite")
        env = self._base_env(db_path)
        port = int(env["PORT"])
        proc = subprocess.Popen([sys.executable] + args, cwd=SRC, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            self._wait_ready(port, proc)
            status, headers, body = url_get(port, "/")
            self.assertEqual(status, 200)
            self.assertIn("CLNS", body.decode("utf-8"))
            self.assertTrue(os.path.exists(db_path), "IMPORT_COMPLIANCE_DB 경로에 DB가 생성되지 않았습니다")
            # 리콜 로컬 인덱스가 작업 DB로 복사되었는지 (data/recalls.sqlite가 있을 때)
            store = Store(db_path)
            try:
                from import_compliance import recall_index
                if os.path.exists(recall_index.default_index_path()):
                    self.assertGreater(recall_index.summary(store)["items"], 0)
            finally:
                store.close()
        finally:
            proc.terminate()
            try:
                output = proc.communicate(timeout=10)[0]
            except subprocess.TimeoutExpired:
                proc.kill()
                output = proc.communicate()[0]
        self.assertIn("listening on http://127.0.0.1", output)
        self.assertNotIn(FAKE_KEY, output)

    def test_module_entrypoint_with_environment(self):
        self._run_and_check(["-m", "import_compliance.server"])

    def test_cli_serve_entrypoint(self):
        self._run_and_check(["-m", "import_compliance.cli", "--serve"])


class LegacyBrandTest(unittest.TestCase):
    """프로젝트 전체에 이전 브랜드 잔재가 남지 않았는지 고정한다."""

    # 이전 브랜드 토큰은 프로젝트 자체 검색에 걸리지 않도록 분리해 둔다.
    LEGACY = ("trade" + "check", "kl" + "air")
    SUFFIXES = (".py", ".md", ".yaml", ".yml", ".json", ".txt", ".sql",
                ".example", ".dockerignore", ".gitignore", "Dockerfile")
    # 대용량 실측 산출물은 검사에서 제외한다.
    SKIP_FILES = {"live-scenario-results-2026-11-18.json"}
    SKIP_DIRS = {"__pycache__", ".git", "data", "node_modules"}

    def test_no_legacy_brand_strings_in_project(self):
        root = os.path.dirname(SRC)
        hits = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            for name in filenames:
                if name in self.SKIP_FILES or not name.endswith(self.SUFFIXES):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8", errors="ignore") as handle:
                        text = handle.read().lower()
                except OSError:
                    continue
                for token in self.LEGACY:
                    if token in text:
                        hits.append(os.path.relpath(path, root) + " -> " + token)
        self.assertEqual(hits, [], "이전 브랜드 잔재가 남아 있습니다: " + ", ".join(hits))


if __name__ == "__main__":
    unittest.main(verbosity=2)
