"""0.5.3 회귀 테스트 — 외부 코드ㆍ라이브 검수 제보 5건과 그 수정을 고정한다.

1. [높음] 광고 문구 검수 조사('을/를/이/가') 누락 — `AD-01` 등이 조사에서 끊겼다.
2. [높음] 광고 축과 수입 절차 축 판정이 합산돼 준수 문구도 `check_likely` 로 고정됐다.
3. [P1] `X-Tier` 헤더 신뢰로 무료 250회 한도 우회 + HTTP 요청 제한 부재.
4. [P1] `get_legal_basis` 가 `exact_match: false` 인데도 다른 법령의 조문을 인용했다.
5. [P1] `/v1/inquiry` 유실 대비(저널ㆍ알림ㆍ관리자 요약) 부재.

실행: PYTHONPATH=src python3 -m unittest discover -s src/tests -q
"""
from __future__ import annotations

import io
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
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import advertising, inquiry_alert, usage  # noqa: E402
from import_compliance.api import call_tool, submit_inquiry  # noqa: E402
from import_compliance.live_api import LiveApiClient  # noqa: E402
from import_compliance.ratelimit import SlidingWindowLimiter, client_key  # noqa: E402
from import_compliance.server import _api_key_tier, make_handler  # noqa: E402
from import_compliance.store import FREE_MONTHLY_CALLS, QuotaExceeded, Store  # noqa: E402

SENTINEL_CONTACT = "buyer-sentinel@example.test"
SENTINEL_MESSAGE = "ZZ-센티넬메모-9988"
FAKE_OC = "testoc"

LAW_SEARCH_ONLY_RULE = json.dumps({
    "LawSearch": {
        "totalCnt": 1,
        "law": [{
            "법령일련번호": "288525",
            "법령상세링크": "/DRF/lawService.do?OC=%s&target=law&MST=288525" % FAKE_OC,
            "법령명한글": "관세법 시행규칙", "법령구분명": "재정경제부령", "소관부처명": "재정경제부",
            "공포일자": "20260731", "시행일자": "20260731", "현행연혁코드": "현행",
            "법령ID": "006392",
        }],
    }
}, ensure_ascii=False)

LAW_SEARCH_EXACT = json.dumps({
    "LawSearch": {
        "totalCnt": 2,
        "law": [
            {"법령일련번호": "288525",
             "법령상세링크": "/DRF/lawService.do?OC=%s&target=law&MST=288525" % FAKE_OC,
             "법령명한글": "관세법 시행규칙", "법령구분명": "재정경제부령", "소관부처명": "재정경제부",
             "공포일자": "20260731", "시행일자": "20260731", "현행연혁코드": "현행", "법령ID": "006392"},
            {"법령일련번호": "290673",
             "법령상세링크": "/DRF/lawService.do?OC=%s&target=law&MST=290673" % FAKE_OC,
             "법령명한글": "관세법", "법령구분명": "법률", "소관부처명": "재정경제부",
             "공포일자": "20260324", "시행일자": "20261002", "현행연혁코드": "현행", "법령ID": "001556"},
        ],
    }
}, ensure_ascii=False)

LAW_BODY = json.dumps({
    "법령": {
        "기본정보": {"법령명_한글": "관세법"},
        "조문": {"조문단위": [{
            "조문번호": "226", "조문여부": "조문", "조문시행일자": "20261002",
            "조문제목": "허가ㆍ승인 등의 증명 및 확인",
            "조문내용": "제226조(허가ㆍ승인 등의 증명 및 확인)",
            "항": [{"항번호": "①",
                    "항내용": "① 수출입을 할 때 법령에서 정하는 바에 따라 허가ㆍ승인ㆍ표시 또는 "
                             "그 밖의 조건을 갖출 필요가 있는 물품은 세관장에게 그 허가ㆍ승인ㆍ표시 "
                             "또는 그 밖의 조건을 갖춘 것임을 증명하여야 한다."}],
        }]},
    }
}, ensure_ascii=False)


