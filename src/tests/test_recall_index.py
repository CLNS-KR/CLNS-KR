"""리콜 로컬 인덱스 테스트: 파일데이터 파싱·적재·검색·툴 경로.

실행: python3 tests/test_recall_index.py   (pytest 불필요, 표준 unittest)
네트워크를 쓰지 않는다. 실제 내려받은 파일이 있으면 통합 검증 1건을 추가로 돈다.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import recall_index  # noqa: E402
from import_compliance.api import call_tool  # noqa: E402
from import_compliance.store import Store  # noqa: E402

ITEM_CSV = (
    "인증번호,모델명,제품명,브랜드명,사업자구분,법정제품분류,리콜종류,리콜사업자명,"
    "제조국가명,제조사명,제조사국가명,리콜방법,위해유형,안전성조사명,등록일\r\n"
    "B053R138-3003,R03P,건전지,오로라,수입,화학>건전지>망간건전지,명령에따른리콜,(주)오로라,"
    "국외>아시아지역>중국,(주)오로라,국내>아시아지역>대한민국,환불,유해물질,1차,2021-02-24\r\n"
    "SU07219-19001,MF-1000,무선 미니 선풍기,쿨러맥스,수입,전기기기>선풍기>선풍기,자발적리콜,쿨러맥스,"
    "국외>아시아지역>중국,쿨러맥스,국외>아시아지역>중국,교환,감전,1차,2020-06-26\r\n"
    ",,,,,,,,,,,,,,\r\n"
)

STATS_CSV = (
    "연도,생활용품_리콜명령,생활용품_리콜권고,생활용품_자발적 리콜,전기용품_리콜명령,"
    "전기용품_리콜권고,전기용품_자발적 리콜,어린이제품_리콜명령,어린이제품_리콜권고,어린이제품_자발적 리콜\r\n"
    "2024,49,4,6,55,1,15,130,1,5\r\n"
    "2025,44,2,10,46,1,17,128,1,6\r\n"
)


class ParseTest(unittest.TestCase):
    def test_parse_items_skips_blank_rows(self):
        rows = recall_index.parse_items(ITEM_CSV)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["product_name"], "건전지")
        self.assertEqual(rows[0]["category"], "화학>건전지>망간건전지")
        self.assertEqual(rows[0]["registered_on"], "2021-02-24")

    def test_decode_csv_handles_cp949(self):
        text = recall_index.decode_csv(ITEM_CSV.encode("cp949"))
        self.assertIn("인증번호", text)

    def test_parse_stats_widens_to_long(self):
        rows = recall_index.parse_stats(STATS_CSV)
        self.assertEqual(len(rows), 18)
        pick = {(r["year"], r["category"], r["disposition"]): r["count"] for r in rows}
        self.assertEqual(pick[("2025", "전기용품", "리콜명령")], 46)
        self.assertEqual(pick[("2024", "어린이제품", "자발적리콜")], 5)


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        recall_index.load_items(self.store, ITEM_CSV)
        recall_index.load_stats(self.store, STATS_CSV)

    def test_summary_coverage(self):
        info = recall_index.summary(self.store)
        self.assertEqual(info["items"], 2)
        self.assertEqual(info["first_registered_on"], "2020-06-26")
        self.assertEqual(info["last_registered_on"], "2021-02-24")
        self.assertEqual(info["stats_years"], ["2024", "2025"])
        self.assertIn("갱신이 멈춘", info["coverage_note_ko"])

    def test_search_by_product_and_model(self):
        hits = recall_index.search(self.store, ["무선 선풍기"])
        self.assertTrue(hits)
        self.assertEqual(hits[0]["product_name"], "무선 미니 선풍기")
        exact = recall_index.search(self.store, ["MF-1000"], model="MF-1000")
        self.assertEqual(exact[0]["model"], "MF-1000")
        self.assertIn("model:exact", exact[0]["matched"])

    def test_search_unknown_returns_empty(self):
        self.assertEqual(recall_index.search(self.store, ["가습기"]), [])

    def test_tool_uses_local_index(self):
        out = call_tool("lookup_recall", {"brand": "쿨러맥스", "product_name": "선풍기"}, self.store)
        self.assertTrue(out["ok"])
        block = out["result"]["recall"]
        self.assertEqual(block["state"], "local_index")
        self.assertEqual(block["match_count"], 1)
        self.assertFalse(block["fresh"])  # 정적 스냅샷임을 숨기지 않는다
        self.assertEqual(out["result"]["verdict"]["code"], "check_likely")

    def test_tool_reports_zero_match_not_absence(self):
        out = call_tool("lookup_recall", {"brand": "없는브랜드"}, self.store)
        block = out["result"]["recall"]
        self.assertEqual(block["state"], "local_index_no_match")
        self.assertEqual(out["result"]["verdict"]["code"], "info_needed")
        self.assertIn("0건은", block["note_ko"])

    def test_stats_table(self):
        rows = recall_index.stats_table(self.store)
        self.assertEqual(len(rows), 18)
        self.assertEqual(rows[0]["year"], "2025")


class IndexFileCopyTest(unittest.TestCase):
    """이미 빌드된 인덱스 파일(데이터 배포용)을 작업 DB로 복사하는 경로."""

    def test_copy_from_index_file_keeps_source_untouched(self):
        index_path = recall_index.default_index_path()
        if not os.path.exists(index_path):
            self.skipTest("recall index sqlite not built")
        before = os.stat(index_path)
        work = Store(":memory:")
        self.addCleanup(work.close)
        copied = recall_index.load_from_index(work)
        self.assertGreaterEqual(copied, 800)
        self.assertGreater(recall_index.summary(work)["items"], 0)
        self.assertTrue(recall_index.search(work, ["전지"], limit=2))
        after = os.stat(index_path)
        self.assertEqual((before.st_size, before.st_mtime), (after.st_size, after.st_mtime))

    def test_copy_skipped_when_store_is_the_index(self):
        index_path = recall_index.default_index_path()
        if not os.path.exists(index_path):
            self.skipTest("recall index sqlite not built")
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.path = index_path  # 인덱스 파일을 직접 작업 DB로 쓰는 경우
        self.assertEqual(recall_index.load_from_index(store), 0)


class RealFileIntegrationTest(unittest.TestCase):
    """실제 내려받은 파일데이터가 있으면 적재 건수를 확인한다(없으면 skip)."""

    def test_real_csv_loads(self):
        raw_dir = recall_index.default_raw_dir()
        path = os.path.join(raw_dir, "recall_15040696.csv")
        if not os.path.exists(path):
            self.skipTest("real recall CSV not downloaded")
        store = Store(":memory:")
        self.addCleanup(store.close)
        with open(path, "rb") as handle:
            count = recall_index.load_items(store, recall_index.decode_csv(handle.read()))
        self.assertGreaterEqual(count, 800)
        info = recall_index.summary(store)
        self.assertEqual(info["last_registered_on"], "2022-07-26")


if __name__ == "__main__":
    unittest.main(verbosity=2)
