"""`/healthz` 버전 노출·`/v1/stats` 트래픽 구분 회귀 테스트 — 0.5.6.

확인하는 것
- `/healthz` JSON 에 `version` 이 현재 버전으로 들어간다(배포·레지스트리 버전 확인용).
- `/v1/stats` 가 경로를 다섯 묶음(`traffic.by_channel`)으로, 요청 종류를 셋
  (`traffic.by_client`)으로 접어 보여 준다.
- 구분은 익명 카운트다 — User-Agent 원문·IP·쿠키를 저장하지 않는다는 문구가 응답에 남는다.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from import_compliance import usage  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402


class HealthzVersionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store(":memory:")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()

    def test_healthz_includes_version(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], __version__)

    def test_stats_has_traffic_buckets(self):
        usage.record_request(self.store, "GET", "/", client="browser")
        usage.record_request(self.store, "GET", "/robots.txt", client="bot")
        usage.record_request(self.store, "POST", "/mcp", client="bot")
        usage.record_request(self.store, "GET", "/404", client="other")
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v1/stats?days=7",
                                    timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        traffic = data["traffic"]
        self.assertGreaterEqual(traffic["by_channel"]["web"], 1)
        self.assertGreaterEqual(traffic["by_channel"]["crawler_files"], 1)
        self.assertGreaterEqual(traffic["by_channel"]["mcp"], 1)
        self.assertGreaterEqual(traffic["by_client"]["bot"], 2)
        self.assertIn("channel_labels_ko", traffic)
        self.assertIn("User-Agent 원문", traffic["note_ko"])
        self.assertIn("traffic", data)


class ClassificationUnitTest(unittest.TestCase):
    def test_client_class(self):
        self.assertEqual(usage.client_class("Mozilla/5.0 (iPhone) Safari/604.1"), "browser")
        self.assertEqual(usage.client_class("python-requests/2.31.0"), "bot")
        self.assertEqual(usage.client_class("GPTBot/1.0"), "bot")
        self.assertEqual(usage.client_class(""), "other")
        self.assertEqual(usage.client_class("custom-tool"), "other")

    def test_channel_of(self):
        self.assertEqual(usage.channel_of("/"), "web")
        self.assertEqual(usage.channel_of("/p/선풍기"), "web")
        self.assertEqual(usage.channel_of("/privacy"), "web")
        self.assertEqual(usage.channel_of("/robots.txt"), "crawler_files")
        self.assertEqual(usage.channel_of("/v1/tools"), "api")
        self.assertEqual(usage.channel_of("/mcp"), "mcp")
        self.assertEqual(usage.channel_of("/static/og.png"), "assets")
        self.assertEqual(usage.channel_of("/404"), "not_found")

    def test_unknown_client_class_is_not_stored(self):
        store = Store(":memory:")
        try:
            usage.record_request(store, "GET", "/", client="Mozilla/5.0 raw string")
            rows = store.usage_rows(usage.today_kst(), usage.today_kst())
        finally:
            store.close()
        clients = [row for row in rows if row["kind"] == usage.KIND_CLIENT]
        self.assertEqual(clients, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
