"""0.5.10 회귀 — 첫 화면 단순화와 결과 결론 요약.

무엇을 고정하는가
----------------
1. **첫 화면**: 질문 1개 + 입력창 1개 + 큰 버튼 1개. 세부 조건(HS·원산지·품목군·
   수입 목적·무선·어린이·광고·전성분)은 접힌 `details` 안에 있고, 탭 바는 첫 화면
   아래(보조 도구)로 내려간다.
2. **결과 화면**: 맨 위가 "이 상품, 핵심 체크리스트 N가지" 요약 카드이고,
   N 은 접혀 있는 체크리스트 항목 수와 정확히 같다. 필수 인증·주의할 점·예상
   비용·기간 세 칸이 한 화면에 들어가고, 근거 법령·리콜 같은 상세는 접힌다.
3. **계약 유지**: `/v1/*`·`/mcp` 링크, JSON-LD·og:image, 리콜 기준일(2022-07-26),
   공유 바 3개, 폼 필드 id 는 그대로다.

실행: PYTHONPATH=src python3 -m unittest discover -s src/tests -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import web_ui  # noqa: E402
from import_compliance.standards import REGULATION_TAGS  # noqa: E402

try:  # 페이지 스크립트를 실제로 돌려 보기 위한 선택 의존
    import quickjs  # type: ignore

    HAVE_QUICKJS = True
except Exception:  # noqa: BLE001
    quickjs = None  # type: ignore
    HAVE_QUICKJS = False

# 세부 조건으로 접혀 있어야 하는 입력들(첫 화면에 펼쳐 두지 않는다).
DETAIL_FIELD_IDS = (
    "hs", "origin", "kind", "rra", "drug-qty", "drug-unit", "drug-rx",
    "cosmetic-ingredients-onestop", "ad-copy-onestop", "ad-label-onestop",
)


class FirstScreenTest(unittest.TestCase):
    """첫 화면은 질문 하나·입력창 하나·버튼 하나."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()
        start = cls.page.index('id="tab-check"')
        cls.hero = cls.page[start:cls.page.index('id="result"', start)]

    def test_single_question_and_one_input_on_first_screen(self):
        self.assertIn("무엇을 수입·판매하시나요?", self.hero)
        # '세부 조건 선택' 앞(= 실제 첫 화면)만 센다.
        above_fold = self.hero[: self.hero.index("세부 조건 선택")]
        self.assertEqual(above_fold.count("<input"), 1, "첫 화면 입력창은 품목명 하나여야 합니다")
        self.assertEqual(above_fold.count("<select"), 0, "첫 화면에 선택 목록이 펼쳐져 있습니다")
        self.assertEqual(above_fold.count('role="radiogroup"'), 0, "첫 화면에 라디오 선택지가 펼쳐져 있습니다")

    def test_one_primary_button_and_it_comes_before_details(self):
        self.assertEqual(self.hero.count('class="primary big"'), 1)
        # 버튼은 세부 조건 접기보다 앞에 있어야 스크롤 없이 누를 수 있다.
        self.assertLess(self.hero.index('id="check-submit"'), self.hero.index("세부 조건 선택"))

    def test_advanced_fields_are_inside_closed_details(self):
        fold_at = self.hero.index("세부 조건 선택")
        for field_id in DETAIL_FIELD_IDS:
            with self.subTest(field=field_id):
                self.assertGreater(self.hero.index(f'id="{field_id}"'), fold_at,
                                   f"{field_id} 가 접힌 영역 밖(첫 화면)에 있습니다")
        # 기본은 접힌 상태여야 한다(open 속성을 두지 않는다).
        self.assertNotRegex(self.hero, r"<details[^>]*\bopen\b")

    def test_tab_bar_is_below_the_hero_and_uses_short_korean_labels(self):
        self.assertGreater(self.page.index('class="tabs"'), self.page.index('id="tab-check"'))
        self.assertGreater(self.page.index('class="tabs"'), self.page.index("무엇을 수입·판매하시나요?"))
        for label in (">규제·인증<", ">한글표시사항<", ">HS·리콜<", ">API·MCP<"):
            self.assertIn(label, self.page)
        # 영문 축 이름은 툴팁(title)으로 남겨 /v1/meta 의 service_axes 와 연결을 유지한다.
        for axis in ("CLNS Check", "CLNS Label", "CLNS Intelligence", "CLNS API &amp; MCP"):
            self.assertIn(f'title="{axis}', self.page)

    def test_full_width_single_column_on_a_phone(self):
        # 390px 폭: 검색 줄이 세로로 쌓이고 큰 버튼이 폭을 채운다.
        self.assertIn("@media (max-width:560px)", self.page)
        block = self.page[self.page.index("@media (max-width:560px)") :][:400]
        self.assertIn(".searchrow{flex-direction:column}", block)
        self.assertIn("button.primary.big{width:100%}", block)
        # 요약 3칸도 좁은 화면에서는 1열로 쌓는다.
        self.assertIn(".sumgrid{grid-template-columns:1fr}", self.page)

    def test_example_chips_do_not_wrap_into_rows(self):
        css = self.page[self.page.index(".presets{"):]
        css = css[: css.index("}")]
        self.assertIn("flex-wrap:nowrap", css)
        self.assertIn("overflow-x:auto", css)


