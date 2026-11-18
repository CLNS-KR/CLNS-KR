"""SQLite 기반 캐시·쿼터·감사 저장소와 공공 API 폴백 게이트웨이.

Postgres 이관 시 동일 스키마를 사용한다(src/schema.sql 참고).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

KST = timezone(timedelta(hours=9))
FREE_MONTHLY_CALLS = 250
DEFAULT_STALE_HOURS = 72

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id       TEXT PRIMARY KEY,
    name_ko         TEXT NOT NULL,
    provider        TEXT NOT NULL,
    license_scope   TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    update_cycle    TEXT NOT NULL,
    last_ok_at      TEXT
);

CREATE TABLE IF NOT EXISTS api_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    query_key       TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_snapshots_lookup ON api_snapshots(source_id, query_key, fetched_at DESC);

CREATE TABLE IF NOT EXISTS derived_findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash      TEXT NOT NULL,
    trap_id         TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    confidence      REAL NOT NULL,
    evidence_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id   TEXT NOT NULL UNIQUE,
    client_id       TEXT NOT NULL,
    tier            TEXT NOT NULL,
    query_text      TEXT NOT NULL,
    overall_verdict TEXT NOT NULL,
    response_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessments_client ON assessments(client_id, created_at DESC);

CREATE TABLE IF NOT EXISTS quota_usage (
    client_id       TEXT NOT NULL,
    period          TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (client_id, period)
);

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    target_url      TEXT NOT NULL,
    secret_hash     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1
);

-- 국표원 리콜 파일데이터 적재분(15040696 건별 이력, 15054301 연도별 집계)
CREATE TABLE IF NOT EXISTS recall_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id          TEXT NOT NULL,
    cert_no             TEXT,
    model               TEXT,
    product_name        TEXT,
    brand               TEXT,
    business_type       TEXT,
    category            TEXT,
    recall_type         TEXT,
    recall_business     TEXT,
    manufacture_country TEXT,
    manufacturer        TEXT,
    manufacturer_country TEXT,
    recall_method       TEXT,
    hazard_type         TEXT,
    safety_inspection   TEXT,
    registered_on       TEXT,
    source_url          TEXT,
    loaded_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_recall_items_model ON recall_items(model);
CREATE INDEX IF NOT EXISTS idx_recall_items_product ON recall_items(product_name);
CREATE INDEX IF NOT EXISTS idx_recall_items_brand ON recall_items(brand);

CREATE TABLE IF NOT EXISTS recall_stats (
    dataset_id      TEXT NOT NULL,
    year            TEXT NOT NULL,
    category        TEXT NOT NULL,
    disposition     TEXT NOT NULL,
    count           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, year, category, disposition)
);
"""


class QuotaExceeded(RuntimeError):
    pass


