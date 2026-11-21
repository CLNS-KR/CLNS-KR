"""0.2.0 식약처 행정처분(15124560·15124559) 연동·폴백 테스트.

검증 대상
---------
1. 데이터셋 식별자·엔드포인트가 실제 공공데이터포털 값과 맞는지
2. 원본의 개인정보(업소명·연락처·주소·인허가번호)를 **읽지도 저장하지도 않는지**
3. 실시간 조회 → 로컬 캐시 → 내장 대표 적발 패턴 순으로 폴백하는지
4. 승인 전파 전(코드 30)·키 없음·오프라인에서도 같은 형태의 응답이 나오는지
5. MCP/HTTP 등록과 스키마(disposition_items) 정합성

실행: python3 tests/test_mfds_disposition.py   (네트워크 불필요 · 가짜 transport 사용)
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
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import mfds_dispositions  # noqa: E402
from import_compliance.api import call_tool  # noqa: E402
from import_compliance.live_api import (  # noqa: E402
    MFDS_DISPOSITION_ENDPOINTS,
    SOURCE_DISPOSITION_MFG,
    SOURCE_DISPOSITION_SALES,
    LiveApiClient,
)
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402

FAKE_KEY = "FAKE_SERVICE_KEY_f0r_t3st"

LIVE_JSON = {
    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
    "body": {"pageNo": 1, "totalCount": 1, "numOfRows": 1, "items": [{
        "PRCSCITYPOINT_BSSHNM": "가상식품",
        "INDUTY_CD_NM": "식품제조가공업",
        "LCNS_NO": "20100380419",
        "DSPS_DCSNDT": "20241112",
        "DSPS_BGNDT": "20241112",
        "DSPS_ENDDT": "-",
        "DSPS_TYPECD_NM": "영업정지",
        "VILTCN": "(20241017)표시기준 위반, 연락처 " "010-" "1234-" "5678",
        "ADDR": "부산광역시 동구",
        "TELNO": "051-123-4567",
        "PRSDNT_NM": "홍길동",
        "DSPSCN": "영업정지 15일",
        "LAWORD_CD_NM": "식품 등의 표시·광고에 관한 법률 제4조(표시의 기준) 3항",
        "PUBLIC_DT": "20261111",
        "LAST_UPDT_DTM": "2024-11-20 19:41:21",
        "DSPSDTLS_SEQ": "4639639",
        "DSPS_INSTTCD_NM": "부산광역시 동구",
    }]},
}

ERROR_30 = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
    "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "returnAuthMsg": "등록되지 않은 서비스키",
    "returnReasonCode": "30",
}}}


def fake_transport(url: str, timeout: float):
    if "AdmmRsltFoodMnftPrcsService01" in url:
        return 200, json.dumps(LIVE_JSON, ensure_ascii=False), "application/json"
    return 403, json.dumps(ERROR_30), "application/json"


class DatasetTest(unittest.TestCase):
    def test_dataset_ids_and_endpoints(self):
        self.assertEqual(mfds_dispositions.DATASETS["manufacturing"]["dataset_id"], "15124560")
        self.assertEqual(mfds_dispositions.DATASETS["sales"]["dataset_id"], "15124559")
        self.assertIn("/AdmmRsltFoodMnftPrcsService01/getAdmmRsltFoodMnftPrcsBssh01",
                      MFDS_DISPOSITION_ENDPOINTS["manufacturing"])
        self.assertIn("/AdmmRsltFoodSaleService01/getAdmmRsltFoodSaleBssh01",
                      MFDS_DISPOSITION_ENDPOINTS["sales"])
        self.assertEqual(mfds_dispositions.DATASETS["manufacturing"]["source_id"], SOURCE_DISPOSITION_MFG)
        self.assertEqual(mfds_dispositions.DATASETS["sales"]["source_id"], SOURCE_DISPOSITION_SALES)

    def test_builtin_patterns_are_aggregates_not_individuals(self):
        rows = mfds_dispositions.BUILTIN_PATTERNS
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            self.assertIn("law_reference", row)
            self.assertIn("check_ko", row)
            self.assertNotIn("업소명", json.dumps(row, ensure_ascii=False))
        manufacturing = [r for r in rows if r["industry"] == "manufacturing"
                         and r.get("observed_2026_11_19")]
        self.assertEqual(sum(r["observed_2026_11_19"] for r in manufacturing if r["pattern_id"] == "PD-01"), 94)


class NormalizeTest(unittest.TestCase):
    def test_private_fields_are_dropped(self):
        row = mfds_dispositions.normalize_item(LIVE_JSON["body"]["items"][0], "manufacturing")
        self.assertIsNotNone(row)
        for key in ("business_name", "representative", "phone", "address", "license_no"):
            self.assertNotIn(key, row)
        raw = json.dumps(row, ensure_ascii=False)
        for secret in ("가상식품", "홍길동", "051-123-4567", "20100380419"):
            self.assertNotIn(secret, raw)
        self.assertIn("[연락처]", row["violation_summary"])
        self.assertEqual(row["confirmed_on"], "2024-11-12")
        self.assertEqual(row["disposition_seq"], "4639639")

    def test_rows_without_seq_or_violation_are_skipped(self):
        self.assertIsNone(mfds_dispositions.normalize_item({"DSPSDTLS_SEQ": "", "VILTCN": "위반"}, "sales"))
        self.assertIsNone(mfds_dispositions.normalize_item({"DSPSDTLS_SEQ": "1", "VILTCN": ""}, "sales"))

    def test_long_numbers_masked_but_dates_kept(self):
        text = mfds_dispositions.sanitize_text("20241017 위반, 신고번호 1234567 접수")
        self.assertIn("20241017", text)
        self.assertIn("[번호]", text)


class LookupFallbackTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_offline_returns_patterns(self):
        block = mfds_dispositions.lookup(self.store, None, industry="manufacturing", keyword="표시")
        self.assertEqual(block["state"], "corpus_only")
        self.assertEqual(block["source"], "pattern_fallback")
        ids = [row["pattern_id"] for row in block["patterns"]]
        self.assertIn("PD-06", ids)
        self.assertIn("pii_policy_ko", block)

    def test_key_missing_state(self):
        live = LiveApiClient(service_key="", transport=fake_transport, sleep=lambda s: None)
        block = mfds_dispositions.lookup(self.store, live, industry="sales")
        self.assertEqual(block["datasets"][0]["state"], "key_missing")
        self.assertEqual(block["source"], "pattern_fallback")

    def test_code_30_becomes_approval_pending(self):
        live = LiveApiClient(service_key=FAKE_KEY, transport=fake_transport, sleep=lambda s: None,
                             max_attempts=1)
        block = mfds_dispositions.lookup(self.store, live, industry="sales")
        self.assertEqual(block["datasets"][0]["state"], "approval_pending")
        self.assertIn("승인", block["datasets"][0]["note_ko"])
        self.assertTrue(block["patterns"])

    def test_live_then_cache(self):
        live = LiveApiClient(service_key=FAKE_KEY, transport=fake_transport, sleep=lambda s: None)
        block = mfds_dispositions.lookup(self.store, live, industry="manufacturing", rows=20, limit=5)
        self.assertEqual(block["datasets"][0]["state"], "live")
        self.assertEqual(block["match_count"], 1)
        self.assertEqual(self.store.disposition_count("15124560"), 1)
        cached = mfds_dispositions.lookup(self.store, None, industry="manufacturing", keyword="표시")
        self.assertEqual(cached["source"], "local_cache")
        self.assertEqual(cached["matches"][0]["disposition_seq"], "4639639")

    def test_save_is_idempotent(self):
        row = mfds_dispositions.normalize_item(LIVE_JSON["body"]["items"][0], "manufacturing")
        self.assertEqual(self.store.save_dispositions([row]), 1)
        self.assertEqual(self.store.save_dispositions([row]), 0)
        self.assertEqual(self.store.disposition_count(), 1)

    def test_summary_counts_by_law(self):
        row = mfds_dispositions.normalize_item(LIVE_JSON["body"]["items"][0], "manufacturing")
        self.store.save_dispositions([row])
        summary = self.store.disposition_summary(["15124560"])
        self.assertEqual(summary[0]["count"], 1)
        self.assertTrue(summary[0]["law_reference"].startswith("식품 등의 표시"))


class DispositionToolTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_tool_registered_with_schema(self):
        from import_compliance.api import mcp_manifest, TOOL_DEFS
        self.assertIn("lookup_mfds_disposition", [t["name"] for t in TOOL_DEFS])
        entry = next(t for t in mcp_manifest()["tools"] if t["name"] == "lookup_mfds_disposition")
        self.assertEqual(sorted(entry["inputSchema"]["properties"]),
                         ["confirmed_on", "industry", "keyword", "license_no", "limit", "rows"])

    def test_offline_response_shape(self):
        out = call_tool("lookup_mfds_disposition", {"industry": "manufacturing"}, self.store)
        self.assertTrue(out["ok"])
        result = out["result"]
        for key in ("verdict", "answer", "findings", "evidence", "disposition_lookup",
                    "data_provenance", "disclaimer", "assessment_status"):
            self.assertIn(key, result)
        lookup = result["disposition_lookup"]
        for key in ("state", "source", "matches", "patterns", "datasets", "pii_policy_ko", "coverage_ko"):
            self.assertIn(key, lookup)
        self.assertEqual(result["verdict"]["code"], "info_needed")
        self.assertTrue(result["findings"])
        self.assertEqual(result["findings"][0]["case_id"], "MFDS-PATTERN")

    def test_live_match_raises_verdict(self):
        live = LiveApiClient(service_key=FAKE_KEY, transport=fake_transport, sleep=lambda s: None)
        out = call_tool("lookup_mfds_disposition", {"industry": "manufacturing"},
                        self.store, live=live)
        result = out["result"]
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertEqual(result["assessment_status"], "APPLICABLE")
        self.assertTrue(result["findings"][0]["case_id"].startswith("MFDS-"))
        blob = json.dumps(result, ensure_ascii=False)
        for secret in ("가상식품", "홍길동", "051-123-4567", "20100380419",
                       "010-" "1234-" "5678"):
            self.assertNotIn(secret, blob)
        self.assertIn("개인정보", blob)

    def test_invalid_arguments(self):
        self.assertEqual(call_tool("lookup_mfds_disposition", {"industry": "restaurant"},
                                   self.store)["error"], "invalid_argument")
        self.assertEqual(call_tool("lookup_mfds_disposition", {"confirmed_on": "2024-11"},
                                   self.store)["error"], "invalid_argument")

    def test_guidance_avoids_conclusive_phrasing(self):
        from import_compliance.policy import find_conclusive_phrasing
        out = call_tool("lookup_mfds_disposition", {"industry": "all"}, self.store)
        joined = out["result"]["answer"]["headline"] + " " + " ".join(out["result"]["answer"]["guidance"])
        self.assertEqual(find_conclusive_phrasing(joined), [], joined)

    def test_license_no_is_not_echoed(self):
        out = call_tool("lookup_mfds_disposition", {"industry": "manufacturing",
                                                    "license_no": "20100380419"}, self.store)
        self.assertNotIn("20100380419", json.dumps(out, ensure_ascii=False))


class SchemaTest(unittest.TestCase):
    def test_schema_sql_and_store_agree(self):
        with open(os.path.join(SRC, "schema.sql"), encoding="utf-8") as handle:
            ddl = handle.read()
        self.assertIn("CREATE TABLE disposition_items", ddl)
        for column in ("dataset_id", "disposition_seq", "violation_summary", "law_reference",
                       "confirmed_on", "loaded_at"):
            self.assertIn(column, ddl)
        self.assertNotIn("PRSDNT_NM", ddl)
        self.assertNotIn("TELNO", ddl)
        store = Store(":memory:")
        self.addCleanup(store.close)
        cols = {row["name"] for row in store.conn.execute("PRAGMA table_info(disposition_items)")}
        for column in ("dataset_id", "disposition_seq", "industry", "disposition_type",
                       "confirmed_on", "violation_summary", "law_reference", "agency", "loaded_at"):
            self.assertIn(column, cols)

    def test_live_client_capability(self):
        live = LiveApiClient(service_key=FAKE_KEY, transport=fake_transport, sleep=lambda s: None)
        self.assertTrue(live.capabilities()["mfds_disposition"])


class HttpRouteTest(unittest.TestCase):
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
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/tools/{name}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Client-Id": "disposition-http"},
            method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_new_tools_over_http(self):
        out = self._post("check_ad_labeling", {"product_type": "general_food",
                                               "ad_copy": "항암 효과가 있는 차"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["tool"], "check_ad_labeling")
        self.assertEqual(out["result"]["verdict"]["code"], "check_likely")

        out = self._post("lookup_mfds_disposition", {"industry": "all"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["tool"], "lookup_mfds_disposition")
        self.assertIn("disposition_lookup", out["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
