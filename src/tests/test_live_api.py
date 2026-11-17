"""실API 어댑터 회귀 테스트 — 네트워크 없이 고정 응답으로만 검증한다.

실행: python3 tests/test_live_api.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import live_api  # noqa: E402
from import_compliance.api import call_tool  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.live_api import (  # noqa: E402
    LiveApiClient,
    LiveApiError,
    load_env,
    normalize_customs_item,
    normalize_law_article,
    normalize_law_item,
    normalize_mfds_permit_item,
    normalize_mfds_product_item,
    register_sources,
    redact,
)
from import_compliance.store import SourceGateway, Store  # noqa: E402

FAKE_KEY = "testkey0123456789abcdef0123456789abcdef0123456789abcdef01234567"
FAKE_OC = "testoc"

CUSTOMS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<response><header><resultCode>00</resultCode><resultMsg>정상서비스.</resultMsg></header>
<body><items>
<item><aplyStrtDt>20200406</aplyStrtDt><bfhnAffcRtmTpcd>2</bfhnAffcRtmTpcd>
<dcerCfrmLworCd>01</dcerCfrmLworCd><dcerCfrmLworNm>약사법</dcerCfrmLworNm>
<hsSgn>3307903000</hsSgn><reqApreIttCd>243</reqApreIttCd>
<reqApreIttNm>한국의약품수출입협회</reqApreIttNm>
<reqCfrmIstmNm>표준통관예정보고서(의약품등)</reqCfrmIstmNm></item>
</items></body></response>"""

CUSTOMS_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>정상서비스.</resultMsg></header>
<body><items/></body></response>"""

UNREGISTERED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OpenAPI_ServiceResponse>
<cmmMsgHeader>
  <errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg>
  <returnAuthMsg>등록되지 않은 서비스키입니다.</returnAuthMsg>
  <returnReasonCode>30</returnReasonCode>
</cmmMsgHeader></OpenAPI_ServiceResponse>"""

MFDS_PERMIT_JSON = json.dumps({
    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
    "body": {"pageNo": 1, "totalCount": 2, "numOfRows": 2, "items": [
        {"RECEIPT_NO": "19980028027", "NOTICE_GOODS_NAME": "가공식품",
         "BSN_OFC_NAME": "(주)비스밀라인터프라이즈", "GOODS_KOR_NAME": "칠리파우다",
         "GOODS_ENG_NAME": "RED CHILLI POWDER", "ITEM_NAME": "고추가루",
         "MANUFAC_NAME": "M.MANZOOR & CO.", "MANUFAC_COUNTRY_NAME": "파키스탄",
         "XPORT_COUNTRY_NAME": "파키스탄", "ACCEPT_DATE": "19980725"},
    ]},
}, ensure_ascii=False)

MFDS_PRODUCT_JSON = json.dumps({
    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
    "body": {"pageNo": 1, "totalCount": 1, "numOfRows": 1, "items":
             {"DCLR_PRDT_DIVS_NM": "가공식품", "MNFT_NATN_CD": "CN", "MNFT_NATN_NM": "중국",
              "PRDT_NM": "SOYBEAN PEPTIDE POWDER", "PRDLST_CD": "C0315070300000000000",
              "PRDLST_NM": "두류가공품"}},
}, ensure_ascii=False)

MFDS_IMPROPER_JSON = json.dumps({
    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
    "body": {"pageNo": 1, "totalCount": 1, "numOfRows": 3, "items": [
        {"RECEIPT_NO": "202600367046", "INSTT_NAME": "서울청 김포검사소", "ACCEPT_DATE": "2026-06-04",
         "ITEM_NAME": "영양소,기능성복합제품", "NOTICE_GOODS_NAME": "건강기능식품",
         "GOODS_KOR_NAME": "초임계 rTG 오메가3", "GOODS_ENG_NAME": "RTG OMEGA-3",
         "MANUFAC_COUNTRY_NAME": "미국", "EXPORT_COUNTRY_NAME": "미국",
         "NOTICE_MANUFAC_NAME": "LIFEBLOOM CORP.",
         "FAIL_REASON_DETAIL": "EPA와 DHA의 합 부적합 [기준 : 표시량의 80~120%, 결과 : 58%]"},
    ]},
}, ensure_ascii=False)

