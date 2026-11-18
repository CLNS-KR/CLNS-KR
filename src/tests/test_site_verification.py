"""검색엔진 소유확인 회귀 테스트 — 구글 서치콘솔·네이버 서치어드바이저.

확인 항목
- `GOOGLE_SITE_VERIFICATION`·`NAVER_SITE_VERIFICATION` 메타태그가 `/` 와 `/p/{slug}` head 에 들어가는가
- `SITE_VERIFICATION_FILES` 로 등록한 HTML 파일이 루트 경로에서 그대로 서빙되는가(GET/HEAD)
- 환경변수가 없으면 기존 응답과 완전히 같은가(빈 태그·404)
- 화이트리스트 밖 문자·경로 이탈(`../`, 슬래시 포함 이름)은 거부되는가

실행: python3 tests/test_site_verification.py   (네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

from import_compliance import pseo, site_verification, web_ui  # noqa: E402

from test_patches_p0_p1 import ServerHarness  # noqa: E402

GOOGLE_TOKEN = "GgOoGgLlEe-token_1234.abc"
NAVER_TOKEN = "naver1234abcd5678efgh"
GOOGLE_FILE = {"google1a2b3c4d5e6f.html": "google-site-verification: google1a2b3c4d5e6f.html"}
NAVER_FILE = {"naver1a2b3cdef4567gh8i9jk0lmnop12qrs3.html":
              "naver-site-verification: naver1a2b3cdef4567gh8i9jk0lmnop12qrs3.html"}


class VerificationEnvMixin(unittest.TestCase):
    """환경변수 3개를 테스트마다 깨끗하게 세팅/복원한다."""

    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in
                       (site_verification.ENV_GOOGLE, site_verification.ENV_NAVER,
                        site_verification.ENV_FILES)}
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class MetaTagTest(VerificationEnvMixin):
    def test_no_env_means_no_tag(self):
        self.assertEqual(site_verification.meta_tags(), "")
        page = web_ui.render_page()
        self.assertNotIn("google-site-verification", page)
        self.assertNotIn("naver-site-verification", page)

    def test_tags_reach_main_page_and_pseo_page(self):
        os.environ[site_verification.ENV_GOOGLE] = GOOGLE_TOKEN
        os.environ[site_verification.ENV_NAVER] = NAVER_TOKEN
        expected_google = f'<meta name="google-site-verification" content="{GOOGLE_TOKEN}">'
        expected_naver = f'<meta name="naver-site-verification" content="{NAVER_TOKEN}">'
        for html in (web_ui.render_page(), pseo.render_index()):
            self.assertIn(expected_google, html)
            self.assertIn(expected_naver, html)
            self.assertLess(html.index(expected_google), html.index("</head>"))

    def test_token_is_sanitized(self):
        os.environ[site_verification.ENV_GOOGLE] = '"><script>alert(1)</script>'
        token = site_verification._token(os.environ[site_verification.ENV_GOOGLE])
        self.assertEqual(set(token) - set("0123456789abcdefghijklmnopqrstuvwxyz"
                                         "ABCDEFGHIJKLMNOPQRSTUVWXYZ._:-"), set())
        tags = site_verification.meta_tags()
        self.assertNotIn("<script", tags)
        self.assertEqual(tags.count('"'), 4)  # name="…" content="…" 두 쌍뿐


class VerificationFileTest(VerificationEnvMixin):
    def test_files_are_normalized(self):
        os.environ[site_verification.ENV_FILES] = json.dumps({**GOOGLE_FILE, **NAVER_FILE})
        files = site_verification.files()
        self.assertEqual(set(files), {"/" + k for k in list(GOOGLE_FILE) + list(NAVER_FILE)})

    def test_bad_entries_are_dropped(self):
        os.environ[site_verification.ENV_FILES] = json.dumps({
            "../etc/passwd.html": "x",
            "nested/path.html": "x",
            "ok.html": "fine",
            "no-extension": "x",
            "empty.html": "   ",
        })
        self.assertEqual(site_verification.files(), {"/ok.html": "fine"})

    def test_invalid_json_is_ignored(self):
        os.environ[site_verification.ENV_FILES] = "{not json"
        self.assertEqual(site_verification.files(), {})


class VerificationHttpTest(VerificationEnvMixin, ServerHarness):
    def setUp(self):
        VerificationEnvMixin.setUp(self)
        os.environ[site_verification.ENV_FILES] = json.dumps({**GOOGLE_FILE, **NAVER_FILE})
        os.environ[site_verification.ENV_GOOGLE] = GOOGLE_TOKEN

    def test_google_file_is_served(self):
        status, headers, body = self.raw("/google1a2b3c4d5e6f.html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(body.decode(), GOOGLE_FILE["google1a2b3c4d5e6f.html"])

    def test_naver_file_is_served(self):
        path = "/" + list(NAVER_FILE)[0]
        status, _, body = self.raw(path)
        self.assertEqual(status, 200)
        self.assertEqual(body.decode(), list(NAVER_FILE.values())[0])

    def test_head_is_answered(self):
        status, _, body = self.raw("/google1a2b3c4d5e6f.html", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")

    def test_unknown_path_is_404(self):
        status, _, _ = self.raw("/google-not-registered.html")
        self.assertEqual(status, 404)

    def test_home_page_carries_tag(self):
        status, _, body = self.raw("/")
        self.assertEqual(status, 200)
        self.assertIn(GOOGLE_TOKEN.encode(), body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
