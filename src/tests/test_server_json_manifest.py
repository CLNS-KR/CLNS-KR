"""server.json(공식 MCP Registry 제출 매니페스트) 자기검증.

레지스트리는 `description` 을 100자 이하로 제한한다(2025-12-11 schema, `ServerDetail.description`).
0.1.4 게시 때 이 한도 초과(106자)로 publish 가 422 로 실패했으므로, 태그를 찍기 전에
CI(테스트 잡)에서 같은 규칙을 먼저 검사해 실패를 릴리스 단계가 아니라 커밋 단계에서 잡는다.

실행: python3 tests/test_server_json_manifest.py   (네트워크 불필요)
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

from import_compliance.version import __version__  # noqa: E402

MANIFEST_PATH = os.path.join(ROOT, "server.json")

# https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json → definitions.ServerDetail
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
MAX_DESCRIPTION = 100
MAX_TITLE = 100


class ServerManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MANIFEST_PATH, encoding="utf-8") as handle:
            cls.manifest = json.load(handle)

    def test_required_fields_present(self):
        for field in ("name", "description", "version"):
            self.assertIn(field, self.manifest, f"필수 필드 누락: {field}")
            self.assertTrue(str(self.manifest[field]).strip(), f"빈 값: {field}")

    def test_name_is_reverse_dns_namespace(self):
        name = self.manifest["name"]
        self.assertRegex(name, NAME_PATTERN)
        self.assertEqual(name.count("/"), 1)
        self.assertLessEqual(len(name), 200)
        self.assertEqual(name, "io.github.CLNS-KR/clns")

    def test_description_within_registry_limit(self):
        description = self.manifest["description"]
        self.assertLessEqual(
            len(description), MAX_DESCRIPTION,
            f"description 이 {len(description)}자입니다. 레지스트리 한도는 {MAX_DESCRIPTION}자입니다: {description!r}",
        )
        self.assertGreaterEqual(len(description), 1)

    def test_title_within_registry_limit(self):
        title = self.manifest.get("title")
        if title is not None:
            self.assertLessEqual(len(title), MAX_TITLE)

    def test_version_matches_package_version(self):
        self.assertEqual(self.manifest["version"], __version__)

    def test_remote_matches_live_server(self):
        remotes = self.manifest.get("remotes") or []
        self.assertTrue(remotes, "remotes 가 비어 있으면 원격 MCP 서버로 등록되지 않는다")
        remote = remotes[0]
        self.assertEqual(remote["type"], "streamable-http")
        self.assertEqual(remote["url"], "https://clns-kr.onrender.com/mcp")

    def test_repository_points_to_public_source(self):
        repo = self.manifest.get("repository") or {}
        self.assertEqual(repo.get("url"), "https://github.com/CLNS-KR/CLNS-KR")
        self.assertEqual(repo.get("source"), "github")

    def test_no_distribution_package_expected(self):
        """원격(streamable-http) 서버라 npm/PyPI 패키지 필드는 두지 않는다."""
        self.assertNotIn("packages", self.manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
