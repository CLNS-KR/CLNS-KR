"""0.5.4 — 무료 베타 파일럿 구분 태그(`cohort`/`source`) 회귀 테스트.

외부 협업 쪽 베타 테스터와 소개 글(CiteChart 등)에서 들어온 문의를 나중에 구분해 셀 수
있도록 `POST /v1/inquiry` 에 **선택** 필드 `cohort`(별칭 `source`)를 더했다. 이 파일은
그 필드가 (1) 종전 요청과 100% 호환되고, (2) 저장·저널·알림·관리자 요약까지 이어지고,
(3) 연락처·메모가 새 경로로 새지 않는지를 고정한다.

실행: PYTHONPATH=src python3 -m unittest discover -s src/tests -q
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import api, inquiry_alert, usage  # noqa: E402
from import_compliance.api import INQUIRY_COHORT_MAX, submit_inquiry  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402

CONTACT = "beta" + "@" + "example.test"
OTHER_CONTACT = "other" + "@" + "example.test"
PHONE = "010" + "-1111-2222"
MESSAGE = "베타 테스트로 일괄 검수 3건 돌려봤습니다"

OLD_SCHEMA = """
CREATE TABLE inquiries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact     TEXT NOT NULL,
    topic       TEXT NOT NULL,
    message     TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL
);
"""


class CohortValidationTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _payload(self, **overrides):
        payload = {"contact": CONTACT, "topic": "clns_pro_batch", "message": MESSAGE}
        payload.update(overrides)
        return payload

    def _row(self):
        return self.store.conn.execute(
            "SELECT contact, topic, message, cohort FROM inquiries ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def test_cohort_is_stored_and_echoed(self):
        out = submit_inquiry(self._payload(cohort="beta_pilot"), self.store)
        self.assertTrue(out["ok"])
        self.assertEqual(out["cohort"], "beta_pilot")
        self.assertEqual(self._row()["cohort"], "beta_pilot")
        self.assertNotIn(CONTACT, json.dumps(out, ensure_ascii=False))
        self.assertNotIn(MESSAGE, json.dumps(out, ensure_ascii=False))

    def test_source_is_an_alias(self):
        out = submit_inquiry(self._payload(source="citechart"), self.store)
        self.assertTrue(out["ok"])
        self.assertEqual(out["cohort"], "citechart")
        self.assertEqual(self._row()["cohort"], "citechart")

    def test_cohort_wins_over_source_when_both_given(self):
        out = submit_inquiry(self._payload(cohort="beta_pilot", source="citechart"), self.store)
        self.assertTrue(out["ok"])
        self.assertEqual(out["cohort"], "beta_pilot")

    def test_tag_is_lowercased_and_trimmed(self):
        out = submit_inquiry(self._payload(source="  Beta_Pilot-2  "), self.store)
        self.assertTrue(out["ok"])
        self.assertEqual(out["cohort"], "beta_pilot-2")

    def test_missing_or_empty_tag_keeps_old_behaviour(self):
        for payload in (self._payload(), self._payload(cohort=""), self._payload(cohort="   "),
                        self._payload(cohort=None)):
            with self.subTest(payload=payload):
                out = submit_inquiry(payload, self.store)
                self.assertTrue(out["ok"])
                self.assertEqual(out["cohort"], "")
                self.assertEqual(self._row()["cohort"], "")

    def test_max_length_boundary(self):
        exact = "b" * INQUIRY_COHORT_MAX
        self.assertTrue(submit_inquiry(self._payload(cohort=exact), self.store)["ok"])
        out = submit_inquiry(self._payload(cohort="b" * (INQUIRY_COHORT_MAX + 1)), self.store)
        self.assertFalse(out["ok"])
        self.assertEqual(out["field"], "cohort")
        self.assertIn(str(INQUIRY_COHORT_MAX), out["message"])

    def test_rejects_bad_characters_and_non_strings(self):
        for value in ("베타파일럿", "beta pilot", "beta/pilot", "-beta", 42, ["beta_pilot"],
                      {"tag": "beta_pilot"}, "beta\rpilot"):
            with self.subTest(value=value):
                out = submit_inquiry(self._payload(cohort=value), self.store)
                self.assertFalse(out["ok"], value)
                self.assertEqual(out["field"], "cohort", value)
        # 잘못된 태그는 접수 자체를 만들지 않는다.
        self.assertEqual(self.store.count_inquiries(), 0)

    def test_missing_required_field_wins_over_bad_tag(self):
        out = submit_inquiry({"contact": "no", "topic": "other", "cohort": "beta pilot"}, self.store)
        self.assertFalse(out["ok"])
        self.assertEqual(out["field"], "contact")


class CohortStorageTest(unittest.TestCase):
    def test_journal_line_carries_tag(self):
        directory = tempfile.mkdtemp(prefix="clns-cohort-")
        store = Store(os.path.join(directory, "app.sqlite"))
        self.addCleanup(store.close)
        store.record_inquiry(CONTACT, "api_mcp", MESSAGE, cohort="beta_pilot")
        path = os.path.join(directory, "inquiries.jsonl")
        with open(path, encoding="utf-8") as handle:
            line = json.loads(handle.readline())
        self.assertEqual(line["cohort"], "beta_pilot")
        self.assertEqual(line["topic"], "api_mcp")

    def test_seed_restores_tag_from_journal(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        written = store.seed_inquiries([{
            "contact": CONTACT, "topic": "other", "message": MESSAGE,
            "received_at": "2026-11-21T10:00:00", "fingerprint": "fp-cohort-1",
            "cohort": "citechart",
        }])
        self.assertEqual(written, 1)
        row = store.conn.execute("SELECT cohort FROM inquiries").fetchone()
        self.assertEqual(row["cohort"], "citechart")

    def test_existing_db_without_column_is_migrated(self):
        directory = tempfile.mkdtemp(prefix="clns-legacy-")
        path = os.path.join(directory, "app.sqlite")
        conn = sqlite3.connect(path)
        conn.executescript(OLD_SCHEMA)
        conn.commit()
        conn.close()
        store = Store(path)
        self.addCleanup(store.close)
        columns = {row["name"] for row in store.conn.execute("PRAGMA table_info(inquiries)")}
        self.assertIn("cohort", columns)
        record = store.record_inquiry(CONTACT, "other", "", cohort="beta_pilot")
        self.assertGreater(record["id"], 0)
        row = store.conn.execute("SELECT cohort FROM inquiries WHERE id=?", (record["id"],)).fetchone()
        self.assertEqual(row["cohort"], "beta_pilot")

    def test_admin_summary_counts_by_cohort(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.record_inquiry(CONTACT, "clns_pro_batch", "", cohort="beta_pilot")
        store.record_inquiry(PHONE, "api_mcp", "", cohort="beta_pilot")
        store.record_inquiry("카톡 clns_test", "other", "", cohort="citechart")
        store.record_inquiry(OTHER_CONTACT, "other", "")
        summary = usage.inquiry_summary(store)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_cohort"]["beta_pilot"], 2)
        self.assertEqual(summary["by_cohort"]["citechart"], 1)
        self.assertEqual(summary["by_cohort"]["(태그 없음)"], 1)
        dumped = json.dumps(summary, ensure_ascii=False)
        for sentinel in (CONTACT, OTHER_CONTACT, "카톡 clns_test"):
            self.assertNotIn(sentinel, dumped)


class CohortAlertTest(unittest.TestCase):
    def test_webhook_payload_and_log_carry_tag(self):
        import io

        record = {"id": 7, "received_at": "2026-11-21T10:00:00", "journal": "ok",
                  "cohort": "beta_pilot"}
        stream = io.StringIO()
        sent = {}

        def sender(url, body, timeout):
            sent["payload"] = json.loads(body.decode("utf-8"))
            return 200

        result = inquiry_alert.alert(record, "clns_pro_batch", CONTACT, MESSAGE,
                                     cohort="beta_pilot", webhook_url="https://hook.example.test/x",
                                     sender=sender, stream=stream)
        self.assertEqual(result["webhook"]["state"], "sent")
        self.assertEqual(sent["payload"]["cohort"], "beta_pilot")
        self.assertIn("cohort=beta_pilot", stream.getvalue())

    def test_webhook_payload_hides_contact_when_excluded(self):
        record = {"id": 7, "received_at": "2026-11-21T10:00:00", "journal": "ok",
                  "cohort": "citechart"}
        payload = inquiry_alert.webhook_payload(record, "other", CONTACT, MESSAGE,
                                               include_contact=False)
        self.assertEqual(payload["cohort"], "citechart")
        self.assertNotIn("contact", payload)
        self.assertNotIn("message", payload)

    def test_payload_omits_tag_when_empty(self):
        record = {"id": 8, "received_at": "2026-11-21T10:00:00", "journal": "ok"}
        payload = inquiry_alert.webhook_payload(record, "other", CONTACT, "")
        self.assertNotIn("cohort", payload)


class CohortHttpTest(unittest.TestCase):
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

    def _post(self, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/inquiry",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}")

    def test_post_with_source_alias(self):
        status, body = self._post({"contact": CONTACT, "topic": "api_mcp",
                                   "message": MESSAGE, "source": "citechart"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["cohort"], "citechart")
        self.assertNotIn(CONTACT, json.dumps(body, ensure_ascii=False))

    def test_post_without_tag_is_unchanged(self):
        status, body = self._post({"contact": "no-tag" + "@" + "example.test", "topic": "other"})
        self.assertEqual(status, 200)
        self.assertEqual(body["cohort"], "")
        self.assertEqual(set(body) >= {"ok", "id", "received_at", "topic", "delivery"}, True)

    def test_bad_tag_is_400_with_field(self):
        status, body = self._post({"contact": CONTACT, "topic": "other", "cohort": "beta pilot"})
        self.assertEqual(status, 400)
        self.assertEqual(body["field"], "cohort")


class CohortDocsTest(unittest.TestCase):
    def setUp(self):
        from import_compliance import web_ui

        self.page = web_ui.render_page()

    def test_api_table_mentions_tag(self):
        self.assertIn("cohort", self.page)
        self.assertIn("beta_pilot", self.page)

    def test_web_form_forwards_query_param_tag(self):
        self.assertIn("function cohortTag(", self.page)
        self.assertIn("cohort: cohortTag()", self.page)
        self.assertIn('get("cohort")', self.page)
        self.assertIn("[a-z0-9][a-z0-9._:-]{0,39}", self.page)

    def test_inquiry_form_still_does_not_ask_for_identity(self):
        self.assertNotRegex(self.page, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertRegex(self.page, r'id="inquiry-form"')


if __name__ == "__main__":
    unittest.main(verbosity=2)
