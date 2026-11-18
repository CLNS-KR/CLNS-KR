"""표준 라이브러리만으로 동작하는 경량 HTTP 서버 (사람용 웹 UI + JSON API + MCP).

배포 환경 대응
--------------
- `HOST` (기본 `0.0.0.0`), `PORT` (환경변수 우선, 기본 8787)
- `IMPORT_COMPLIANCE_DB` (기본 `data/recalls.sqlite` — 리콜 로컬 인덱스가 들어 있는 SQLite)
- `IMPORT_COMPLIANCE_LIVE=1` 이면 `.env`/환경변수의 공공 API 키로 실시간 조회 모드
- `PUBLIC_BASE_URL` 로 robots/llms/sitemap 의 공개 주소를 바꿀 수 있다
- `python -m import_compliance.server` 한 줄로 기동, `--host/--port/--db/--live` 로 덮어쓰기

경로
----
- `GET /` 사람용 웹 UI · `GET /healthz`
- `GET /p/` 품목별 수입 요건 인덱스 · `GET /p/{slug}` 품목별 무료 체크 페이지(서버 렌더 HTML, JS 없음)
- `GET /v1/stats` 익명 일별 사용 통계(IP·UA·쿠키 미저장)
- `POST /mcp` · `POST /v1/mcp` MCP JSON-RPC 2.0 (initialize·tools/list·tools/call·ping)
- `GET /.well-known/mcp/server-card.json` MCP 서버 카드
- `GET /v1/mcp` 툴 매니페스트(사람이 읽는 JSON) · `GET /v1/meta`
- `POST /v1/tools/{tool}` REST JSON
- `GET /robots.txt` · `GET /llms.txt` · `GET /sitemap.xml` · `GET /static/og.png`
- `OPTIONS *` CORS preflight(204) — 모든 응답에 `Access-Control-Allow-Origin: *`

보안
----
- 키는 응답·페이지·로그 어디에도 쓰지 않는다(키가 있으면 capabilities 불리언만 노출).
- 페이지는 외부 CDN 없이 인라인 CSS/JS만 쓰고, CSP로 외부 로드를 막는다.
- 처리되지 않은 예외는 스택트레이스 없이 `internal_error`로 응답한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from . import mcp_http, pseo, static_files, usage
from .api import call_tool, mcp_manifest
from .live_api import from_environment, register_sources
from .store import Store
from .web_ui import render_page

MAX_BODY = 64 * 1024
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787

# 웹 UI가 부르는 이름과 실제 툴 이름이 다른 경우를 흡수한다(매니페스트에는 정식 이름만 노출).
TOOL_ALIASES: Dict[str, str] = {"assess_import_risk": "assess_import_case"}

CLIENT_ID_RE = re.compile(r"[^0-9A-Za-z._:-]")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'"
    ),
}

# 브라우저 기반 MCP 클라이언트(Glama 플레이그라운드 등)가 바로 붙을 수 있게 모든 응답에 CORS 를 준다.
# 인증이 없는 공개 읽기 API이므로 `*` 로 열어도 노출되는 비밀이 없다(키는 서버 쪽에만 있다).
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, Accept, X-Client-Id, X-Tier, MCP-Protocol-Version, Last-Event-ID"
    ),
    "Access-Control-Expose-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}

MCP_PATHS = ("/mcp", "/v1/mcp")


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def default_db_path() -> str:
    """서버 작업 DB(판정 이력·쿼터·캐시). 이미지에 넣어 둔 리콜 인덱스는 기동 시 복사해 온다."""
    return os.path.join(project_root(), "data", "app.sqlite")


def _int_env(value: Optional[str], fallback: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return parsed if 0 <= parsed <= 65535 else fallback


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def config_from_env(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """환경변수만 읽어 서버 설정을 만든다(부작용 없음)."""
    env = os.environ if env is None else env
    return {
        "host": (env.get("HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST,
        "port": _int_env(env.get("PORT"), DEFAULT_PORT),
        "db_path": (env.get("IMPORT_COMPLIANCE_DB") or "").strip() or default_db_path(),
        "live_mode": _truthy(env.get("IMPORT_COMPLIANCE_LIVE")),
    }


def _client_id(raw: Optional[str]) -> str:
    value = CLIENT_ID_RE.sub("", str(raw or ""))[:64]
    return value or "anonymous"


def _days_param(query: str) -> int:
    """`?days=7` 같은 질의값을 1~30 사이 정수로 해석한다(불량이면 기본값)."""
    from urllib.parse import parse_qs

    try:
        raw = (parse_qs(query or "").get("days") or [""])[0]
        return int(raw)
    except (TypeError, ValueError):
        return usage.DEFAULT_DAYS


def make_handler(store: Store, live=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "clns/0.1"
        sys_version = ""

        def version_string(self) -> str:  # 파이썬 버전 노출 없이 제품명만
            return self.server_version

        # --- 응답 헬퍼 -----------------------------------------------------
        def _common_headers(self) -> None:
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            for key, value in CORS_HEADERS.items():
                self.send_header(key, value)

        def _send_json(self, status: int, payload: Any, cache: str = "no-store") -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self._common_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, status: int, text: str, content_type: str,
                       cache: str = "public, max-age=3600") -> None:
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self._common_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, status: int, body: bytes, content_type: str,
                        cache: str = "public, max-age=86400") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self._common_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self._common_headers()
            self.end_headers()

        def _send_html(self, status: int, html: str,
                       cache: str = "no-cache") -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self._common_headers()
            self.end_headers()
            self.wfile.write(body)

        def _head(self, status: int, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", "0")
            self._common_headers()
            self.end_headers()

        def log_message(self, fmt: str, *args: Any) -> None:  # 조용한 로그(경로·상태만)
            return

        # --- 라우팅 ---------------------------------------------------------
        def do_HEAD(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._head(200, "text/html; charset=utf-8")
            elif path == "/healthz":
                self._head(200, "application/json; charset=utf-8")
            elif path == "/robots.txt":
                self._head(200, "text/plain; charset=utf-8")
            elif path == "/llms.txt":
                self._head(200, "text/plain; charset=utf-8")
            elif path == "/sitemap.xml":
                self._head(200, "application/xml; charset=utf-8")
            elif path == "/.well-known/mcp/server-card.json":
                self._head(200, "application/json; charset=utf-8")
            elif path == "/static/og.png":
                self._head(200, "image/png")
            elif path in ("/p", "/p/"):
                self._head(200, "text/html; charset=utf-8")
            elif path.startswith("/p/"):
                self._head(200, "text/html; charset=utf-8")
            elif path == "/v1/stats":
                self._head(200, "application/json; charset=utf-8")
            else:
                self._head(404, "application/json; charset=utf-8")

        def do_OPTIONS(self) -> None:  # noqa: N802
            """CORS preflight. 브라우저 기반 MCP·API 클라이언트가 본문 없이 호출할 수 있다."""
            self.send_response(204)
            self.send_header("Allow", "GET, POST, HEAD, OPTIONS")
            self.send_header("Content-Length", "0")
            self._common_headers()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            usage.record_request(store, "GET", path)
            try:
                if path in ("/", "/index.html"):
                    self._send_html(200, render_page())
                elif path in ("/p", "/p/"):
                    self._send_html(200, pseo.render_index())
                elif path.startswith("/p/"):
                    slug = path[len("/p/"):].strip("/")
                    page = pseo.render_item(slug)
                    if page is None:
                        self._send_json(404, {"ok": False, "error": "not_found",
                                              "message": "unknown_item"})
                    else:
                        self._send_html(200, page, cache="public, max-age=600")
                elif path == "/favicon.ico":
                    self.send_response(204)
                    self._common_headers()
                    self.end_headers()
                elif path == "/healthz":
                    self._send_json(200, {"ok": True, "service": "clns-kr", "live": live is not None})
                elif path == "/robots.txt":
                    self._send_text(200, static_files.robots_txt(), "text/plain; charset=utf-8")
                elif path == "/llms.txt":
                    self._send_text(200, static_files.llms_txt(), "text/plain; charset=utf-8")
                elif path == "/sitemap.xml":
                    self._send_text(200, static_files.sitemap_xml(), "application/xml; charset=utf-8")
                elif path == "/.well-known/mcp/server-card.json":
                    self._send_json(200, static_files.server_card(),
                                    cache="public, max-age=300")
                elif path == "/static/og.png":
                    image = static_files.load_og_image()
                    if image is None:
                        self._send_json(404, {"ok": False, "error": "not_found"})
                    else:
                        self._send_bytes(200, image, "image/png")
                elif path == "/v1/mcp":
                    # GET 은 사람이 읽는 매니페스트다. JSON-RPC 는 POST /mcp · POST /v1/mcp 가 담당한다.
                    self._send_json(200, mcp_manifest())
                elif path == "/v1/meta":
                    self._send_json(200, call_tool("get_service_meta", {}, store,
                                                   client_id=self._client(), tier=self._tier(),
                                                   live=live))
                elif path == "/v1/stats":
                    days = urlparse(self.path).query
                    self._send_json(200, usage.stats_payload(store, _days_param(days)),
                                    cache="public, max-age=300")
                elif path.rstrip("/") == "/mcp":
                    # 스트리밍(SSE) GET 은 제공하지 않는다. MCP 스펙이 허용하는 405 로 알린다.
                    self.send_response(405)
                    self.send_header("Allow", "POST, OPTIONS")
                    self.send_header("Content-Length", "0")
                    self._common_headers()
                    self.end_headers()
                else:
                    self._send_json(404, {"ok": False, "error": "not_found"})
            except Exception:  # noqa: BLE001 - 공개 배포에서 내부 정보를 노출하지 않는다
                self._send_json(500, {"ok": False, "error": "internal_error"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            usage.record_request(store, "POST", path)
            if path.rstrip("/") in MCP_PATHS:
                self._handle_mcp()
                return
            if not path.startswith("/v1/tools/"):
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            name = path.rsplit("/", 1)[-1]
            name = TOOL_ALIASES.get(name, name)
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                self._send_json(400, {"ok": False, "error": "invalid_content_length"})
                return
            if length > MAX_BODY:
                self._send_json(413, {"ok": False, "error": "payload_too_large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                args = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"ok": False, "error": "invalid_json"})
                return
            if not isinstance(args, dict):
                self._send_json(400, {"ok": False, "error": "invalid_argument",
                                      "message": "request_body_must_be_object"})
                return
            try:
                result = call_tool(name, args, store, client_id=self._client(),
                                   tier=self._tier(), live=live)
            except Exception:  # noqa: BLE001
                self._send_json(500, {"ok": False, "error": "internal_error", "tool": name})
                return
            self._send_json(200, result)

        # --- MCP (JSON-RPC 2.0) ---------------------------------------------
        def _handle_mcp(self) -> None:
            """POST /mcp · POST /v1/mcp — JSON-RPC 2.0 한 건 또는 배치를 처리한다."""
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                self._send_json(400, mcp_http.error_response(None, -32600, "invalid_content_length"))
                return
            if length > MAX_BODY:
                self._send_json(413, mcp_http.error_response(None, -32600, "payload_too_large"))
                return
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw.strip() else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(200, mcp_http.error_response(None, -32700, "parse_error"))
                return
            try:
                options = {"store": store, "client_id": self._client(),
                           "tier": self._tier(), "live": live}
                if isinstance(payload, list):
                    if not payload:
                        self._send_json(200, mcp_http.error_response(None, -32600, "invalid_request"))
                        return
                    out = mcp_http.batch(payload, **options)
                    if not out:
                        self._send_empty(202)
                        return
                    self._send_json(200, out)
                    return
                out = mcp_http.handle(payload, **options)
            except Exception:  # noqa: BLE001 - 내부 정보를 노출하지 않는다
                self._send_json(500, mcp_http.error_response(None, -32603, "internal_error"))
                return
            if out is None:  # notification → 본문 없이 202
                self._send_empty(202)
                return
            self._send_json(200, out)

        # --- 요청 메타 ------------------------------------------------------
        def _client(self) -> str:
            return _client_id(self.headers.get("X-Client-Id"))

        def _tier(self) -> str:
            tier = str(self.headers.get("X-Tier", "free") or "free").strip().lower()
            return tier if tier in ("free", "pro_waitlist") else "free"

    return Handler


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, db_path: str = "",
          live=None) -> None:
    """서버를 기동한다(블로킹). db_path가 비면 작업 DB(data/app.sqlite)를 쓴다."""
    from . import recall_index

    db_path = db_path or default_db_path()
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    store = Store(db_path)
    # 리콜 로컬 인덱스(이미지 포함)를 작업 DB로 복사한다 — 원본 파일은 쓰지 않는다.
    try:
        recall_index.load_from_index(store)
    except Exception:  # noqa: BLE001 - 인덱스 복사 실패가 기동을 막지 않게
        pass
    if live is not None:
        register_sources(store)
    httpd = ThreadingHTTPServer((host, port), make_handler(store, live=live))
    # Render 같은 PaaS는 PORT를 주입하고 로그로 기동 확인을 하므로 즉시 출력한다.
    print(f"CLNS listening on http://{host}:{port} "
          f"(db={db_path}, live={'on' if live is not None else 'off'})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        store.close()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m import_compliance.server",
        description="CLNS HTTP 서버 — Korea Import Compliance MCP & API · PRODUCT COMPLIANCE INTELLIGENCE · KOREA (웹 UI + JSON API)",
    )
    parser.add_argument("--host", default=None, help="바인드 주소 (기본 0.0.0.0, 환경변수 HOST)")
    parser.add_argument("--port", type=int, default=None, help="포트 (기본 8787, 환경변수 PORT 우선)")
    parser.add_argument("--db", default=None, help="SQLite 경로 (기본 data/recalls.sqlite)")
    parser.add_argument("--live", action="store_true", help="실API 조회 모드(.env/환경변수 키 사용)")
    parser.add_argument("--no-live", action="store_true", help="IMPORT_COMPLIANCE_LIVE=1 이어도 코퍼스 모드로 기동")
    args = parser.parse_args(argv)

    cfg = config_from_env()
    host = args.host or cfg["host"]
    port = args.port if args.port is not None else cfg["port"]
    db_path = args.db or cfg["db_path"]
    live_on = args.live or (cfg["live_mode"] and not args.no_live)

    live = None
    if live_on:
        live = from_environment()
        if live is None:
            print("경고: 실API 모드지만 DATA_GO_KR_SERVICE_KEY / LAW_GO_KR_OC 가 없습니다. "
                  "코퍼스·법령 근거만으로 동작합니다.", file=sys.stderr, flush=True)
        else:
            print(f"실API 모드: {live.capabilities()}", flush=True)

    serve(host=host, port=port, db_path=db_path, live=live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
