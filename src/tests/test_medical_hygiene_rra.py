"""0.1.4 회귀 테스트 — 의료기기·위생용품 카드, 전파 적합성평가 실연동, pSEO 연결 일관성.

실행: python3 tests/test_medical_hygiene_rra.py   (표준 unittest, 네트워크 불필요)

검증 축
1. **법령 검증 산출물**: `medical-hygiene-law-verification.json` 의 조문 시행일이
   오늘(검증일) 이하이고, 미래 시행 개정 조문은 `skipped_future_versions` 로 빠졌는지.
   코퍼스 카드(TRAP-21·22)의 legal_basis 시행일이 이 산출물과 일치하는지.
2. **카드 동작**: 의료기기·위생용품 쟁점이 잡히고, 생리대(의약외품)는 잡히지 않는지.
3. **전파 적합성평가(RRA)**: 키 없는 공개 API 파싱·캐시(7일 TTL)·오류 상태와
   `data_provenance` 반영이 사실대로 되는지(네트워크 없이 transport 주입).
4. **pSEO**: 35개 페이지가 규제 축·법적 근거·면책·MCP 안내를 모두 갖는지.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import pseo  # noqa: E402
from import_compliance.api import call_tool  # noqa: E402
from import_compliance.corpus import load_corpus  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.live_api import (  # noqa: E402
    LiveApiClient,
    detect_cert_no,
    normalize_cert_no,
    normalize_rra_item,
    parse_rra_xml,
)
from import_compliance.policy import SCOPE_LIMITS_KO  # noqa: E402
from import_compliance.standards import CASE_REGULATION_TAGS, REGULATION_TAGS  # noqa: E402
from import_compliance.store import Store  # noqa: E402

VERIFICATION_PATH = os.path.join(ROOT, "medical-hygiene-law-verification.json")

RRA_OK_XML = """<GetAuthInfoResponse>
  <bsmNm>테스트전자(주)</bsmNm>
  <mtlNm>특정소출력무선기기(무선조정용)</mtlNm>
  <matlBscMdlNm>TEST-100</matlBscMdlNm>
  <mtlCefNo>R-TEST-00-0001</mtlCefNo>
  <matlMfrNm>테스트제조(주)</matlMfrNm>
  <dtlInfCdNm>한국</dtlInfCdNm>
  <cvaPcsYmd>2024-05-07</cvaPcsYmd>
  <matlEtcMtr> </matlEtcMtr>
  <resultMsg>조회되었습니다.</resultMsg>
  <resultCode>0000</resultCode>
</GetAuthInfoResponse>"""

RRA_NOT_FOUND_XML = """<GetAuthInfoResponse>
  <resultMsg>조회결과가 없습니다.</resultMsg>
  <resultCode>0001</resultCode>
</GetAuthInfoResponse>"""

RRA_MISSING_XML = """<GetAuthInfoResponse>
  <resultMsg>검색할 인증번호가 없습니다.</resultMsg>
  <resultCode>0098</resultCode>