def fake_transport(routes):
    """경로 조각 → (status, body) 매핑으로 응답하는 가짜 transport(네트워크 없음)."""
    calls = []

    def transport(url, timeout):
        calls.append(url)
        for needle, (status, body) in routes.items():
            if needle in url:
                return status, body, "application/json"
        raise AssertionError(f"unexpected url: {url}")

    transport.calls = calls  # type: ignore[attr-defined]
    return transport


# ---------------------------------------------------------------------------
# 1. 조사 허용
# ---------------------------------------------------------------------------
class AdParticleTest(unittest.TestCase):
    """조사가 끼어도 어간-서술어를 이어서 대조해야 한다."""

    def test_reported_live_phrases_are_detected(self):
        # 외부 라이브 테스트에서 미탐지된 4문장
        for phrase in ("치매를 예방합니다", "당뇨를 개선해 줍니다",
                       "혈압을 낮춰 줍니다", "탈모를 방지합니다"):
            with self.subTest(phrase=phrase):
                result = advertising.review(phrase, "general_food")
                ids = [finding["rule_id"] for finding in result["findings"]]
                self.assertIn("AD-01", ids, phrase)
                self.assertEqual(result["verdict"], "check_likely")

    def test_other_particles_and_disease_claims(self):
        for phrase in ("암을 예방합니다", "혈당을 낮춰 줍니다", "질병의 예방에 좋습니다",
                       "기억력을 개선합니다", "관절염 통증을 완화합니다",
                       "숙변을 제거합니다", "면역력을 강화합니다"):
            with self.subTest(phrase=phrase):
                result = advertising.review(phrase, "general_food")
                self.assertTrue(result["findings"], phrase)

    def test_cosmetics_functional_particles(self):
        for phrase in ("주름을 개선합니다", "피부 장벽을 강화합니다",
                       "각질을 제거합니다", "자외선을 차단합니다"):
            with self.subTest(phrase=phrase):
                result = advertising.review(phrase, "cosmetics")
                ids = [finding["rule_id"] for finding in result["findings"]]
                self.assertIn("AD-09", ids, phrase)

    def test_plain_form_still_matches(self):
        result = advertising.review("치매 예방", "general_food")
        self.assertIn("AD-01", [finding["rule_id"] for finding in result["findings"]])

    def test_medicine_disclaimer_is_not_flagged(self):
        # 조사 허용이 고지문('질병의 예방 및 치료를 위한 의약품이 아닙니다')을 오탐하지 않는다.
        for phrase in ("이 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다",
                       "이 제품은 질병의 예방 및 치료를 위한 의약품이 아님"):
            with self.subTest(phrase=phrase):
                result = advertising.review(phrase, "health_functional_food")
                self.assertEqual(result["findings"], [])


