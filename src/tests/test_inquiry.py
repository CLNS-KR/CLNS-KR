"""CLNS Pro 사전 신청·도입 문의(`POST /v1/inquiry`) 회귀 테스트.

- 유효 입력은 SQLite `inquiries` 에 1건 저장되고 `{ok, id, received_at}` 만 돌려준다
- 연락처·관심 항목·메모 유효성 검사(400 + `field`)
- 무료 쿼터를 쓰지 않는다(신청은 호출이 아니다)
- `/v1/stats`·공개 페이지 어디에도 연락처가 노출되지 않는다(익명성 계약 유지)
- 웹 UI 폼(id·선택지·JS 참조)이 실제로 붙어 있다

실행: PYTHONPATH=src python3 -m unittest discover -s src/tests -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import web_ui  # noqa: E402
from import_compliance.api import (  # noqa: E402
    INQUIRY_MESSAGE_MAX,
    INQUIRY_TOPICS,
    submit_inquiry,
)
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402

SENTINEL_CONTACT = "buyer-sentinel@example.test"
SENTINEL_PHONE = "010-0000-0000"
SENTINEL_MESSAGE = "센티넬메모-일괄검수-1200건"


class StoreTest(unittest.TestCase):
    def test_table_exists_and_record_roundtrip(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        record = store.record_inquiry(SENTINEL_CONTACT, "clns_pro_batch", SENTINEL_MESSAGE)
        self.assertIsInstance(record["id"], int)
        self.assertGreater(record["id"], 0)
        self.assertRegex(record["received_at"], r"^\d{4}-\d{2}-\d{2}T")
        row = store.conn.execute(
            "SELECT contact, topic, message, received_at FROM inquiries WHERE id=?",
            (record["id"],)).fetchone()
        self.assertEqual(row["contact"], SENTINEL_CONTACT)
        self.assertEqual(row["topic"], "clns_pro_batch")
        self.assertEqual(row["message"], SENTINEL_MESSAGE)
        self.assertEqual(row["received_at"], record["received_at"])
        self.assertEqual(store.count_inquiries(), 1)

    def test_ids_increase_and_counts_accumulate(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        first = store.record_inquiry("010-" "1111-" "2222", "api_mcp", "")
        second = store.record_inquiry("카톡 clns_test", "other", "")
        self.assertGreater(second["id"], first["id"])
        self.assertEqual(store.count_inquiries(), 2)
        self.assertEqual(store.count_inquiries(since_day="2999-01-01"), 0)

    def test_schema_is_created_on_existing_db_file(self):
        """이미 쓰던 DB 파일을 열어도 inquiries 테이블이 생긴다(마이그레이션 없이)."""
        import tempfile

        path = os.path.join(tempfile.mkdtemp(prefix="clns-inquiry-"), "app.sqlite")
        store = Store(path)
        store.close()
        store = Store(path)
        try:
            record = store.record_inquiry("user@example.test", "other", "재접속 후 접수")
            self.assertGreater(record["id"], 0)
        finally:
            store.close()


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _valid(self, **overrides):
        payload = {"contact": "buyer@example.test", "topic": "clns_pro_batch",
                   "message": "월 1,200건 일괄 검수 문의"}
        payload.update(overrides)
        return payload

    def test_valid_payload_is_stored(self):
        out = submit_inquiry(self._valid(), self.store)
        self.assertTrue(out["ok"])
        self.assertTrue(out["id"])
        self.assertEqual(out["topic"], "clns_pro_batch")
        self.assertIn("received_at", out)
        # 접수한 연락처를 응답으로 되돌려주지 않는다.
        self.assertNotIn("buyer@example.test", json.dumps(out, ensure_ascii=False))
        self.assertNotIn("contact", out)
        self.assertEqual(self.store.count_inquiries(), 1)

    def test_message_is_optional(self):
        out = submit_inquiry({"contact": SENTINEL_PHONE, "topic": "other"}, self.store)
        self.assertTrue(out["ok"])
        row = self.store.conn.execute("SELECT message FROM inquiries ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row["message"], "")

    def test_every_topic_is_accepted(self):
        for topic in INQUIRY_TOPICS:
            self.assertTrue(submit_inquiry(self._valid(topic=topic), self.store)["ok"])

    def test_non_object_payload_is_rejected(self):
        out = submit_inquiry(["buyer@example.test"], self.store)  # type: ignore[arg-type]
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "invalid_argument")
        self.assertEqual(out["field"], "body")

    def test_contact_rules(self):
        cases = {
            "not_string": {"contact": 821012345678},
            "too_short": {"contact": "ab"},
            "too_long": {"contact": "a" * 121},
            "broken_email": {"contact": "buyer@example"},
            "space_in_email": {"contact": "buy er@example.test"},
            "control_chars": {"contact": "buyer\u0000@example.test"},
        }
        missing = submit_inquiry({"topic": "other"}, self.store)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["field"], "contact")
        for label, override in cases.items():
            with self.subTest(label):
                out = submit_inquiry(self._valid(**override), self.store)
                self.assertFalse(out["ok"], label)
                self.assertEqual(out["field"], "contact", label)
                self.assertNotIn("example.test", out.get("message", ""))
        self.assertEqual(self.store.count_inquiries(), 0)

    def test_contact_accepts_phone_and_messenger_id(self):
        for contact in (SENTINEL_PHONE, "010 " "1234 " "5678", "+82 10 " "1234 " "5678",
                        "카톡 clns_test"):
            with self.subTest(contact):
                self.assertTrue(submit_inquiry(self._valid(contact=contact), self.store)["ok"])

    def test_topic_rules(self):
        missing = submit_inquiry({"contact": SENTINEL_PHONE}, self.store)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["field"], "topic")
        for override in ({"topic": ""}, {"topic": "clns_pro"}, {"topic": 3}):
            with self.subTest(override):
                out = submit_inquiry(self._valid(**override), self.store)
                self.assertFalse(out["ok"])
                self.assertEqual(out["field"], "topic")
        self.assertEqual(self.store.count_inquiries(), 0)

    def test_message_rules(self):
        out = submit_inquiry(self._valid(message="가" * (INQUIRY_MESSAGE_MAX + 1)), self.store)
        self.assertFalse(out["ok"])
        self.assertEqual(out["field"], "message")
        out = submit_inquiry(self._valid(message=123), self.store)
        self.assertFalse(out["ok"])
        self.assertEqual(out["field"], "message")
        # 정확히 500자는 통과하고, 제어문자는 제거된다.
        out = submit_inquiry(self._valid(message="가" * INQUIRY_MESSAGE_MAX), self.store)
        self.assertTrue(out["ok"])
        out = submit_inquiry(self._valid(message="가\u0007나"), self.store)
        self.assertTrue(out["ok"])
        row = self.store.conn.execute("SELECT message FROM inquiries ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row["message"], "가나")


class HttpTest(unittest.TestCase):
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

    def _raw(self, path, body=b"", headers=None, method="POST"):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body, method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read().decode("utf-8")

    def _post(self, payload, headers=None):
        return self._raw("/v1/inquiry", json.dumps(payload).encode("utf-8"), headers)

    def test_valid_submission_returns_id_and_no_contact(self):
        status, headers, body = self._post(
            {"contact": SENTINEL_CONTACT, "topic": "api_mcp", "message": SENTINEL_MESSAGE},
            {"X-Client-Id": "web-inquiry-0001"})
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertGreater(out["id"], 0)
        self.assertNotIn(SENTINEL_CONTACT, body)
        self.assertNotIn(SENTINEL_MESSAGE, body)

    def test_invalid_submission_returns_400_with_field(self):
        status, _, body = self._post({"contact": "no", "topic": "other"})
        self.assertEqual(status, 400)
        out = json.loads(body)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "invalid_argument")
        self.assertEqual(out["field"], "contact")

    def test_invalid_json_returns_400(self):
        status, _, body = self._raw("/v1/inquiry", b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_json")

    def test_oversized_body_returns_413(self):
        status, _, body = self._raw("/v1/inquiry", b"{}",
                                    {"Content-Length": str(1024 * 1024)})
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body)["error"], "payload_too_large")

    def test_inquiry_does_not_consume_free_quota(self):
        client = "web-inquiry-quota-01"
        self._post({"contact": SENTINEL_PHONE, "topic": "other"}, {"X-Client-Id": client})
        self.assertEqual(self.store.quota_used(client), 0)

    def test_stats_never_expose_contact_or_message(self):
        status, _, body = self._post(
            {"contact": SENTINEL_CONTACT, "topic": "clns_pro_batch", "message": SENTINEL_MESSAGE})
        self.assertEqual(status, 200)
        _, _, stats = self._raw("/v1/stats?days=1", method="GET")
        data = json.loads(stats)
        text = json.dumps(data, ensure_ascii=False)
        for sentinel in (SENTINEL_CONTACT, SENTINEL_MESSAGE):
            self.assertNotIn(sentinel, text)
            self.assertNotIn(sentinel.split("@")[0], text)
        # 문의는 툴 호출로 세지도 않는다.
        for day in data["days"]:
            self.assertNotIn("inquiry", day["tools"])
            self.assertNotIn("submit_inquiry", day["tools"])
        # 경로 버킷은 하나로만 잡힌다(임의 문자열이 통계에 남지 않는다).
        self.assertIn("/v1/inquiry", data["totals"]["paths"])

    def test_get_on_inquiry_path_is_not_a_tool(self):
        status, _, _ = self._raw("/v1/inquiry", method="GET")
        self.assertEqual(status, 404)


class UiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_inquiry_card_is_above_footer(self):
        self.assertIn('id="inquiry"', self.page)
        self.assertIn("CLNS Pro 사전 신청 · 도입 문의", self.page)
        self.assertLess(self.page.index('id="inquiry"'), self.page.index("<footer>"))
        self.assertGreater(self.page.index('id="inquiry"'), self.page.index('id="tab-api"'))

    def test_inquiry_form_fields_exist(self):
        for field_id in ("inquiry-form", "inquiry-topic", "inquiry-contact",
                         "inquiry-message", "inquiry-submit", "inquiry-note"):
            self.assertIn(f'id="{field_id}"', self.page)
        for topic in INQUIRY_TOPICS:
            self.assertIn(f'<option value="{topic}">', self.page)
        self.assertIn('maxlength="120"', self.page)
        self.assertIn('maxlength="500"', self.page)
        # 연락처 예시(이메일·휴대폰 모양)를 페이지에 노출하지 않는다.
        self.assertNotRegex(self.page, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertNotRegex(self.page, r"01\d[- ]?\d{3,4}[- ]?\d{4}")

    def test_script_posts_to_inquiry_endpoint(self):
        self.assertIn("/v1/inquiry", self.page)
        ids = set(re.findall(r'id="([^"]+)"', self.page))
        refs = set(re.findall(r'getElementById\("([^"]+)"\)', self.page))
        self.assertTrue(refs <= ids, "HTML에 없는 id를 참조합니다: " + str(sorted(refs - ids)))

    def test_footer_privacy_mentions_inquiry_scope(self):
        self.assertIn("회신하는 용도로만 저장", self.page)
        self.assertIn("통계·공개 화면에는 쓰지 않습니다", self.page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
