"""결과 공유·복사 UI + 롱테일 질문 가이드 15종(카탈로그 1.2.0) 회귀 테스트.

검증 항목
1. `CLNS Check`·`국내 판매페이지 문구만 빠르게 검수` 결과 영역에 각각 버튼 2개
   (`결과 요약 복사`·`공유 링크 복사`)가 있고, 클립보드 복사는 `navigator.clipboard.writeText`
   → `textarea` + `execCommand` 폴백 순서로 동작하며 `복사됨` 피드백을 표시한다.
2. 페이지의 인라인 JS 는 문자열·주석을 걷어낸 뒤 괄호·중괄호·대괄호 균형과 인용부호
   종료를 만족한다(따옴표 하나로 스크립트 전체가 죽는 사고를 막는다).
3. 공유 링크는 품목명·품목군·원산지만 담고(`item`·`cat`·`origin`), 들어온 파라미터는
   허용된 선택지 값일 때만 입력란에 채운다.
4. 카탈로그가 65종이고, 새 15종이 근거 조문·규제 태그·툴·단정 금지 규칙을 지킨다.
5. `/guides/{slug}` 렌더와 sitemap·llms.txt·v1/meta 카운트가 카탈로그를 자동 반영한다.
6. 새 파일·페이지에 실명·연락처·이메일·사업자 정보가 없다.

실행: PYTHONPATH=src python3 -m unittest tests.test_share_and_longtail_guides -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html import escape
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import guides, pseo, static_files, web_ui  # noqa: E402
from import_compliance.api import TOOL_INDEX, call_tool  # noqa: E402
from import_compliance.policy import find_conclusive_phrasing  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.standards import REGULATION_TAGS  # noqa: E402
from import_compliance.store import Store  # noqa: E402

try:  # 로컬 검증용 임베디드 JS 엔진(CI 에 없으면 해당 테스트만 건너뛴다)
    import quickjs  # type: ignore
    HAVE_QUICKJS = True
except Exception:  # noqa: BLE001
    quickjs = None  # type: ignore
    HAVE_QUICKJS = False

BASE = "https://clns-kr.onrender.com"

NEW_SLUGS = (
    "smartstore-brand-logo-resale",
    "children-kc-13-safety-confirm",
    "rf-one-unit-direct-buy",
    "general-food-hff-like-ad",
    "cosmetic-functional-claim-words",
    "food-import-registration-order",
    "natural-100-percent-claim",
    "purchase-agency-vs-parallel-import",
    "list-clearance-excluded-items",
    "cosmetics-import-labeling-sticker",
    "hff-item-report-import",
    "kc-cert-number-verify",
    "detail-page-before-after-review",
    "origin-marking-online-listing",
    "food-allergen-labeling",
)

SHARE_PAIRS = (
    ("result-share", "result-share-note", "result-copy-summary", "result-copy-link"),
    ("ec-share", "ec-share-note", "ec-copy-summary", "ec-copy-link"),
)

# 개인정보·시크릿은 값이 아니라 모양으로 잡는다(테스트 파일이 개인정보를 담지 않게).
PERSONAL_PATTERNS = (
    r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}",
    r"[\w.+-]+@(?:gmail|naver|kakao|hanmail|nate|daum)\.com",
    r"(?:github|gitlab)\.com/[A-Za-z0-9-]+",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
)


def inline_script(html: str) -> str:
    """페이지의 인라인 실행 스크립트(JSON‑LD 제외)를 하나 돌려준다."""
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    if len(blocks) != 1:
        raise AssertionError(f"인라인 스크립트가 1개가 아닙니다: {len(blocks)}")
    return blocks[0]


def strip_js_literals(source: str) -> str:
    """문자열 리터럴과 주석을 공백으로 바꾼 '코드만 남은' 소스를 돌려준다.

    문자열 안의 괄호가 균형 검사에 섞이지 않게 하고, 닫히지 않은 인용부호를 잡는다.
    """
    out = []
    index = 0
    length = len(source)
    state = "code"
    quote = ""
    while index < length:
        char = source[index]
        nxt = source[index + 1] if index + 1 < length else ""
        if state == "code":
            if char == "/" and nxt == "/":
                state = "line_comment"
                index += 2
                out.append(" ")
                continue
            if char == "/" and nxt == "*":
                state = "block_comment"
                index += 2
                out.append(" ")
                continue
            if char in "\"'`":
                state = "string"
                quote = char
                index += 1
                out.append(" ")
                continue
            out.append(char)
            index += 1
            continue
        if state == "line_comment":
            if char == "\n":
                state = "code"
                out.append("\n")
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                state = "code"
                index += 2
                continue
            index += 1
            continue
        # string
        if char == "\\":
            index += 2
            continue
        if char == "\n":
            raise AssertionError("JS 문자열 리터럴이 줄바꿈으로 끊겼습니다")
        if char == quote:
            state = "code"
            index += 1
            continue
        index += 1
    if state == "string":
        raise AssertionError("JS 문자열 리터럴이 닫히지 않았습니다")
    if state == "block_comment":
        raise AssertionError("JS 블록 주석이 닫히지 않았습니다")
    return "".join(out)


def bracket_problems(cleaned: str) -> list:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    problems = []
    line = 1
    for char in cleaned:
        if char == "\n":
            line += 1
            continue
        if char in "([{":
            stack.append((char, line))
        elif char in ")]}":
            if not stack:
                problems.append(f"line {line}: 여는 괄호 없이 {char}")
                continue
            opener, opener_line = stack.pop()
            if opener != pairs[char]:
                problems.append(f"line {line}: {opener_line}행 {opener} 와 {char} 짝이 맞지 않음")
    for opener, opener_line in stack:
        problems.append(f"line {opener_line}: {opener} 가 닫히지 않음")
    return problems


class ShareUiContractTest(unittest.TestCase):
    """결과 영역의 복사·공유 버튼 계약(정적 HTML + JS)."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()
        cls.script = inline_script(cls.page)

    def test_both_result_areas_have_two_buttons(self):
        self.assertEqual(self.page.count("결과 요약 복사"), 2)
        self.assertEqual(self.page.count("공유 링크 복사"), 2)
        for bar_id, note_id, copy_id, link_id in SHARE_PAIRS:
            with self.subTest(bar=bar_id):
                self.assertIn(f'id="{bar_id}"', self.page)
                self.assertIn(f'id="{note_id}"', self.page)
                self.assertIn(f'id="{copy_id}"', self.page)
                self.assertIn(f'id="{link_id}"', self.page)
                # 결과가 나오기 전에는 감춰 둔다.
                self.assertRegex(self.page, rf'class="sharebar" id="{bar_id}" hidden')
                self.assertRegex(self.page, rf'id="{copy_id}"[^>]*>결과 요약 복사<')
                self.assertRegex(self.page, rf'id="{link_id}"[^>]*>공유 링크 복사<')

    def test_copy_uses_clipboard_with_textarea_fallback(self):
        self.assertIn("navigator.clipboard", self.script)
        self.assertIn("navigator.clipboard.writeText", self.script)
        self.assertIn("execCommand(\"copy\")", self.script)
        self.assertIn("createElement(\"textarea\")", self.script)
        # 클립보드 API 실패(권한 없음·비보안 컨텍스트) 시 폴백으로 내려간다.
        self.assertRegex(self.script, r"writeText\(payload\)\.then\(function\(\)\{ done\(true\); \}, function\(\)\{ fallback\(\); \}\)")
        self.assertIn("복사됨", self.script)

    def test_summary_contains_verdict_items_basis_and_source(self):
        summary = self.script[self.script.index("function checkSummaryText"):]
        summary = summary[:summary.index("function ecSummaryText")]
        for token in ("판정:", "주요 위험·확인 항목:", "근거 법령:", "규칙·케이스 ID:"):
            self.assertIn(token, summary)
        self.assertIn("SOURCE_URL", summary)
        self.assertIn('SOURCE_URL = "https://clns-kr.onrender.com"', self.script)
        ec = self.script[self.script.index("function ecSummaryText"):]
        ec = ec[:ec.index("function shareUrl")]
        for token in ("판정:", "금지 위험 문구:", "근거 법령:"):
            self.assertIn(token, ec)

    def test_share_link_carries_only_safe_parameters(self):
        share = self.script[self.script.index("function shareUrl"):]
        share = share[:share.index("function setShareBar")]
        for key in ("item=", "cat=", "origin="):
            self.assertIn(key, share)
        # 긴 상세 문구·성분표·HS 코드 같은 본문은 공유 URL 에 넣지 않는다.
        for forbidden in ("ad_copy", "detail_copy", "label_text", "cosmetic_ingredients", "hs_code"):
            self.assertNotIn(forbidden, share)
        self.assertIn("encodeURIComponent", share)

    def test_shared_parameters_prefill_allowed_values_only(self):
        self.assertIn('shared.get("item")', self.script)
        self.assertIn('shared.get("cat")', self.script)
        self.assertIn('shared.get("origin")', self.script)
        prefill = self.script[self.script.index("공유 링크로 들어온 경우"):]
        self.assertIn("optionValue", prefill)
        self.assertIn("syncConditionalFields()", prefill)
        # ?q= 프리필과 충돌하지 않게 q 가 있으면 품목명을 덮어쓰지 않는다.
        self.assertIn('!shared.get("q")', prefill)

    def test_inline_javascript_is_balanced(self):
        cleaned = strip_js_literals(self.script)
        self.assertEqual(bracket_problems(cleaned), [])
        # 괄호 균형이 실제로 검사되는지(자기검증): 일부러 깨면 문제가 잡힌다.
        self.assertTrue(bracket_problems("function a(){ return (1; }"))

    def test_no_escaped_double_quotes_inside_script(self):
        self.assertNotIn('\\"', self.script)

    def test_page_stays_anonymous(self):
        for word in ("대표자", "사업자등록번호", "주민등록", "통신판매업"):
            self.assertNotIn(word, self.page)
        for pattern in PERSONAL_PATTERNS:
            self.assertIsNone(re.search(pattern, self.page), pattern)

    def test_share_buttons_are_wired_after_render(self):
        # 결과를 그린 뒤 공유 바를 켜고, 실패·초기화 때 다시 감춘다.
        self.assertEqual(self.script.count('setShareBar("result-share", true)'), 1)
        self.assertEqual(self.script.count('setShareBar("result-share", false)'), 2)
        self.assertEqual(self.script.count('setShareBar("ec-share", true)'), 1)
        self.assertEqual(self.script.count('setShareBar("ec-share", false)'), 1)


