"""0.5.2 P0·P1 결함 수정 회귀 테스트.

검증 대상
--------
- **P0 탭 3개 먹통**: `panels` 가 4개 탭(check·label·hs·api)을 모두 매핑하고, `showTab` 이
  없는 패널을 만나도 예외 없이 넘어가며, `#label` 딥링크·`/?q=`·`/?item=` 유입이 check 탭을 연다.
- **P1 내부 코드 노출**: 결과 화면의 '추가 확인 항목'·실시간 조회 상태·오류 안내가
  `functional_cosmetic`·`battery_type`·`energy_density`·`facts.rra_cert_no`·`check_kc_certification`
  같은 내부 키를 그대로 보여 주지 않는다(한국어 라벨로 치환).
- **P1 다크 모드 대비**: `--brand-fill`/`--on-brand` 조합이 WCAG AA(4.5:1) 이상.
- **P1 오타·누락**: '전파인증 예외' 오타 제거, API 탭 툴 표가 실제 15종과 일치,
  CLNS Label 탭에도 요약 복사·공유 링크 버튼.
- **P1 404**: 페이지 주소는 사람용 404 HTML, `/v1/…` API 주소는 종전 JSON 404.
- 버전 0.5.2 동기화(version.py·server.json·Dockerfile·페이지 푸터).

실행: PYTHONPATH=src python3 -m unittest discover -s src/tests -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from html import escape
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

from import_compliance import static_files, web_ui  # noqa: E402
from import_compliance.api import TOOL_INDEX, call_tool  # noqa: E402
from import_compliance.server import make_handler  # noqa: E402
from import_compliance.store import Store  # noqa: E402
from import_compliance.version import __version__  # noqa: E402

try:
    import quickjs  # type: ignore

    HAVE_QUICKJS = True
except Exception:  # noqa: BLE001 - quickjs 가 없으면 정적 검사만 한다
    quickjs = None  # type: ignore
    HAVE_QUICKJS = False

TAB_KEYS = ("check", "label", "hs", "api")
TAB_PANELS = {"check": "tab-check", "label": "tab-label", "hs": "tab-hs", "api": "tab-api"}
BASE = "https://clns-kr.onrender.com"


# ---------------------------------------------------------------------------
# 페이지 스크립트를 실제로 돌리는 최소 DOM (탭 버튼 4개 포함)
# ---------------------------------------------------------------------------
JS_STUB = r"""
var __listeners = [];
var __elements = {};
var __history = [];
function makeElem(id){
  return {
    id: id, value: "", textContent: "", innerHTML: "", hidden: true, open: false,
    style: {}, checked: false, attrs: {},
    options: [{value: ""}, {value: "cosmetics"}, {value: "functional_cosmetics"},
              {value: "general_food"}, {value: "health_functional_food"},
              {value: "kc_electronics"}, {value: "pet_food"}, {value: "general_goods"},
              {value: "food"}, {value: "electronics"}, {value: "중국"}, {value: "미국"}],
    addEventListener: function(type, fn){ __listeners.push([id || "?", type, fn]); },
    setAttribute: function(k, v){ this.attrs[k] = v; },
    getAttribute: function(k){ return this.attrs[k] === undefined ? null : this.attrs[k]; },
    removeAttribute: function(k){ delete this.attrs[k]; },
    appendChild: function(child){ return child; },
    removeChild: function(){},
    select: function(){}, focus: function(){}, reset: function(){}, scrollIntoView: function(){},
    querySelector: function(){ return makeElem("inner"); },
    querySelectorAll: function(){ return []; },
    requestSubmit: function(){}, dispatchEvent: function(){}
  };
}
var __buttons = [];
var __tabKeys = ["check", "label", "hs", "api"];
for (var __i = 0; __i < __tabKeys.length; __i++){
  var __b = makeElem("tabbtn-" + __tabKeys[__i]);
  __b.attrs["data-tab"] = __tabKeys[__i];
  __buttons.push(__b);
}
var document = {
  getElementById: function(id){
    // 실제 DOM 과 같게: 없는 id(undefined 포함)는 null 을 돌려준다.
    if (id === null || id === undefined || id === "") return null;
    if (!__elements[id]) __elements[id] = makeElem(id);
    return __elements[id];
  },
  querySelector: function(){ return makeElem("q"); },
  querySelectorAll: function(selector){
    if (String(selector).indexOf("nav.tabs") !== -1) return __buttons;
    return [];
  },
  createElement: function(tag){ return makeElem(tag); },
  body: makeElem("body"),
  execCommand: function(){ return true; },
  addEventListener: function(){}
};
var location = { origin: "http://127.0.0.1:8931", search: "__SEARCH__", hash: "__HASH__" };
var localStorage = { getItem: function(){ return null; }, setItem: function(){} };
var window = { setTimeout: function(){ return 1; } };
var navigator = {};
var history = { replaceState: function(state, title, url){ __history.push(url); } };
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

