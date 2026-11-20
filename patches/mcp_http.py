"""MCP Streamable HTTP(JSON-RPC 2.0) 최소 구현 — 표준 라이브러리만 사용. (제안안, 아직 배포 안 됨)

지금 배포본은 `GET /v1/mcp` 하나만 있어서 MCP 클라이언트가 붙지 못한다.
`POST /v1/mcp`(initialize / tools/list / tools/call)를 이 모듈로 처리하면
Smithery·Cursor·Claude Code·공식 MCP Registry 의 remote 서버로 쓸 수 있다.

붙이는 방법 (server.py, do_POST 안 맨 위):

    path = urlparse(self.path).path
    if path in ("/mcp", "/v1/mcp"):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0") or 0)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(200, mcp_http.error_response(None, -32700, "parse_error"))
            return
        out = mcp_http.handle(payload, store=store, client_id=self._client(),
                              tier=self._tier(), live=live)
        if out is None:                      # notification → 본문 없이 202
            self.send_response(202)
            self._common_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(200, out)
        return

그리고 do_GET 의 "/v1/mcp" 는 **매니페스트 대신** 405 를 돌려주거나(권장),
기존 매니페스트를 `/v1/mcp/manifest` 로 옮긴다. 같은 경로가 GET 매니페스트와
POST JSON-RPC 를 겸하면 스캐너가 헷갈린다(Smithery 는 POST initialize 로 판정한다).

정직하게 남길 한계: 이 구현은 응답을 JSON 한 덩어리로 돌려준다(SSE 스트리밍 없음).
MCP 스펙상 서버가 스트리밍을 강제하지 않으므로 대부분의 클라이언트는 그대로 동작한다.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .api import call_tool, mcp_manifest

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "clns"
SERVER_VERSION = "0.1.1"


def _ok(msg_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def error_response(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text_result(result: Dict[str, Any], is_error: bool = False) -> Dict[str, Any]:
    """툴 결과를 MCP content 블록으로 감싼다. 사람/AI가 읽을 본문은 JSON 텍스트."""
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "structuredContent": result,
        "isError": is_error,
    }


def handle(payload: Any, *, store: Any, client_id: str = "anonymous", tier: str = "free",
           live: Any = None) -> Optional[Dict[str, Any]]:
    """JSON-RPC 한 건을 처리한다. notification(응답 없음)이면 None."""
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return error_response(None, -32600, "invalid_request")

    method = payload.get("method")
    msg_id = payload.get("id")                      # 없으면 notification
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return _ok(msg_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "한국 수입 규제 사전 점검. 품목명과 HS 10자리를 주면 세관장확인 요건·식약처 수입 이력·"
                "국내 리콜·근거 법령을 3단계로 판정한다. 확정 판정이 아니며, 0건은 '요건 없음'이 아니다. "
                "결과의 disclaimer 와 scope_limits_ko 를 사용자에게 함께 전달할 것."
            ),
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _ok(msg_id, {})

    if method == "tools/list":
        manifest = mcp_manifest()
        return _ok(msg_id, {"tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in manifest["tools"]
        ]})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return error_response(msg_id, -32602, "invalid_params")
        result = call_tool(name, arguments, store, client_id=client_id, tier=tier, live=live)
        if isinstance(result, dict) and result.get("ok") is False:
            return _ok(msg_id, _text_result(result, is_error=True))
        return _ok(msg_id, _text_result(result))

    if msg_id is None:                              # 알 수 없는 notification 은 조용히 무시
        return None
    return error_response(msg_id, -32601, "method_not_found")


def batch(payloads: List[Any], **kwargs: Any) -> List[Dict[str, Any]]:
    """JSON-RPC 배치(2025-03-26 까지 허용). 최신 스펙은 배치를 지원하지 않으므로 선택 사항."""
    out = []
    for item in payloads:
        res = handle(item, **kwargs)
        if res is not None:
            out.append(res)
    return out
