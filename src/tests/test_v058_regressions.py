"""0.5.8 점검 회귀 — 전수조사(2026-11-22)에서 나온 결함을 다시 열리지 않게 고정한다.

무엇을 지키는가
---------------
1. `/healthz` 는 요청 제한(429)에서 빠진다 — 배포 플랫폼·업타임 모니터가 429 를 받으면
   정상 서비스가 장애로 읽힌다.
2. `robots.txt` 의 **봇별 그룹에도** `Disallow: /v1/` 이 있다. robots.txt 는 크롤러마다
   가장 구체적으로 일치하는 그룹 하나만 적용하므로, 봇별 그룹에 `Allow: /` 만 있으면
   `/v1/` 차단이 사라진다.
3. `GET /mcp` 는 405 를 돌려주되 빈 본문이 아니라 쓰는 법을 적은 JSON 을 준다.
4. `/v1/meta` 의 `service_axes` 가 화면 탭(4개)과 같다.
5. 스냅샷 첫 관측일은 `baseline` 으로 표시되고, 추이 안내 문구가 그 총량을 '신규'로
   세지 않는다(전일 비교가 없는 날의 1415건이 매일 '신규 급증'으로 보이던 문제).
6. 세관장확인 요건 표의 머리말이 **묶은 뒤 행 수**를 쓰고, 기관별 원본 건수를 함께 밝힌다
   (요건 6건이라고 쓰고 표에는 2행만 나오던 불일치).
7. DUR 성분명의 `,,,`·끝 쉼표를 화면에서 읽히게 다듬는다.
8. llms.txt 가 실제 툴 개수·법령 고지 페이지·해설/메타 툴을 담는다.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import api, static_files, web_ui  # noqa: E402
from import_compliance.api import TOOL_DEFS  # noqa: E402
from import_compliance.live_api import (_tidy_ingredient_list,  # noqa: E402
                                        normalize_drug_dur_item)
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402


class RobotsGroupsTest(unittest.TestCase):
    CRAWLERS = ("Googlebot", "Bingbot", "GPTBot", "ClaudeBot", "PerplexityBot", "Yeti")

    def test_every_bot_group_keeps_api_disallow(self):
        text = static_files.robots_txt("https://example.test")
        for agent in self.CRAWLERS:
            with self.subTest(agent=agent):
                block = text.split(f"User-agent: {agent}", 1)[1].split("\n\n", 1)[0]
                self.assertIn("Allow: /", block)
                self.assertIn("Disallow: /v1/", block)

    def test_star_group_still_blocks_api(self):
        text = static_files.robots_txt("https://example.test")
        star = text.split("User-agent: *", 1)[1].split("\n\n", 1)[0]
        self.assertIn("Disallow: /v1/", star)


class LlmsTxtTest(unittest.TestCase):
    def test_lists_every_tool_and_notice_pages(self):
        text = static_files.llms_txt("https://example.test")
        self.assertIn(f"툴 {len(TOOL_DEFS)}종", text)
        for path in ("/privacy", "/terms", "/about"):
            self.assertIn("https://example.test" + path, text)
        for tool in ("explain_trap", "get_service_meta", "check_feed_import"):
            self.assertIn(tool, text)

    def test_no_broken_particle_typo(self):
        self.assertNotIn("조회 실패은", static_files.llms_txt())


class ServiceMetaAxesTest(unittest.TestCase):
    def test_axes_match_ui_tabs(self):
        import html as html_module

        store = Store(":memory:")
        self.addCleanup(store.close)
        meta = api.tool_get_service_meta({}, store, "t", "free")
        axes = meta["result"]["service_axes"]
        page = html_module.unescape(web_ui.render_page())
        for axis in axes:
            self.assertIn(axis, page, axis)
        self.assertEqual(len(axes), 4)


class HttpBehaviourTest(unittest.TestCase):
    def start(self, **kwargs):
        store = Store(":memory:")
        self.addCleanup(store.close)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, **kwargs))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1], store

    def raw(self, port, path, method="GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_healthz_is_never_rate_limited(self):
        port, _ = self.start(rate_limit=2)
        for _ in range(6):
            status, _, body = self.raw(port, "/healthz")
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["ok"])

    def test_get_mcp_explains_post_only(self):
        port, _ = self.start()
        status, headers, body = self.raw(port, "/mcp")
        self.assertEqual(status, 405)
        self.assertEqual(headers.get("Allow"), "POST, OPTIONS")
        payload = json.loads(body)
        self.assertEqual(payload["error"], "method_not_allowed")
        self.assertIn("/v1/mcp", payload["note_ko"])

    def test_head_matches_get_status(self):
        port, _ = self.start()
        for path in ("/", "/v1/meta", "/v1/mcp", "/p/", "/p/usb-mini-fan", "/p/no-such",
                     "/guides/", "/guides/no-such", "/about", "/nope-xyz"):
            with self.subTest(path=path):
                get_status = self.raw(port, path)[0]
                head_status = self.raw(port, path, method="HEAD")[0]
                self.assertEqual(head_status, get_status)


class SnapshotBaselineTest(unittest.TestCase):
    RECALL_HEADER = ("인증번호,모델명,제품명,브랜드명,사업자구분,법정제품분류,리콜종류,리콜사업자명,"
                     "제조국가명,제조사명,제조사국가명,리콜방법,위해유형,안전성조사명,등록일")

    def make_store(self) -> Store:
        from import_compliance import recall_index

        store = Store(":memory:")
        self.addCleanup(store.close)
        recall_index.load_items(store, "\n".join([
            self.RECALL_HEADER,
            "C1,M-OLD,완구 자동차,토이브랜드,제조업,완구>기타완구>기타,리콜명령,토이브랜드,"
            "중국,토이제조,중국,회수,유해물질,어린이완구,2026-11-09",
        ]) + "\n")
        return store

    def test_first_observation_is_baseline_and_not_counted_as_new(self):
        from import_compliance import snapshots

        store = self.make_store()
        first = snapshots.take_snapshot(store, "2026-11-20", cosmetic_catalog={"prohibited": {}, "restricted": {}},
                                        drug_catalog={})
        self.assertTrue(first["first_observation"])
        self.assertTrue(first["diff"]["baseline"])
        data = snapshots.trends(store, days=7, today="2026-11-20")
        self.assertTrue(data["series"][0]["baseline"])
        self.assertTrue(data["last_observed_diff"]["baseline"])

        payload = api.tool_get_compliance_trends({"days": 7, "as_of": "2026-11-20"}, store, "t", "free")
        lines = payload["result"]["answer"]["guidance"]
        self.assertTrue(any("첫 관측" in line for line in lines), lines)
        self.assertFalse(any("스냅샷에서는 전일 대비 신규" in line for line in lines), lines)

    def test_second_day_is_a_real_diff(self):
        from import_compliance import snapshots

        store = self.make_store()
        kwargs = {"cosmetic_catalog": {"prohibited": {}, "restricted": {}}, "drug_catalog": {}}
        snapshots.take_snapshot(store, "2026-11-20", **kwargs)
        second = snapshots.take_snapshot(store, "2026-11-21", **kwargs)
        self.assertFalse(second["diff"]["baseline"])
        self.assertEqual(second["diff"]["new"], 0)
        self.assertFalse(snapshots.trends(store, days=7, today="2026-11-21")["series"][-1]["baseline"])
        payload = api.tool_get_compliance_trends({"days": 7, "as_of": "2026-11-21"}, store, "t", "free")
        lines = payload["result"]["answer"]["guidance"]
        self.assertTrue(any("스냅샷에서는 전일 대비 신규" in line for line in lines), lines)


class RequirementCountLabelTest(unittest.TestCase):
    def test_label_uses_grouped_rows_and_keeps_raw_count(self):
        page = web_ui.render_page()
        self.assertIn("기관별 응답", page)
        self.assertIn("요건 \" + esc(String(rows.length)) + \"종", page)


class DurIngredientTest(unittest.TestCase):
    def test_commas_are_tidied(self):
        self.assertEqual(_tidy_ingredient_list("멜라토닌,,,밀리그램,별규,"), "멜라토닌, 밀리그램, 별규")
        self.assertEqual(_tidy_ingredient_list(""), "")
        row = normalize_drug_dur_item({"MATERIAL_NAME": "멜라토닌,,,밀리그램,별규,",
                                       "ITEM_NAME": "멜라토서방정2밀리그램(멜라토닌)"})
        self.assertEqual(row["material"], "멜라토닌, 밀리그램, 별규")


class CorpusCitationTest(unittest.TestCase):
    def test_no_third_party_mirror_urls(self):
        root = os.path.dirname(SRC)
        raw = open(os.path.join(root, "src", "traps_20.json"), encoding="utf-8").read()
        for host in ("govbrief.kr", "lawplayer.com", "albup.co.kr"):
            self.assertNotIn(host, raw, host)

    def test_administrative_rule_urls_are_official(self):
        root = os.path.dirname(SRC)
        data = json.load(open(os.path.join(root, "src", "traps_20.json"), encoding="utf-8"))
        for trap in data["traps"]:
            for basis in trap["legal_basis"]:
                if "고시" in basis["law"] or "규정" in basis["law"] or "공고" in basis["law"]:
                    self.assertTrue(
                        basis["url"].startswith("https://www.law.go.kr/LSW/")
                        or basis["url"].startswith("https://www.customs.go.kr/")
                        or basis["url"].startswith("https://www.law.go.kr/법령/"),
                        (trap["id"], basis["law"], basis["url"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