JS_EXPOSE = ("globalThis.__clns = {panels: panels, showTab: showTab, fieldKo: fieldKo, "
             "codeKo: codeKo, channelKo: channelKo, "
             "verdictBlock: verdictBlock, labelSummaryText: labelSummaryText, shareUrl: shareUrl, "
             "shareState: shareState, setShareBar: setShareBar, humanError: humanError, "
             "liveStateKo: liveStateKo};")


def inline_script(page: str) -> str:
    match = re.search(r"<script>(.*?)</script>", page, re.S)
    if not match:
        raise AssertionError("인라인 스크립트를 찾지 못했습니다")
    return match.group(1)


def js_context(search: str = "", hash_value: str = ""):
    script = inline_script(web_ui.render_page()).rstrip()
    marker = "})();"
    if not script.endswith(marker):
        raise AssertionError("페이지 스크립트가 예상한 IIFE 형태가 아닙니다")
    body = script[: -len(marker)] + JS_EXPOSE + marker
    context = quickjs.Context()
    stub = JS_STUB.replace("__SEARCH__", search).replace("__HASH__", hash_value)
    context.eval(stub)
    context.eval(body)
    return context


def click_tab(context, key):
    """탭 버튼에 걸린 클릭 핸들러를 실제로 부른다(0.5.1 에서는 여기서 TypeError 가 났다)."""
    return context.eval(
        "(function(){ var hit = null;"
        " for (var i = 0; i < __listeners.length; i++){"
        "   if (__listeners[i][0] === 'tabbtn-" + key + "' && __listeners[i][1] === 'click'){ hit = __listeners[i][2]; }"
        " }"
        " if (!hit) throw new Error('tab handler missing: " + key + "');"
        " hit(); return true; })()")


SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*_[a-z0-9_]+")