# ---------------------------------------------------------------------------
# 2. 광고 축 / 수입 절차 축 분리
# ---------------------------------------------------------------------------
class AxisSeparationTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _call(self, payload):
        out = call_tool("check_ad_labeling", payload, self.store, client_id="axis-test")
        self.assertTrue(out["ok"], out)
        return out["result"]

    def test_compliant_copy_is_not_blocked_by_import_axis(self):
        result = self._call({
            "product_name": "비타민C",
            "product_type": "health_functional_food",
            "ad_copy": "비타민C는 항산화 작용을 합니다. 하루 한 알로 영양 보충.",
        })
        self.assertEqual(result["ad_review"]["verdict"], "low_risk")
        self.assertEqual(result["verdict"]["code"], "low_risk")
        self.assertIn("ad_copy", result["verdict"]["combined_axes"])
        self.assertNotIn("import_procedure", result["verdict"]["combined_axes"])
        # 절차 축은 사라지지 않고 따로 남는다
        self.assertEqual(result["import_procedure"]["state"], "run")
        self.assertIn(result["import_procedure"]["verdict"],
                      ("check_likely", "info_needed", "low_risk"))
        self.assertIn("scope_ko", result["verdict"])
        for finding in result["findings"]:
            self.assertIn(finding["axis"], ("ad_copy", "ecommerce", "labeling", "import_procedure"))

    def test_import_axis_findings_are_separated_and_labelled(self):
        result = self._call({"product_name": "홍삼 스틱", "product_type": "health_functional_food",
                             "ad_copy": "홍삼 스틱, 하루 한 포로 간편하게."})
        block_cases = {row["case_id"] for row in result["import_procedure"]["findings"]}
        import_findings = [f for f in result["findings"] if f["axis"] == "import_procedure"]
        self.assertEqual({f["case_id"] for f in import_findings}, block_cases)
        if import_findings:
            self.assertTrue(any(line.startswith("수입 절차 축")
                                for line in result["answer"]["guidance"]))

    def test_high_risk_copy_still_blocks(self):
        result = self._call({"product_type": "general_food", "ad_copy": "항암 효과가 있는 차"})
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertEqual(result["import_procedure"]["state"], "not_run")

    def test_without_product_name_import_axis_is_not_run(self):
        result = self._call({"product_type": "cosmetics", "ad_copy": "미백 크림"})
        self.assertEqual(result["import_procedure"]["state"], "not_run")
        self.assertIsNone(result["import_procedure"]["verdict"])
        self.assertEqual(result["import_procedure"]["findings"], [])
        # 수입 절차 축을 돌리지 않으면 빈 판정을 꾸며내지 않고 코퍼스 근거만 남긴다.
        self.assertEqual(result["assessment_id"], "")
        self.assertEqual(result["data_provenance"]["sources"][0]["state"], "corpus_only")
        self.assertEqual(result["verdict"]["code"], "check_likely")

    def test_label_axis_only_uses_labeling_verdict(self):
        result = self._call({"product_type": "cosmetics", "label_text": "명칭 크림 / 용량 50mL"})
        self.assertEqual(result["verdict"]["combined_axes"], ["labeling"])
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertNotIn("label_text", result["missing_information"])

    def test_axes_block_lists_each_axis(self):
        result = self._call({"product_name": "수입 크림", "product_type": "cosmetics",
                             "ad_copy": "주름 개선 크림", "label_text": "명칭 크림"})
        axes = result["axes"]
        self.assertIsNotNone(axes["ad_copy"])
        self.assertIsNotNone(axes["labeling"])
        self.assertEqual(axes["import_procedure"]["state"], "run")
        self.assertEqual(axes["combined"]["verdict"], result["verdict"]["code"])
        self.assertEqual(axes["combined"]["included_axes"], result["verdict"]["combined_axes"])

    def test_import_axis_verdict_never_overrides_ad_axis(self):
        # 품목명이 절차 트랩을 강하게 끌어도 광고 판정은 광고 축만 본다.
        result = self._call({"product_name": "수입 유아용 젖병",
                             "product_type": "health_functional_food",
                             "ad_copy": "비타민C는 항산화 작용을 합니다."})
        self.assertEqual(result["verdict"]["code"], "low_risk")
        if result["import_procedure"]["verdict"] in ("check_likely", "info_needed"):
            self.assertIn("수입 절차 축은 별도로", result["assessment_status_note_ko"])


