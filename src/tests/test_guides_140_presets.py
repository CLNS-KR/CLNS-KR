"""가이드 카탈로그 1.4.0 — 롱테일 질문 17종(68 → 85) + 웹 UI 대표 품목 프리셋 회귀 테스트.

검증 항목
1. 카탈로그가 1.4.0(85종)이고, 새 17종이 근거 조문·규제 태그·툴·단정 금지 규칙을 지킨다.
2. 새 질문이 기존 질문과 다른 검색 의도를 갖고, 서로 다른 카테고리에 흩어져 있다.
3. `CLNS Check` 입력창 위에 대표 품목 버튼 5개가 있고, 누르면 품목명·품목군·원산지가
   채워진 뒤 바로 점검이 실행된다(모바일에서 누르기 쉬운 크기·접근성 이름 포함).
4. 페이지 인라인 JS 는 문자열·주석을 걷어낸 뒤에도 괄호·인용부호 균형을 만족한다.
5. `/guides/{slug}`·sitemap·llms.txt·v1/meta 가 새 카탈로그를 자동 반영한다.

실행: PYTHONPATH=src python3 -m unittest tests.test_guides_140_presets -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
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
    "perfume-60ml-direct-buy",
    "wine-liquor-direct-buy",
    "order-multiple-aggregate",
    "used-luxury-brand-ip",
    "contact-lens-medical-device",
    "vape-device-import",
    "quarantine-meat-dairy",
    "stroller-carseat-kc",
    "led-multitap-kc",
    "kitchen-appliance-110v-kc",
    "wearable-health-device",
    "roasted-coffee-tea-import",
    "tumbler-food-contact",
    "cosmetics-quality-inspection",
    "food-purchase-agency-registration",
    "food-expiry-labeling",
    "purchase-agency-withdrawal",
)

PRESET_LABELS = ("멜라토닌 직구", "강아지 간식", "수입 화장품", "블루투스 이어폰", "유아용 의류")
PRESET_KEYS = ("melatonin", "dog-treat", "cosmetics", "earbuds", "kids-clothes")


def inline_script(html: str) -> str:
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    if len(blocks) != 1:
        raise AssertionError(f"인라인 스크립트가 1개가 아닙니다: {len(blocks)}")
    return blocks[0]


def strip_js_literals(source: str) -> str:
    """문자열 리터럴·주석을 공백으로 바꾼 '코드만 남은' 소스를 돌려준다."""
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
                out.append(" ")
                continue
            index += 1
            continue
        if state == "string":
            if char == "\\":
                index += 2
                continue
            if char == quote:
                state = "code"
            index += 1
            continue
    if state == "string":
        raise AssertionError("닫히지 않은 문자열 리터럴이 있습니다")
    return "".join(out)


def bracket_problems(code: str):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for char in code:
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != pairs[char]:
                return [char]
    return stack


class GuideCatalog140Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = guides.items()
        cls.index = {item["slug"]: item for item in cls.items}

    def test_catalog_version_and_count(self):
        meta = guides.catalog_meta()
        self.assertEqual(meta["version"], "1.6.0")
        self.assertEqual(meta["verified_on"], "2026-11-21")
        self.assertGreaterEqual(meta["count"], 85)
        self.assertEqual(len({item["slug"] for item in self.items}), len(self.items))

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
                self.assertTrue(item["question_ko"].endswith("?"))

    def test_questions_are_distinct_and_spread_across_categories(self):
        questions = [item["question_ko"] for item in self.items]
        self.assertEqual(len(set(questions)), len(questions))
        categories = {self.index[slug]["category"] for slug in NEW_SLUGS}
        self.assertGreaterEqual(len(categories), 6)
        joined = " ".join(self.index[slug]["question_ko"] for slug in NEW_SLUGS)
        for token in ("향수", "와인", "합산", "중고 명품", "콘택트렌즈", "전자담배",
                      "육포", "유모차", "멀티탭", "110V", "스마트워치", "원두",
                      "텀블러", "품질검사", "구매대행", "소비기한", "청약철회"):
            self.assertIn(token, joined)

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

    def test_basis_keys_resolve_to_registry_only(self):
        registry = guides.basis_registry()
        for slug in NEW_SLUGS:
            item = self.index[slug]
            self.assertTrue(item.get("basis_keys") or item.get("cases"), slug)
            for key in item.get("basis_keys") or []:
                self.assertIn(key, registry, slug)

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


class PresetButtonsHtmlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()
        cls.script = inline_script(cls.page)
        cls.form = cls.page[cls.page.index('id="check-form"'):]
        cls.form = cls.form[:cls.form.index("</form>")]

    def test_five_preset_buttons_inside_check_form(self):
        buttons = re.findall(r'<button type="button" class="preset"[^>]*>([^<]+)</button>', self.form)
        self.assertEqual(len(buttons), 5)
        self.assertEqual(tuple(label.strip() for label in buttons), PRESET_LABELS)
        for key in PRESET_KEYS:
            self.assertIn(f'data-preset="{key}"', self.form)
            self.assertIn(f'id="preset-{key}"', self.form)

    def test_presets_sit_above_product_input(self):
        presets_at = self.form.index('class="presets"')
        product_at = self.form.index('id="product"')
        self.assertLess(presets_at, product_at)
        self.assertIn('role="group"', self.form[max(0, presets_at - 60):presets_at + 160])
        # 0.5.10: 첫 화면을 줄이면서 라벨을 '예시로 1초 체험' 으로 줄였다(버튼·동작은 그대로).
        self.assertIn("예시로 1초 체험", self.form)

    def test_presets_are_mobile_friendly_and_labelled(self):
        self.assertIn(".presets button{", self.page)
        css = self.page[self.page.index(".presets button{"):]
        css = css[:css.index("}")]
        self.assertIn("min-height:38px", css)
        self.assertIn("white-space:nowrap", css)
        # 터치 기본 크기 확보 + 키보드 포커스 표시
        self.assertIn(".presets button:focus-visible", self.page)

    def test_script_defines_every_preset_and_submits(self):
        for key in PRESET_KEYS:
            self.assertIn(f'"{key}": {{product:', self.script)
        self.assertIn("function applyPreset(key)", self.script)
        self.assertIn("form.requestSubmit()", self.script)
        self.assertIn('document.querySelectorAll(".preset[data-preset]")', self.script)

    def test_inline_javascript_is_balanced(self):
        cleaned = strip_js_literals(self.script)
        self.assertEqual(bracket_problems(cleaned), [])
        self.assertTrue(bracket_problems("function a(){ return (1; }"))
        self.assertNotIn('\\"', self.script)


JS_STUB = r"""
var __elements = {};
var __radios = {};
var __submitCalls = 0;
function makeElem(id){
  return {
    id: id, value: "", textContent: "", innerHTML: "", hidden: true, open: false,
    style: {}, checked: false,
    options: [{value: ""}],
    addEventListener: function(){}, setAttribute: function(){}, removeAttribute: function(){},
    appendChild: function(c){ return c; }, removeChild: function(){},
    select: function(){}, focus: function(){}, reset: function(){}, scrollIntoView: function(){},
    querySelector: function(){ return makeElem("inner"); },
    querySelectorAll: function(){ return []; },
    requestSubmit: function(){ __submitCalls = __submitCalls + 1; },
    dispatchEvent: function(){},
    getAttribute: function(){ return null; }
  };
}
var __form = makeElem("check-form");
__form.querySelector = function(sel){
  if (!__radios[sel]) __radios[sel] = makeElem(sel);
  return __radios[sel];
};
var document = {
  getElementById: function(id){
    if (id === "check-form") return __form;
    if (!__elements[id]) __elements[id] = makeElem(id);
    return __elements[id];
  },
  querySelector: function(){ return makeElem("q"); },
  querySelectorAll: function(){ return []; },
  createElement: function(tag){ return makeElem(tag); },
  body: makeElem("body"),
  execCommand: function(){ return true; },
  addEventListener: function(){}
};
var location = { origin: "http://127.0.0.1:8931", search: "", hash: "" };
var localStorage = { getItem: function(){ return null; }, setItem: function(){} };
var window = { setTimeout: function(){ return 1; } };
var navigator = {};
var history = { replaceState: function(){} };
function __chain(){ var o = {}; o.then = function(){ return o; }; o.catch = function(){ return o; }; return o; }
var fetch = function(){ return __chain(); };
function URLSearchParams(qs){ this.get = function(){ return null; }; }
function Event(name){ this.type = name; }
"""

JS_EXPOSE = ("globalThis.__clns = {applyPreset: applyPreset, PRESETS: PRESETS};")


def preset_context():
    script = inline_script(web_ui.render_page()).rstrip()
    marker = "})();"
    if not script.endswith(marker):
        raise AssertionError("페이지 스크립트가 예상한 IIFE 형태가 아닙니다")
    body = script[: -len(marker)] + JS_EXPOSE + marker
    context = quickjs.Context()
    context.eval(JS_STUB)
    context.eval(body)
    return context


@unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
class PresetRuntimeTest(unittest.TestCase):
    def test_script_loads_without_error(self):
        context = preset_context()
        self.assertEqual(context.eval("Object.keys(globalThis.__clns.PRESETS).length"), 5)

    def test_melatonin_preset_fills_fields_and_runs_check(self):
        context = preset_context()
        context.eval('globalThis.__clns.applyPreset("melatonin")')
        self.assertEqual(context.eval('document.getElementById("product").value'),
                         "미국산 멜라토닌 수면 영양제")
        self.assertEqual(context.eval('document.getElementById("kind").value'), "drug")
        self.assertEqual(context.eval('document.getElementById("origin").value'), "미국")
        self.assertEqual(context.eval('document.getElementById("drug-qty").value'), "2")
        self.assertEqual(context.eval('document.getElementById("drug-unit").value'), "병")
        self.assertEqual(context.eval('__form.querySelector(\'input[name="purpose"][value="self_use"]\').checked'), True)
        self.assertEqual(context.eval('__form.querySelector(\'input[name="drug-channel"][value="online"]\').checked'), True)
        self.assertEqual(context.eval("__submitCalls"), 1)

    def test_earbuds_preset_sets_wire_and_hs(self):
        context = preset_context()
        context.eval('globalThis.__clns.applyPreset("earbuds")')
        self.assertEqual(context.eval('document.getElementById("product").value'), "중국산 블루투스 이어폰")
        self.assertEqual(context.eval('document.getElementById("hs").value'), "8518309000")
        self.assertEqual(context.eval('__form.querySelector(\'input[name="wire"][value="yes"]\').checked'), True)
        self.assertEqual(context.eval("__submitCalls"), 1)

    def test_kids_clothes_preset_marks_children_product(self):
        context = preset_context()
        context.eval('globalThis.__clns.applyPreset("kids-clothes")')
        self.assertEqual(context.eval('document.getElementById("origin").value'), "베트남")
        self.assertEqual(context.eval('__form.querySelector(\'input[name="child"][value="yes"]\').checked'), True)

    def test_unknown_preset_is_ignored(self):
        context = preset_context()
        context.eval('globalThis.__clns.applyPreset("nope")')
        self.assertEqual(context.eval("__submitCalls"), 0)
        self.assertEqual(context.eval('document.getElementById("product").value'), "")


class ServedGuidePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = None
        cls.server = None
        cls.store = Store()
        handler = make_handler(cls.store)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.server is not None:
            cls.server.shutdown()
            cls.server.server_close()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8")

    def test_every_new_guide_renders_with_faq(self):
        for slug in NEW_SLUGS:
            with self.subTest(slug=slug):
                status, html = self.get(f"/guides/{slug}")
                self.assertEqual(status, 200)
                item = guides.get_item(slug)
                self.assertIn(item["question_ko"], html)
                self.assertIn(item["answer_ko"], html)
                self.assertIn("근거 법령", html)
                block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
                payload = json.loads(block.group(1))
                faq = next(node for node in payload["@graph"] if node["@type"] == "FAQPage")
                self.assertEqual(faq["mainEntity"][0]["name"], item["question_ko"])

    def test_sitemap_and_llms_reflect_all_guides(self):
        status, raw = self.get("/sitemap.xml")
        self.assertEqual(status, 200)
        root = ET.fromstring(raw)
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [node.text for node in root.iter(ns + "loc")]
        for slug in NEW_SLUGS:
            self.assertIn(f"{BASE}/guides/{slug}", locs)
        # +3: /about·/privacy·/terms 고지 페이지(0.5.6)
        self.assertEqual(len(locs), 1 + len(pseo.indexable_paths())
                         + len(guides.indexable_paths()) + 3)
        status, body = self.get("/llms.txt")
        self.assertEqual(status, 200)
        self.assertIn(f"{len(guides.items())}개 질문", body)

    def test_service_meta_reports_150(self):
        payload = call_tool("get_service_meta", {}, self.store)["result"]
        self.assertEqual(payload["guides"]["count"], len(guides.items()))
        self.assertEqual(payload["guides"]["catalog_version"], "1.6.0")

    def test_home_page_carries_preset_buttons(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertEqual(html.count('class="preset"'), 5)
        for label in PRESET_LABELS:
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
