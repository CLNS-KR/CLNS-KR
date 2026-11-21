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
KIND_CLIENT = "client"      # 요청이 브라우저/봇/기타 중 무엇이었는지(3종, 원문 UA 미저장)
KINDS = (KIND_PATH, KIND_TOOL, KIND_VERDICT, KIND_FLAG, KIND_CLIENT)

# 트래픽 구분 — 경로를 사람이 읽는 다섯 묶음으로만 나눈다(개별 주소는 paths 에 그대로).
CLIENT_CLASSES = ("browser", "bot", "other")
CHANNELS = ("web", "crawler_files", "api", "mcp", "assets", "not_found")
CHANNEL_LABELS_KO = {
    "web": "사람이 여는 페이지",
    "crawler_files": "검색·AI 크롤러용 파일(robots·llms·sitemap·서버카드)",
    "api": "REST API(/v1/…)",
    "mcp": "MCP(/mcp·/v1/mcp)",
    "assets": "정적 자산(/static·favicon)",
    "not_found": "없는 주소(/404)",
}
# User-Agent 원문은 저장하지 않는다. 종류를 가르는 데만, 요청 순간에만 본다.
_BOT_MARKERS = ("bot", "crawler", "spider", "curl", "wget", "python-requests", "python-urllib",
                "httpx", "go-http-client", "node-fetch", "java/", "okhttp", "libwww", "axios",
                "gptbot", "claudebot", "perplexity", "anthropic", "openai", "yeti", "glama",
                "mcporter", "scan")

VERDICT_CODES = ("check_likely", "info_needed", "low_risk")
FLAG_ZERO = "zero_results"
FLAG_ERROR = "errors"
FLAG_QUOTA = "quota_exceeded"
FLAG_RATE_LIMITED = "rate_limited"

