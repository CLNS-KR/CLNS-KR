"""3종 크로스 링크 + 식약처 의약품 API 실연동(2026-11-21 활용승인) 회귀 테스트.

검증 축
1. `CLNS` 홈에 **GRNT·FRNC 형제 서비스 링크**가 푸터와 안내 카드에 있다.
2. `CLNS Check`의 첫 프리셋이 **멜라토닌·수면영양제 직구**(해외직구 2병)로 채워지고
   의약품 입력 패널이 열리는 값을 넣는다.
3. `drugs.search_terms()`가 원산지·판매 수식어를 지워 성분명을 뽑는다.
4. 식약처 의약품 API 4종(허가정보·DUR·e약은요·마약류 오남용)을 가짜 transport로 호출해
   `drug_live` 블록·요약·정규화 필드가 만들어지고, 서비스키가 응답에 새지 않는다.

실행: python3 -m unittest discover -s tests   (네트워크 불필요)
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import api, drugs, web_ui  # noqa: E402
from import_compliance.live_api import LiveApiClient, load_env  # noqa: E402
from import_compliance.store import Store  # noqa: E402

FAKE_KEY = "FAKE_DRUG_KEY_7c1a"
CLNS_SELF = "https://clns-kr.onrender.com/"
GRNT_URL = "https://grnt-kr.onrender.com/"
FRNC_URL = "https://frnc.onrender.com/"


def _payload(items, total=None):
    return json.dumps({
        "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
        "body": {"pageNo": 1, "numOfRows": len(items), "totalCount": total if total is not None else len(items),
                 "items": items},
    }, ensure_ascii=False)


PERMIT_JSON = _payload([
    {"ITEM_SEQ": "202001452", "ITEM_NAME": "멜라토서방정2밀리그램(멜라토닌)",
     "ITEM_ENG_NAME": "Melato PR Tab. 2mg", "ENTP_NAME": "한림제약(주)",
     "ITEM_PERMIT_DATE": "20200302", "SPCLTY_PBLC": "전문의약품",
     "PRDUCT_TYPE": "[01120]최면진정제", "ITEM_INGR_NAME": "Melatonin",
     "PERMIT_KIND_CODE": "허가", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "202001453", "ITEM_NAME": "멜라토정2밀리그램(멜라토닌)",
     "ENTP_NAME": "한림제약(주)", "ITEM_PERMIT_DATE": "20200302",
     "SPCLTY_PBLC": "전문의약품", "PRDUCT_TYPE": "[01120]최면진정제",
     "ITEM_INGR_NAME": "Melatonin", "PERMIT_KIND_CODE": "허가", "CANCEL_NAME": "정상"},
], total=33)

DUR_JSON = _payload([
    {"ITEM_SEQ": "202001452", "ITEM_NAME": "멜라토서방정2밀리그램(멜라토닌)",
     "ENTP_NAME": "한림제약(주)", "ITEM_PERMIT_DATE": "2020March2nd",
     "ETC_OTC_CODE": "전문의약품", "CLASS_NO": "[112]최면진정제",
     "MATERIAL_NAME": "멜라토닌,,,밀리그램,별규,"},
])

EASY_JSON = _payload([{
    "entpName": "켄뷰코리아판매유한회사", "itemName": "어린이타이레놀산160밀리그램(아세트아미노펜)",
    "itemSeq": "202005623", "efcyQesitm": "이 약은 감기로 인한 발열 및 통증에 사용합니다.",
    "useMethodQesitm": "만 7~12세 소아는 1회 권장용량을 4~6시간마다 복용합니다.",
    "atpnWarnQesitm": "매일 세잔 이상 정기적 음주자는 의사와 상의하십시오.",
}])

NARCOTIC_JSON = _payload([
    {"DRUG_NO": "T12", "DRFSTF": "페닐프로파놀아민", "DRFSTF_ENG": "Phenylpropanolamine",
     "TYPE_CODE": "기타", "PHARM": "생체내이용률은 거의 100%", "SIDE_EFFECT": "고혈압, 불면"},
    {"DRUG_NO": "T31", "DRFSTF": "멜라토닌 유사체", "DRFSTF_ENG": "Melatonin analogue",
     "TYPE_CODE": "오남용", "PHARM": None, "SIDE_EFFECT": "졸림"},
])


class FakeTransport:
    """URL 조각으로 응답을 고르는 네트워크 없는 transport(호출 URL을 기록한다)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append(url)
        for fragment, response in self.routes.items():
            if fragment in url:
                return response[0], response[1], "application/json"
        return 404, "not found", "text/plain"


class DrugSearchTermTest(unittest.TestCase):
    def test_strips_origin_and_supplement_words(self):
        self.assertEqual(drugs.search_terms("미국산 멜라토닌 수면 영양제")[0], "멜라토닌")

    def test_keeps_latin_ingredient(self):
        self.assertEqual(drugs.search_terms("Cannabidiol 30정"), ["Cannabidiol"])

    def test_drops_ambiguous_unit_tokens(self):
        self.assertNotIn("30정", drugs.search_terms("아데랄 30정"))

    def test_brand_alias_maps_to_ingredient(self):
        self.assertEqual(drugs.search_terms("리탈린 10mg")[0], "메틸페니데이트")

    def test_empty_input(self):
        self.assertEqual(drugs.search_terms(""), [])