LAW_SEARCH_JSON = json.dumps({
    "LawSearch": {
        "totalCnt": 2,
        "law": [
            {"법령일련번호": "288525", "법령상세링크": "/DRF/lawService.do?OC=%s&target=law&MST=288525" % FAKE_OC,
             "법령명한글": "관세법 시행규칙", "법령구분명": "재정경제부령", "소관부처명": "재정경제부",
             "공포일자": "20260731", "시행일자": "20260731", "현행연혁코드": "현행", "법령ID": "006392"},
            {"법령일련번호": "290673", "법령상세링크": "/DRF/lawService.do?OC=%s&target=law&MST=290673" % FAKE_OC,
             "법령명한글": "관세법", "법령구분명": "법률", "소관부처명": "재정경제부",
             "공포일자": "20260324", "시행일자": "20261002", "현행연혁코드": "현행", "법령ID": "001556"},
        ],
    }
}, ensure_ascii=False)

LAW_BODY_JSON = json.dumps({
    "법령": {
        "기본정보": {"법령명_한글": "관세법"},
        "조문": {"조문단위": [
            {"조문번호": "226", "조문여부": "전문", "조문시행일자": "20261002",
             "조문내용": "제9장 통관 <개정 2010.12.30>"},
            {"조문번호": "226", "조문여부": "조문", "조문시행일자": "20261002",
             "조문제목": "허가ㆍ승인 등의 증명 및 확인",
             "조문내용": "제226조(허가ㆍ승인 등의 증명 및 확인)",
             "항": [{"항번호": "①", "항내용": "① 수출입을 할 때 법령에서 정하는 바에 따라 허가ㆍ승인ㆍ표시 "
                                            "또는 그 밖의 조건을 갖출 필요가 있는 물품은 세관장에게 그 "
                                            "허가ㆍ승인ㆍ표시 또는 그 밖의 조건을 갖춘 것임을 증명하여야 한다."}]},
            {"조문번호": "227", "조문여부": "조문", "조문시행일자": "20261002",
             "조문제목": "의무 이행의 요구 및 조사",
             "조문내용": "제227조(의무 이행의 요구 및 조사)"},
        ]},
    }
}, ensure_ascii=False)


def fake_transport(routes):
    """경로 조각 → (status, body) 매핑으로 응답하는 가짜 transport."""
    calls = []

    def transport(url, timeout):
        calls.append(url)
        for needle, (status, body) in routes.items():
            if needle in url:
                return status, body, "application/json"
        raise AssertionError(f"unexpected url: {url}")

    transport.calls = calls  # type: ignore[attr-defined]
    return transport


