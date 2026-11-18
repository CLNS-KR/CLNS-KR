"""익명 일별 사용 카운터.

무엇을 남기는가
--------------
- `date (YYYY-MM-DD, Asia/Seoul)` · 경로 · 툴 이름 · `verdict.code` · 0건/오류 여부의 **호출 수**만.

무엇을 남기지 않는가
--------------------
- IP(및 X-Forwarded-For 같은 전달 헤더), User-Agent 원문, 쿠키, Referer, 세션 ID,
  클라이언트 ID, 질의문 원문. 집계 키는 서버가 아는 경로·툴 이름으로만 한정하고,
  모르는 경로는 `/404` 한 칸으로 뭉갠다(임의 문자열이 통계에 남지 않게).

한계
----
- 무료 플랜은 영구 디스크가 없어 재배포 시 카운터가 초기화된다(일별 집계라 감수).
- 여러 워커 프로세스가 각자 SQLite 를 쓰면 합산되지 않는다(단일 인스턴스 전제).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

KST_OFFSET = timedelta(hours=9)
KST = timezone(KST_OFFSET)
MAX_DAYS = 30
DEFAULT_DAYS = 7

# 집계 종류(kind)
KIND_PATH = "path"
KIND_TOOL = "tool"
KIND_VERDICT = "verdict"
KIND_FLAG = "flag"
KINDS = (KIND_PATH, KIND_TOOL, KIND_VERDICT, KIND_FLAG)

VERDICT_CODES = ("check_likely", "info_needed", "low_risk")
FLAG_ZERO = "zero_results"
FLAG_ERROR = "errors"
FLAG_QUOTA = "quota_exceeded"

FIXED_PATHS = (
    "/", "/p/", "/healthz", "/robots.txt", "/llms.txt", "/sitemap.xml",
    "/.well-known/mcp/server-card.json", "/static/og.png", "/v1/meta", "/v1/mcp",
    "/v1/stats", "/v1/tools", "/mcp", "/favicon.ico", "/404",
)

KEY_RE = re.compile(r"[^0-9A-Za-z._:/{}-]")
MAX_KEY = 64


def today_kst() -> str:
    """KST 기준 오늘 날짜(YYYY-MM-DD). 서버 타임존과 무관하게 계산한다."""
    return datetime.now(KST).strftime("%Y-%m-%d")


def _day_shift(day: str, delta_days: int) -> str:
    base = datetime.strptime(day, "%Y-%m-%d")
    return (base + timedelta(days=delta_days)).strftime("%Y-%m-%d")


def safe_key(value: Any) -> str:
    """집계 키 정화 — 허용 문자만 남기고 자른다(임의 입력이 통계에 남지 않게)."""
    return KEY_RE.sub("", str(value or ""))[:MAX_KEY]


def _known_paths() -> set:
    paths = set(FIXED_PATHS)
    try:
        from . import pseo  # 지연 import(모듈 순환 방지)

        for slug in pseo.slugs():
            paths.add(f"/p/{slug}")
    except Exception:  # noqa: BLE001 - 카탈로그가 없어도 카운터는 동작해야 한다
        pass
    return paths


def path_key(path: str) -> str:
    """요청 경로 → 집계 키. 아는 경로만 그대로, 나머지는 `/404`."""
    raw = str(path or "").split("?", 1)[0]
    if not raw.startswith("/"):
        return "/404"
    trimmed = raw.rstrip("/") if raw.rstrip("/") else "/"
    if trimmed.startswith("/v1/tools/"):
        return "/v1/tools"
    known = _known_paths()
    for candidate in (raw, trimmed):
        if candidate in known:
            return candidate
    return "/404"


def record_request(store: Any, method: str, path: str, day: Optional[str] = None) -> None:
    """요청 1건을 경로 버킷에 센다. GET/POST 이외 메서드는 세지 않는다."""
    if store is None or str(method or "").upper() not in ("GET", "POST"):
        return
    try:
        store.bump_usage(day or today_kst(), KIND_PATH, path_key(path))
    except Exception:  # noqa: BLE001 - 계측 실패가 응답을 막지 않는다
        pass


def _zero_result(name: str, result: Any) -> bool:
    """'조회 0건'을 셀 수 있는 툴만 판별한다(모르면 False)."""
    data = result if isinstance(result, dict) else {}
    payload = data.get("result") if isinstance(data.get("result"), dict) else data
    if not isinstance(payload, dict):
        return False
    if name == "lookup_recall":
        recall = payload.get("recall") if isinstance(payload.get("recall"), dict) else {}
        count = recall.get("match_count")
        return isinstance(count, int) and count == 0
    if name in ("lookup_hs_requirements", "assess_import_case"):
        block = payload.get("hs_requirements_live")
        if isinstance(block, dict) and block.get("state") == "live":
            count = block.get("requirement_count")
            return isinstance(count, int) and count == 0
        return False
    if name == "check_food_cosmetics":
        block = payload.get("food_import_live")
        if not isinstance(block, dict) or block.get("state") not in ("live", "partial"):
            return False
        counts = []
        for key in ("product_db", "import_permit_history", "improper_history"):
            part = block.get(key)
            if isinstance(part, dict) and isinstance(part.get("match_count"), int):
                counts.append(part["match_count"])
        return bool(counts) and all(count == 0 for count in counts)
    return False


def record_tool(store: Any, name: str, result: Any, day: Optional[str] = None) -> None:
    """툴 호출 1건 → 툴/판정/플래그 카운트. 개인 식별 정보는 받지 않는다."""
    if store is None:
        return
    stamp = day or today_kst()
    key = safe_key(name) or "unknown"
    try:
        store.bump_usage(stamp, KIND_TOOL, key)
        data = result if isinstance(result, dict) else {}
        payload = data.get("result") if isinstance(data.get("result"), dict) else {}
        verdict = payload.get("verdict") if isinstance(payload.get("verdict"), dict) else {}
        code = str(verdict.get("code") or "")
        if code in VERDICT_CODES:
            store.bump_usage(stamp, KIND_VERDICT, code)
        if data.get("ok") is False:
            error = str(data.get("error") or "")
            store.bump_usage(stamp, KIND_FLAG,
                             FLAG_QUOTA if error == "quota_exceeded" else FLAG_ERROR)
        elif _zero_result(key, data):
            store.bump_usage(stamp, KIND_FLAG, FLAG_ZERO)
    except Exception:  # noqa: BLE001
        pass


def _empty_day(day: str) -> Dict[str, Any]:
    return {"date": day, "requests": 0, "paths": {}, "tools": {}, "verdicts": {},
            "flags": {}}


def stats_payload(store: Any, days: int = DEFAULT_DAYS,
                  today: Optional[str] = None) -> Dict[str, Any]:
    """`GET /v1/stats` 응답. 익명 집계만 담고, 개인정보 필드는 만들지 않는다."""
    try:
        window = max(1, min(MAX_DAYS, int(days)))
    except (TypeError, ValueError):
        window = DEFAULT_DAYS
    end = today or today_kst()
    start = _day_shift(end, -(window - 1))
    empty = [_empty_day(_day_shift(start, offset)) for offset in range(window)]
    by_day = {row["date"]: row for row in empty}

    if store is not None:
        try:
            rows = store.usage_rows(start, end)
        except Exception:  # noqa: BLE001
            rows = []
        for row in rows:
            day = str(row.get("day") or "")
            target = by_day.get(day)
            if target is None:
                continue
            kind = str(row.get("kind") or "")
            key = safe_key(row.get("key"))
            count = int(row.get("count") or 0)
            if kind == KIND_PATH:
                target["paths"][key] = count
                target["requests"] += count
            elif kind == KIND_TOOL:
                target["tools"][key] = count
            elif kind == KIND_VERDICT:
                target["verdicts"][key] = count
            elif kind == KIND_FLAG:
                target["flags"][key] = count

    totals: Dict[str, Any] = {"requests": 0, "paths": {}, "tools": {}, "verdicts": {},
                              "flags": {}}
    for row in empty:
        totals["requests"] += row["requests"]
        for kind in ("paths", "tools", "verdicts", "flags"):
            for key, value in row[kind].items():
                totals[kind][key] = totals[kind].get(key, 0) + value

    return {
        "ok": True,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "timezone": "Asia/Seoul",
        "window_days": window,
        "from": start,
        "to": end,
        "privacy": {
            "stores_ip": False,
            "stores_user_agent": False,
            "stores_cookies": False,
            "stores_identifiers": False,
            "granularity": "date (YYYY-MM-DD, Asia/Seoul) · 경로 · 툴 · verdict.code · 0건/오류",
            "note_ko": (
                "IP·User-Agent 원문·쿠키·개인 식별자는 저장하지 않습니다. 알 수 없는 경로는 "
                "/404 한 칸으로 합산하며, 재배포 시 카운터가 초기화될 수 있습니다."
            ),
        },
        "days": empty,
        "totals": totals,
    }
