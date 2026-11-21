"""스키마 0.1.3 검증: 표준 판정 상태·누락 정보·공통 지리 필드·하위 호환.

실행: python3 tests/test_schema_013.py   (표준 unittest)

0.1.3 에서 추가된 필드
- `assessment_status` (APPLICABLE / NOT_APPLICABLE / POTENTIALLY_APPLICABLE /
  REVIEW_REQUIRED / UNKNOWN), `missing_information`
- `destination` / `jurisdiction` / `origin` / `origin_source` / `schema_version`
- 각 finding 의 `regulation_tags`

기존 `verdict`(3단계)·`findings`·`evidence`·`data_provenance`·`disclaimer`·
`scope_limits_ko`·`tier`·`next_actions` 계약은 그대로 유지되는지 함께 고정한다.
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
from import_compliance.api import TOOL_DEFS, call_tool  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.policy import SCOPE_LIMITS_KO  # noqa: E402
from import_compliance.standards import (  # noqa: E402
    ASSESSMENT_STATUS,
    ASSESSMENT_STATUS_ORDER,
    MISSING_FIELD_ALIAS,
    SCHEMA_VERSION,
    apply_status,
    detect_origin,
    status_for,
)
from import_compliance.store import Store  # noqa: E402

# 0.1.2 까지의 응답 최상위 키(하위 호환 기준선)
BASE_KEYS = (
    "assessment_id", "engine", "query", "verdict", "answer", "findings", "evidence",
    "data_provenance", "disclaimer", "scope_limits_ko", "tier", "client_id", "next_actions",
)


def assess_once(query: str, facts=None) -> dict:
    store = Store(":memory:")
    try:
        return assess(query, facts, store=store)
    finally:
        store.close()


class VersionTest(unittest.TestCase):
    def test_package_version_is_0_2_0(self):
        self.assertEqual(__version__, "0.5.7")
        # 엔진 버전이 0.3.0 으로 올라가도 응답 스키마 0.1.3 의 필드 계약은 그대로 둔다
        # (0.2.0 이후 추가된 ad_review·labeling_check·disposition_lookup·trends 는 블록 추가뿐, 기존 필드 삭제·의미 변경이 없다).
        self.assertEqual(SCHEMA_VERSION, "0.1.3")
        self.assertEqual(web_ui.SERVICE_VERSION, "0.5.7")

    def test_dockerfile_version_is_0_2_0(self):
        with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as handle:
            docker = handle.read()
        self.assertIn('org.opencontainers.image.version="0.5.7"', docker)

    def test_response_reports_schema_version(self):
        result = assess_once("중국산 과자를 구매대행으로 들여와 판매")
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["engine"]["version"], "1.0.7")


class StandardFieldsTest(unittest.TestCase):
    def test_geography_defaults(self):
        result = assess_once("중국산 과자를 구매대행으로 들여와 판매")
        self.assertEqual(result["destination"], "KR")
        self.assertEqual(result["jurisdiction"], "KR")
        self.assertEqual(result["origin"], "CN")
        self.assertEqual(result["origin_source"], "query")

    def test_origin_is_null_when_unknown(self):
        result = assess_once("수입 식품을 원포장 그대로 한글표시 없이 유통")
        self.assertIsNone(result["origin"])
        self.assertIsNone(result["origin_source"])

    def test_origin_from_facts_wins(self):
        result = assess_once("리튬이온 배터리를 수입해 판매",
                             {"origin": "베트남", "battery_type": "리튬이온"})
        self.assertEqual(result["origin"], "VN")
        self.assertEqual(result["origin_source"], "facts")

    def test_origin_detection_covers_major_partners_and_iso(self):
        cases = {
            "미국산 오메가3를 수입해 판매": "US",
            "일본 젤리 간식을 직구로 들여와 되팔려고 해": "JP",
            "Made in China 전기포트 HS 8516": "CN",
            "인도네시아산 커피를 수입": "ID",
            "인도산 향신료를 수입": "IN",
            "독일 앰플 화장품을 수입해 판매": "DE",
            "프랑스 세럼 화장품": "FR",
            "대만산 충전기를 수입해 판매": "TW",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(detect_origin(query.lower()), expected)

    def test_origin_present_on_every_tool_result(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        for definition in TOOL_DEFS:
            name = definition["name"]
            args = {
                "assess_import_case": {"query": "미국산 수딩크림 화장품을 수입해 판매"},
                "lookup_hs_requirements": {"hs_code": "8507601000"},
                "check_kc_certification": {"product_name": "USB 충전기"},
                "check_food_cosmetics": {"product_name": "비타민", "kind": "health_functional"},
                "check_drug_import": {"product_name": "멜라토닌", "channel": "carry"},
                "check_ad_labeling": {"product_type": "general_food", "ad_copy": "다이어트에 좋은 차"},
                "check_ecommerce_compliance": {"detail_copy": "단순변심 환불 불가, 오늘만 특가"},
                "check_korean_labeling": {"product_type": "cosmetics", "label_text": "명칭 수분 크림"},
                "check_feed_import": {"product_name": "강아지 간식", "purpose": "resale"},
                "lookup_mfds_disposition": {"industry": "manufacturing"},
                "lookup_recall": {"brand": "테스트브랜드"},
                "get_legal_basis": {"law": "관세법"},
                "explain_trap": {"case_id": "TRAP-04"},
                "get_compliance_trends": {"days": 7},
                "get_service_meta": {},
            }[name]
            with self.subTest(tool=name):
                payload = call_tool(name, args, store)["result"]
                for key in ("schema_version", "destination", "jurisdiction", "origin"):
                    self.assertIn(key, payload)
                self.assertEqual(payload["destination"], "KR")
                self.assertEqual(payload["jurisdiction"], "KR")


class AssessmentStatusTest(unittest.TestCase):
    def test_five_standard_states_exist(self):
        self.assertEqual(ASSESSMENT_STATUS_ORDER, [
            "APPLICABLE", "NOT_APPLICABLE", "POTENTIALLY_APPLICABLE",
            "REVIEW_REQUIRED", "UNKNOWN",
        ])
        for status in ASSESSMENT_STATUS_ORDER:
            self.assertTrue(ASSESSMENT_STATUS[status]["label_ko"])
            self.assertTrue(ASSESSMENT_STATUS[status]["label_en"])

    def test_status_mapping_table(self):
        self.assertEqual(status_for("check_likely", finding_count=2), "APPLICABLE")
        self.assertEqual(status_for("check_likely", finding_count=1,
                                    missing_information=["ac_plug"]), "POTENTIALLY_APPLICABLE")
        self.assertEqual(status_for("info_needed", finding_count=1), "REVIEW_REQUIRED")
        self.assertEqual(status_for("low_risk", finding_count=1), "NOT_APPLICABLE")
        self.assertEqual(status_for("info_needed", finding_count=0), "UNKNOWN")
        self.assertEqual(status_for("nonsense", finding_count=3), "UNKNOWN")

    def test_status_values_in_real_answers(self):
        applicable = assess_once("USB-C 65W 충전기를 중국에서 수입해 판매",
                                 {"rated_power": "65W", "ac_plug": "yes"})
        self.assertEqual(applicable["verdict"]["code"], "check_likely")
        self.assertEqual(applicable["assessment_status"], "APPLICABLE")

        review = assess_once("유아용 원목 완구를 수입해 판매",
                             {"product_name": "원목 완구", "target_age": "만 3세"})
        self.assertEqual(review["assessment_status"], "REVIEW_REQUIRED")

        not_applicable = assess_once("적외선 리모컨을 수입해 판매")
        self.assertEqual(not_applicable["assessment_status"], "NOT_APPLICABLE")

        unknown = assess_once("우주선 부품 수입")
        self.assertEqual(unknown["assessment_status"], "UNKNOWN")
        self.assertEqual(unknown["findings"], [])

        potentially = assess_once("블루투스 이어폰을 수입해 판매")
        self.assertEqual(potentially["assessment_status"], "POTENTIALLY_APPLICABLE")

    def test_status_labels_accompany_status(self):
        result = assess_once("중국산 과자를 구매대행으로 들여와 판매")
        self.assertIn("assessment_status", result)
        self.assertEqual(result["assessment_status_label_ko"],
                         ASSESSMENT_STATUS[result["assessment_status"]]["label_ko"])
        self.assertEqual(result["assessment_status_label_en"],
                         ASSESSMENT_STATUS[result["assessment_status"]]["label_en"])
        self.assertTrue(result["assessment_status_note_ko"])

    def test_status_follows_verdict_change(self):
        """ api 가 실시간 조회로 verdict 를 올려도 상태가 어긋나지 않아야 한다. """
        result = assess_once("HS 850760 수입요건")
        self.assertEqual(result["assessment_status"], "REVIEW_REQUIRED")
        result["verdict"]["code"] = "check_likely"
        result["missing_information"] = []
        apply_status(result)
        self.assertEqual(result["assessment_status"], "APPLICABLE")
        result["verdict"]["code"] = "low_risk"
        apply_status(result)
        self.assertEqual(result["assessment_status"], "NOT_APPLICABLE")

    def test_status_is_present_in_hs_and_kc_tools(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        for name, args in (
            ("lookup_hs_requirements", {"hs_code": "850760"}),
            ("check_kc_certification", {"product_name": "USB 충전기"}),
            ("check_food_cosmetics", {"product_name": "비타민", "kind": "health_functional"}),
        ):
            with self.subTest(tool=name):
                payload = call_tool(name, args, store)["result"]
                self.assertIn(payload["assessment_status"], ASSESSMENT_STATUS_ORDER)
                self.assertIn("missing_information", payload)


class MissingInformationTest(unittest.TestCase):
    def test_missing_information_uses_standard_names(self):
        result = assess_once("충전기를 수입해 판매")
        self.assertEqual(result["missing_information"], ["rated_power", "ac_plug"])

        hs = assess_once("전기포트 HS 8516으로 수입요건 확인")
        self.assertIn("hs_10_code", hs["missing_information"])

        child = assess_once("유아용 완구를 수입해 판매")
        self.assertIn("intended_age", child["missing_information"])

        wireless = assess_once("무선 스피커를 수입해 판매", {"rf_tx": "unknown"})
        self.assertIn("wireless_function", wireless["missing_information"])

    def test_alias_map_is_consistent(self):
        for internal, external in MISSING_FIELD_ALIAS.items():
            with self.subTest(field=internal):
                self.assertTrue(internal)
                self.assertTrue(external)
                self.assertRegex(external, r"^[a-z0-9_]+$")

    def test_missing_information_detail_carries_prompt_and_case(self):
        result = assess_once("충전기를 수입해 판매")
        detail = {item["field"]: item for item in result["missing_information_detail"]}
        self.assertEqual(set(detail), set(result["missing_information"]))
        self.assertEqual(detail["rated_power"]["case_id"], "TRAP-04")
        self.assertTrue(detail["rated_power"]["prompt"])
        self.assertEqual(detail["rated_power"]["source_field"], "rated_power")

    def test_missing_information_is_empty_when_specs_are_complete(self):
        result = assess_once("USB-C 65W 충전기를 수입해 판매",
                             {"rated_power": "65W", "ac_plug": "yes"})
        self.assertEqual(result["missing_information"], [])
        self.assertEqual(result["missing_information_detail"], [])

    def test_findings_keep_internal_missing_inputs(self):
        """기존 findings.missing_inputs 계약(필드·프롬프트·허용값)은 그대로 둔다."""
        result = assess_once("충전기를 수입해 판매")
        finding = result["findings"][0]
        fields = {item["field"] for item in finding["missing_inputs"]}
        self.assertEqual(fields, {"rated_power", "ac_plug"})
        for item in finding["missing_inputs"]:
            self.assertIn("prompt", item)
            self.assertIn("allowed_values", item)


class RegulationTagTest(unittest.TestCase):
    def test_each_finding_has_tags(self):
        result = assess_once("중국산 과자를 구매대행으로 들여와 판매")
        self.assertTrue(result["findings"])
        for finding in result["findings"]:
            with self.subTest(case=finding["case_id"]):
                self.assertTrue(finding["regulation_tags"])

    def test_top_level_tags_are_union_of_findings(self):
        result = assess_once("리튬이온 배터리가 내장된 무선 스피커를 수입해 판매",
                             {"battery_type": "리튬이온", "energy_density": "250Wh/L"})
        union = []
        for finding in result["findings"]:
            for tag in finding["regulation_tags"]:
                if tag not in union:
                    union.append(tag)
        self.assertEqual(result["regulation_tags"], union)
        self.assertIn("BATTERY_SAFETY", union)
        self.assertIn("RF_CONFORMITY", union)


class BackwardCompatibilityTest(unittest.TestCase):
    def test_all_previous_top_level_keys_still_exist(self):
        result = assess_once("중국산 과자를 구매대행으로 들여와 판매")
        for key in BASE_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, result)

    def test_verdict_contract_is_unchanged(self):
        for query in ("중국산 과자를 구매대행으로 들여와 판매", "적외선 리모컨을 수입해 판매",
                      "유아용 원목 완구를 수입해 판매"):
            with self.subTest(query=query):
                verdict = assess_once(query)["verdict"]
                self.assertIn(verdict["code"], ("check_likely", "info_needed", "low_risk"))
                self.assertIn("label_ko", verdict)
                self.assertIn("label_en", verdict)
                self.assertFalse(verdict["determinative"])
                self.assertTrue(verdict["note_ko"])

    def test_finding_contract_is_unchanged(self):
        finding = assess_once("중국산 과자를 구매대행으로 들여와 판매")["findings"][0]
        for key in ("case_id", "title", "issue_ko", "category", "verdict", "verdict_label_ko",
                    "verdict_label_en", "confidence", "reason", "matched_signals",
                    "missing_inputs", "misconception", "explanation", "scenario",
                    "next_steps", "notes", "legal_basis"):
            with self.subTest(key=key):
                self.assertIn(key, finding)

    def test_response_is_json_serializable(self):
        result = assess_once("블루투스 스피커를 수입해 판매")
        text = json.dumps(result, ensure_ascii=False)
        self.assertIn("assessment_status", text)
        self.assertIn("missing_information", text)

    def test_scope_limits_disclose_medical_device_gap(self):
        joined = " ".join(SCOPE_LIMITS_KO)
        self.assertIn("의료기기", joined)
        self.assertIn("위생용품", joined)
        result = assess_once("중국산 과자를 구매대행으로 들여와 판매")
        self.assertIn("의료기기", " ".join(result["scope_limits_ko"]))


class ServiceMetaTest(unittest.TestCase):
    def test_meta_exposes_schema_testset_and_status_levels(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        meta = call_tool("get_service_meta", {}, store)["result"]
        self.assertEqual(meta["schema_version"], SCHEMA_VERSION)
        self.assertEqual(meta["assessment_status_levels"], ASSESSMENT_STATUS_ORDER)
        self.assertEqual(meta["destination"], "KR")
        self.assertEqual(meta["jurisdiction"], "KR")
        self.assertIn("BATTERY_SAFETY", meta["regulation_tags"])
        # 0.1.4: 의료기기·위생용품 태그가 어휘에 추가됐다(필드 계약은 그대로).
        self.assertIn("MEDICAL_DEVICE_IMPORT", meta["regulation_tags"])
        self.assertIn("HYGIENE_PRODUCT_IMPORT", meta["regulation_tags"])
        self.assertEqual(meta["testset"]["cases"], 100)
        self.assertEqual(meta["testset"]["version"], "1.0.1")
        self.assertEqual(sum(meta["testset"]["domains"].values()), 100)
        # 기존 메타 계약 유지
        self.assertEqual(meta["service"], "CLNS")
        self.assertEqual(meta["verdict_levels"], ["check_likely", "info_needed", "low_risk"])


class WebUiSchemaTest(unittest.TestCase):
    def test_page_renders_standard_status_and_missing_information(self):
        page = web_ui.render_page()
        self.assertIn("assessment_status", page)
        self.assertIn("missing_information", page)
        self.assertIn("상태", page)
        self.assertIn("추가 확인 항목", page)

    def test_page_still_renders_when_new_fields_absent(self):
        """구버전 응답(새 필드 없음)에도 판정 블록이 깨지지 않아야 한다."""
        page = web_ui.render_page()
        self.assertIn("result = result || {}", page)
        self.assertIn("if (result.assessment_status)", page)

    def test_page_shows_jurisdiction_and_origin(self):
        page = web_ui.render_page()
        self.assertIn("목적지 ", page)
        self.assertIn("원산지 ", page)


class AnonymityTest(unittest.TestCase):
    """새 파일에도 개인정보·시크릿이 없어야 한다(서비스 식별자는 CLNS-KR 뿐)."""

    NEW_FILES = ("testset_100.json", os.path.join("import_compliance", "standards.py"),
                 os.path.join("tools", "build_testset_100.py"))

    def test_no_personal_data_or_secret_in_new_files(self):
        # 주의: 검사 패턴에도 실명을 적지 않는다(테스트 파일이 그대로 공개되므로).
        # 이름은 애초에 코드·데이터에 등장하지 않아야 하고, 여기서는 형식으로만 잡는다.
        patterns = [
            re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),          # 이메일
            re.compile(r"01[016789]-?\d{3,4}-?\d{4}"),       # 휴대전화
            re.compile(r"\d{6}-?[1-4]\d{6}"),                 # 주민등록번호 형태
            re.compile(r"DATA_GO_KR_SERVICE_KEY\s*=\s*\S{20,}"),
            re.compile(r"LAW_GO_KR_OC\s*=\s*\S{6,}"),
        ]
        for relative in self.NEW_FILES:
            path = os.path.join(SRC, relative)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for pattern in patterns:
                with self.subTest(file=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
