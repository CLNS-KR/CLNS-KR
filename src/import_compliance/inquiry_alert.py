"""문의 접수 알림 — 영구 디스크가 없는 배포에서도 리드를 잃지 않게 한다.

배경
----
`POST /v1/inquiry` 는 CLNS Pro 사전 신청ㆍ도입 문의를 SQLite 에만 담았다. Render 무료
플랜처럼 영구 디스크가 없으면 재기동ㆍ슬립 해제마다 DB 가 비어 문의가 사라지고,
관리자 알림도 없어 접수 사실조차 알 수 없었다(외부 코드 검수 제보).

세 겹으로 남긴다
--------------
1. **SQLite** `inquiries` — 서버가 살아 있는 동안의 원본(기존 그대로).
2. **append-only 저널** `data/inquiries.jsonl` — `data/` 가 볼륨이면 재기동 후 DB 로
   복원한다(`store.seed_inquiries`). 권한은 600.
3. **웹훅 알림**(선택) — `CLNS_INQUIRY_WEBHOOK_URL` 이 설정돼 있으면 접수 즉시 JSON 을
   POST 해 운영자 채널에 사본을 남긴다. 주소는 운영자가 환경변수로만 넣는다(사용자
   입력을 URL 로 쓰지 않으므로 SSRF 경로가 아니다).
4. **stdout 한 줄** — 플랫폼 로그에 남겨, 2ㆍ3 이 모두 실패해도 흔적이 남게 한다.
   연락처는 마스킹하고 메모 본문은 쓰지 않는다.

연락처는 문의에 회신하기 위한 목적에만 쓴다. 웹훅 본문에 연락처를 넣는 것이 기본이고
(`CLNS_INQUIRY_WEBHOOK_EXCLUDE_CONTACT=1` 이면 마스킹본만 보낸다), 공개 집계ㆍ공개
응답으로는 내보내지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

INQUIRY_EVENT = "clns_inquiry"
WEBHOOK_TIMEOUT_SECONDS = 3.0
_ALLOWED_SCHEMES = ("http://", "https://")


def mask_contact(contact: str) -> str:
    """로그ㆍ알림 미리보기용 마스킹(원문은 저장 경로에만 둔다)."""
    text = str(contact or "").strip()
    if "@" in text:
        local, _, domain = text.partition("@")
        head = local[:2]
        return f"{head}{'*' * max(1, len(local) - len(head))}@{domain}"
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 7:
        return "***-" + digits[-4:]
    return "***"


def webhook_payload(record: Dict[str, Any], topic: str, contact: str, message: str,
                    *, include_contact: bool = True,
                    cohort: str = "") -> Dict[str, Any]:
    """웹훅 본문. 회신에 필요한 최소 항목만 담는다(문의 전문은 담지 않는다).

    `cohort`(0.5.4)는 무료 베타·소개 유입 구분 태그로, 값이 있을 때만 넣는다.
    """
    payload: Dict[str, Any] = {
        "event": INQUIRY_EVENT,
        "id": record.get("id"),
        "received_at": record.get("received_at"),
        "topic": topic,
        "contact_masked": mask_contact(contact),
        "message_chars": len(message or ""),
    }
    tag = str(cohort or record.get("cohort") or "").strip()
    if tag:
        payload["cohort"] = tag
    if include_contact:
        payload["contact"] = contact
        if message:
            payload["message"] = message
    return payload


def _default_sender(url: str, body: bytes, timeout: float) -> int:
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "CLNS-inquiry-alert/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 운영자가 설정한 http(s) 주소만
        return int(getattr(response, "status", 200) or 200)


def post_webhook(url: str, payload: Dict[str, Any], *,
                 sender: Optional[Callable[[str, bytes, float], int]] = None,
                 timeout: float = WEBHOOK_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """웹훅 1건 전송. 실패해도 예외를 올리지 않고 상태로 돌려준다."""
    target = str(url or "").strip()
    if not target:
        return {"state": "skipped", "note_ko": "CLNS_INQUIRY_WEBHOOK_URL 이 설정되지 않았습니다."}
    if not target.lower().startswith(_ALLOWED_SCHEMES):
        return {"state": "skipped", "note_ko": "웹훅 주소는 http(s) 여야 합니다."}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        status = int((sender or _default_sender)(target, body, timeout))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return {"state": "failed", "error": type(exc).__name__}
    except Exception as exc:  # noqa: BLE001 - 알림 실패가 접수를 막지 않는다
        return {"state": "failed", "error": type(exc).__name__}
    if status >= 400:
        return {"state": "failed", "status": status}
    return {"state": "sent", "status": status}


def alert(record: Dict[str, Any], topic: str, contact: str, message: str, *,
          cohort: str = "",
          webhook_url: Optional[str] = None,
          sender: Optional[Callable[[str, bytes, float], int]] = None,
          stream: Any = None) -> Dict[str, Any]:
    """접수 1건 알림. 저널 상태는 `record['journal']` 에서 읽어 함께 보고한다."""
    url = webhook_url
    if url is None:
        url = os.environ.get("CLNS_INQUIRY_WEBHOOK_URL") or ""
    exclude = str(os.environ.get("CLNS_INQUIRY_WEBHOOK_EXCLUDE_CONTACT") or "").strip().lower()
    include_contact = exclude not in ("1", "true", "yes", "on")
    payload = webhook_payload(record, topic, contact, message, include_contact=include_contact,
                              cohort=cohort)
    result: Dict[str, Any] = {
        "journal": str(record.get("journal") or "unknown"),
        "webhook": post_webhook(url, payload, sender=sender),
    }
    tag = str(payload.get("cohort") or "")
    line = (f"[inquiry] id={record.get('id')} topic={topic} "
            f"contact={payload['contact_masked']} received_at={record.get('received_at')} "
            f"message_chars={payload['message_chars']} journal={result['journal']} "
            f"webhook={result['webhook'].get('state')}")
    if tag:
        line += f" cohort={tag}"
    try:
        out = stream or None
        if out is not None:
            print(line, file=out, flush=True)
        else:
            print(line, flush=True)
        result["log"] = "ok"
    except Exception:  # noqa: BLE001 - 로그 실패도 접수를 막지 않는다
        result["log"] = "failed"
    return result