class EnvTest(unittest.TestCase):
    def test_load_env_parses_file_and_env_override(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as handle:
            handle.write("# comment\nDATA_GO_KR_SERVICE_KEY=filevalue\nLAW_GO_KR_OC=testoc\n")
            path = handle.name
        self.addCleanup(os.unlink, path)
        self.assertEqual(load_env(path)["DATA_GO_KR_SERVICE_KEY"], "filevalue")
        os.environ["DATA_GO_KR_SERVICE_KEY"] = "envvalue"
        try:
            self.assertEqual(load_env(path)["DATA_GO_KR_SERVICE_KEY"], "envvalue")
        finally:
            del os.environ["DATA_GO_KR_SERVICE_KEY"]

    def test_missing_env_returns_none(self):
        self.assertIsNone(live_api.from_environment({}))

    def test_environment_only_keys_work_without_env_file(self):
        """컨테이너/PaaS에는 .env 파일이 없고 환경변수만 있다."""
        gone = os.path.join(tempfile.gettempdir(), "clns-no-such.env")
        if os.path.exists(gone):
            os.unlink(gone)
        os.environ["DATA_GO_KR_SERVICE_KEY"] = "envonlykey"
        os.environ["LAW_GO_KR_OC"] = "envonlyoc"
        try:
            values = load_env(gone)
            self.assertEqual(values.get("DATA_GO_KR_SERVICE_KEY"), "envonlykey")
            client = live_api.from_environment(values)
            self.assertIsNotNone(client)
            self.assertTrue(client.has_customs)
            self.assertTrue(client.has_law)
        finally:
            del os.environ["DATA_GO_KR_SERVICE_KEY"]
            del os.environ["LAW_GO_KR_OC"]

    def test_repr_and_redact_hide_key(self):
        client = LiveApiClient(service_key=FAKE_KEY, law_oc=FAKE_OC)
        self.assertNotIn(FAKE_KEY, repr(client))
        self.assertNotIn(FAKE_KEY, redact(f"url?serviceKey={FAKE_KEY}", FAKE_KEY))
        self.assertIn("REDACTED", redact(f"key={FAKE_KEY}", FAKE_KEY))

    def test_missing_key_raises_without_network(self):
        client = LiveApiClient(service_key="", law_oc="")
        with self.assertRaises(LiveApiError):
            client.customs_checkpoint("3307903000")


class ParsingTest(unittest.TestCase):
    def test_customs_normalization(self):
        client = LiveApiClient(service_key=FAKE_KEY,
                               transport=fake_transport({"retrieveCcctLworCd": (200, CUSTOMS_XML)}))
        fetch = client.customs_checkpoint("3307903000", "import")
        self.assertEqual(fetch.state, "live")
        self.assertEqual(fetch.result_code, "00")
        row = normalize_customs_item(fetch.items[0])
        self.assertEqual(row["hs_code"], "3307903000")
        self.assertEqual(row["requirement_law"], "약사법")
        self.assertEqual(row["requirement_agency"], "한국의약품수출입협회")
        self.assertEqual(row["applies_from"], "2020-04-06")
        self.assertEqual(row["timing"], "사후확인")
        # 외부 상태 블록에는 원본 payload 가 없다
        self.assertNotIn("items", fetch.status())

    def test_customs_empty_items_is_live_not_error(self):
        client = LiveApiClient(service_key=FAKE_KEY,
                               transport=fake_transport({"retrieveCcctLworCd": (200, CUSTOMS_EMPTY_XML)}))
        fetch = client.customs_checkpoint("3307903010", "import")
        self.assertEqual(fetch.state, "live")
        self.assertEqual(fetch.items, [])

    def test_mfds_single_and_list_items(self):
        client = LiveApiClient(service_key=FAKE_KEY, transport=fake_transport({
            "getImrtsCnfirmList05": (200, MFDS_PERMIT_JSON),
            "getIprtFoodPrdtDBInq02": (200, MFDS_PRODUCT_JSON),
        }))
        permit = client.mfds_import_permit(product_name="칠리", rows=3)
        self.assertEqual(permit.total_count, 2)
        self.assertEqual(normalize_mfds_permit_item(permit.items[0])["product_name_ko"], "칠리파우다")
        product = client.mfds_product_db(product_name="SOYBEAN", rows=1)
        self.assertEqual(len(product.items), 1)  # 객체 1건도 리스트로 정규화
        self.assertEqual(normalize_mfds_product_item(product.items[0])["item_name"], "두류가공품")
        # 요청 파라미터 이름 확인 (서비스별 대소문자가 다르다)
        permit_url = client._transport.calls[0]
        self.assertIn("goods_kor_name=", permit_url)
        product_url = client._transport.calls[1]
        self.assertIn("PRDT_NM=", product_url)
        self.assertIn("IprtFoodPrdtDBService02", product_url)

    def test_mfds_improper_normalization(self):
        client = LiveApiClient(service_key=FAKE_KEY, transport=fake_transport({
            "getInspctImproptList05": (200, MFDS_IMPROPER_JSON),
        }))
        fetch = client.mfds_improper(product_name="오메가3", rows=3)
        self.assertEqual(fetch.total_count, 1)
        row = live_api.normalize_mfds_improper_item(fetch.items[0])
        self.assertEqual(row["product_name_ko"], "초임계 rTG 오메가3")
        self.assertEqual(row["manufacture_country"], "미국")
        self.assertEqual(row["accepted_on"], "2026-06-04")
        self.assertIn("80~120%", row["fail_reason"])
        self.assertIn("goods_kor_name=", client._transport.calls[0])

    def test_law_normalization_hides_oc(self):
        client = LiveApiClient(law_oc=FAKE_OC,
                               transport=fake_transport({"lawSearch.do": (200, LAW_SEARCH_JSON)}))
        fetch = client.law_search("관세법")
        self.assertEqual(len(fetch.items), 2)
        for item in fetch.items:
            row = normalize_law_item(item)
            self.assertNotIn(FAKE_OC, row["url"])
            self.assertTrue(row["url"].startswith("https://www.law.go.kr/법령/"))
        self.assertEqual(normalize_law_item(fetch.items[1])["effective_from"], "2026-10-02")

    def test_law_article_filter_and_paragraphs(self):
        client = LiveApiClient(law_oc=FAKE_OC,
                               transport=fake_transport({"lawService.do": (200, LAW_BODY_JSON)}))
        fetch = client.law_articles("290673", article="226")
        self.assertEqual(len(fetch.items), 1)  # '전문'(장·절 제목) 제외
        unit = normalize_law_article(fetch.items[0])
        self.assertEqual(unit["article"], "제226조")
        self.assertIn("세관장에게", unit["paragraphs"][0])


class RetryTest(unittest.TestCase):
    def test_unregistered_key_retries_once_then_succeeds(self):
        sleeps = []
        responses = [(400, UNREGISTERED_XML), (200, CUSTOMS_XML)]
        calls = []

        def transport(url, timeout):
            calls.append(url)
            return responses[len(calls) - 1] + ("application/xml",)

        client = LiveApiClient(service_key=FAKE_KEY, transport=transport, sleep=sleeps.append)
        fetch = client.customs_checkpoint("3307903000")
        self.assertEqual(fetch.state, "live")
        self.assertEqual(fetch.attempts, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [live_api.UNREGISTERED_RETRY_SLEEP])  # 15초 1회 대기

    def test_unregistered_key_reports_code_after_retry(self):
        sleeps = []

        def transport(url, timeout):
            return 400, UNREGISTERED_XML, "application/xml"

        client = LiveApiClient(service_key=FAKE_KEY, transport=transport, sleep=sleeps.append)
        with self.assertRaises(LiveApiError) as ctx:
            client.customs_checkpoint("3307903000")
        self.assertEqual(ctx.exception.code, "30")
        self.assertTrue(ctx.exception.retryable)
        self.assertIn("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", ctx.exception.message)
        self.assertNotIn(FAKE_KEY, ctx.exception.message)
        self.assertEqual(len(sleeps), 1)

    def test_no_service_error_does_not_retry(self):
        sleeps = []

        def transport(url, timeout):
            return 400, UNREGISTERED_XML.replace("30", "12"), "application/xml"

        client = LiveApiClient(service_key=FAKE_KEY, transport=transport, sleep=sleeps.append)
        with self.assertRaises(LiveApiError) as ctx:
            client.customs_checkpoint("3307903000")
        self.assertEqual(ctx.exception.code, "12")
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(sleeps, [])

    def test_json_403_error_body_is_recognized(self):
        """실제 게이트웨이는 미등록 키를 HTTP 403 + JSON 본문으로도 돌려준다."""
        body = json.dumps({"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
            "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
            "returnAuthMsg": "등록되지 않은 서비스키",
            "returnReasonCode": "30"}}}, ensure_ascii=False)
        sleeps = []

        def transport(url, timeout):
            return 403, body, "application/json"

        client = LiveApiClient(service_key=FAKE_KEY, transport=transport, sleep=sleeps.append)
        with self.assertRaises(LiveApiError) as ctx:
            client.customs_checkpoint("3307903000")
        self.assertEqual(ctx.exception.code, "30")
        self.assertEqual(ctx.exception.http_status, 403)
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual([entry["outcome"] for entry in client.call_log],
                         ["retry_after_unregistered", "error"])


