"""stdio MCP 엔트리포인트 — `python -m import_compliance.mcp_stdio`.

Glama·mcp.so 같은 로컬 실행형 MCP 디렉터리는 "클라이언트가 프로세스를 띄워
stdin/stdout 으로 대화하는 서버"를 기본으로 본다. HTTP 서버(`server.py`)와
같은 툴·같은 JSON-RPC 로직(`mcp_http.handle`)을 그대로 재사용하되, 전송만
한 줄에 한 건씩 주고받는 JSON-RPC 로 바꾼다.

전송 규격
---------
- stdin: 한 줄에 JSON-RPC 2.0 메시지 1건(개행 구분). 빈 줄은 무시한다.
- stdout: 요청(id 있음)에 대한 응답 1줄. notification(응답 없음)에는 아무것도 쓰지 않는다.
- 로그는 전부 stderr 로 보낸다(디렉터리·클라이언트가 stdout 을 파싱하므로).

설정(환경변수)
--------------
- `IMPORT_COMPLIANCE_DB` — 카운터·캐시용 SQLite 경로. 없으면 `:memory:`(프로세스 종료 시 소멸).
- `IMPORT_COMPLIANCE_LIVE=1` — `.env`/환경변수의 공공 API 키로 실시간 조회.
  키가 없으면 코퍼스·법령 근거만으로 동작한다.

한계
----
- stdio 는 1:1 연결이라 인증·세션 개념이 없다(HTTP 와 동일하게 무인증).
- 파일 잠금이 필요한 다중 프로세스 공유 DB 는 지원하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional, TextIO

from . import mcp_http
from .api import mcp_tools  # noqa: F401 - 클라이언트 introflection 호환용 재노출
from .store import Store
from .version import __version__


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def serve(stdin: TextIO, stdout: TextIO, *, store: Store, live: Any = None,
          client_id: str = "stdio", tier: str = "free") -> int:
    """줄 단위 JSON-RPC 루프. 테스트에서 파이프를 그대로 주입할 수 있다."""
    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(mcp_http.error_response(None, -32700, "parse_error")) + "\n")
            stdout.flush()
            continue
        try:
            if isinstance(payload, list):
                # 최신 MCP 스펙은 배치를 지원하지 않지만, 들어오면 한 줄에 배열로 돌려준다.
                out = mcp_http.batch(payload, store=store, client_id=client_id,
                                     tier=tier, live=live)
                if out:
                    stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
                    stdout.flush()
                continue
            response = mcp_http.handle(payload, store=store, client_id=client_id,
                                       tier=tier, live=live)
        except Exception:  # noqa: BLE001 - 내부 정보를 노출하지 않고 JSON-RPC 오류로만
            response = mcp_http.error_response(
                payload.get("id") if isinstance(payload, dict) else None,
                -32603, "internal_error")
        if response is None:  # notification → 출력 없음
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0


def _store_from_env(path: Optional[str] = None) -> Store:
    target = (path or os.environ.get("IMPORT_COMPLIANCE_DB") or "").strip() or ":memory:"
    if target != ":memory:":
        directory = os.path.dirname(os.path.abspath(target))
        if directory:
            os.makedirs(directory, exist_ok=True)
    return Store(target)


def _live_from_env(enabled: bool) -> Any:
    if not enabled:
        return None
    from .live_api import from_environment

    return from_environment()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m import_compliance.mcp_stdio",
        description="CLNS stdio MCP 서버 — 한국 수입 규제 사전 점검(세관장확인·식약처·리콜·근거 법령). "
                    "한 줄에 JSON-RPC 2.0 한 건씩 stdin 으로 받고 stdout 으로 응답한다.",
    )
    parser.add_argument("--db", default=None,
                        help="SQLite 경로(기본: 환경변수 IMPORT_COMPLIANCE_DB, 없으면 :memory:)")
    parser.add_argument("--live", action="store_true",
                        help="실API 모드(.env/환경변수 키 사용)")
    parser.add_argument("--version", action="version", version=f"clns {__version__}")
    args = parser.parse_args(argv)

    live_on = args.live or str(os.environ.get("IMPORT_COMPLIANCE_LIVE", "")).strip().lower() in (
        "1", "true", "yes", "on")
    live = _live_from_env(live_on)
    if live_on and live is None:
        _log("경고: IMPORT_COMPLIANCE_LIVE 이지만 DATA_GO_KR_SERVICE_KEY / LAW_GO_KR_OC 가 없습니다. "
             "코퍼스·법령 근거만으로 동작합니다.")
    elif live is not None:
        from .live_api import register_sources

        _log(f"실API 모드: {live.capabilities()}")

    store = _store_from_env(args.db)
    if live is not None:
        try:
            from .live_api import register_sources

            register_sources(store)
        except Exception:  # noqa: BLE001
            pass
    _log(f"CLNS stdio MCP ready (v{__version__}, tools={len(mcp_tools())}, db={store.path})")
    try:
        return serve(sys.stdin, sys.stdout, store=store, live=live)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