class LongTailGuideCatalogTest(unittest.TestCase):
    """카탈로그 1.2.0 — 65종 이상, 새 15종의 근거·태그·문안 규칙."""

    @classmethod
    def setUpClass(cls):
        cls.items = guides.items()
        cls.index = {item["slug"]: item for item in cls.items}

    def test_catalog_reaches_sixty_five_questions(self):
        self.assertGreaterEqual(len(self.items), 68)
        self.assertEqual(len({item["slug"] for item in self.items}), len(self.items))
        meta = guides.catalog_meta()
        self.assertEqual(meta["count"], len(self.items))
        self.assertEqual(meta["version"], "1.5.0")
        self.assertEqual(meta["verified_on"], "2026-11-21")

    def test_new_slugs_are_present_and_indexable(self):
        for slug in NEW_SLUGS:
            with self.subTest(slug=slug):
                item = self.index.get(slug)
                self.assertIsNotNone(item)
                self.assertTrue(guides.is_indexable(item))
                self.assertGreaterEqual(len(item["answer_ko"]), guides.THIN_MIN_ANSWER)
                self.assertGreaterEqual(len(item["summary_ko"]), 60)
                self.assertGreaterEqual(len(item["question_ko"]), 10)
                self.assertGreaterEqual(len(item["checkpoints_ko"]), guides.THIN_MIN_CHECKPOINTS)
                self.assertGreaterEqual(len(item.get("keywords") or []), 5)

    def test_new_questions_cover_distinct_search_intents(self):
        questions = {item["slug"]: item["question_ko"] for item in self.items}
        self.assertEqual(len(set(questions.values())), len(questions))
        # 브리프에서 지정한 검색 의도가 새 질문에 실제로 들어갔는지 확인한다.
        joined = " ".join(questions[slug] for slug in NEW_SLUGS)
        for token in ("상표권", "13세", "1인 1대", "건강기능식품",
                      "미백", "영업등록", "천연", "구매대행", "목록통관", "알레르기"):
            self.assertIn(token, joined)
        categories = {self.index[slug]["category"] for slug in NEW_SLUGS}
        self.assertGreaterEqual(len(categories), 6)

    def test_new_questions_reference_verified_basis(self):
        for slug in NEW_SLUGS:
            item = self.index[slug]
            with self.subTest(slug=slug):
                self.assertIn(item["tool"], TOOL_INDEX)
                for tag in item["tags"]:
                    self.assertIn(tag, REGULATION_TAGS)
                    self.assertNotEqual(guides.authority_for(tag), "소관 기관 확인")
                    self.assertIn(guides.tool_for_tag(tag), TOOL_INDEX)
                basis = guides.legal_basis(item)
                self.assertTrue(basis, "근거 조문이 비어 있습니다")
                for row in basis:
                    self.assertTrue(row.get("law"))
                    self.assertTrue(row.get("article"))
                    self.assertRegex(str(row.get("effective_date") or ""), r"^\d{4}-\d{2}-\d{2}$")
                    self.assertTrue(str(row.get("quote") or "").strip())
                    self.assertTrue(str(row.get("url") or "").startswith("http"))

    def test_new_questions_avoid_conclusive_phrasing(self):
        for slug in NEW_SLUGS:
            item = self.index[slug]
            texts = [item["answer_ko"], item["summary_ko"], *item["checkpoints_ko"],
                     *(item.get("key_points_ko") or [])]
            for text in texts:
                with self.subTest(slug=slug):
                    self.assertEqual(find_conclusive_phrasing(text), [], text[:60])

    def test_new_questions_link_to_existing_pages(self):
        slugs = set(self.index)
        for slug in NEW_SLUGS:
            item = self.index[slug]
            with self.subTest(slug=slug):
                self.assertTrue(item.get("related_guides"))
                for related in item["related_guides"]:
                    self.assertIn(related, slugs)
                for product in item.get("related_items") or []:
                    self.assertIsNotNone(pseo.get_item(product), product)