class DrugLiveApiTest(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport({
            "getDrugPrdtPrmsnInq08": (200, PERMIT_JSON),
            "getDurPrdlstInfoList03": (200, DUR_JSON),
            "getDrbEasyDrugList": (200, EASY_JSON),
            "getNrcdGnrlzList": (200, NARCOTIC_JSON),
        })
        self.live = LiveApiClient(service_key=FAKE_KEY, transport=self.transport)
        self.store = Store(":memory:")

    def _run(self, product="미국산 멜라토닌 수면 영양제"):
        return api.call_tool("check_drug_import",
                             {"product_name": product, "channel": "online",
                              "quantity": 2, "unit": "병"},
                             store=self.store, client_id="test-client", tier="free",
                             live=self.live)["result"]

    def test_four_drug_apis_are_called_with_normalized_term(self):
        self._run()
        urls = " ".join(self.transport.calls)
        for endpoint in ("getDrugPrdtPrmsnInq08", "getDurPrdlstInfoList03",
                         "getDrbEasyDrugList", "getNrcdGnrlzList"):
            self.assertIn(endpoint, urls)
        # 원본 제품명이 아니라 정규화한 성분명을 보낸다(URL 인코딩을 풀어서 확인).
        decoded = [urllib.parse.unquote(url) for url in self.transport.calls]
        self.assertTrue(any("item_name=멜라토닌" in url for url in decoded))
        self.assertFalse(any("미국산" in url for url in decoded))

    def test_drug_live_block_shape(self):
        result = self._run()
        block = result["drug_live"]
        self.assertEqual(block["state"], "live")
        self.assertEqual(block["search_term"], "멜라토닌")
        self.assertEqual(block["permit"]["match_count"], 33)
        self.assertEqual(block["permit"]["samples"][0]["classification"], "전문의약품")
        self.assertEqual(block["permit"]["samples"][0]["permit_date"], "2020-03-02")
        self.assertEqual(block["dur"]["samples"][0]["class_name"], "[112]최면진정제")
        self.assertEqual(block["easy"]["samples"][0]["item_name"], "어린이타이레놀산160밀리그램(아세트아미노펜)")
        self.assertEqual(block["narcotic"]["match_count"], 1)
        self.assertEqual(block["narcotic"]["matches"][0]["ingredient_ko"], "멜라토닌 유사체")
        self.assertIn("33건", block["summary_ko"])
        self.assertIn("전문의약품", block["summary_ko"])

    def test_check_block_exposes_live_summary_and_sources(self):
        result = self._run()
        check = result["drug_import_check"]
        self.assertEqual(check["state"], "kr_prescription_only")
        self.assertEqual(check["live_api_state"], "live")
        self.assertEqual(check["live_api_search_term"], "멜라토닌")
        self.assertIn("식약처", check["live_api_summary_ko"])
        self.assertEqual({row["state"] for row in check["api_candidates"]}, {"live"})
        sources = {row.get("source_id"): row for row in result["data_provenance"]["sources"]}
        for source_id in ("mfds_drug_permit", "mfds_drug_easy", "mfds_dur", "mfds_narcotic_misuse"):
            self.assertEqual(sources[source_id]["state"], "live")

    def test_service_key_never_serialized(self):
        result = self._run()
        dumped = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(FAKE_KEY, dumped)
        self.assertNotIn("serviceKey", dumped)

    def test_without_live_client_says_skipped(self):
        result = api.call_tool("check_drug_import",
                               {"product_name": "미국산 멜라토닌 수면 영양제", "channel": "online"},
                               store=self.store, client_id="test-client", tier="free")["result"]
        self.assertNotIn("drug_live", result)
        self.assertIn("건너뛰었습니다", result["drug_import_check"]["coverage_ko"])


class CrossLinkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_footer_links_sibling_services(self):
        footer = self.page[self.page.index("<footer>"):self.page.index("</footer>")]
        self.assertIn(GRNT_URL, footer)
        self.assertIn(FRNC_URL, footer)
        self.assertIn("GRNT", footer)
        self.assertIn("FRNC", footer)

    def test_sibling_card_inside_main(self):
        main = self.page[self.page.index("<main>"):self.page.index("</main>")]
        self.assertIn('id="siblings"', main)
        self.assertIn(GRNT_URL, main)
        self.assertIn(FRNC_URL, main)

    def test_links_open_in_new_tab_without_referrer(self):
        for url in (GRNT_URL, FRNC_URL):
            anchor = self.page[:self.page.index(url) + len(url)]
            start = anchor.rindex("<a ")
            tag = self.page[start:self.page.index(">", start) + 1]
            self.assertIn('rel="noopener noreferrer"', tag)
            self.assertIn('target="_blank"', tag)

    def test_melatonin_preset_is_first_and_fills_drug_inputs(self):
        form = self.page[self.page.index('id="check-form"'):]
        form = form[:form.index("</form>")]
        self.assertIn('id="preset-melatonin"', form)
        self.assertIn("멜라토닌 직구", form)
        self.assertLess(form.index("멜라토닌 직구"), form.index("강아지 간식"))
        self.assertIn('"melatonin": {product: "미국산 멜라토닌 수면 영양제"', self.page)
        self.assertIn('channel: "online"', self.page)

    def test_data_note_reflects_approved_drug_apis(self):
        self.assertIn("2026-11-21 활용승인", self.page)
        self.assertNotIn("식약처 의약품 허가정보·e약은요·DUR API는 활용승인 전", self.page)

    def test_live_section_markers_are_in_page(self):
        self.assertIn("식약처 의약품 실시간 대조", self.page)
        for marker in ("제품 허가정보", "DUR 품목정보", "e약은요", "마약류 약물·오남용 정보",
                       "15095677", "15059486", "15075057", "15058963", "function drugLiveBlock"):
            self.assertIn(marker, self.page, marker)


def _real_key_present() -> bool:
    try:
        env = load_env()
    except Exception:  # noqa: BLE001 - .env 가 없으면 실호출 테스트는 건너뛴다
        return False
    return bool(env.get("DATA_GO_KR_SERVICE_KEY"))


if __name__ == "__main__":
    unittest.main()
