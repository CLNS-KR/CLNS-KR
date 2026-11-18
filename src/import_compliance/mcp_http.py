"""MCP Streamable HTTP(JSON-RPC 2.0) 최소 구현 — 표준 라이브러리만 사용.

`POST /mcp` · `POST /v1/mcp` 로 들어온 JSON-RPC 2.0 한 건(또는 배치)을 처리한다.
지원 메서드: `initialize`, `notifications/initialized`, `notifications/cancelled`,
`ping`, `tools/list`, `tools/call`, `resources/list`, `prompts/list`.
그 밖의 요청은 JSON-RPC 표준 에러(-32601)로 돌려준다.

정직하게 남길 한계
------------------
- 응답은 `application/json` 한 덩어리다(SSE 스트리밍 없음). MCP 스펙은 서버에
  스트리밍을 강제하지 않으므로 대부분의 클라이언트는 그대로 동작한다.
- 상태를 저장하지 않는다(세션 ID 없음). 툴 호출에는 인증이 필요 없다.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .api import call_tool, mcp_tools
from .version import __version__

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "clns"
SERVER_VERSION = __version__

INSTRUCTIONS_KO = (
    "한국 수입 규제 사전 점검. 품목명과 HS 10자리를 주면 세관장확인 요건·식약처 수입 이력·"
    "국내 리콜·근거 법령을 3단계로 판정한다. 확정 판정이 아니며, 0건은 '요건 없음'이 아니다. "
    "결과의 disclaimer 와 scope_limits_ko 를 사용자에게 함께 전달할 것."
)


def _ok(msg_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def error_response(msg_id: Any, code: int, message: str,
                   data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


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
            "instructions": INSTRUCTIONS_KO,
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _ok(msg_id, {})

    if method == "tools/list":
        return _ok(msg_id, {"tools": mcp_tools()})

    if method == "resources/list":
        return _ok(msg_id, {"resources": []})

    if method == "prompts/list":
        return _ok(msg_id, {"prompts": []})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return error_response(msg_id, -32602, "invalid_params")
        result = call_tool(name, arguments, store, client_id=client_id, tier=tier, live=live)
        if isinstance(result, dict) and result.get("ok") is False:
            if result.get("error") == "unknown_tool":
                # 툴 이름 자체가 없으면 프로토콜 오류로 알린다(클라이언트가 목록을 다시 읽도록).
                return error_response(msg_id, -32602, "unknown_tool",
                                      data={"tool": name})
            return _ok(msg_id, _text_result(result, is_error=True))
        return _ok(msg_id, _text_result(result))

    if msg_id is None:                              # 알 수 없는 notification 은 조용히 무시
        return None
    return error_response(msg_id, -32601, "method_not_found", data={"method": method})


def batch(payloads: List[Any], **kwargs: Any) -> List[Dict[str, Any]]:
    """JSON-RPC 배치(2025-03-26 까지 허용). 최신 스펙은 배치를 지원하지 않으므로 선택 사항."""
    out = []
    for item in payloads:
        res = handle(item, **kwargs)
        if res is not None:
            out.append(res)
    return out