JS_STUB_TEMPLATE = r"""
var __listeners = [];
var __elements = {};
var __created = [];
function makeElem(id){
  return {
    id: id, value: "", textContent: "", innerHTML: "", hidden: true, open: false,
    style: {}, checked: false,
    options: [{value: ""}, {value: "food"}, {value: "health_functional"},
              {value: "electronics"}, {value: "중국"}, {value: "미국"}],
    addEventListener: function(type, fn){ __listeners.push([id || "?", type, fn]); },
    setAttribute: function(){}, removeAttribute: function(){},
    appendChild: function(child){ __created.push(child); return child; },
    removeChild: function(){},
    select: function(){}, focus: function(){}, reset: function(){},
    scrollIntoView: function(){},
    querySelector: function(){ return makeElem("inner"); },
    querySelectorAll: function(){ return []; },
    requestSubmit: function(){}, dispatchEvent: function(){},
    getAttribute: function(){ return null; }
  };
}
var document = {
  getElementById: function(id){
    if (!__elements[id]) __elements[id] = makeElem(id);
    return __elements[id];
  },
  querySelector: function(){ return makeElem("q"); },
  querySelectorAll: function(){ return []; },
  createElement: function(tag){ var el = makeElem(tag); __created.push(el); return el; },
  body: makeElem("body"),
  execCommand: function(){ return true; },
  addEventListener: function(){}
};
var location = { origin: "http://127.0.0.1:8931", search: "__SEARCH__", hash: "" };
var localStorage = { getItem: function(){ return null; }, setItem: function(){} };
var window = { setTimeout: function(){ return 1; } };
var navigator = {};
var history = { replaceState: function(){} };
function __chain(){ var o = {}; o.then = function(){ return o; }; o.catch = function(){ return o; }; return o; }
var fetch = function(){ return __chain(); };
function URLSearchParams(qs){
  this._map = {};
  var parts = String(qs || "").replace(/^\?/, "").split("&");
  for (var i = 0; i < parts.length; i++){
    if (!parts[i]) continue;
    var kv = parts[i].split("=");
    this._map[decodeURIComponent(kv[0])] = decodeURIComponent((kv[1] || "").replace(/\+/g, " "));
  }
}
URLSearchParams.prototype.get = function(key){
  return Object.prototype.hasOwnProperty.call(this._map, key) ? this._map[key] : null;
};
function Event(name){ this.type = name; }
"""

