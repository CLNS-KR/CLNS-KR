"""버전 동기화 검사 — 한 곳만 올리고 다른 곳을 잊는 사고를 막는다.

버전은 다음 다섯 곳에 같은 값으로 있어야 한다.

1. `src/import_compliance/version.py` `__version__`
2. `server.json` `version` (MCP Registry 매니페스트)
3. `Dockerfile` `org.opencontainers.image.version`
4. `web_ui.SERVICE_VERSION` (페이지 머리말ㆍ푸터)
5. `GET /v1/mcp` 매니페스트의 `serverInfo.version`(`clns/<버전>`)

새 버전을 낼 때는 이 파일의 `EXPECTED_VERSION` 만 고치면 나머지 지점이 함께 검사된다.

실행: PYTHONPATH=src python3 -m unittest discover -s src/tests -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import __version__, web_ui  # noqa: E402
from import_compliance.api import mcp_manifest  # noqa: E402

EXPECTED_VERSION = "0.5.8"


def read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class VersionSyncTest(unittest.TestCase):
    def test_package_version(self):
        self.assertEqual(__version__, EXPECTED_VERSION)

    def test_version_file_literal(self):
        self.assertIn(f'__version__ = "{EXPECTED_VERSION}"', read("src", "import_compliance", "version.py"))

    def test_server_manifest_version(self):
        self.assertEqual(json.loads(read("server.json"))["version"], EXPECTED_VERSION)

    def test_dockerfile_label_version(self):
        self.assertIn(f'org.opencontainers.image.version="{EXPECTED_VERSION}"', read("Dockerfile"))

    def test_web_ui_version(self):
        self.assertEqual(web_ui.SERVICE_VERSION, EXPECTED_VERSION)

    def test_mcp_manifest_version(self):
        manifest = mcp_manifest()
        self.assertEqual(manifest["version"], "clns/" + EXPECTED_VERSION)
        self.assertEqual(manifest["serverInfo"]["version"], "clns/" + EXPECTED_VERSION)

    def test_home_page_shows_version(self):
        page = web_ui.render_page()
        self.assertIn(f"v{EXPECTED_VERSION}", page)

    def test_declared_release_versions_match(self):
        """버전을 선언하는 자리(주석 이력 제외)는 모두 같은 값이어야 한다."""
        declarations = {
            os.path.join("src", "import_compliance", "version.py"):
                re.compile(r'__version__\s*=\s*"([^"]+)"'),
            "server.json": re.compile(r'"version"\s*:\s*"([^"]+)"'),
            "Dockerfile": re.compile(r'org\.opencontainers\.image\.version="([^"]+)"'),
        }
        for relative, pattern in declarations.items():
            found = set(pattern.findall(read(relative)))
            with self.subTest(file=relative):
                self.assertEqual(found, {EXPECTED_VERSION})


if __name__ == "__main__":
    unittest.main(verbosity=2)