class ResultSummaryTest(unittest.TestCase):
    """결과 맨 위의 결론 요약 카드."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_summary_card_exists_with_three_answer_boxes(self):
        self.assertIn("function resultSummaryCard(", self.page)
        self.assertIn("이 상품, 핵심 체크리스트", self.page)
        for heading in ("<h3>필수 인증</h3>", "<h3>주의할 점</h3>", "<h3>예상 비용·기간</h3>"):
            self.assertIn(heading, self.page)
        # 요약 카드가 결과의 첫 카드여야 한다.
        self.assertLess(self.page.index("resultSummaryCard(result, data)"),
                        self.page.index("sectionCollapsible(\"판정 요지\""))

    def test_summary_numbers_come_from_the_checklist(self):
        self.assertIn("function checklistItems(", self.page)
        self.assertIn("return checklistItems(result).length;", self.page)

    def test_details_are_collapsed_behind_summary(self):
        for needle in ('sectionCollapsible("판정 요지"', 'sectionCollapsible("근거 법령·조항"',
                       'sectionCollapsible("면책·이용 범위"'):
            self.assertIn(needle, self.page)
        # 리콜 기준일과 '최신 리콜 미포함' 은 접힌 카드 제목에도 남는다.
        self.assertIn("로컬 리콜 참고 (국표원 · 2022-07-26 기준)", self.page)
        self.assertIn("최신 리콜 미포함", self.page)

    def test_tag_labels_come_from_the_standard_vocabulary(self):
        self.assertIn('var TAG_LABELS_KO = {"', self.page)
        for code in ("RF_CONFORMITY", "BATTERY_SAFETY", "CUSTOMS_CHECKPOINT"):
            self.assertIn(code, self.page, code)
            self.assertIn(REGULATION_TAGS[code]["label_ko"], self.page, code)
        # 태그 사전이 비어도 첫 화면이 죽지 않아야 한다.
        self.assertEqual(web_ui.render_page().count("__TAG_LABELS__"), 0)

    def test_regulation_tag_labels_helper_is_total(self):
        labels = web_ui.regulation_tag_labels()
        self.assertEqual(set(labels), set(REGULATION_TAGS))
        self.assertTrue(all(isinstance(v, str) for v in labels.values()))


@unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
class SummaryRenderTest(unittest.TestCase):
    """실제로 렌더해 본 요약 카드 — 개수 일치·내부 코드 비노출."""

    EXTRA = "globalThis.__ui = {resultSummaryCard: resultSummaryCard, checklistItems: checklistItems};"

    @classmethod
    def setUpClass(cls):
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import test_v052_p0_p1_regressions as base  # 같은 tests/ 폴더의 DOM 스텁 재사용

        cls.base = base
        script = base.inline_script(web_ui.render_page()).rstrip()
        marker = "})();"
        if not script.endswith(marker):
            raise unittest.SkipTest("페이지 스크립트가 예상한 IIFE 형태가 아닙니다")
        body = script[: -len(marker)] + cls.EXTRA + marker
        cls.ctx = quickjs.Context()
        cls.ctx.eval(base.JS_STUB.replace("__SEARCH__", "").replace("__HASH__", ""))
        cls.ctx.eval(body)
        cls.result = {
            "verdict": {"code": "check_likely", "label_ko": "확인 대상 가능성 높음"},
            "regulation_tags": ["RF_CONFORMITY", "BATTERY_SAFETY", "KOREAN_LABELING"],
            "findings": [
                {"verdict": "check_likely", "issue_ko": "무선기기의 전파 적합성평가", "missing_inputs": []},
                {"verdict": "info_needed", "issue_ko": "리튬 배터리 인증과 운송 요건", "missing_inputs": []},
            ],
            "missing_information": ["battery_type", "energy_density"],
            "next_actions": ["기자재별 기기부호 확인", "지정시험기관 시험성적서 준비"],
            "data_provenance": {"checked_at": "2026-11-22T15:00:00+09:00"},
            "tariff_fta": {"base_rate_hint": "0% ~ 8% (ITA 대상 0%)", "vat_rate": "10% (합산액의 10%)"},
        }
        cls.html = cls.ctx.eval("__ui.resultSummaryCard(" + json.dumps(cls.result, ensure_ascii=False)
                                + ", {product: '중국산 무선이어폰'})")

    def test_count_matches_checklist_length(self):
        count = self.ctx.eval("__ui.checklistItems(" + json.dumps(self.result, ensure_ascii=False) + ").length")
        self.assertIn(f"핵심 체크리스트 <em>{count}</em>가지", self.html)
        start = self.html.index('<ul class="check">')
        check_list = self.html[start : self.html.index("</ul>", start)]
        self.assertEqual(check_list.count("<li>"), count, "제목의 개수와 실제 체크리스트 항목 수가 다릅니다")

    def test_certs_are_korean_labels_not_tags(self):
        self.assertIn("전파 적합성평가", self.html)
        self.assertIn("전지·배터리 안전", self.html)
        for code in ("RF_CONFORMITY", "BATTERY_SAFETY", "KOREAN_LABELING"):
            self.assertNotIn(code, self.html, "내부 규제 태그가 그대로 노출됩니다")

    def test_cost_lines_are_short_and_labeled(self):
        self.assertIn("예상 관세", self.html)
        self.assertIn("0% ~ 8%", self.html)
        self.assertNotIn("ITA 대상 0%", self.html, "괄호 설명은 요약에서 잘라야 합니다")
        self.assertIn("인증·통관 비용·기간", self.html)

    def test_summary_carries_product_name_and_verdict(self):
        self.assertIn("입력한 품목: 중국산 무선이어폰", self.html)
        self.assertIn("확인 대상 가능성 높음", self.html)


class ContractKeptTest(unittest.TestCase):
    """단순화 뒤에도 백엔드·SEO 계약은 그대로."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_api_and_seo_surfaces_remain(self):
        for path in ("/v1/mcp", "/v1/meta", "/privacy", "/terms", "/about",
                     "/.well-known/mcp/server-card.json", "/guides/", "/p/"):
            self.assertIn(f'href="{path}', self.page, path)
        # 헬스체크는 링크가 아니라 엔드포인트 표에 남는다.
        self.assertIn("<code>/healthz</code>", self.page)
        self.assertIn('content="https://clns-kr.onrender.com/static/og.png"', self.page)
        self.assertIn('<script type="application/ld+json">', self.page)
        self.assertIn('"@type": "WebApplication"', self.page)

    def test_recall_as_of_label_is_still_visible(self):
        self.assertIn("2022-07-26 기준", self.page)

    def test_form_ids_keep_their_meaning(self):
        for field_id in ("check-form", "product", "check-submit", "hs-form", "hs-code",
                         "label-form", "ec-copy", "inquiry-form"):
            self.assertIn(f'id="{field_id}"', self.page, field_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
