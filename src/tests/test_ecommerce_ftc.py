"""0.4.0 국내 이커머스 공정위ㆍ전자상거래법 검수 테스트.

검증 대상
---------
1. 공정위 표시광고법ㆍ전자상거래법 규칙 14종이 대표 문구를 실제로 잡아내는지
2. 위험도(높음/주의)ㆍ근거 조문(시행일ㆍ원문 URL)ㆍ수정 전→후 문구가 함께 오는지
3. 고지ㆍ근거 문구가 함께 있으면 위험도를 낮추는지(뒷광고 표시, 최저가 근거, 구독 고지)
4. 판매자 정보ㆍ거래조건 고지 체크가 누락을 잡는지
5. `check_ecommerce_compliance` 툴과 `check_ad_labeling`ㆍ`assess_import_case` 원스톱 통합
6. 웹 UIㆍMCPㆍ가이드(`/guides/`)에 연결되고, 문구가 단정 표현ㆍ개인정보를 담지 않는지

실행: python3 tests/test_ecommerce_ftc.py   (네트워크 불필요)
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

from import_compliance import ecommerce, guides, web_ui  # noqa: E402
from import_compliance.api import BILLABLE_TOOLS, TOOL_DEFS, TOOL_INDEX, call_tool, mcp_manifest  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.standards import REGULATION_TAGS  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402

CANONICAL = {
    "EC-01": "정가 89,000원 → 특가 29,000원",
    "EC-02": "오늘만 이 가격! 마감 임박!",
    "EC-03": "체험단으로 선정되어 직접 써봤어요",
    "EC-04": "업체에서 보내주셨어요. 감사합니다!",
    "EC-05": "단순변심 환불 불가",
    "EC-06": "배송 지연 시 책임지지 않습니다",
    "EC-07": "FDA 승인 제품",
    "EC-08": "국내 최저가!",
    "EC-09": "매월 자동 결제됩니다",
    "EC-10": "월 9,900원부터",
    "EC-11": "해지는 고객센터 전화로만 가능합니다",
    "EC-12": "취소 시 위약금 10%",
    "EC-13": "100% 환불 보장",
    "EC-14": "후기 작성 시 1,000원 적립금 지급",
}

NEW_GUIDE_SLUGS = (
    "refund-policy-wording", "fake-discount-rate", "sponsored-review-disclosure",
    "lowest-price-no1-claim", "urgency-claim", "seller-info-disclosure",
    "subscription-autorenewal-notice", "free-trial-conversion", "price-total-display",
    "return-fee-charge", "review-reward-disclosure", "delivery-delay-refund",
    "certification-award-proof", "cancel-flow-dark-pattern",
)

PERSONAL_PATTERNS = (
    r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}",
    r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com",
    r"(?:github|gitlab)\.com/[A-Za-z0-9-]+",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
)


def review(text, **kwargs):
    return ecommerce.review(text, **kwargs)


class RuleCoverageTest(unittest.TestCase):
    def test_at_least_ten_rule_types(self):
        self.assertGreaterEqual(len(ecommerce.ECOMMERCE_RULES), 10)

    def test_rule_ids_are_unique_and_indexed(self):
        ids = [rule["id"] for rule in ecommerce.ECOMMERCE_RULES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(ecommerce.RULE_INDEX))

    def test_every_rule_matches_its_canonical_example(self):
        self.assertEqual(set(CANONICAL), {rule["id"] for rule in ecommerce.ECOMMERCE_RULES})
        for rule_id, sample in CANONICAL.items():
            with self.subTest(rule=rule_id):
                result = review(sample)
                ids = [finding["rule_id"] for finding in result["findings"]]
                self.assertIn(rule_id, ids, f"{rule_id} 가 '{sample}' 를 잡지 못했습니다")

    def test_every_rule_has_basis_and_rewrite(self):
        for rule in ecommerce.ECOMMERCE_RULES:
            with self.subTest(rule=rule["id"]):
                self.assertTrue(rule["why_ko"])
                self.assertTrue(rule["safer_ko"])
                self.assertTrue(rule["before_ko"])
                self.assertTrue(rule["after_ko"])
                self.assertIn(rule["risk"], ("high", "caution"))
                self.assertIn(rule["id"], ecommerce.TAG_BY_RULE)
                self.assertIn(ecommerce.TAG_BY_RULE[rule["id"]], REGULATION_TAGS)
                self.assertTrue(rule["basis"])
                for basis in rule["basis"]:
                    for key in ("law", "article", "effective_date", "url", "quote", "verified_on"):
                        self.assertIn(key, basis)
                    self.assertTrue(basis["url"].startswith("http"))
                    self.assertRegex(basis["effective_date"], r"^\d{4}-\d{2}-\d{2}$")
                    self.assertLessEqual(basis["effective_date"], ecommerce.VERIFIED_ON)

    def test_finding_shape_carries_wording_and_basis(self):
        result = review("단순변심 환불 불가, 체험단으로 선정되어 직접 써봤어요")
        self.assertTrue(result["findings"])
        for finding in result["findings"]:
            self.assertIn(finding["risk"], ("high", "caution"))
            self.assertIn(finding["risk_label_ko"], ("높음", "주의"))
            self.assertTrue(finding["matched_phrases"])
            self.assertTrue(finding["safer_ko"])
            self.assertTrue(finding["fix_example_ko"].startswith("수정 전:"))
            self.assertIn("수정 후:", finding["fix_example_ko"])
            self.assertTrue(finding["legal_basis"])


class RuleBehaviorTest(unittest.TestCase):
    def test_refund_restriction_is_high(self):
        result = review("단순변심 환불 불가 / 세일 상품 반품 불가 / 수령 후 3일 내 환불 신청")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-05")
        self.assertEqual(entry["risk"], "high")
        laws = {row["law"] for row in entry["legal_basis"]}
        self.assertIn(ecommerce.EC_NAME_KO, laws)
        self.assertIn(ecommerce.NOTICE_CONSUMER_GUIDE_KO, laws)

    def test_correct_withdrawal_period_is_not_flagged(self):
        """법이 정한 7일을 그대로 안내한 문구는 제한 문구가 아니다."""
        result = review("수령 후 7일 이내 청약철회 가능(반품 배송비 구매자 부담)")
        self.assertEqual(result["findings"], [])

    def test_shortened_withdrawal_period_is_flagged(self):
        result = review("불량으로 인한 환불은 물건 수령 후 5일 내에 고객센터로 신청한 경우에 한해서 가능")
        self.assertIn("EC-05", [f["rule_id"] for f in result["findings"]])

    def test_paid_review_without_disclosure_is_high(self):
        result = review("체험단으로 선정되어 직접 써봤어요! 정말 좋아요")
        self.assertEqual(result["verdict"], "check_likely")
        self.assertIn("EC-03", [f["rule_id"] for f in result["findings"]])

    def test_paid_review_with_disclosure_is_suppressed(self):
        result = review("체험단으로 선정되었습니다. #광고 ○○사로부터 제품을 제공받아 작성했습니다")
        self.assertNotIn("EC-03", [f["rule_id"] for f in result["findings"]])
        self.assertIn("EC-03", [row["rule_id"] for row in result["suppressed_notes_ko"]])

    def test_vague_disclosure_is_still_caution(self):
        result = review("업체에서 보내주셨어요. 감사합니다!")
        self.assertIn("EC-04", [f["rule_id"] for f in result["findings"]])

    def test_lowest_price_without_evidence(self):
        result = review("국내 최저가! 판매 1위!")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-08")
        self.assertEqual(entry["risk"], "caution")
        self.assertIn("최저가", entry["matched_phrases"])

    def test_lowest_price_with_evidence_is_suppressed(self):
        result = review("국내 최저가! 2026.11.20 자사 조사 기준 3개 판매처 비교")
        self.assertNotIn("EC-08", [f["rule_id"] for f in result["findings"]])

    def test_free_trial_without_notice_escalates_to_high(self):
        result = review("첫 달 0원! 지금 구독하세요")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-09")
        self.assertEqual(entry["risk"], "high")

    def test_subscription_notice_suppresses(self):
        result = review("첫 달 0원. 매월 15일 9,900원 자동결제됩니다. 언제든 해지할 수 있습니다")
        self.assertEqual(result["findings"], [])

    def test_partial_price_display_is_high(self):
        result = review("월 9,900원부터 (배송비 별도)")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-10")
        self.assertEqual(entry["risk"], "high")
        self.assertIn("제21조의2제1항제1호", [b["article"] for b in entry["legal_basis"]])

    def test_cancel_flow_restriction_is_high(self):
        result = review("해지는 고객센터 전화로만 가능합니다")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-11")
        self.assertEqual(entry["risk"], "high")

    def test_extra_penalty_is_high(self):
        result = review("취소 시 결제금액의 10% 위약금 + 검수비 2,000원 공제")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-12")
        self.assertEqual(entry["risk"], "high")
        self.assertIn("제18조제9항", [b["article"] for b in entry["legal_basis"]])

    def test_delivery_evasion_is_high(self):
        result = review("배송 지연 시 책임지지 않으며 품절된 경우 환불이 불가합니다")
        ids = [f["rule_id"] for f in result["findings"]]
        self.assertIn("EC-06", ids)
        self.assertEqual(result["risk_high"] >= 1, True)

    def test_award_and_patent_are_caution(self):
        result = review("세계 최초 특허 획득! FDA 승인 제품")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-07")
        self.assertEqual(entry["risk"], "caution")
        laws = {row["law"] for row in entry["legal_basis"]}
        self.assertIn(ecommerce.NOTICE_DESIGNATION_KO, laws)

    def test_guarantee_wording_is_caution(self):
        result = review("100% 환불 보장, 평생 무상 A/S")
        self.assertEqual(result["verdict"], "info_needed")

    def test_review_reward_is_caution(self):
        result = review("후기 작성 시 1,000원 적립금 지급")
        entry = next(f for f in result["findings"] if f["rule_id"] == "EC-14")
        self.assertEqual(entry["risk"], "caution")

    def test_urgency_claim_is_caution(self):
        result = review("오늘만 이 가격! 마감 임박! 선착순 100명")
        ids = [f["rule_id"] for f in result["findings"]]
        self.assertIn("EC-02", ids)
        self.assertEqual(result["findings"][0]["risk"], "caution")

    def test_clean_copy_is_low_risk(self):
        result = review("상품 구성과 소재, 사용 방법을 안내합니다. 배송은 평일 2~3영업일 소요됩니다.")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["verdict"], "low_risk")

    def test_health_claim_copy_is_not_ecommerce_issue(self):
        """식약처 축(효능 표현)은 ecommerce 엔진이 잡지 않는다(축을 섞지 않는다)."""
        result = review("체지방 감소에 도움을 줄 수 있음")
        self.assertEqual(result["findings"], [])

    def test_short_input_reports_info_needed(self):
        self.assertEqual(review("가")["verdict"], "info_needed")

    def test_limit_caps_findings(self):
        result = review("정가 89,000원 → 29,000원 오늘만 마감임박 체험단 협찬 최저가 환불 불가 위약금 100% 보장",
                       limit=2)
        self.assertEqual(len(result["findings"]), 2)


class DisclosureCheckTest(unittest.TestCase):
    COMPLETE = (
        "상호 ○○커머스 / 대표 홍길동 / 주소 서울시 ○○구 ○○로 1 / 전화 02-000-0000 / "
        "통신판매업 신고 제2026-서울○○-0000호 / 판매가 29,000원 카드 결제 / "
        "택배 발송, 평일 14시 이전 결제 시 2~3영업일 내 도착 / 배송비 3,000원(3만원 이상 무료) / "
        "수령 후 7일 이내 청약철회 가능(반품 배송비 구매자 부담) / "
        "교환·반품은 수령 후 7일 이내 신청, 환불은 반품 확인 후 3영업일 이내, 지연 시 지연배상금 지급"
    )

    def test_complete_page_passes(self):
        result = ecommerce.disclosures(self.COMPLETE)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["verdict"], "low_risk")
        self.assertGreaterEqual(result["completion_rate"], 1.0)

    def test_missing_seller_identity_is_caught(self):
        result = ecommerce.disclosures("상품 소개와 가격 29,000원만 있습니다")
        self.assertIn("상호 및 대표자 성명", result["missing"])
        self.assertIn("통신판매업 신고번호", result["missing"])
        self.assertEqual(result["verdict"], "check_likely")

    def test_shipping_and_withdrawal_items(self):
        result = ecommerce.disclosures("택배 발송, 2~3영업일 내 도착 / 배송비 3,000원 / 청약철회는 수령 후 7일 이내")
        self.assertNotIn("배송방법ㆍ예상 배송기간ㆍ배송비", result["missing"])
        self.assertNotIn("청약철회 기한ㆍ행사방법ㆍ효과", result["missing"])

    def test_conditional_subscription_item(self):
        text = self.COMPLETE + " / 매월 자동 결제되는 구독 상품입니다"
        result = ecommerce.disclosures(text)
        self.assertIn("정기결제 결제일ㆍ금액ㆍ해지 방법", result["conditional_missing"])

    def test_no_input_is_info_needed(self):
        result = ecommerce.disclosures("")
        self.assertEqual(result["verdict"], "info_needed")
        self.assertEqual(result["missing"], [])

    def test_check_combines_review_and_disclosure(self):
        result = ecommerce.check("단순변심 환불 불가")
        self.assertEqual(result["combined_verdict"], "check_likely")
        self.assertGreaterEqual(result["disclosure_missing_count"], 1)
        self.assertEqual(len(result["basis_sources"]), 4)

    def test_check_can_skip_disclosure(self):
        result = ecommerce.check("단순변심 환불 불가", include_disclosure=False)
        self.assertEqual(result["disclosure_check"]["checklist"], [])
        self.assertEqual(result["combined_verdict"], "check_likely")


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def _call(self, payload):
        return call_tool("check_ecommerce_compliance", payload, self.store, client_id="ec-test")

    def test_tool_registered_and_schema(self):
        names = [tool["name"] for tool in TOOL_DEFS]
        self.assertIn("check_ecommerce_compliance", names)
        self.assertIn("check_ecommerce_compliance", BILLABLE_TOOLS)
        entry = next(t for t in mcp_manifest()["tools"] if t["name"] == "check_ecommerce_compliance")
        props = entry["inputSchema"]["properties"]
        for key in ("detail_copy", "product_name", "channel", "disclosure_items", "include_disclosure"):
            self.assertIn(key, props)

    def test_high_risk_copy_returns_contract(self):
        out = self._call({"detail_copy": "단순변심 환불 불가, 체험단으로 선정되어 직접 써봤어요, 국내 최저가",
                          "channel": "cursor"})
        self.assertTrue(out["ok"])
        result = out["result"]
        self.assertEqual(result["verdict"]["code"], "check_likely")
        self.assertEqual(result["channel"], "other")
        for key in ("answer", "findings", "evidence", "ecommerce_review", "disclosure_check",
                    "ecommerce", "assessment_status", "disclaimer", "data_provenance",
                    "scope_limits_ko", "tier", "next_actions", "missing_information"):
            self.assertIn(key, result)
        self.assertEqual(result["ecommerce"]["rules"], len(ecommerce.ECOMMERCE_RULES))
        self.assertIn("WITHDRAWAL_REFUND", result["regulation_tags"])
        self.assertIn("SELLER_DISCLOSURE", result["regulation_tags"])

    def test_channel_label(self):
        out = self._call({"detail_copy": "상품 안내입니다. 배송은 2일 소요됩니다.", "channel": "smartstore"})
        self.assertEqual(out["result"]["channel_label_ko"], "네이버 스마트스토어")

    def test_disclosure_items_can_be_asserted(self):
        out = self._call({"detail_copy": "상품 안내입니다",
                          "disclosure_items": {"seller_identity": True, "seller_contact": True,
                                               "mail_order_no": True, "price_payment": True,
                                               "shipping": True, "withdrawal": True,
                                               "exchange_refund": True}})
        result = out["result"]
        self.assertEqual(result["disclosure_check"]["missing"], [])
        self.assertNotIn("SELLER_DISCLOSURE", result["regulation_tags"])

    def test_evidence_has_effective_dates_and_urls(self):
        out = self._call({"detail_copy": "단순변심 환불 불가"})
        self.assertTrue(out["result"]["evidence"])
        for row in out["result"]["evidence"]:
            self.assertTrue(row["law"])
            self.assertTrue(row["url"].startswith("http"))
            self.assertRegex(row["effective_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_invalid_arguments(self):
        self.assertEqual(call_tool("check_ecommerce_compliance", {}, self.store)["error"],
                         "invalid_argument")
        self.assertEqual(call_tool("check_ecommerce_compliance", {"detail_copy": "가"}, self.store)["error"],
                         "invalid_argument")
        self.assertEqual(call_tool("check_ecommerce_compliance",
                                   {"detail_copy": "가" * 8001}, self.store)["error"], "invalid_argument")
        self.assertEqual(call_tool("check_ecommerce_compliance",
                                   {"detail_copy": "상품 안내", "disclosure_items": []},
                                   self.store)["error"], "invalid_argument")

    def test_guidance_avoids_conclusive_phrasing(self):
        out = self._call({"detail_copy": "100% 환불 보장, 무조건 교환, 단순변심 환불 불가"})
        joined = " ".join(out["result"]["answer"]["guidance"])
        self.assertEqual(find_conclusive_phrasing(joined), [], joined)

    def test_mcp_jsonrpc_call(self):
        from import_compliance import mcp_http

        listing = mcp_http.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                  store=self.store, client_id="mcp-ec")
        names = {tool["name"] for tool in listing["result"]["tools"]}
        self.assertIn("check_ecommerce_compliance", names)
        called = mcp_http.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "check_ecommerce_compliance",
                                             "arguments": {"detail_copy": "단순변심 환불 불가"}}},
                                 store=self.store, client_id="mcp-ec")
        self.assertFalse(called["result"].get("isError"))
        self.assertIn("check_ecommerce_compliance", called["result"]["content"][0]["text"])


class OneStopIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_check_ad_labeling_adds_ecommerce_findings(self):
        out = call_tool("check_ad_labeling",
                        {"product_type": "general_food",
                         "ad_copy": "다이어트에 좋은 차! 단순변심 환불 불가, 체험단으로 선정되어 써봤어요"},
                        self.store)
        result = out["result"]
        categories = {finding["category"] for finding in result["findings"]}
        self.assertIn("ecommerce", categories)
        self.assertIn("advertising", categories)
        self.assertIn("ecommerce_review", result)
        self.assertGreaterEqual(result["ad_labeling"]["ecommerce_finding_count"], 2)
        self.assertIn("REVIEW_MARKETING", result["regulation_tags"])
        self.assertIn("WITHDRAWAL_REFUND", result["regulation_tags"])
        laws = {row["law"] for row in result["evidence"]}
        self.assertIn(ecommerce.EC_NAME_KO, laws)

    def test_check_ad_labeling_without_copy_has_no_ecommerce_block(self):
        out = call_tool("check_ad_labeling", {"product_type": "cosmetics", "label_text": "명칭 크림"},
                        self.store)
        self.assertNotIn("ecommerce_review", out["result"])

    def test_assess_import_case_with_detail_copy(self):
        out = call_tool("assess_import_case",
                        {"query": "국산 핸드크림을 자사몰에서 판매",
                         "facts": {"detail_copy": "오늘만 49% 할인! 단순변심 환불 불가",
                                   "purpose": "resale"}}, self.store)
        result = out["result"]
        self.assertIn("ecommerce_review", result)
        ids = [finding["case_id"] for finding in result["findings"]]
        self.assertIn("EC-05", ids)
        self.assertIn("WITHDRAWAL_REFUND", result["regulation_tags"])
        union = []
        for finding in result["findings"]:
            for tag in finding["regulation_tags"]:
                if tag not in union:
                    union.append(tag)
        self.assertEqual(result["regulation_tags"], union)

    def test_assess_import_case_without_copy_is_unchanged(self):
        out = call_tool("assess_import_case", {"query": "국산 핸드크림을 자사몰에서 판매"}, self.store)
        self.assertNotIn("ecommerce_review", out["result"])


class GuideTest(unittest.TestCase):
    def test_new_guides_are_in_catalog(self):
        slugs = set(guides.slugs())
        for slug in NEW_GUIDE_SLUGS:
            with self.subTest(slug=slug):
                self.assertIn(slug, slugs)
                item = guides.get_item(slug)
                self.assertEqual(item["category"], "국내 이커머스·공정위")
                self.assertEqual(item["tool"], "check_ecommerce_compliance")
                self.assertGreaterEqual(len(item["checkpoints_ko"]), 3)
                self.assertGreaterEqual(len(item["answer_ko"]), 80)

    def test_new_guides_have_ecommerce_basis(self):
        for slug in NEW_GUIDE_SLUGS:
            with self.subTest(slug=slug):
                item = guides.get_item(slug)
                basis = guides.legal_basis(item)
                self.assertTrue(basis)
                laws = {row["law"] for row in basis}
                self.assertTrue(
                    any(law in laws for law in (ecommerce.FTC_NAME_KO, ecommerce.EC_NAME_KO,
                                                ecommerce.NOTICE_DESIGNATION_KO,
                                                ecommerce.NOTICE_PRODUCT_INFO_KO,
                                                ecommerce.NOTICE_CONSUMER_GUIDE_KO,
                                                ecommerce.NOTICE_RECOMMENDATION_KO)),
                    laws,
                )

    def test_new_guide_answers_avoid_conclusive_phrasing(self):
        for slug in NEW_GUIDE_SLUGS:
            item = guides.get_item(slug)
            texts = [item["answer_ko"], item["summary_ko"], *item["checkpoints_ko"],
                     *(item.get("key_points_ko") or [])]
            for text in texts:
                with self.subTest(slug=slug):
                    self.assertEqual(find_conclusive_phrasing(text), [], text[:60])

    def test_new_guides_use_known_tags_and_tools(self):
        for slug in NEW_GUIDE_SLUGS:
            item = guides.get_item(slug)
            self.assertIn(item["tool"], TOOL_INDEX)
            for tag in item["tags"]:
                self.assertIn(tag, REGULATION_TAGS)
                self.assertNotEqual(guides.authority_for(tag), "소관 기관 확인")
                self.assertIn(guides.tool_for_tag(tag), TOOL_INDEX)

    def test_new_guides_are_indexable_and_render(self):
        for slug in NEW_GUIDE_SLUGS:
            item = guides.get_item(slug)
            self.assertTrue(guides.is_indexable(item))
            html = guides.render_guide(slug)
            self.assertIsNotNone(html)
            self.assertIn("한 줄 답변", html)
            self.assertIn("근거 법령", html)
            self.assertIn("check_ecommerce_compliance", html)
            self.assertNotIn('content="noindex,follow"', html)

    def test_index_lists_ecommerce_category(self):
        html = guides.render_index()
        self.assertIn("국내 이커머스·공정위", html)
        for slug in NEW_GUIDE_SLUGS:
            self.assertIn(f"/guides/{slug}", html)

    def test_guide_count_matches_catalog(self):
        # 카탈로그 버전은 가이드를 추가할 때마다 여기서 함께 올린다(1.2.0: 롱테일 15종).
        self.assertEqual(guides.catalog_meta()["version"], "1.6.0")
        self.assertGreaterEqual(len(guides.items()), 68)


class WebUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_page_mentions_ecommerce_check(self):
        self.assertIn('id="check-demo-shop"', self.page)
        self.assertIn("/v1/tools/check_ecommerce_compliance", self.page)
        self.assertIn("공정거래위원회", self.page)
        self.assertIn("국내 판매페이지 검수", self.page)
        self.assertIn("ecommerceFindingsBlock", self.page)
        self.assertIn("ecommerceDisclosureBlock", self.page)

    def test_standalone_detail_page_form_exists(self):
        """품목명 없이 상세페이지 문구만 넣어 검수하는 입력란."""
        for field_id in ("ec-copy", "ec-channel", "ec-submit", "ec-result", "ec-demo"):
            self.assertIn(f'id="{field_id}"', self.page)
        self.assertIn("국내 판매페이지 문구만 빠르게 검수", self.page)
        self.assertIn('postTool("check_ecommerce_compliance"', self.page)

    def test_page_has_no_personal_data_markers(self):
        self.assertNotRegex(self.page, r"01\d[- ]?\d{3,4}[- ]?\d{4}")
        self.assertNotRegex(self.page, r"[\w.+-]+@[\w-]+\.[\w.]+")

    def test_guide_count_is_rendered(self):
        self.assertNotIn("__GUIDE_COUNT__", self.page)
        self.assertIn(str(len(guides.items())), self.page)


class VersionAndAnonymityTest(unittest.TestCase):
    def test_version_is_0_4_0(self):
        self.assertEqual(__version__, "0.5.7")
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["version"], __version__)

    def test_new_files_have_no_personal_data_or_secrets(self):
        patterns = [re.compile(pattern) for pattern in PERSONAL_PATTERNS]
        targets = [
            os.path.join("src", "import_compliance", "ecommerce.py"),
            os.path.join("src", "import_compliance", "api.py"),
            os.path.join("src", "import_compliance", "web_ui.py"),
            os.path.join("src", "guides_items.json"),
            os.path.join("src", "tests", "test_ecommerce_ftc.py"),
            "11-ecommerce-ftc-0.4.0.md",
            "README.md",
        ]
        for relative in targets:
            path = os.path.join(ROOT, relative)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for pattern in patterns:
                with self.subTest(file=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))

    def test_no_hardcoded_secrets_in_module(self):
        with open(os.path.join(SRC, "import_compliance", "ecommerce.py"), encoding="utf-8") as handle:
            text = handle.read()
        for pattern in (r"DATA_GO_KR_SERVICE_KEY\s*=", r"LAW_GO_KR_OC\s*=",
                        r"ghp_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{20,}"):
            self.assertIsNone(re.search(pattern, text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