class TabSwitchContractTest(unittest.TestCase):
    """P0: 네 탭이 모두 열리고, 없는 패널을 만나도 스크립트가 멈추지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    def test_panels_maps_every_tab_to_an_existing_section(self):
        for key, panel_id in TAB_PANELS.items():
            with self.subTest(tab=key):
                self.assertRegex(self.page, rf'{key}:\s*"{panel_id}"')
                self.assertIn(f'id="{panel_id}"', self.page)
                self.assertIn(f'data-tab="{key}"', self.page)

    def test_show_tab_guards_missing_panel(self):
        script = inline_script(self.page)
        block = script[script.index("function showTab"):]
        block = block[:block.index("var initial")]
        # 패널이 없을 때 곧바로 .hidden 을 만지지 않는다.
        self.assertNotIn(").hidden =", block)
        self.assertIn("if (panel) panel.hidden = !on;", block)

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_each_tab_click_shows_only_its_panel(self):
        context = js_context()
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                click_tab(context, key)  # 0.5.1: label 에서 TypeError
                for other in TAB_KEYS:
                    expected = other != key
                    self.assertEqual(
                        context.eval(f'__elements["{TAB_PANELS[other]}"].hidden'), expected,
                        (key, other))
                self.assertEqual(context.eval(f'__buttons[{TAB_KEYS.index(key)}].attrs["aria-selected"]'),
                                 "true")
                self.assertEqual(context.eval("__history[__history.length - 1]"), "#" + key)

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_label_hash_deep_link_opens_label_tab(self):
        context = js_context(hash_value="#label")
        self.assertFalse(context.eval('__elements["tab-label"].hidden'))
        self.assertTrue(context.eval('__elements["tab-check"].hidden'))

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_q_funnel_fills_product_and_opens_check_tab(self):
        context = js_context(search="?q=%EB%B8%94%EB%A3%A8%ED%88%AC%EC%8A%A4%20%EC%8A%A4%ED%94%BC%EC%BB%A4")
        self.assertEqual(context.eval('__elements["product"].value'), "블루투스 스피커")
        self.assertFalse(context.eval('__elements["tab-check"].hidden'))
        self.assertTrue(context.eval('__elements["tab-label"].hidden'))

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_item_share_funnel_fills_allowed_values_only(self):
        context = js_context(
            search="?item=%EB%B9%84%ED%83%80%EB%AF%BC%20D3&cat=food&origin=%EC%A4%91%EA%B5%AD")
        self.assertEqual(context.eval('__elements["product"].value'), "비타민 D3")
        self.assertEqual(context.eval('__elements["kind"].value'), "food")
        self.assertEqual(context.eval('__elements["origin"].value'), "중국")
        self.assertFalse(context.eval('__elements["tab-check"].hidden'))


class InternalKeyExposureTest(unittest.TestCase):
    """P1: 내부 키·상태 코드를 사용자 화면에 그대로 내보내지 않는다."""

    def test_label_map_covers_missing_information_spec_names(self):
        from import_compliance.standards import MISSING_FIELD_ALIAS

        script = inline_script(web_ui.render_page())
        block = script[script.index("var FIELD_LABELS_KO"):]
        block = block[:block.index("function fieldKo")]
        for name in sorted(set(MISSING_FIELD_ALIAS.values())):
            with self.subTest(field=name):
                self.assertRegex(block, rf"\b{name}:\s*\"")

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_missing_information_renders_korean_labels(self):
        context = js_context()
        html = context.eval(
            'globalThis.__clns.verdictBlock({code: "info_needed", label_ko: "추가 정보 필요", '
            'note_ko: "확인 항목이 남았습니다."}, {missing_information: '
            '["functional_cosmetic", "battery_type", "energy_density", "product_name", "unknown_internal_key"]})')
        visible = re.sub(r"<[^>]+>", " ", html)
        self.assertEqual(SNAKE_CASE.findall(visible), [], visible)
        for label in ("기능성화장품", "배터리", "에너지밀도", "제품명"):
            self.assertIn(label, html)
        self.assertIn("추가 확인 항목", html)

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_unmapped_key_never_reaches_the_screen(self):
        context = js_context()
        self.assertEqual(context.eval('globalThis.__clns.fieldKo("some_internal_key")'), "추가 확인 항목")
        self.assertEqual(context.eval('globalThis.__clns.fieldKo("기능성 표방")'), "기능성 표방")

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_error_codes_become_korean_messages(self):
        context = js_context()
        self.assertEqual(context.eval('globalThis.__clns.humanError({message: "product_name_required"})'),
                         "제품명을 입력해 주세요.")
        self.assertEqual(context.eval('globalThis.__clns.humanError({error: "hs_code_must_be_numeric"})'),
                         "HS 코드는 숫자 10자리로 입력해 주세요.")
        # 모르는 내부 코드도 그대로 노출하지 않는다.
        self.assertEqual(context.eval('globalThis.__clns.humanError({message: "some_new_code"})'),
                         "입력한 내용을 다시 확인해 주세요.")
        # 이미 한국어인 안내문은 그대로 둔다.
        self.assertEqual(context.eval('globalThis.__clns.humanError({message: "품목명을 적어 주세요."})'),
                         "품목명을 적어 주세요.")

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_live_state_codes_become_korean(self):
        context = js_context()
        self.assertEqual(context.eval('globalThis.__clns.liveStateKo("timeout")'), "응답 시간 초과")
        self.assertEqual(context.eval('globalThis.__clns.liveStateKo("network")'), "네트워크 연결 실패")
        self.assertEqual(context.eval('globalThis.__clns.liveStateKo("weird_new_state")'), "일시 오류")

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_country_and_channel_codes_are_korean(self):
        context = js_context()
        self.assertEqual(context.eval('globalThis.__clns.codeKo("KR")'), "대한민국")
        self.assertEqual(context.eval('globalThis.__clns.codeKo("CN")'), "중국")
        self.assertEqual(context.eval('globalThis.__clns.channelKo("carry")'), "휴대 반입")
        self.assertEqual(context.eval('globalThis.__clns.channelKo("online")'), "해외직구")
        html = context.eval(
            'globalThis.__clns.verdictBlock({code: "info_needed", label_ko: "추가 정보 필요", '
            'note_ko: "확인 항목이 남았습니다."}, {destination: "KR", jurisdiction: "KR", '
            'origin: "CN", assessment_status: "REVIEW_REQUIRED", '
            'assessment_status_label_ko: "검토 필요"})')
        self.assertIn("목적지 대한민국", html)
        self.assertIn("원산지 중국", html)
        visible = re.sub(r"<[^>]+>", " ", html)
        self.assertNotIn("REVIEW_REQUIRED", visible)
        self.assertNotRegex(visible, r"\b(KR|CN)\b")

    def test_label_actions_do_not_name_internal_tools(self):
        result = call_tool("check_korean_labeling", {"product_type": "kc_electronics"},
                           Store(":memory:"), client_id="test", tier="free")["result"]
        text = " ".join(result["next_actions"])
        for name in TOOL_INDEX:
            with self.subTest(tool=name):
                self.assertNotIn(name, text)
        self.assertIn("KC", text)

    def test_rra_guidance_does_not_print_internal_field_path(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        result = call_tool("assess_import_case",
                           {"query": "중국산 블루투스 스피커를 수입해 판매",
                            "facts": {"rf_tx": "yes", "purpose": "resale"}},
                           store, client_id="test", tier="free")["result"]
        text = " ".join(result.get("answer", {}).get("guidance") or [])
        self.assertNotIn("facts.", text)
        self.assertNotIn("rra_cert_no", text)


class DarkModeContrastTest(unittest.TestCase):
    """P1: 다크 모드 버튼·로고 대비가 WCAG AA(4.5:1) 이상."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()

    @staticmethod
    def _luminance(color: str) -> float:
        value = color.strip().lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]

        def linear(channel: float) -> float:
            return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

        r, g, b = (linear(channel) for channel in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @classmethod
    def contrast(cls, fg: str, bg: str) -> float:
        high, low = sorted((cls._luminance(fg), cls._luminance(bg)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def _tokens(self, css: str) -> dict:
        return dict(re.findall(r"(--[a-z-]+):\s*(#[0-9a-fA-F]{3,6})", css))

    def test_button_and_logo_tokens_meet_aa_in_both_schemes(self):
        light = self._tokens(self.page[: self.page.index("prefers-color-scheme: dark")])
        dark_block = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}",
                               self.page, re.S)
        self.assertIsNotNone(dark_block)
        dark = self._tokens(dark_block.group(1))
        for scheme, tokens in (("light", light), ("dark", dark)):
            with self.subTest(scheme=scheme):
                self.assertIn("--brand-fill", tokens)
                self.assertIn("--on-brand", tokens)
                ratio = self.contrast(tokens["--on-brand"], tokens["--brand-fill"])
                self.assertGreaterEqual(round(ratio, 2), 4.5, (scheme, tokens, ratio))

    def test_tokens_are_what_button_and_logo_use(self):
        self.assertRegex(self.page, r"\.mark\{[^}]*background:var\(--brand-fill\)[^}]*color:var\(--on-brand\)")
        self.assertRegex(self.page, r"button\.primary\{[^}]*color:var\(--on-brand\); background:var\(--brand-fill\)")

    def test_white_on_light_brand_is_gone(self):
        # 0.5.1 의 2.4:1 조합(#7ea6ff 배경 + 흰 글씨)을 다시 만들지 않는다.
        self.assertNotIn("color:#fff; background:var(--brand);", self.page)
        self.assertNotIn("background:var(--brand);color:#fff", self.page)


class CopyShareAndLabelTest(unittest.TestCase):
    """P1: CLNS Label 탭에도 요약 복사·공유 링크가 붙는다."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()
        cls.script = inline_script(cls.page)

    def test_label_share_bar_sits_in_label_tab(self):
        label_start = self.page.index('id="tab-label"')
        label_end = self.page.index('id="tab-hs"')
        bar = self.page.index('id="label-share"')
        self.assertGreater(bar, label_start)
        self.assertLess(bar, label_end)
        self.assertRegex(self.page, r'class="sharebar" id="label-share" hidden')
        self.assertIn('id="label-copy-summary"', self.page)
        self.assertIn('id="label-copy-link"', self.page)

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_label_summary_is_korean_and_names_no_internal_key(self):
        context = js_context()
        summary = context.eval(
            'globalThis.__clns.labelSummaryText({product_type_label_ko: "화장품", '
            'verdict: {label_ko: "확인 필요", code: "check_likely"}, '
            'required_count: 12, present_count: 7, missing_count: 5, '
            'missing: ["화장품의 명칭", "전성분"], conditional_missing: ["주의사항"], '
            'next_actions: ["누락 항목을 라벨에 추가하세요."], '
            'evidence: [{law: "화장품법", article: "제10조"}]})')
        self.assertIn("[CLNS 한글표시사항 체크] 화장품", summary)
        self.assertIn("확인 안 된 필수 항목: 화장품의 명칭, 전성분", summary)
        self.assertIn("근거 법령: 화장품법 제10조", summary)
        self.assertEqual(SNAKE_CASE.findall(summary), [], summary)
        self.assertTrue(summary.rstrip().endswith(BASE))

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_label_share_link_keeps_only_the_product_group(self):
        context = js_context()
        context.eval('globalThis.__clns.shareState.label = {summary: "", group: "cosmetics"};')
        self.assertEqual(context.eval('globalThis.__clns.shareUrl("label")'),
                         f"{BASE}/?lg=cosmetics#label")
        context.eval('globalThis.__clns.shareState.label = {summary: "", group: ""};')
        self.assertEqual(context.eval('globalThis.__clns.shareUrl("label")'), f"{BASE}/#label")

    @unittest.skipUnless(HAVE_QUICKJS, "quickjs 가 없어 JS 실행 검증은 건너뜁니다")
    def test_label_result_opens_share_bar_and_reset_hides_it(self):
        context = js_context()
        context.eval('document.getElementById("label-share");')
        self.assertTrue(context.eval('__elements["label-share"].hidden'))
        context.eval('globalThis.__clns.setShareBar("label-share", true);')
        self.assertFalse(context.eval('__elements["label-share"].hidden'))
        self.assertIn('setShareBar("label-share", true)', self.script)
        # 실패·초기화 두 경로에서 다시 감춘다.
        self.assertEqual(self.script.count('setShareBar("label-share", false)'), 2)


class NotFoundHtmlTest(unittest.TestCase):
    """P1: 페이지 주소는 사람용 404 HTML, API 주소는 종전 JSON 404."""

    @classmethod
    def setUpClass(cls):
        cls.store = Store(":memory:")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store, live=None))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()

    def raw(self, path, *, method="GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read()

    def test_unknown_page_returns_human_html(self):
        status, headers, body = self.raw("/nope-xyz")
        text = body.decode("utf-8")
        self.assertEqual(status, 404)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn("페이지를 찾을 수 없습니다", text)
        self.assertIn("404", text)
        for link in ('href="/"', 'href="/p/"', 'href="/guides/"'):
            self.assertIn(link, text)
        self.assertIn('name="robots" content="noindex"', text)
        # JSON 오류 본문을 그대로 돌려주지 않는다.
        self.assertNotIn('"error": "not_found"', text)
        # 외부 자원·스크립트 없이 완결된다.
        self.assertNotIn("<script", text.lower())
        self.assertNotIn("cdn.", text.lower())

    def test_unknown_item_and_guide_pages_are_human_404(self):
        for path in ("/p/no-such-item", "/guides/no-such-guide"):
            with self.subTest(path=path):
                status, headers, body = self.raw(path)
                self.assertEqual(status, 404)
                self.assertIn("text/html", headers.get("Content-Type", ""))
                self.assertIn("페이지를 찾을 수 없습니다", body.decode("utf-8"))

    def test_api_paths_keep_json_404(self):
        for path in ("/v1/nope-xyz", "/v1/inquiry"):
            with self.subTest(path=path):
                status, headers, body = self.raw(path)
                self.assertEqual(status, 404)
                self.assertIn("application/json", headers.get("Content-Type", ""))
                self.assertEqual(json.loads(body.decode("utf-8"))["error"], "not_found")

    def test_unknown_post_keeps_json_404(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/nope-xyz",
                                         data=b"{}", method="POST")
        try:
            urllib.request.urlopen(request, timeout=10)
            self.fail("404 가 나야 합니다")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
            self.assertIn("application/json", exc.headers.get("Content-Type", ""))

    def test_head_on_unknown_page_says_html(self):
        status, headers, _ = self.raw("/nope-xyz", method="HEAD")
        self.assertEqual(status, 404)
        self.assertIn("text/html", headers.get("Content-Type", ""))

    def test_not_found_page_escapes_reflected_path(self):
        html = web_ui.render_not_found('/nope"><script>alert(1)</script>')
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn('<script', html.lower())

    def test_render_not_found_truncates_long_paths(self):
        html = web_ui.render_not_found("/" + "a" * 500)
        self.assertNotIn("a" * 201, html)


class TypoAndToolTableTest(unittest.TestCase):
    """P1: 오타 제거와 API 탭 툴 목록 일치."""

    @classmethod
    def setUpClass(cls):
        cls.page = web_ui.render_page()
        cls.llms = static_files.llms_txt()

    def test_typo_is_fixed_everywhere(self):
        self.assertNotIn("전파 예생", self.page)
        self.assertIn("1인 1대 전파인증 예외", self.page)
        self.assertNotIn("전파 예생", self.llms)
        self.assertIn("1인 1대 전파인증 예외", self.llms)

    def test_api_tab_lists_every_real_tool(self):
        label_start = self.page.index('id="tab-api"')
        table = self.page[label_start:self.page.index("</section>", label_start)]
        listed = set(re.findall(r"<code>/v1/tools/([a-z_]+)</code>", table))
        self.assertEqual(listed - {"assess_import_risk"}, set(TOOL_INDEX))
        self.assertIn("check_feed_import", listed)
        self.assertIn("반려동물 사료", table)

    def test_footer_version_is_0_5_2(self):
        self.assertIn("v" + __version__, self.page)


class VersionSyncTest(unittest.TestCase):
    def test_version_bumped_and_synced(self):
        self.assertEqual(__version__, "0.5.8")
        self.assertEqual(web_ui.SERVICE_VERSION, "0.5.8")
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["version"], "0.5.8")
        with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as handle:
            self.assertIn('org.opencontainers.image.version="0.5.8"', handle.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