# IIFE 내부 함수를 검증용으로 노출한다(페이지 동작은 그대로).
JS_EXPOSE = ("globalThis.__clns = {checkSummaryText: checkSummaryText, "
             "ecSummaryText: ecSummaryText, shareUrl: shareUrl, copyText: copyText, "
             "shareState: shareState, setShareBar: setShareBar};")


def js_context(search: str = ""):
    """페이지 인라인 JS 를 가짜 DOM 위에서 실제로 로드한 컨텍스트를 돌려준다."""
    script = inline_script(web_ui.render_page()).rstrip()
    marker = "})();"
    if not script.endswith(marker):
        raise AssertionError("페이지 스크립트가 예상한 IIFE 형태가 아닙니다")
    body = script[: -len(marker)] + JS_EXPOSE + marker
    context = quickjs.Context()
    context.eval(JS_STUB_TEMPLATE.replace("__SEARCH__", search))
    context.eval(body)
    return context


@unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
class ShareUiRuntimeTest(unittest.TestCase):
    """페이지 JS 를 실제로 실행해 공유 링크·요약·클립보드 폴백을 확인한다."""

    def test_script_loads_without_error(self):
        context = js_context()
        self.assertTrue(context.eval("typeof globalThis.__clns.checkSummaryText"))

    def test_share_url_keeps_only_safe_parameters(self):
        context = js_context()
        context.eval('globalThis.__clns.shareState.check = {product: "중국산 블루투스 스피커",'
                     ' cat: "electronics", origin: "중국", summary: ""};')
        url = context.eval('globalThis.__clns.shareUrl("check")')
        self.assertTrue(url.startswith(f"{BASE}/?"))
        self.assertTrue(url.endswith("#check"))
        self.assertIn("item=%EC%A4%91%EA%B5%AD%EC%82%B0%20", url)
        self.assertIn("cat=electronics", url)
        self.assertIn("origin=%EC%A4%91%EA%B5%AD", url)
        self.assertEqual(url.count("="), 3)
        self.assertEqual(context.eval('globalThis.__clns.shareUrl("ec")'), f"{BASE}/?cat=ec#check")

    def test_check_summary_lists_verdict_items_basis_and_rule_ids(self):
        context = js_context()
        summary = context.eval(
            'globalThis.__clns.checkSummaryText("중국산 블루투스 스피커", {'
            'verdict: {label_ko: "확인 가능성 높음", code: "check_likely"},'
            'findings: [{issue_ko: "전파 적합성평가", verdict: "check_likely", case_id: "TRAP-06"},'
            '           {issue_ko: "리콜 이력", verdict: "low_risk", case_id: "TRAP-20"}],'
            'evidence: [{law: "전파법", article: "제58조의2"}]})')
        self.assertIn("[CLNS 사전 점검] 중국산 블루투스 스피커", summary)
        self.assertIn("판정: 확인 가능성 높음 (check_likely)", summary)
        self.assertIn("주요 위험·확인 항목: 전파 적합성평가", summary)
        self.assertIn("현재 정보상 가능성 낮음: 리콜 이력", summary)
        self.assertIn("근거 법령: 전파법 제58조의2", summary)
        self.assertIn("규칙·케이스 ID: TRAP-06, TRAP-20", summary)
        self.assertTrue(summary.rstrip().endswith(BASE))

    def test_ecommerce_summary_separates_high_risk(self):
        context = js_context()
        summary = context.eval(
            'globalThis.__clns.ecSummaryText({verdict: {label_ko: "확인 필요", code: "check_likely"},'
            ' channel_label_ko: "네이버 스마트스토어",'
            ' ecommerce_review: {findings: [{name_ko: "허위 할인율", risk: "high"},'
            '                              {name_ko: "청약철회 제한", risk: "caution"}]},'
            ' evidence: [{law: "표시·광고의 공정화에 관한 법률", article: "제3조제1항제2호"}]})')
        self.assertIn("[CLNS 판매페이지 사전 점검] 네이버 스마트스토어", summary)
        self.assertIn("금지 위험 문구: 허위 할인율", summary)
        self.assertIn("주의·확인 문구: 청약철회 제한", summary)
        self.assertIn("표시·광고의 공정화에 관한 법률 제3조제1항제2호", summary)

    def test_copy_falls_back_to_textarea_when_clipboard_missing(self):
        context = js_context()
        copied = context.eval('(function(){ var got = null;'
                              ' globalThis.__clns.copyText("hello", function(ok){ got = ok; });'
                              ' return got; })()')
        self.assertTrue(copied)
        self.assertGreaterEqual(context.eval("__created.length"), 1)
        self.assertEqual(context.eval("__created[0].value"), "hello")

    def test_shared_parameters_prefill_inputs(self):
        context = js_context("?item=%EB%B9%84%ED%83%80%EB%AF%BC%20D3&cat=food&origin=%EC%A4%91%EA%B5%AD")
        self.assertEqual(context.eval('__elements["product"].value'), "비타민 D3")
        self.assertEqual(context.eval('__elements["kind"].value'), "food")
        self.assertEqual(context.eval('__elements["origin"].value'), "중국")
        self.assertIn("공유 링크", context.eval('__elements["form-note"].textContent'))

    def test_unknown_parameter_values_are_ignored(self):
        context = js_context("?cat=evil&origin=nowhere")
        self.assertEqual(context.eval('__elements["kind"].value'), "")
        self.assertEqual(context.eval('__elements["origin"].value'), "")

    def test_share_bar_starts_hidden_and_opens_on_result(self):
        context = js_context()
        self.assertTrue(context.eval('document.getElementById("result-share").hidden'))
        context.eval('globalThis.__clns.setShareBar("result-share", true);')
        self.assertFalse(context.eval('document.getElementById("result-share").hidden'))


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.store = Store(os.path.join(cls.tmpdir.name, "app.sqlite"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()
        cls.tmpdir.cleanup()

    def raw(self, path, method="GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def text(self, path):
        status, headers, body = self.raw(path)
        return status, headers, body.decode("utf-8")


class LongTailGuidePageTest(ServerCase):
    """새 가이드가 서버 렌더 HTML·구조화 데이터·발견 경로에 실제로 실린다."""

    def test_new_guides_render_for_crawlers(self):
        for slug in NEW_SLUGS:
            item = guides.get_item(slug)
            with self.subTest(slug=slug):
                status, headers, html = self.text(f"/guides/{slug}")
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["Content-Type"])
                # 질문에 따옴표가 들어가면 HTML 이스케이프된 형태로 렌더된다.
                self.assertIn(f"<h1>{escape(item['question_ko'])}</h1>", html)
                self.assertIn("한 줄 답변", html)
                self.assertIn("대표 체크포인트", html)
                self.assertIn("근거 법령", html)
                self.assertIn("시행", html)
                self.assertIn("면책", html)
                self.assertIn(f'<link rel="canonical" href="{BASE}/guides/{slug}">', html)
                self.assertIn("/?q=", html)
                self.assertIn('href="/mcp"', html)
                self.assertIn("<script", html)
                self.assertNotIn("<script src=", html)
                # 구조화 데이터(FAQPage)가 질문·답변을 그대로 담는다.
                block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
                self.assertIsNotNone(block)
                payload = json.loads(block.group(1))
                faq = next(node for node in payload["@graph"] if node["@type"] == "FAQPage")
                entity = faq["mainEntity"][0]
                self.assertEqual(entity["name"], item["question_ko"])
                self.assertEqual(entity["acceptedAnswer"]["text"], item["answer_ko"])

    def test_guide_index_lists_all_sixty_five(self):
        status, _, html = self.text("/guides/")
        self.assertEqual(status, 200)
        self.assertIn(f"수입 규제 질문 {len(guides.items())}선", html)
        for slug in NEW_SLUGS:
            self.assertIn(f"/guides/{slug}\"", html)

    def test_sitemap_and_llms_carry_new_guides(self):
        status, _, raw = self.raw("/sitemap.xml")
        self.assertEqual(status, 200)
        root = ET.fromstring(raw)
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(ns + "loc")]
        for slug in NEW_SLUGS:
            self.assertIn(f"{BASE}/guides/{slug}", locs)
        self.assertEqual(len(locs), 1 + len(pseo.indexable_paths()) + len(guides.indexable_paths()))
        self.assertEqual(len(locs), len(set(locs)))

        status, _, body = self.raw("/llms.txt")
        self.assertEqual(status, 200)
        llms = body.decode("utf-8")
        self.assertIn(f"{len(guides.items())}개 질문", llms)
        self.assertIn(f"{len(pseo.items())}개 품목", llms)

    def test_service_meta_reports_new_catalog_version(self):
        payload = call_tool("get_service_meta", {}, self.store)["result"]
        self.assertEqual(payload["guides"]["count"], len(guides.items()))
        self.assertEqual(payload["guides"]["count"], len(guides.items()))
        self.assertEqual(payload["guides"]["catalog_version"], "1.5.0")

    def test_share_url_style_pages_still_work(self):
        # 공유 링크가 가리키는 홈은 쿼리 파라미터가 붙어도 같은 화면을 돌려준다.
        status, _, html = self.text("/?item=%EC%A4%91%EA%B5%AD%EC%82%B0%20%EB%B8%94%EB%A3%A8%ED%88%AC%EC%8A%A4%20%EC%8A%A4%ED%94%BC%EC%BB%A4&cat=electronics&origin=%EC%A4%91%EA%B5%AD")
        self.assertEqual(status, 200)
        self.assertIn('id="result-share"', html)
        self.assertIn('id="ec-share"', html)


class AnonymousNewFilesTest(unittest.TestCase):
    def test_touched_files_have_no_personal_data_or_secrets(self):
        patterns = [re.compile(pattern) for pattern in PERSONAL_PATTERNS]
        targets = [
            os.path.join("src", "import_compliance", "web_ui.py"),
            os.path.join("src", "import_compliance", "guides.py"),
            os.path.join("src", "guides_items.json"),
            os.path.join("src", "tests", "test_share_and_longtail_guides.py"),
        ]
        for relative in targets:
            with open(os.path.join(ROOT, relative), encoding="utf-8") as handle:
                text = handle.read()
            for pattern in patterns:
                with self.subTest(file=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))

    def test_generated_crawler_files_are_anonymous(self):
        for text in (static_files.sitemap_xml(), static_files.llms_txt(),
                     static_files.robots_txt()):
            for pattern in PERSONAL_PATTERNS:
                self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main(verbosity=2)
