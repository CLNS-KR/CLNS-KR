"""정적 고지 페이지(`/privacy`·`/terms`·`/about`) 회귀 테스트 — 0.5.6.

확인하는 것
- 세 주소가 실제 HTTP 200 HTML 로 열리고, HEAD 도 200 이다(크롤러·프리뷰 대응).
- canonical·og:image·설명이 들어 있고, /static/og.png 가 실제 PNG 로 내려간다.
- 푸터·사이트맵·익명 카운터가 세 주소를 알고 있다.
- 익명 운영 원칙: 실명·직업·개인 연락처·상대 서비스 핸들이 페이지에 없다.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from import_compliance import legal, static_files, usage, web_ui  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402

SLUGS = ("privacy", "terms", "about")


class LegalPagesHttpTest(unittest.TestCase):
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

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")

    def test_pages_are_served_as_html(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                status, content_type, body = self._get(f"/{slug}")
                self.assertEqual(status, 200)
                self.assertIn("text/html", content_type)
                self.assertIn(legal.TITLES[slug], body)
                self.assertIn("ko", body.split("\n")[1])

    def test_trailing_slash_and_head(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(self._get(f"/{slug}/")[0], 200)
                req = urllib.request.Request(f"http://127.0.0.1:{self.port}/{slug}", method="HEAD")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertIn("text/html", resp.headers.get("Content-Type", ""))

    def test_canonical_and_share_meta(self):
        root = static_files.base_url()
        for slug in SLUGS:
            with self.subTest(slug=slug):
                body = self._get(f"/{slug}")[2]
                self.assertIn(f'<link rel="canonical" href="{root}/{slug}">', body)
                self.assertIn(f'<meta property="og:image" content="{root}/static/og.png">', body)
                self.assertIn('property="og:description"', body)

    def test_og_image_is_png(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/static/og.png", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/png")
            self.assertEqual(resp.read(8), b"\x89PNG\r\n\x1a\n")

    def test_unknown_path_still_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/privacy-policy")
        self.assertEqual(ctx.exception.code, 404)


class LegalContentTest(unittest.TestCase):
    def test_home_footer_links_pages(self):
        page = web_ui.render_page()
        for slug in SLUGS:
            self.assertIn(f'href="/{slug}"', page)

    def test_sitemap_lists_pages(self):
        xml = static_files.sitemap_xml()
        root = static_files.base_url()
        for slug in SLUGS:
            self.assertIn(f"<loc>{root}/{slug}</loc>", xml)

    def test_stats_counts_pages_not_404(self):
        for slug in SLUGS:
            self.assertEqual(usage.path_key(f"/{slug}"), f"/{slug}")

    def test_privacy_states_retention_and_delete_path(self):
        body = legal.render("privacy")
        self.assertIn("180일", body)
        self.assertIn("/v1/inquiry", body)
        self.assertIn("삭제", body)
        self.assertIn("IP", body)
        self.assertIn("User-Agent", body)

    def test_terms_state_scope_and_liability(self):
        body = legal.render("terms")
        self.assertIn("확정 판정이 아닙니다", body)
        self.assertIn("관세사법", body)
        self.assertIn("책임", body)
        self.assertIn("무료", body)

    def test_about_introduces_three_services_and_sources(self):
        body = legal.render("about")
        for name in ("CLNS", "GRNT", "FRNC"):
            self.assertIn(name, body)
        self.assertIn("관세청", body)
        self.assertIn("식품의약품안전처", body)

    def test_no_identity_leak_in_legal_pages(self):
        """익명 운영 — 실명·직업·개인 메일·전화·상대 핸들이 고지 페이지에 없다."""
        forbidden = [r"@[a-z0-9.-]+\.(?:com|net|co\.kr|kr)", r"01\d[- ]?\d{3,4}[- ]?\d{4}",
                     r"조" r"종사", r"파" r"일럿", r"@pi" r"lot", r"Pilo" r"tage", r"비" r"행"]
        for slug in SLUGS:
            body = legal.render(slug)
            for pattern in forbidden:
                with self.subTest(slug=slug, pattern=pattern):
                    self.assertIsNone(re.search(pattern, body, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