def now_kst() -> datetime:
    return datetime.now(KST)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def snapshot_age_hours(stamp: str) -> float:
    """스냅샷 시각(ISO) ~ 지금(KST) 경과시간(시간). 파싱 불가면 아주 큰 값."""
    try:
        then = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return 1e9
    if then.tzinfo is None:
        then = then.replace(tzinfo=KST)
    return max(0.0, (now_kst() - then).total_seconds() / 3600.0)


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        # 웹 서버(ThreadingHTTPServer)가 같은 연결을 여러 스레드에서 쓰므로 재진입 가능한 락을 쓴다.
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        if path != ":memory:":
            # 배포 환경(다중 요청)에서 읽기/쓰기 경합을 줄인다.
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA busy_timeout=5000")
            except sqlite3.Error:
                pass
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- sources / snapshots -------------------------------------------------
    def upsert_source(self, source_id: str, name_ko: str, provider: str, license_scope: str,
                      base_url: str, update_cycle: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO sources(source_id, name_ko, provider, license_scope, base_url, update_cycle) "
                "VALUES (?,?,?,?,?,?)",
                (source_id, name_ko, provider, license_scope, base_url, update_cycle),
            )
            self.conn.commit()

    def put_snapshot(self, source_id: str, query_key: str, payload: Dict[str, Any], status: str = "ok") -> None:
        stamp = iso(now_kst())
        with self._lock:
            self.conn.execute(
                "INSERT INTO api_snapshots(source_id, query_key, payload_json, fetched_at, status) VALUES (?,?,?,?,?)",
                (source_id, query_key, json.dumps(payload, ensure_ascii=False), stamp, status),
            )
            if status == "ok":
                self.conn.execute("UPDATE sources SET last_ok_at=? WHERE source_id=?", (stamp, source_id))
            self.conn.commit()

    def latest_snapshot(self, source_id: str, query_key: str) -> Optional[sqlite3.Row]:
        """폴백은 성공한 스냅샷만 쓴다(실패 기록은 감사용으로만 남긴다)."""
        with self._lock:
            cur = self.conn.execute(
                "SELECT * FROM api_snapshots WHERE source_id=? AND query_key=? AND status='ok' "
                "ORDER BY fetched_at DESC LIMIT 1",
                (source_id, query_key),
            )
            return cur.fetchone()

    def get_cached_snapshot(self, source_id: str, query_key: str,
                            ttl_hours: float) -> Optional[Tuple[Dict[str, Any], float]]:
        """TTL 안에 있는 성공 스냅샷을 (payload, 경과시간)으로 돌려준다.

        TTL 을 넘긴 스냅샷은 버린다(오래된 값을 신선한 값처럼 쓰지 않는다).
        """
        if ttl_hours <= 0:
            return None
        row = self.latest_snapshot(source_id, query_key)
        if row is None:
            return None
        age_hours = snapshot_age_hours(row["fetched_at"])
        if age_hours > ttl_hours:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload, age_hours

    # --- quota ---------------------------------------------------------------
    def quota_used(self, client_id: str, period: Optional[str] = None) -> int:
        period = period or now_kst().strftime("%Y-%m")
        with self._lock:
            row = self.conn.execute(
                "SELECT used FROM quota_usage WHERE client_id=? AND period=?", (client_id, period)
            ).fetchone()
        return int(row["used"]) if row else 0

    def consume_quota(self, client_id: str, tier: str = "free", limit: int = FREE_MONTHLY_CALLS) -> Dict[str, int]:
        if tier != "free":
            return {"used": 0, "limit": -1, "remaining": -1}
        period = now_kst().strftime("%Y-%m")
        used = self.quota_used(client_id, period)
        if used >= limit:
            raise QuotaExceeded(f"free tier monthly limit reached ({used}/{limit})")
        with self._lock:
            self.conn.execute(
                "INSERT INTO quota_usage(client_id, period, used) VALUES (?,?,1) "
                "ON CONFLICT(client_id, period) DO UPDATE SET used = used + 1",
                (client_id, period),
            )
            self.conn.commit()
        used += 1
        return {"used": used, "limit": limit, "remaining": limit - used}

    # --- assessments ---------------------------------------------------------
    def record_assessment(self, assessment_id: str, client_id: str, tier: str, query_text: str,
                          overall_verdict: str, response: Dict[str, Any]) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO assessments(assessment_id, client_id, tier, query_text, overall_verdict, response_json, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (assessment_id, client_id, tier, query_text, overall_verdict,
                 json.dumps(response, ensure_ascii=False), iso(now_kst())),
            )
            self.conn.commit()

    def count_assessments(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM assessments").fetchone()
        return int(row["c"])

    def update_assessment(self, assessment_id: str, overall_verdict: str,
                          response: Dict[str, Any]) -> None:
        """응답 후처리(세관장확인 요건 반영 등)로 판정이 바뀌면 저장본도 같은 결론으로 맞춘다."""
        if not assessment_id:
            return
        with self._lock:
            self.conn.execute(
                "UPDATE assessments SET overall_verdict=?, response_json=? WHERE assessment_id=?",
                (overall_verdict, json.dumps(response, ensure_ascii=False), assessment_id),
            )
            self.conn.commit()


class SourceGateway:
    """공공 API 호출부.

    live 클라이언트가 주입되면 실호출을 시도하고, 성공하면 스냅샷을 남긴 뒤
    'live' 상태를 돌려준다. 실패하거나 클라이언트가 없으면 기존 캐시 폴백 규칙
    (최신 스냅샷 → 72h 초과 시 판정 강등 → 미연결)을 그대로 따른다.
    """

    def __init__(self, store: Store, stale_hours: int = DEFAULT_STALE_HOURS, live=None) -> None:
        self.store = store
        self.stale_hours = stale_hours
        self.live = live

    def get(self, source_id: str, query_key: str, *, live_failure: bool = True,
            live_query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.live is not None and live_query:
            live_state = self._live(source_id, query_key, live_query)
            if live_state is not None:
                return live_state
        snap = self.store.latest_snapshot(source_id, query_key)
        if live_failure:
            if snap is None:
                return {
                    "source_id": source_id,
                    "state": "unavailable",
                    "fresh": None,
                    "age_hours": None,
                    "data": None,
                    "note_ko": "실시간 소스 연결 실패·미연결. 판정은 코퍼스·법령 근거로만 수행",
                }
            age = self._age_hours(snap["fetched_at"])
            return {
                "source_id": source_id,
                "state": "cached_fallback",
                "fresh": age <= self.stale_hours,
                "age_hours": round(age, 1),
                "fetched_at": snap["fetched_at"],
                "data": json.loads(snap["payload_json"]),
            }
        return {
            "source_id": source_id,
            "state": "live",
            "fresh": True,
            "age_hours": 0.0,
            "fetched_at": iso(now_kst()),
            "data": json.loads(snap["payload_json"]) if snap else None,
        }

    def _live(self, source_id: str, query_key: str, live_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """실API 호출. 이 게이트웨이가 모르는 소스면 None(기존 경로로)."""
        from .live_api import LiveApiError, SOURCE_CUSTOMS

        try:
            if source_id == SOURCE_CUSTOMS and live_query.get("hs_code"):
                hs_code = str(live_query["hs_code"])
                if len(hs_code) != 10 or not hs_code.isdigit():
                    return None
                fetch = self.live.customs_checkpoint(hs_code, live_query.get("direction", "import"))
            else:
                return None
        except LiveApiError as exc:
            # 실패는 숨기지 않고 상태로 남긴다(폴백 판단은 호출부가 한다).
            self.store.put_snapshot(source_id, query_key,
                                    {"error": exc.message, "result_code": exc.code}, status="error")
            return None

        from .live_api import normalize_customs_item

        normalized = [normalize_customs_item(item) for item in fetch.items]
        self.store.put_snapshot(source_id, query_key,
                                {"items": normalized, "item_count": len(normalized),
                                 "result_code": fetch.result_code})
        return {
            "source_id": source_id,
            "state": "live",
            "fresh": True,
            "age_hours": 0.0,
            "fetched_at": fetch.fetched_at,
            "item_count": len(normalized),
            "result_code": fetch.result_code,
            "data": {"items": normalized},
        }

    def _age_hours(self, stamp: str) -> float:
        return snapshot_age_hours(stamp)