# ---------------------------------------------------------------------------
# 3-1. 티어 위조 차단
# ---------------------------------------------------------------------------
class TierHeaderSecurityTest(unittest.TestCase):
    def test_tier_header_alone_is_ignored(self):
        self.assertEqual(_api_key_tier({"X-Tier": "pro_waitlist"}, env={}), "free")
        self.assertEqual(_api_key_tier({"X-Tier": "pro_waitlist"}, env={"CLNS_PRO_API_KEYS": ""}), "free")

    def test_tier_is_accepted_only_with_server_issued_key(self):
        env = {"CLNS_PRO_API_KEYS": "key-one,key-two"}
        self.assertEqual(_api_key_tier({"X-Tier": "pro_waitlist", "X-Api-Key": "key-two"}, env),
                         "pro_waitlist")
        self.assertEqual(_api_key_tier({"X-Tier": "pro_waitlist", "Authorization": "Bearer key-one"}, env),
                         "pro_waitlist")
        self.assertEqual(_api_key_tier({"X-Tier": "pro_waitlist", "X-Api-Key": "wrong"}, env), "free")
        self.assertEqual(_api_key_tier({"X-Tier": "pro_waitlist"}, env), "free")

    def test_unknown_tier_value_falls_back_to_free(self):
        env = {"CLNS_PRO_API_KEYS": "key-one"}
        self.assertEqual(_api_key_tier({"X-Tier": "enterprise", "X-Api-Key": "key-one"}, env), "free")

    def test_non_free_tier_does_not_lift_quota(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.consume_quota("c-tier", tier="free", limit=1)
        with self.assertRaises(QuotaExceeded):
            store.consume_quota("c-tier", tier="pro_waitlist", limit=1)

    def test_http_tier_header_cannot_bypass_quota(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        client = "web-spoof-01"
        for _ in range(FREE_MONTHLY_CALLS):
            store.consume_quota(client)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/tools/assess_import_case",
            data=json.dumps({"query": "중국산 완구 수입 판매"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Client-Id": client,
                     "X-Tier": "pro_waitlist", "X-Api-Key": "made-up"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "quota_exceeded")


# ---------------------------------------------------------------------------
# 3-2. HTTP 요청 제한
# ---------------------------------------------------------------------------
class RateLimitTest(unittest.TestCase):
    def test_limiter_counts_and_recovers(self):
        now = [1000.0]
        limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
        self.assertTrue(limiter.check("k")["allowed"])
        self.assertTrue(limiter.check("k")["allowed"])
        blocked = limiter.check("k")
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["remaining"], 0)
        self.assertEqual(blocked["retry_after"], 60)
        now[0] += 61
        self.assertTrue(limiter.check("k")["allowed"])

    def test_key_is_a_short_hash_not_the_address(self):
        key = client_key(b"salt", "203.0.113.77")
        self.assertEqual(len(key), 16)
        self.assertNotIn("203.0.113.77", key)
        self.assertNotEqual(key, client_key(b"other-salt", "203.0.113.77"))

    def test_http_returns_429_and_flags_it(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                    make_handler(store, rate_limit=2, tool_rate_limit=1))
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)

        def get(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
                    return response.status, response.headers, json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as error:
                return error.code, error.headers, json.loads(error.read() or b"{}")

        self.assertEqual(get("/healthz")[0], 200)
        self.assertEqual(get("/healthz")[0], 200)
        status, headers, body = get("/healthz")
        self.assertEqual(status, 429)
        self.assertEqual(body["error"], "rate_limited")
        self.assertGreaterEqual(int(headers.get("Retry-After")), 1)
        self.assertNotIn("127.0.0.1", json.dumps(body, ensure_ascii=False))
        flags = usage.stats_payload(store, days=1)["totals"]["flags"]
        self.assertGreaterEqual(flags.get(usage.FLAG_RATE_LIMITED, 0), 1)

    def test_rate_limit_keys_are_not_stored(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, rate_limit=5))
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        for _ in range(3):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5):
                pass
        dump = "\n".join(str(dict(row)) for row in
                         store.conn.execute("SELECT day, kind, key, count FROM usage_daily"))
        self.assertNotIn("127.0.0.1", dump)
        self.assertNotIn("203.0.113", dump)