class GatewayAndToolTest(unittest.TestCase):
    def _client(self):
        return LiveApiClient(service_key=FAKE_KEY, law_oc=FAKE_OC, transport=fake_transport({
            "retrieveCcctLworCd": (200, CUSTOMS_XML),
            "getImrtsCnfirmList05": (200, MFDS_PERMIT_JSON),
            "getInspctImproptList05": (200, MFDS_IMPROPER_JSON),
            "getIprtFoodPrdtDBInq02": (200, MFDS_PRODUCT_JSON),
            "lawSearch.do": (200, LAW_SEARCH_JSON),
        }))

    def test_gateway_live_then_snapshot_fallback(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        register_sources(store)
        gateway = SourceGateway(store, live=self._client())
        state = gateway.get("customs_requirements", "hs", live_query={"hs_code": "3307903000"})
        self.assertEqual(state["state"], "live")
        self.assertEqual(state["item_count"], 1)
        # 원본 payload 는 내부 스냅샷에만 남고, 외부 상태 블록은 정규화 결과만 준다
        self.assertEqual(state["data"]["items"][0]["requirement_law"], "약사법")

        offline = SourceGateway(store)
        fallback = offline.get("customs_requirements", "hs")
        self.assertEqual(fallback["state"], "cached_fallback")
        self.assertTrue(fallback["fresh"])

    def test_gateway_live_error_falls_back_honestly(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        register_sources(store)
        client = LiveApiClient(service_key=FAKE_KEY,
                               transport=fake_transport({"retrieveCcctLworCd": (400, UNREGISTERED_XML)}),
                               sleep=lambda _: None)
        gateway = SourceGateway(store, live=client)
        state = gateway.get("customs_requirements", "hs", live_query={"hs_code": "3307903000"})
        self.assertEqual(state["state"], "unavailable")
        self.assertIsNone(state["fresh"])

    def test_lookup_hs_tool_exposes_normalized_only(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        register_sources(store)
        out = call_tool("lookup_hs_requirements", {"hs_code": "3307903000"}, store,
                        live=self._client())
        self.assertTrue(out["ok"])
        result = out["result"]
        self.assertEqual(result["verdict"]["code"], "check_likely")
        block = result["hs_requirements_live"]
        self.assertEqual(block["state"], "live")
        self.assertEqual(block["requirement_count"], 1)
        self.assertEqual(block["requirements"][0]["requirement_agency"], "한국의약품수출입협회")
        blob = json.dumps(result["hs_requirements_live"], ensure_ascii=False)
        for raw_field in ("hsSgn", "imexTpcd", "dcerCfrmLworNm", "reqApreIttNm", "payload_json"):
            self.assertNotIn(raw_field, blob)
        self.assertEqual(
            set(block["requirements"][0]),
            {"hs_code", "requirement_law", "requirement_agency", "requirement_document",
             "applies_from", "timing"},
        )

    def test_lookup_hs_tool_zero_items_stays_info_needed(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        register_sources(store)
        client = LiveApiClient(service_key=FAKE_KEY,
                               transport=fake_transport({"retrieveCcctLworCd": (200, CUSTOMS_EMPTY_XML)}))
        out = call_tool("lookup_hs_requirements", {"hs_code": "3307903010"}, store, live=client)
        self.assertEqual(out["result"]["verdict"]["code"], "info_needed")
        self.assertEqual(out["result"]["hs_requirements_live"]["requirement_count"], 0)

    def test_lookup_hs_tool_without_live_unchanged(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        out = call_tool("lookup_hs_requirements", {"hs_code": "3307903000"}, store)
        self.assertNotIn("hs_requirements_live", out["result"])

    def test_food_tool_live_block(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        register_sources(store)
        out = call_tool("check_food_cosmetics", {"product_name": "칠리", "kind": "food",
                                                 "purpose": "resale"}, store, live=self._client())
        block = out["result"]["food_import_live"]
        self.assertEqual(block["state"], "live")
        self.assertEqual(block["import_permit_history"]["match_count"], 2)
        self.assertEqual(block["product_db"]["samples"][0]["item_name"], "두류가공품")

    def test_legal_basis_tool_uses_exact_law_match_and_article(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        client = LiveApiClient(law_oc=FAKE_OC, transport=fake_transport({
            "lawSearch.do": (200, LAW_SEARCH_JSON),
            "lawService.do": (200, LAW_BODY_JSON),
        }))
        out = call_tool("get_legal_basis", {"law": "관세법", "article": "226"}, store, live=client)
        block = out["result"]["law_live"]
        self.assertEqual(block["state"], "live")
        self.assertEqual(block["confirmed"][0]["law_name"], "관세법")
        self.assertTrue(block["confirmed"][0]["exact_match"])
        self.assertEqual(block["article_text"]["article"], "제226조")
        self.assertNotIn(FAKE_OC, json.dumps(block, ensure_ascii=False))

    def test_assess_with_live_reports_live_provenance(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        register_sources(store)
        result = assess("HS 3307903000 수입요건", {}, store=store, live=self._client())
        states = {src["source_id"]: src["state"] for src in result["data_provenance"]["sources"]}
        self.assertEqual(states.get("customs_requirements"), "live")
        blob = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("payload_json", blob)
        for source in result["data_provenance"]["sources"]:
            self.assertNotIn("data", source)

    def test_assess_without_live_makes_no_calls(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        client = self._client()
        assess("블루투스 스피커 수입 판매", store=store)  # live 미주입
        self.assertEqual(client._transport.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
