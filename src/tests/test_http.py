"""HTTP 서버 스모크 테스트 (실제 소켓 사용)."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from import_compliance.api import TOOL_DEFS  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class HttpSmokeTest(unittest.TestCase):
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

    def _post(self, name, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/tools/{name}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Client-Id": "smoke"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_healthz_and_manifest(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=5) as resp:
            self.assertEqual(json.loads(resp.read())["ok"], True)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v1/mcp", timeout=5) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(manifest["tools"]), len(TOOL_DEFS))

    def test_assess_over_http(self):
        out = self._post("assess_import_case", {"query": "중국산 유아용 완구를 수입해 판매"})
        self.assertTrue(out["ok"])
        self.assertIn(out["result"]["verdict"]["code"], ("check_likely", "info_needed"))
        self.assertIn("disclaimer", out["result"])

    def test_bad_json_and_unknown_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v1/payment", timeout=5)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