# ---------------------------------------------------------------------------
# 4. 법령명 정확 일치
# ---------------------------------------------------------------------------
class LegalBasisExactMatchTest(unittest.TestCase):
    def _store(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        return store

    def _client(self, search_json):
        return LiveApiClient(law_oc=FAKE_OC, transport=fake_transport({
            "lawSearch.do": (200, search_json),
            "lawService.do": (200, LAW_BODY),
        }))

    def test_mismatch_does_not_quote_another_law_article(self):
        store = self._store()
        out = call_tool("get_legal_basis", {"law": "관세법", "article": "226"},
                        store, live=self._client(LAW_SEARCH_ONLY_RULE))
        result = out["result"]
        block = result["law_live"]
        self.assertEqual(block["state"], "name_mismatch")
        self.assertEqual(block["confirmed"], [])
        self.assertEqual(len(block["name_mismatch"]), 1)
        candidate = block["name_mismatch"][0]
        self.assertFalse(candidate["exact_match"])
        self.assertEqual(candidate["law_name"], "관세법 시행규칙")
        self.assertEqual(candidate["requested_law"], "관세법")
        # 조문 본문ㆍ인용은 비어 있어야 한다(다른 법령의 조문을 근거처럼 쓰지 않는다).
        self.assertEqual(block["article_text"]["text"], "")
        self.assertEqual(block["article_text"]["paragraphs"], [])
        self.assertEqual(block["article_text"]["state"], "law_name_mismatch")
        self.assertNotIn("세관장에게", json.dumps(block, ensure_ascii=False))
        self.assertIn("정확히 일치하는 법령이 없어", result["law_name_mismatch_ko"])

    def test_exact_match_still_returns_article_body(self):
        store = self._store()
        out = call_tool("get_legal_basis", {"law": "관세법", "article": "226"},
                        store, live=self._client(LAW_SEARCH_EXACT))
        block = out["result"]["law_live"]
        self.assertEqual(block["state"], "live")
        self.assertTrue(block["confirmed"][0]["exact_match"])
        self.assertEqual(block["confirmed"][0]["law_name"], "관세법")
        self.assertIn("세관장에게", block["article_text"]["paragraphs"][0])
        self.assertNotIn("name_mismatch", block)


# ---------------------------------------------------------------------------
# 5. 문의 접수 유실 대비
# ---------------------------------------------------------------------------
class InquiryDurabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_path = os.path.join(self.tmpdir.name, "app.sqlite")
        self.journal = os.path.join(self.tmpdir.name, "inquiries.jsonl")

    def test_record_writes_private_journal(self):
        store = Store(self.db_path)
        self.addCleanup(store.close)
        record = store.record_inquiry(SENTINEL_CONTACT, "clns_pro_batch", "1,200건 문의")
        self.assertEqual(record["journal"], "ok")
        self.assertTrue(os.path.exists(self.journal))
        self.assertEqual(os.stat(self.journal).st_mode & 0o777, 0o600)
        rows = store.read_inquiry_journal()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contact"], SENTINEL_CONTACT)
        self.assertEqual(rows[0]["fingerprint"], record["fingerprint"])

    def test_memory_store_has_no_journal_file(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        record = store.record_inquiry("02-111-2222", "other", "")
        self.assertEqual(record["journal"], "off")
        self.assertEqual(store.inquiry_journal, "")

    def test_seed_restores_after_redeploy_and_is_idempotent(self):
        store = Store(self.db_path)
        store.record_inquiry(SENTINEL_CONTACT, "api_mcp", "연동 문의")
        store.close()
        # 재배포로 작업 DB 가 비었다고 가정: 같은 폴더의 새 DB 로 복원
        fresh = Store(os.path.join(self.tmpdir.name, "app-after-redeploy.sqlite"))
        self.addCleanup(fresh.close)
        rows = fresh.read_inquiry_journal()
        self.assertEqual(fresh.seed_inquiries(rows), 1)
        self.assertEqual(fresh.seed_inquiries(rows), 0)
        self.assertEqual(fresh.count_inquiries(), 1)
        row = fresh.conn.execute("SELECT contact FROM inquiries").fetchone()
        self.assertEqual(row["contact"], SENTINEL_CONTACT)

    def test_submit_inquiry_reports_delivery_without_echoing_contact(self):
        store = Store(self.db_path)
        self.addCleanup(store.close)
        captured = {}

        def alerter(**kwargs):
            captured.update(kwargs)
            return {"journal": "ok", "webhook": {"state": "sent"}}

        out = submit_inquiry({"contact": SENTINEL_CONTACT, "topic": "api_mcp",
                              "message": "문의"}, store, alerter=alerter)
        self.assertTrue(out["ok"])
        self.assertEqual(out["delivery"], {"journal": "ok", "webhook": "sent"})
        self.assertEqual(captured["contact"], SENTINEL_CONTACT)
        self.assertNotIn(SENTINEL_CONTACT, json.dumps(out, ensure_ascii=False))
        self.assertNotIn("contact", out)

    def test_alert_masks_contact_and_tolerates_webhook_failure(self):
        record = {"id": 7, "received_at": "2026-11-21T10:00:00+09:00", "journal": "ok"}
        body = {}

        def failing_sender(url, payload, timeout):
            body.update(json.loads(payload.decode("utf-8")))
            raise OSError("network down")

        stream = io.StringIO()
        with mock.patch.dict(os.environ, {"CLNS_INQUIRY_WEBHOOK_URL": "https://example.test/hook"},
                             clear=False):
            result = inquiry_alert.alert(record, "other", SENTINEL_CONTACT, "메모",
                                         sender=failing_sender, stream=stream)
        self.assertEqual(result["webhook"]["state"], "failed")
        self.assertEqual(result["journal"], "ok")
        self.assertEqual(body["contact"], SENTINEL_CONTACT)  # 기본은 회신용 연락처 포함
        logged = stream.getvalue()
        self.assertNotIn(SENTINEL_CONTACT, logged)
        self.assertIn("bu***", logged)

    def test_alert_can_exclude_contact_from_webhook(self):
        record = {"id": 8, "received_at": "2026-11-21T10:00:00+09:00", "journal": "ok"}
        body = {}

        def sender(url, payload, timeout):
            body.update(json.loads(payload.decode("utf-8")))
            return 204

        with mock.patch.dict(os.environ, {
                "CLNS_INQUIRY_WEBHOOK_URL": "https://example.test/hook",
                "CLNS_INQUIRY_WEBHOOK_EXCLUDE_CONTACT": "1"}, clear=False):
            result = inquiry_alert.alert(record, "other", SENTINEL_CONTACT, "메모",
                                         sender=sender, stream=io.StringIO())
        self.assertEqual(result["webhook"]["state"], "sent")
        self.assertNotIn("contact", body)
        self.assertIn("contact_masked", body)

    def test_webhook_is_skipped_without_url_or_bad_scheme(self):
        self.assertEqual(inquiry_alert.post_webhook("", {})["state"], "skipped")
        self.assertEqual(inquiry_alert.post_webhook("ftp://example.test/hook", {})["state"], "skipped")

    def test_mask_contact(self):
        self.assertEqual(inquiry_alert.mask_contact("buyer@example.test"), "bu***@example.test")
        self.assertEqual(inquiry_alert.mask_contact("02-123-4567"), "***-4567")
        self.assertEqual(inquiry_alert.mask_contact("짧음"), "***")

    def test_inquiry_summary_counts_without_personal_data(self):
        store = Store(self.db_path)
        self.addCleanup(store.close)
        store.record_inquiry(SENTINEL_CONTACT, "clns_pro_batch", SENTINEL_MESSAGE)
        store.record_inquiry("02-2222-3333", "api_mcp", "")
        summary = usage.inquiry_summary(store, days=7)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_topic"]["clns_pro_batch"], 1)
        self.assertEqual(summary["by_topic"]["api_mcp"], 1)
        blob = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn(SENTINEL_CONTACT, blob)
        self.assertNotIn("02-2222-3333", blob)
        self.assertNotIn(SENTINEL_MESSAGE, blob)

    def test_admin_summary_endpoint_requires_token(self):
        store = Store(self.db_path)
        self.addCleanup(store.close)
        store.record_inquiry(SENTINEL_CONTACT, "other", "")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)

        def get(headers=None):
            request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/inquiry/summary?days=7",
                                             headers=headers or {}, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status, json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read() or b"{}")

        with mock.patch.dict(os.environ, {"CLNS_ADMIN_TOKEN": ""}, clear=False):
            self.assertEqual(get()[0], 404)
        with mock.patch.dict(os.environ, {"CLNS_ADMIN_TOKEN": "admin-token"}, clear=False):
            self.assertEqual(get()[0], 401)
            self.assertEqual(get({"X-Admin-Token": "wrong"})[0], 401)
            status, payload = get({"X-Admin-Token": "admin-token"})
            self.assertEqual(status, 200)
            self.assertEqual(payload["total"], 1)
            self.assertNotIn(SENTINEL_CONTACT, json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