</GetAuthInfoResponse>"""


def rra_transport(body: str, status: int = 200):
    """RRA 호출만 가로채는 가짜 transport(호출 URL을 기록한다)."""
    calls = []

    def transport(url, timeout):
        calls.append(url)
        return status, body, "application/xml"

    transport.calls = calls  # type: ignore[attr-defined]
    return transport


def assess_once(query, facts=None, live=None, store=None):
    own = store is None
    store = store or Store(":memory:")
    try:
        return assess(query, facts, store=store, live=live)
    finally:
        if own:
            store.close()


class LawVerificationTest(unittest.TestCase):
    """법제처 실조회 산출물과 코퍼스 인용이 어긋나지 않게 고정한다."""

    @classmethod
    def setUpClass(cls):
        # 이 산출물은 공개 저장소에 올리지 않는 내부 검증 파일이다(법제처 실조회 결과 원문 포함).
        # 없으면 이 클래스만 건너뛰고 나머지 축(카드·RRA·pSEO)은 CI 에서 그대로 돈다.
        if not os.path.exists(VERIFICATION_PATH):
            raise unittest.SkipTest(
                "medical-hygiene-law-verification.json 없음 — 법령 조문 대조는 로컬에서만 실행"
            )
        with open(VERIFICATION_PATH, encoding="utf-8") as handle:
            cls.artifact = json.load(handle)
        cls.by_law = {block["law"]: block for block in cls.artifact["laws"]}

    def test_artifact_checks_today(self):
        self.assertRegex(self.artifact["checked_on"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(set(self.by_law), {"의료기기법", "위생용품 관리법"})

    def test_every_cited_article_is_already_in_force(self):
        checked = self.artifact["checked_on"]
        for law, block in self.by_law.items():
            with self.subTest(law=law):
                self.assertEqual(block["unresolved"], [])
                self.assertTrue(block["articles"])
                for row in block["articles"]:
                    self.assertLessEqual(row["effective_from"], checked,
                                         f"{law} {row['article']} 시행일이 미래")
                    self.assertTrue(row["text"].startswith(row["article"].split("의")[0]))

    def test_future_effective_amendment_is_excluded(self):
        """의료기기법 2026-10-20 공포분(본문 2027-10-21 시행)은 인용하지 않는다."""
        block = self.by_law["의료기기법"]
        skipped = {row["article"] for row in block["skipped_future_versions"]}
        self.assertIn("제15조", skipped)
        for row in block["skipped_future_versions"]:
            self.assertGreater(row["effective_from"], self.artifact["checked_on"])
        cited = {row["article"] for row in block["articles"]}
        self.assertIn("제15조", cited)
        self.assertEqual({row["effective_from"] for row in block["articles"]}, {"2026-10-08"})

    def test_corpus_cards_match_verified_dates(self):
        corpus = load_corpus()
        expected = {
            "TRAP-21": ("의료기기법", "2026-10-08"),
            "TRAP-22": ("위생용품 관리법", "2026-05-12"),
        }
        for case_id, (law, effective) in expected.items():
            trap = corpus.by_id(case_id)
            self.assertIsNotNone(trap, case_id)
            dates = {basis.effective_date for basis in trap.legal_basis if basis.law == law}
            self.assertEqual(dates, {effective}, case_id)
            for basis in trap.legal_basis:
                self.assertTrue(basis.url.startswith("https://www.law.go.kr/"))
                self.assertEqual(basis.verified_on, self.artifact["checked_on"])
            cited = {basis.article for basis in trap.legal_basis}
            artifact_articles = {row["article"] for row in self.by_law[law]["articles"]}
            for article in cited:
                head = article.split("제")[1].split("조")[0]
                self.assertIn(f"제{head}조", " ".join(artifact_articles), f"{case_id} {article}")

    def test_hygiene_definition_evidence_excludes_sanitary_pads(self):
        """위생용품 관리법 제2조 원문에 기저귀·면봉은 있고 생리대는 없다(의약외품)."""
        block = self.by_law["위생용품 관리법"]
        article = next(row for row in block["articles"] if row["article"] == "제2조")
        self.assertIn("기저귀", article["text_full"])
        self.assertIn("면봉", article["text_full"])
        self.assertNotIn("생리대", article["text_full"])
        medical = self.by_law["의료기기법"]
        definition = next(row for row in medical["articles"] if row["article"] == "제2조")
        self.assertIn("의약외품", definition["text_full"])  # 정의에서 의약외품을 제외

    def test_tags_and_scope_limits_reflect_new_cards(self):
        self.assertIn("MEDICAL_DEVICE_IMPORT", REGULATION_TAGS)
        self.assertIn("HYGIENE_PRODUCT_IMPORT", REGULATION_TAGS)
        self.assertEqual(CASE_REGULATION_TAGS["TRAP-21"], ["MEDICAL_DEVICE_IMPORT"])
        self.assertEqual(CASE_REGULATION_TAGS["TRAP-22"], ["HYGIENE_PRODUCT_IMPORT"])
        scope = " ".join(SCOPE_LIMITS_KO)
        self.assertIn("22개", scope)
        self.assertIn("의약외품", scope)
        self.assertIn("적합성평가", scope)


class MedicalHygieneCardTest(unittest.TestCase):
    def test_medical_device_card_detects_and_cites_import_licence(self):
        result = assess_once("전자혈압계를 중국에서 수입해 판매하려고 해")
        by_id = {finding["case_id"]: finding for finding in result["findings"]}
        self.assertIn("TRAP-21", by_id)
        self.assertEqual(by_id["TRAP-21"]["verdict"], "check_likely")
        tags = by_id["TRAP-21"]["regulation_tags"]
        self.assertIn("MEDICAL_DEVICE_IMPORT", tags)
        laws = {(basis["law"], basis["article"]) for basis in result["evidence"]}
        self.assertIn(("의료기기법", "제15조제1항·제2항"), laws)
        joined = " ".join(result["answer"]["guidance"])
        self.assertIn("수입업 허가", joined)
        self.assertNotIn("확정", result["answer"]["headline"])

    def test_hygiene_card_detects_diaper_and_toothbrush(self):
        for query in ("기저귀를 수입해 판매하려고 해", "칫솔을 수입해 온라인에서 팔려고 해"):
            with self.subTest(query=query):
                result = assess_once(query)
                tags = {tag for finding in result["findings"]
                        for tag in finding["regulation_tags"]}
                self.assertIn("HYGIENE_PRODUCT_IMPORT", tags)

    def test_sanitary_pad_is_not_classified_as_hygiene_product(self):
        """생리대는 의약외품이라 위생용품·의료기기 카드가 붙으면 오답이다."""
        for query in ("생리대를 수입해 판매하려고 해", "생리대 HS 9619 6자리로 요건 확인"):
            with self.subTest(query=query):
                result = assess_once(query)
                tags = {tag for finding in result["findings"]
                        for tag in finding["regulation_tags"]}
                self.assertNotIn("HYGIENE_PRODUCT_IMPORT", tags)
                self.assertNotIn("MEDICAL_DEVICE_IMPORT", tags)
        trap = load_corpus().by_id("TRAP-22")
        self.assertIn("생리대", trap.notes)

    def test_hygiene_card_mentions_classification_boundary(self):
        trap = load_corpus().by_id("TRAP-22")
        joined = f"{trap.correct_answer} {trap.notes}"
        self.assertIn("의약외품", joined)
        self.assertIn("기저귀", joined)


class RraParsingTest(unittest.TestCase):
    def test_parse_found_not_found_and_missing_param(self):
        header, item, _raw = parse_rra_xml(RRA_OK_XML)
        self.assertEqual(header["resultCode"], "0000")
        row = normalize_rra_item(item)
        self.assertEqual(row["cert_no"], "R-TEST-00-0001")
        self.assertEqual(row["base_model"], "TEST-100")
        self.assertEqual(row["certified_on"], "2024-05-07")
        for body, code, state in ((RRA_NOT_FOUND_XML, "0001", "not_found"),
                                  (RRA_MISSING_XML, "0098", "invalid_request")):
            with self.subTest(code=code):
                client = LiveApiClient(transport=rra_transport(body))
                fetch = client.rra_certificate("R-TEST-00-0001")
                self.assertEqual(fetch.result_code, code)
                self.assertEqual(fetch.state, state)
                self.assertFalse(fetch.ok)

    def test_client_is_keyless_and_normalizes_cert_numbers(self):
        client = LiveApiClient()
        self.assertTrue(client.has_rra)
        self.assertIn("rra_conformity", {key for key, value in client.capabilities().items() if value})
        self.assertEqual(normalize_cert_no(" kcc-rem-mjt-mjt "), "KCC-REM-MJT-MJT")
        self.assertEqual(detect_cert_no("적합성평가 R-LARN-00-0210 확인"), "R-LARN-00-0210")
        self.assertIsNone(detect_cert_no("블루투스 스피커 수입"))

    def test_status_endpoint_flags_y_and_n(self):
        ok = LiveApiClient(transport=rra_transport(
            "<GetAuthStatusResponse><resultMsg>조회되었습니다.</resultMsg>"
            "<resultCode>0000</resultCode><authYn>Y</authYn></GetAuthStatusResponse>"))
        self.assertTrue(ok.rra_status("KCC-REM-MJT-MJT"))
        no = LiveApiClient(transport=rra_transport(
            "<GetAuthStatusResponse><resultMsg>조회결과가 없습니다.</resultMsg>"
            "<resultCode>0001</resultCode><authYn>N</authYn></GetAuthStatusResponse>"))
        self.assertIsNone(no.rra_status("ZZZ-EMC-XXX-0001"))
        self.assertIsNone(ok.rra_status(""))

    def test_dataset_id_and_result_labels_are_documented(self):
        from import_compliance.live_api import RRA_DATA_GO_KR_ID, RRA_RESULT_LABEL

        self.assertEqual(RRA_DATA_GO_KR_ID, "3034183")
        self.assertIn("0000", RRA_RESULT_LABEL)
        self.assertIn("0001", RRA_RESULT_LABEL)

    def test_missing_key_does_not_block_rra(self):
        client = LiveApiClient(transport=rra_transport(RRA_OK_XML))
        fetch = client.rra_certificate("R-TEST-00-0001")
        self.assertEqual(fetch.state, "live")
        self.assertEqual(fetch.items[0]["mtlCefNo"], "R-TEST-00-0001")


class RraToolIntegrationTest(unittest.TestCase):
    def _client(self):
        transport = rra_transport(RRA_OK_XML)
        client = LiveApiClient(transport=transport)
        return client, transport

    def test_assess_with_cert_number_reports_live_rra_and_cache(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        client, transport = self._client()
        args = {"query": "블루투스 스피커를 수입해 판매 (적합성평가 R-TEST-00-0001)",
                "facts": {"purpose": "resale"}}
        first = call_tool("assess_import_case", args, store, live=client)["result"]
        self.assertEqual(first["rra_conformity_live"]["state"], "live")
        self.assertEqual(first["rra_conformity_live"]["matches"][0]["base_model"], "TEST-100")
        states = {src["source_id"]: src for src in first["data_provenance"]["sources"]}
        self.assertEqual(states["rra_conformity"]["state"], "live")
        self.assertEqual(states["rra_conformity"]["cert_no"], "R-TEST-00-0001")
        self.assertEqual(len(transport.calls), 1)

        # 7일 TTL 캐시: 같은 번호 재호출은 네트워크를 다시 타지 않는다.
        second = call_tool("assess_import_case", args, store, live=client)["result"]
        self.assertEqual(second["rra_conformity_live"]["state"], "cached_fallback")
        self.assertEqual(second["rra_conformity_live"]["cache_ttl_hours"], 24 * 7)
        self.assertEqual(len(transport.calls), 1)

    def test_assess_without_cert_number_says_number_required_not_unavailable(self):
        result = call_tool("assess_import_case",
                           {"query": "블루투스 이어폰을 수입해 판매하려고 해"}, Store(":memory:"))["result"]
        states = {src["source_id"]: src for src in result["data_provenance"]["sources"]}
        self.assertIn("rra_conformity", states)
        self.assertEqual(states["rra_conformity"]["state"], "certificate_number_required")
        self.assertIn("rra.go.kr", states["rra_conformity"]["official_url"])
        self.assertIn("인증·등록번호", " ".join(result["answer"]["guidance"]))

    def test_not_found_is_stated_as_zero_rows_not_as_non_compliance(self):
        client, _ = self._client()
        store = Store(":memory:")
        self.addCleanup(store.close)
        result = call_tool("assess_import_case",
                           {"query": "무선 마우스 수입 적합성평가 R-TEST-00-0001", "facts": {"purpose": "resale"}},
                           store, live=LiveApiClient(transport=rra_transport(RRA_NOT_FOUND_XML)))["result"]
        self.assertEqual(result["rra_conformity_live"]["state"], "not_found")
        self.assertIn("0건은 '미인증'", result["rra_conformity_live"]["note_ko"])
        states = {src["source_id"]: src for src in result["data_provenance"]["sources"]}
        self.assertEqual(states["rra_conformity"]["state"], "not_found")

    def test_transport_failure_is_reported_honestly(self):
        def broken(url, timeout):
            return 500, "boom", "text/html"

        store = Store(":memory:")
        self.addCleanup(store.close)
        result = call_tool("check_kc_certification",
                           {"product_name": "블루투스 스피커", "rf_tx": "yes",
                            "rra_cert_no": "R-TEST-00-0001"},
                           store, live=LiveApiClient(transport=broken))["result"]
        self.assertEqual(result["rra_conformity_live"]["state"], "error")
        states = {src["source_id"]: src for src in result["data_provenance"]["sources"]}
        self.assertEqual(states["rra_conformity"]["state"], "error")
        self.assertIn("실시간 조회에 실패", " ".join(result["answer"]["guidance"]))

    def test_kc_tool_accepts_cert_number_and_reports_it(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        client, transport = self._client()
        result = call_tool("check_kc_certification",
                           {"product_name": "블루투스 스피커", "rf_tx": "yes",
                            "rra_cert_no": "R-TEST-00-0001"}, store, live=client)["result"]
        self.assertEqual(result["rra_conformity_live"]["state"], "live")
        self.assertEqual(result["query"]["facts_resolved"]["rra_cert_no"], "R-TEST-00-0001")
        self.assertEqual(len(transport.calls), 1)


class PseoConsistencyTest(unittest.TestCase):
    """35개 페이지가 규제 축·근거·면책·MCP 안내를 같은 형식으로 갖는지."""

    def test_every_item_links_regulation_axes_and_disclaimer(self):
        slugs = pseo.slugs()
        self.assertEqual(len(slugs), 35)
        for slug in slugs:
            with self.subTest(slug=slug):
                html = pseo.render_item(slug)
                self.assertIsNotNone(html)
                self.assertIn("이 품목에 걸리는 규제 축", html)
                self.assertIn("HS 요건과 법령상 품목 분류는 다릅니다", html)
                self.assertIn("법적 근거", html)
                self.assertIn("면책", html)
                self.assertIn("본 서비스는 관세사법상", html)
                self.assertIn("/v1/mcp", html)
                self.assertIn("API·MCP로 이 품목 자동 조회", html)
                self.assertIn("해외직구·목록통관으로 들여올 때", html)
                self.assertNotIn("<script src=", html)

    def test_every_item_has_known_traps_and_legal_basis(self):
        corpus = load_corpus()
        known = {trap.id for trap in corpus.traps}
        for item in pseo.items():
            with self.subTest(slug=item["slug"]):
                self.assertTrue(item.get("traps"))
                self.assertTrue(set(item["traps"]) <= known)
                self.assertTrue(pseo._legal_basis(item))
                for tag in pseo._item_tags(item):
                    self.assertIn(tag, REGULATION_TAGS)
                for tag in pseo._item_tags(item):
                    self.assertIn(tag, pseo.TAG_AUTHORITY_KO)
                    self.assertIn(tag, pseo.TAG_TOOL)

    def test_medical_and_hygiene_cards_are_reachable_from_catalog(self):
        used = {trap_id for item in pseo.items() for trap_id in item.get("traps") or []}
        self.assertIn("TRAP-22", used)
        self.assertIn("TRAP-21", used)

    def test_mask_and_bottle_pages_state_law_boundary(self):
        mask = pseo.render_item("disposable-mask")
        self.assertIn("의약외품", mask)
        self.assertIn("비말차단", mask)
        bottle = pseo.render_item("baby-bottle")
        self.assertIn("위생용품 목록에는 없", bottle)

    def test_catalog_metadata_is_current(self):
        meta = pseo.catalog_meta()
        self.assertEqual(meta["count"], 35)
        self.assertEqual(meta["version"], "1.0.1")
        self.assertEqual(meta["verified_on"], "2026-11-18")


if __name__ == "__main__":
    unittest.main(verbosity=2)