FIXED_PATHS = (
    "/", "/p/", "/guides/", "/healthz", "/robots.txt", "/llms.txt", "/sitemap.xml",
    "/.well-known/mcp/server-card.json", "/static/og.png", "/v1/meta", "/v1/mcp",
    "/v1/stats", "/v1/trends", "/v1/tools", "/v1/inquiry", "/v1/inquiry/summary",
    "/mcp", "/favicon.ico", "/404", "/privacy", "/terms", "/about",
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
        from . import guides, pseo  # 지연 import(모듈 순환 방지)

        for slug in pseo.slugs():
            paths.add(f"/p/{slug}")
        for slug in guides.slugs():
            paths.add(f"/guides/{slug}")
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


def client_class(user_agent: Any) -> str:
    """User-Agent → `browser`·`bot`·`other` 3종 중 하나. 원문은 돌려주지도 저장하지도 않는다.

    봇/브라우저 구분은 "얼마나 자동화된 요청이 오는가"를 익명으로 세기 위한 것뿐이며,
    UA 문자열은 이 함수 밖으로 나가지 않습니다.
    """
    ua = str(user_agent or "").strip().lower()
    if not ua:
        return "other"
    if any(marker in ua for marker in _BOT_MARKERS):
        return "bot"
    if "mozilla" in ua or "safari" in ua or "chrome" in ua or "firefox" in ua:
        return "browser"
    return "other"


def channel_of(key: str) -> str:
    """경로 집계 키 → 트래픽 묶음(`CHANNELS`)."""
    value = str(key or "")
    if value in ("/mcp", "/v1/mcp"):
        return "mcp"
    if value.startswith("/v1/"):
        return "api"
    if value in ("/robots.txt", "/llms.txt", "/sitemap.xml",
                 "/.well-known/mcp/server-card.json"):
        return "crawler_files"
    if value.startswith("/static/") or value == "/favicon.ico":
        return "assets"
    if value == "/404":
        return "not_found"
    return "web"


def record_request(store: Any, method: str, path: str, day: Optional[str] = None,
                   client: Optional[str] = None) -> None:
    """요청 1건을 경로 버킷에 센다. `client` 를 주면 종류별(브라우저/봇/기타)로도 1건 센다.

    GET/POST 이외 메서드는 세지 않는다. `client` 는 `client_class()` 결과만 받는다
    (원문 User-Agent 를 넘기지 않는다).
    """
    if store is None or str(method or "").upper() not in ("GET", "POST"):
        return
    stamp = day or today_kst()
    try:
        store.bump_usage(stamp, KIND_PATH, path_key(path))
        kind = str(client or "").strip().lower()
        if kind in CLIENT_CLASSES:
            store.bump_usage(stamp, KIND_CLIENT, kind)
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


def record_rate_limited(store: Any, day: Optional[str] = None) -> None:
    """429 로 된 요청을 플래그로만 센다(경로·주소는 남기지 않는다)."""
    if store is None:
        return
    try:
        store.bump_usage(day or today_kst(), KIND_FLAG, FLAG_RATE_LIMITED)
    except Exception:  # noqa: BLE001 - 계측 실패가 응답을 막지 않는다
        pass


def inquiry_summary(store: Any, days: int = DEFAULT_DAYS,
                   today: Optional[str] = None) -> Dict[str, Any]:
    """CLNS Pro 사전 신청·도입 문의 요약(관리자용).

    건수와 관심 항목만 센다. 연락처ㆍ메모 본문은 읽지도, 돌려주지도 않는다.
    리드 수는 운영 정보이므로 공개 `/v1/stats` 에는 넣지 않고, 관리자 토큰이
    걸린 `/v1/inquiry/summary` 에서만 본다.
    """
    try:
        window = max(1, min(MAX_DAYS, int(days)))
    except (TypeError, ValueError):
        window = DEFAULT_DAYS
    end = today or today_kst()
    start = _day_shift(end, -(window - 1))
    rows: list = []
    cohort_rows: list = []
    if store is not None:
        try:
            rows = store.inquiry_topic_counts(start)
        except Exception:  # noqa: BLE001 - 요약 실패가 서버를 막지 않는다
            rows = []
        try:
            cohort_rows = store.inquiry_cohort_counts(start)
        except Exception:  # noqa: BLE001 - 0.5.4 이전 DB 도 요약은 뜨게 한다
            cohort_rows = []
    by_day = {_day_shift(start, offset): {} for offset in range(window)}
    by_topic: Dict[str, int] = {}
    total = 0
    for row in rows:
        day = str(row.get("day") or "")
        topic = safe_key(row.get("topic")) or "unknown"
        count = int(row.get("count") or 0)
        if day in by_day:
            by_day[day][topic] = by_day[day].get(topic, 0) + count
        by_topic[topic] = by_topic.get(topic, 0) + count
        total += count
    by_cohort: Dict[str, int] = {}
    for row in cohort_rows:
        tag = str(row.get("cohort") or "").strip()[:40] or "(태그 없음)"
        by_cohort[tag] = by_cohort.get(tag, 0) + int(row.get("count") or 0)
    return {
        "ok": True,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "timezone": "Asia/Seoul",
        "window_days": window,
        "from": start,
        "to": end,
        "total": total,
        "by_topic": by_topic,
        "by_cohort": by_cohort,
        "days": [{"date": day, "count": sum(v.values()), "by_topic": v}
                 for day, v in by_day.items()],
        "privacy": {
            "stores_contact_in_summary": False,
            "fields": "건수ㆍ관심 항목ㆍ유입 태그(cohort)ㆍ접수일만(연락처ㆍ메모 본문 제외)",
            "note_ko": (
                "요약은 건수만 세고 연락처ㆍ문의 본문은 읽지 않습니다. 회신이 필요한 원문은 "
                "서버 DB(inquiries)와 접수 저널(data/inquiries.jsonl)에서만 확인합니다."
            ),
        },
    }


def _empty_day(day: str) -> Dict[str, Any]:
    return {"date": day, "requests": 0, "paths": {}, "tools": {}, "verdicts": {},
            "flags": {}, "clients": {}}


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
            elif kind == KIND_CLIENT and key in CLIENT_CLASSES:
                target["clients"][key] = count

    totals: Dict[str, Any] = {"requests": 0, "paths": {}, "tools": {}, "verdicts": {},
                              "flags": {}, "clients": {}}
    for row in empty:
        totals["requests"] += row["requests"]
        for kind in ("paths", "tools", "verdicts", "flags", "clients"):
            for key, value in row[kind].items():
                totals[kind][key] = totals[kind].get(key, 0) + value

    # 경로별 합계를 사람이 읽는 다섯 묶음으로 접는다 — 같은 숫자, 다른 자름.
    channels: Dict[str, int] = {}
    for key, value in totals["paths"].items():
        bucket = channel_of(key)
        channels[bucket] = channels.get(bucket, 0) + value

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
        "traffic": {
            "by_channel": channels,
            "by_client": totals["clients"],
            "channel_labels_ko": CHANNEL_LABELS_KO,
            "note_ko": (
                "요청을 '사람이 여는 페이지 / 크롤러 파일 / REST API / MCP / 정적 자산 / 없는 주소'로만 "
                "나누고, 브라우저·봇·기타 종류만 셉니다. User-Agent 원문·IP·쿠키는 저장하지 않으며, "
                "봇 판별은 문자열 표식으로만 합니다(정확한 판별이 아닌 참고 수치)."
            ),
        },
        "days": empty,
        "totals": totals,
    }
