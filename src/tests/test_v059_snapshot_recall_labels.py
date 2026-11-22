"""0.5.9 회귀 — 스냅샷 backfilled 분류와 리콜 색인 기준일 표시.

배경
----
1. `data/snapshots/` 에는 2026-10-23~11-19 의 `origin="backfilled"` 재구성 파일 28장이
   실제 관측분(2026-11-20~)과 같은 폴더에 있다. 항목(`items`)이 없어 시드 복원은 안 되는데
   예전 코드는 이를 `unreadable`(읽기 실패)로 분류해 손상된 파일과 구분되지 않았다.
2. 국내 리콜 로컬 색인은 2022-07-26 에서 멈춘 정적 파일데이터다. 응답 문장 안에만 묻혀 있던
   기준일을 값(`index_as_of`)과 라벨로 드러내 "최신 리콜까지 본 것"으로 오해되지 않게 한다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import recall_index, snapshots, static_files, web_ui  # noqa: E402
from import_compliance.api import call_tool  # noqa: E402
from import_compliance.store import Store  # noqa: E402

ITEM_CSV = (
    "인증번호,모델명,제품명,브랜드명,사업자구분,법정제품분류,리콜종류,리콜사업자명,"
    "제조국가명,제조사명,제조사국가명,리콜방법,위해유형,안전성조사명,등록일\r\n"
    "B053R138-3003,R03P,건전지,오로라,수입,화학>건전지>망간건전지,명령에따른리콜,(주)오로라,"
    "국외>아시아지역>중국,(주)오로라,국내>아시아지역>대한민국,환불,유해물질,1차,2021-02-24\r\n"
)


class BackfilledSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.dir = tempfile.mkdtemp(prefix="clns-v059-")

    def _write(self, day: str, payload: dict) -> str:
        path = os.path.join(self.dir, f"{day}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        return path

    def test_backfilled_counts_only_file_is_not_unreadable(self):
        self._write("2026-10-23", {"schema": "clns.snapshots/1", "day": "2026-10-23",
                                   "origin": "backfilled",
                                   "counts": {"recall": 846, "disposition": 0}})
        result = snapshots.seed_snapshots(self.store, self.dir)
        self.assertEqual(result["days"], [])
        self.assertEqual(result["counts_only"], ["2026-10-23"])
        self.assertEqual(result["unreadable"], [])
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM compliance_snapshots").fetchone()["n"], 0)

    def test_real_observed_file_still_seeds(self):
        self._write("2026-11-20", {
            "schema": "clns.snapshots/1", "day": "2026-11-20", "origin": "observed",
            "counts": {"recall": 1},
            "items": {"recall": [{"key": "R-1", "label": "건전지", "category": "화학",
                                  "event_date": "2021-02-24", "fingerprint": "abc"}]},
        })
        result = snapshots.seed_snapshots(self.store, self.dir)
        self.assertEqual(result["days"], ["2026-11-20"])
        self.assertEqual(result["counts_only"], [])
        self.assertEqual(result["unreadable"], [])

    def test_corrupt_file_is_still_unreadable(self):
        with open(os.path.join(self.dir, "2026-10-24.json"), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        result = snapshots.seed_snapshots(self.store, self.dir)
        self.assertEqual(result["unreadable"], ["2026-10-24.json"])
        self.assertEqual(result["counts_only"], [])

    def test_persistence_status_names_counts_only_days(self):
        self._write("2026-10-25", {"day": "2026-10-25", "origin": "backfilled",
                                   "counts": {"recall": 846}})
        snapshots.seed_persistence(self.store, seed_dir=self.dir,
                                   usage_path=os.path.join(self.dir, "nope.json"))
        info = snapshots.persistence_status()
        self.assertEqual(info["counts_only_days"], ["2026-10-25"])
        self.assertIn("backfilled", info["counts_only_note_ko"])

    def test_snapshot_folder_readme_documents_origin(self):
        path = os.path.join(ROOT, "data", "snapshots", "README.md")
        self.assertTrue(os.path.exists(path), path)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("backfilled", text)
        self.assertIn("2026-11-20", text)
        self.assertIn("counts_only", text)


class RecallIndexAsOfTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        recall_index.load_items(self.store, ITEM_CSV)

    def test_summary_exposes_index_as_of(self):
        info = recall_index.summary(self.store)
        self.assertEqual(info["last_registered_on"], "2021-02-24")
        self.assertEqual(info["index_as_of"], "2021-02-24")
        self.assertFalse(info["latest_included"])
        self.assertIn("최신 리콜 미포함", info["coverage_label_ko"])
        self.assertIn("2021-02-24", info["coverage_note_ko"])

    def test_tool_envelope_shows_as_of_and_label(self):
        out = call_tool("lookup_recall", {"product_name": "건전지"}, self.store)
        result = out["result"]
        block = result["recall"]
        self.assertEqual(block["index_as_of"], "2021-02-24")
        self.assertFalse(block["latest_included"])
        self.assertIn("최신 리콜 미포함", block["coverage_label_ko"])
        self.assertEqual(block["coverage"]["index_as_of"], "2021-02-24")
        self.assertIn("최신 리콜은 포함되지 않습니다", result["basis_note_ko"])

    def test_zero_match_keeps_as_of_label(self):
        out = call_tool("lookup_recall", {"brand": "없는브랜드"}, self.store)
        block = out["result"]["recall"]
        self.assertEqual(block["state"], "local_index_no_match")
        self.assertIn("최신 리콜 미포함", block["coverage_label_ko"])

    def test_default_index_as_of_constant(self):
        self.assertEqual(recall_index.INDEX_AS_OF, "2022-07-26")
        self.assertIn("2022-07-26", recall_index.INDEX_AS_OF_LABEL_KO)


class RecallLabelSurfaceTest(unittest.TestCase):
    """웹 화면·llms.txt·툴 설명에도 기준일이 드러나는지."""

    def test_web_page_shows_as_of_label(self):
        html = web_ui.render_page()
        self.assertIn("2022-07-26 기준", html)
        self.assertIn("최신 리콜 미포함", html)
        self.assertIn("recall.coverage_label_ko", html)

    def test_llms_txt_marks_as_of(self):
        text = static_files.llms_txt()
        self.assertIn("2022-07-26 기준 과거 색인", text)

    def test_tool_manifest_description_marks_as_of(self):
        from import_compliance.api import TOOL_DEFS
        tool = next(item for item in TOOL_DEFS if item["name"] == "lookup_recall")
        self.assertIn("2022-07-26", tool["description_ko"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
