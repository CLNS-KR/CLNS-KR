"""표준 라이브러리만으로 동작하는 경량 HTTP 서버 (사람용 웹 UI + JSON API).

배포 환경 대응
--------------
- `HOST` (기본 `0.0.0.0`), `PORT` (환경변수 우선, 기본 8787)
- `IMPORT_COMPLIANCE_DB` (기본 `data/recalls.sqlite` — 리콜 로컬 인덱스가 들어 있는 SQLite)
- `IMPORT_COMPLIANCE_LIVE=1` 이면 `.env`/환경변수의 공공 API 키로 실시간 조회 모드
- `python -m import_compliance.server` 한 줄로 기동, `--host/--port/--db/--live` 로 덮어쓰기

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

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._common_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, html: str) -> None:
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
            else:
                self._head(404, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path in ("/", "/index.html"):
                    self._send_html(200, render_page())
                elif path == "/favicon.ico":
                    self.send_response(204)
                    self._common_headers()
                    self.end_headers()
                elif path == "/healthz":
                    self._send_json(200, {"ok": True, "service": "clns-kr", "live": live is not None})
                elif path == "/v1/mcp":
                    self._send_json(200, mcp_manifest())
                elif path == "/v1/meta":
                    self._send_json(200, call_tool("get_service_meta", {}, store,
                                                   client_id=self._client(), tier=self._tier(),
                                                   live=live))
                else:
                    self._send_json(404, {"ok": False, "error": "not_found"})
            except Exception:  # noqa: BLE001 - 공개 배포에서 내부 정보를 노출하지 않는다
                self._send_json(500, {"ok": False, "error": "internal_error"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
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
