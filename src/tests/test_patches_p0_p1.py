"""P0·P1 패치 회귀 테스트 — MCP JSON-RPC·CORS·크롤러 파일·HS 10자리 판정·식약처 캐시.

검증 대상 (05 문서 1-9절 '고칠 것 목록' 그대로)
- P0-1 `POST /mcp`·`POST /v1/mcp` JSON-RPC 2.0, `/.well-known/mcp/server-card.json`, CORS + OPTIONS 204
- P0-2 식약처 3개 오퍼레이션 병렬 호출 + 7일 TTL 캐시(캐시 히트는 `cached_fallback` 으로 정직하게 표시)
- P0-3 HS 10자리 `assess_import_case` 가 세관장확인 요건을 반영하고 `check_likely` 로 올라가는지
- P1-1 `robots.txt`·`llms.txt`·`sitemap.xml` 서빙
- P1-2 canonical·OpenGraph·JSON-LD, og:image 실서빙
- P1-3 `food_import_live.state == "live"` 인데 provenance 는 '연결 실패'이던 모순 제거
- P1-4 화면 입력 문장 중복 제거, P1-5 모바일 390px 탭 잘림 CSS
- `_mfds_live` 게이트가 `has_mfds` 인지

실행: python3 tests/test_patches_p0_p1.py   (네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import test_live_api as fixtures  # 같은 tests/ 폴더의 고정 공개 API 응답  # noqa: E402

from import_compliance import static_files, web_ui  # noqa: E402
from import_compliance.api import call_tool, mcp_tools  # noqa: E402
from import_compliance.live_api import LiveApiClient  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import KST, Store  # noqa: E402


def live_client(**routes):
    """식약처 3개 오퍼레이션 + 관세청 + 법제처 기본 응답을 갖춘 가짜 클라이언트."""
    table = {
        "retrieveCcctLworCd": (200, fixtures.CUSTOMS_XML),
        "getImrtsCnfirmList05": (200, fixtures.MFDS_PERMIT_JSON),
        "getInspctImproptList05": (200, fixtures.MFDS_IMPROPER_JSON),
        "IprtFoodPrdtDBInq02": (200, fixtures.MFDS_PRODUCT_JSON),
    }
    table.update(routes)
    transport = fixtures.fake_transport(table)
    client = LiveApiClient(service_key=fixtures.FAKE_KEY, law_oc=fixtures.FAKE_OC,
                           transport=transport, sleep=lambda seconds: None)
    return client, transport


class ServerHarness(unittest.TestCase):
    """실제 소켓으로 HTTP 계약을 확인하는 공통 하네스."""

    live = None

    @classmethod
    def setUpClass(cls):
        cls.store = Store(":memory:")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store, live=cls.live))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()

    # --- 요청 헬퍼 ---------------------------------------------------------
    def raw(self, path, *, method="GET", body=None, headers=None, timeout=10):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read()

    def post_json(self, path, payload, headers=None):
        status, response_headers, body = self.raw(
            path, method="POST", body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            parsed = json.loads(body.decode("utf-8")) if body else None
        except ValueError:
            parsed = None
        return status, response_headers, parsed

    def rpc(self, payload, path="/mcp"):
        return self.post_json(path, payload)


class McpTransportTest(ServerHarness):
    def test_initialize_negotiates_protocol_and_reports_server(self):
        status, headers, body = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                          "params": {"protocolVersion": "2025-03-26",
                                                     "capabilities": {},
                                                     "clientInfo": {"name": "t", "version": "1"}}})
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertEqual(body["id"], 1)
        result = body["result"]
        self.assertEqual(result["protocolVersion"], "2025-03-26")
        self.assertEqual(result["serverInfo"]["name"], "clns")
        self.assertTrue(result["serverInfo"]["version"])
        self.assertFalse(result["capabilities"]["tools"]["listChanged"])
        self.assertIn("disclaimer", result["instructions"])

    def test_initialize_falls_back_on_unknown_protocol_version(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                               "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(body["result"]["protocolVersion"], "2025-06-18")

    def test_notification_returns_202_without_body(self):
        status, _, raw = self.raw("/mcp", method="POST",
                                  body=json.dumps({"jsonrpc": "2.0",
                                                   "method": "notifications/initialized"}).encode(),
                                  headers={"Content-Type": "application/json"})
        self.assertEqual(status, 202)
        self.assertEqual(raw, b"")

    def test_ping(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": "p1", "method": "ping"})
        self.assertEqual(body, {"jsonrpc": "2.0", "id": "p1", "result": {}})

    def test_tools_list_exposes_eight_tools_with_schemas(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        tools = body["result"]["tools"]
        self.assertEqual(len(tools), len(mcp_tools()))
        names = {tool["name"] for tool in tools}
        for expected in ("assess_import_case", "lookup_hs_requirements", "check_food_cosmetics",
                         "lookup_recall", "get_legal_basis", "get_service_meta"):
            self.assertIn(expected, names)
        for tool in tools:
            self.assertTrue(tool["description"])
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])

    def test_tools_call_returns_structured_content(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                               "params": {"name": "assess_import_case",
                                          "arguments": {"query": "유아용 원목 완구를 수입해 판매"}}})
        result = body["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["type"], "text")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["tool"], "assess_import_case")
        self.assertTrue(payload["ok"])
        self.assertEqual(result["structuredContent"]["result"]["verdict"]["determinative"], False)

    def test_tools_call_unknown_tool_is_protocol_error(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                               "params": {"name": "make_coffee", "arguments": {}}})
        self.assertEqual(body["error"]["code"], -32602)
        self.assertEqual(body["error"]["message"], "unknown_tool")

    def test_tools_call_invalid_arguments_marks_is_error(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                               "params": {"name": "lookup_hs_requirements",
                                          "arguments": {"hs_code": "ABC"}}})
        result = body["result"]
        self.assertTrue(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["error"], "invalid_argument")

    def test_unknown_method_and_invalid_request(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 7, "method": "resources/read"})
        self.assertEqual(body["error"]["code"], -32601)
        _, _, body = self.rpc({"id": 8, "method": "ping"})
        self.assertEqual(body["error"]["code"], -32600)

    def test_parse_error_uses_standard_code(self):
        status, _, raw = self.raw("/mcp", method="POST", body=b"{not json",
                                  headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["error"]["code"], -32700)

    def test_batch_returns_only_answered_requests(self):
        _, _, body = self.rpc([
            {"jsonrpc": "2.0", "id": "a", "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "b", "method": "tools/list"},
        ])
        self.assertIsInstance(body, list)
        self.assertEqual([item["id"] for item in body], ["a", "b"])

    def test_v1_mcp_post_shares_the_same_handler(self):
        _, _, body = self.rpc({"jsonrpc": "2.0", "id": 9, "method": "ping"}, path="/v1/mcp")
        self.assertEqual(body["id"], 9)
        self.assertEqual(body["result"], {})

    def test_get_mcp_is_not_sse_stream(self):
        status, headers, _ = self.raw("/mcp")
        self.assertEqual(status, 405)
        self.assertIn("POST", headers.get("Allow", ""))


class CorsAndServerCardTest(ServerHarness):
    def test_options_preflight_returns_204_with_cors_headers(self):
        status, headers, body = self.raw("/v1/tools/assess_import_case", method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", headers["Access-Control-Allow-Methods"])
        self.assertIn("Content-Type", headers["Access-Control-Allow-Headers"])
        self.assertIn("X-Client-Id", headers["Access-Control-Allow-Headers"])

    def test_options_on_mcp_endpoint(self):
        status, headers, _ = self.raw("/mcp", method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertIn("MCP-Protocol-Version", headers["Access-Control-Allow-Headers"])

    def test_cors_header_on_page_and_api(self):
        _, page_headers, _ = self.raw("/")
        self.assertEqual(page_headers["Access-Control-Allow-Origin"], "*")
        _, api_headers, _ = self.post_json("/v1/tools/get_service_meta", {})
        self.assertEqual(api_headers["Access-Control-Allow-Origin"], "*")

    def test_server_card_lists_tools_from_single_source(self):
        status, headers, raw = self.raw("/.well-known/mcp/server-card.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        card = json.loads(raw)
        self.assertEqual(card["serverInfo"]["name"], "CLNS")
        self.assertFalse(card["authentication"]["required"])
        self.assertEqual(card["authentication"]["schemes"], [])
        self.assertEqual(card["transport"]["endpoint"], "/mcp")
        self.assertEqual(card["resources"], [])
        self.assertEqual(card["prompts"], [])
        self.assertEqual([tool["name"] for tool in card["tools"]],
                         [tool["name"] for tool in mcp_tools()])
        self.assertEqual(len(card["tools"]), len(mcp_tools()))
        self.assertIn("corpus", card)


class CrawlerFilesTest(ServerHarness):
    def test_robots_txt(self):
        status, headers, raw = self.raw("/robots.txt")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        text = raw.decode("utf-8")
        self.assertIn("User-agent: *", text)
        self.assertIn("Disallow: /v1/", text)
        self.assertIn("Sitemap: https://clns-kr.onrender.com/sitemap.xml", text)
        self.assertIn("GPTBot", text)
        self.assertNotIn("제안안", text)

    def test_llms_txt(self):
        status, headers, raw = self.raw("/llms.txt")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        text = raw.decode("utf-8")
        self.assertTrue(text.startswith("# CLNS"))
        self.assertIn("/mcp", text)
        self.assertIn("확정 판정이 아니라", text)
        self.assertIn("0건은 \"요건 없음\"이 아니라", text)
        self.assertNotIn("제안안", text)

    def test_sitemap_xml(self):
        status, headers, raw = self.raw("/sitemap.xml")
        self.assertEqual(status, 200)
        self.assertIn("xml", headers["Content-Type"])
        root = ET.fromstring(raw)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(namespace + "loc")]
        self.assertEqual(locs[0], "https://clns-kr.onrender.com/")
        # pSEO: 인덱스 + 품목 페이지가 동적으로 포함된다(30개 이상).
        self.assertIn("https://clns-kr.onrender.com/p/", locs)
        self.assertIn("https://clns-kr.onrender.com/p/usb-mini-fan", locs)
        self.assertGreaterEqual(len([loc for loc in locs if "/p/" in loc]), 31)
        self.assertEqual(len(locs), len(set(locs)))
        lastmod = [node.text for node in root.iter(namespace + "lastmod")]
        self.assertRegex(lastmod[0], r"^\d{4}-\d{2}-\d{2}$")

    def test_public_base_url_is_configurable(self):
        os.environ["PUBLIC_BASE_URL"] = "https://example.test/"
        try:
            self.assertIn("Sitemap: https://example.test/sitemap.xml", static_files.robots_txt())
            self.assertIn("<loc>https://example.test/</loc>", static_files.sitemap_xml())
        finally:
            os.environ.pop("PUBLIC_BASE_URL", None)

    def test_og_image_is_served_as_png(self):
        status, headers, raw = self.raw("/static/og.png")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", raw[16:24])
        self.assertEqual((width, height), (1200, 630))


class HsCustomsVerdictTest(unittest.TestCase):
    """P0-3: HS 10자리면 assume_import_case 도 세관장확인 요건을 반영한다."""

    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _assess(self, args, live=None):
        out = call_tool("assess_import_case", args, self.store, client_id="patch-test", live=live)
        self.assertTrue(out["ok"], out)
        return out["result"]

    FAN = {"query": "중국산 무선 선풍기를 수입해 판매하려고 해",
           "facts": {"purpose": "resale", "hs_code": "8414519000", "rf_tx": "no"}}

    def test_customs_requirements_raise_verdict_to_check_likely(self):
        client, _ = live_client()
        result = self._assess(self.FAN, live=client)
        self.assertIn("hs_requirements_live", result)
        block = result["hs_requirements_live"]
        self.assertEqual(block["state"], "live")
        self.assertEqual(block["requirement_count"], 1)
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertEqual(result["verdict"]["label_ko"], "확인 대상 가능성 높음")
        guidance = " ".join(result["answer"]["guidance"])
        self.assertIn("요건 1건이 조회되었습니다", guidance)
        self.assertIn("약사법", guidance)

    def test_requirements_are_visible_not_only_counted(self):
        client, _ = live_client()
        result = self._assess(self.FAN, live=client)
        row = result["hs_requirements_live"]["requirements"][0]
        self.assertEqual(row["requirement_agency"], "한국의약품수출입협회")
        self.assertEqual(row["requirement_document"], "표준통관예정보고서(의약품등)")
        provenance = {src.get("source_id"): src for src in result["data_provenance"]["sources"]}
        self.assertEqual(provenance["customs_requirements"]["state"], "live")
        self.assertEqual(provenance["customs_requirements"]["item_count"], 1)

    def test_saved_assessment_matches_raised_verdict(self):
        client, _ = live_client()
        result = self._assess(self.FAN, live=client)
        row = self.store.conn.execute(
            "SELECT overall_verdict, response_json FROM assessments WHERE assessment_id=?",
            (result["assessment_id"],)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["overall_verdict"], "check_likely")
        saved = json.loads(row["response_json"])
        self.assertEqual(saved["verdict"]["code"], "check_likely")
        self.assertIn("hs_requirements_live", saved)

    def test_zero_requirements_keeps_verdict_and_warns(self):
        client, _ = live_client(retrieveCcctLworCd=(200, fixtures.CUSTOMS_EMPTY_XML))
        result = self._assess(self.FAN, live=client)
        self.assertEqual(result["hs_requirements_live"]["requirement_count"], 0)
        self.assertEqual(result["verdict"]["code"], "low_risk")
        guidance = " ".join(result["answer"]["guidance"])
        self.assertIn("0건", guidance)
        self.assertIn("조회되지 않음", guidance)

    def test_six_digit_hs_does_not_call_customs(self):
        client, transport = live_client()
        result = self._assess({"query": "무선 선풍기 수입 판매",
                               "facts": {"purpose": "resale", "hs_code": "841451"}}, live=client)
        self.assertNotIn("hs_requirements_live", result)
        self.assertFalse([url for url in transport.calls if "retrieveCcctLworCd" in url])

    def test_without_live_mode_no_customs_block(self):
        result = self._assess(self.FAN)
        self.assertNotIn("hs_requirements_live", result)

    def test_guidance_has_no_conclusive_phrasing(self):
        from import_compliance.policy import find_conclusive_phrasing

        client, _ = live_client()
        result = self._assess(self.FAN, live=client)
        text = " ".join([result["answer"]["headline"]] + result["answer"]["guidance"])
        self.assertEqual(find_conclusive_phrasing(text), [], text)


class MfdsCacheAndParallelTest(unittest.TestCase):
    """P0-2: 식약처 3개 오퍼레이션 병렬화 + 7일 TTL 캐시."""

    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _food(self, client, product="칠리"):
        out = call_tool("check_food_cosmetics", {"product_name": product, "kind": "food",
                                                 "purpose": "resale"},
                        self.store, client_id="patch-test", live=client)
        self.assertTrue(out["ok"], out)
        return out["result"]

    def test_second_call_hits_seven_day_cache(self):
        client, transport = live_client()
        first = self._food(client)
        self.assertEqual(first["food_import_live"]["state"], "live")
        calls_after_first = len(transport.calls)
        self.assertEqual(calls_after_first, 3)

        second = self._food(client)
        block = second["food_import_live"]
        self.assertEqual(block["state"], "cached_fallback")
        self.assertTrue(block["fresh"])
        self.assertLess(block["age_hours"], 0.1)
        self.assertEqual(block["cache_ttl_hours"], 168)
        self.assertEqual(len(transport.calls), calls_after_first)  # 추가 실호출 없음
        self.assertEqual(block["import_permit_history"]["match_count"], 2)

    def test_expired_cache_refetches(self):
        client, transport = live_client()
        self._food(client)
        expired = (datetime.now(KST) - timedelta(days=8)).isoformat(timespec="seconds")
        self.store.conn.execute("UPDATE api_snapshots SET fetched_at=?", (expired,))
        self.store.conn.commit()
        before = len(transport.calls)
        again = self._food(client)
        self.assertEqual(again["food_import_live"]["state"], "live")
        self.assertEqual(len(transport.calls), before + 3)

    def test_failed_operations_are_not_cached(self):
        client, transport = live_client(getImrtsCnfirmList05=(500, "down"))
        first = self._food(client)
        self.assertEqual(first["food_import_live"]["state"], "partial")
        before = len(transport.calls)
        second = self._food(client)
        self.assertEqual(second["food_import_live"]["state"], "partial")
        self.assertGreater(len(transport.calls), before)  # 캐시하지 않고 재시도

    def test_three_operations_run_in_parallel(self):
        def slow_transport(url, timeout):
            time.sleep(0.4)
            for needle, response in (
                ("getImrtsCnfirmList05", (200, fixtures.MFDS_PERMIT_JSON)),
                ("getInspctImproptList05", (200, fixtures.MFDS_IMPROPER_JSON)),
                ("IprtFoodPrdtDBInq02", (200, fixtures.MFDS_PRODUCT_JSON)),
            ):
                if needle in url:
                    return response + ("application/json",)
            raise AssertionError(f"unexpected url: {url}")

        client = LiveApiClient(service_key=fixtures.FAKE_KEY,
                               transport=slow_transport, sleep=lambda seconds: None)
        started = time.monotonic()
        result = self._food(client, product="병렬테스트")
        elapsed = time.monotonic() - started
        self.assertEqual(result["food_import_live"]["state"], "live")
        self.assertLess(elapsed, 0.85, f"순차 호출로 보입니다({elapsed:.2f}s)")

    def test_provenance_no_longer_contradicts_live_food_block(self):
        client, _ = live_client()
        result = self._food(client)
        self.assertEqual(result["food_import_live"]["state"], "live")
        provenance = {src.get("source_id"): src for src in result["data_provenance"]["sources"]}
        self.assertEqual(provenance["mfds_import_food"]["state"], "live")
        self.assertTrue(provenance["mfds_import_food"]["fresh"])
        blob = json.dumps(provenance["mfds_import_food"], ensure_ascii=False)
        self.assertNotIn("실시간 소스 연결 실패", blob)

    def test_cached_food_block_is_reported_as_cached_in_provenance(self):
        client, _ = live_client()
        self._food(client)
        second = self._food(client)
        provenance = {src.get("source_id"): src for src in second["data_provenance"]["sources"]}
        self.assertEqual(provenance["mfds_import_food"]["state"], "cached_fallback")
        self.assertTrue(provenance["mfds_import_food"]["fresh"])
        self.assertIsNotNone(provenance["mfds_import_food"]["age_hours"])
        self.assertTrue(any("TTL 캐시" in line for line in second["answer"]["guidance"]))

    def test_mfds_gate_uses_has_mfds_not_has_customs(self):
        """법령 OC 만 있고 data.go.kr 키가 없으면 식약처 툴은 실호출하지 않는다."""
        law_only = LiveApiClient(service_key="", law_oc=fixtures.FAKE_OC,
                                 transport=fixtures.fake_transport({}), sleep=lambda _: None)
        self.assertFalse(law_only.has_mfds)
        self.assertFalse(law_only.has_customs)
        self.assertTrue(law_only.has_law)
        out = call_tool("check_food_cosmetics", {"product_name": "칠리", "kind": "food"},
                        self.store, live=law_only)
        self.assertNotIn("food_import_live", out["result"])


class PagePatchTest(unittest.TestCase):
    """P1-2·P1-4·P1-5: head 메타, 화면 문장 중복, 모바일 탭 CSS."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_canonical_open_graph_and_json_ld(self):
        for needle in ('<link rel="canonical" href="https://clns-kr.onrender.com/">',
                       'property="og:type"', 'property="og:site_name"',
                       'property="og:title"', 'property="og:description"',
                       'property="og:url"', 'property="og:image"',
                       'name="twitter:card"', 'application/ld+json',
                       '"@type": "WebApplication"'):
            self.assertIn(needle, self.page)
        self.assertIn('content="https://clns-kr.onrender.com/static/og.png"', self.page)

    def test_json_ld_is_valid_json(self):
        start = self.page.index('<script type="application/ld+json">')
        body = self.page[start:].split(">", 1)[1].split("</script>", 1)[0]
        data = json.loads(body)
        self.assertEqual(data["name"], "CLNS")
        self.assertTrue(data["isAccessibleForFree"])
        self.assertEqual(data["offers"]["price"], "0")

    def test_input_summary_is_not_duplicated(self):
        # buildQuery() 가 뒤에 붙인 '수입해서 판매'를 화면이 다시 출력하지 않는다.
        self.assertIn("입력한 품목: ' + esc(data.product)", self.page)
        self.assertNotIn("result.query ? result.query.text", self.page)

    def test_mobile_tab_grid_prevents_tab_clipping(self):
        self.assertIn("@media (max-width:430px)", self.page)
        start = self.page.index("@media (max-width:430px)")
        block = self.page[start:start + 420]
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", block)
        self.assertIn("white-space:normal", block)
        self.assertIn("nav.tabs button .tab-ko{font-size:9.5px}", block)

    def test_mcp_copy_matches_real_transport(self):
        self.assertIn("JSON-RPC 2.0", self.page)
        self.assertIn("/.well-known/mcp/server-card.json", self.page)
        self.assertNotIn("툴 목록을 그대로 등록할 수 있습니다", self.page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
