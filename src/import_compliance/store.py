"""SQLite 기반 캐시·쿼터·감사 저장소와 공공 API 폴백 게이트웨이.

Postgres 이관 시 동일 스키마를 사용한다(src/schema.sql 참고).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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

CREATE TABLE IF NOT EXISTS usage_daily (
    day         TEXT NOT NULL,              -- YYYY-MM-DD (Asia/Seoul)
    kind        TEXT NOT NULL,              -- path | tool | verdict | flag
    key         TEXT NOT NULL,              -- 서버가 아는 경로·툴명·verdict.code·flag
    count       INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (day, kind, key)
);

CREATE TABLE IF NOT EXISTS recall_stats (
    dataset_id      TEXT NOT NULL,
    year            TEXT NOT NULL,
    category        TEXT NOT NULL,
    disposition     TEXT NOT NULL,
    count           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, year, category, disposition)
);

-- 식약처 행정처분결과 적재분(15124560 식품제조가공업 · 15124559 식품판매업)
-- 원본의 업소명·대표자명·전화번호·주소·인허가번호는 저장하지 않는다.
CREATE TABLE IF NOT EXISTS disposition_items (
    dataset_id          TEXT NOT NULL,
    disposition_seq     TEXT NOT NULL,      -- 원본 행정처분전산키(식별정보 아님)
    industry            TEXT,
    disposition_type    TEXT,
    confirmed_on        TEXT,               -- YYYY-MM-DD
    disposition_from    TEXT,
    disposition_to      TEXT,
    violation_summary   TEXT,               -- 개인정보 패턴 마스킹본
    law_reference       TEXT,
    disposition_summary TEXT,
    agency              TEXT,
    last_updated        TEXT,
    loaded_at           TEXT,
    PRIMARY KEY (dataset_id, disposition_seq)
);
CREATE INDEX IF NOT EXISTS idx_disposition_law ON disposition_items(law_reference);
CREATE INDEX IF NOT EXISTS idx_disposition_confirmed ON disposition_items(confirmed_on DESC);

-- 일일 시계열 스냅샷(해자) — 소스별 항목의 지문을 일자 단위로 보관한다.
-- 같은 날 다시 적재하면 그날 스냅샷을 덮어쓴다(일자 기준 멱등).
CREATE TABLE IF NOT EXISTS compliance_snapshots (
    day           TEXT NOT NULL,            -- YYYY-MM-DD (KST)
    source        TEXT NOT NULL,            -- recall | disposition | cosmetic_* | drug_schedule
    item_key      TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,            -- 항목 내용 해시(변경 판정)
    label         TEXT,
    category      TEXT,
    event_date    TEXT,                     -- 리콜 등록일·처분 확정일(없으면 빈 값)
    payload_json  TEXT,
    origin        TEXT NOT NULL DEFAULT 'observed',  -- observed | backfilled
    taken_at      TEXT NOT NULL,
    PRIMARY KEY (day, source, item_key)
);
CREATE INDEX IF NOT EXISTS idx_compliance_snapshots_source_day
    ON compliance_snapshots(source, day);

-- 스냅샷 실행 기록(그날 소스별 건수·전일 대비 요약)
CREATE TABLE IF NOT EXISTS snapshot_runs (
    day         TEXT PRIMARY KEY,
    taken_at    TEXT NOT NULL,
    origin      TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    diff_json   TEXT NOT NULL
);

-- CLNS Pro 사전 신청·도입 문의. 회신 목적의 연락처 1건만 보관한다.
-- 이 테이블은 공개 집계(/v1/stats)에도, 공개 응답에도 절대 쓰지 않는다.
CREATE TABLE IF NOT EXISTS inquiries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact     TEXT NOT NULL,              -- 이메일 또는 연락처(회신용)
    topic       TEXT NOT NULL,              -- clns_pro_batch | api_mcp | other
    message     TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inquiries_received ON inquiries(received_at DESC);
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

    # --- 식약처 행정처분 적재분 -------------------------------------------------
    def save_dispositions(self, rows: List[Dict[str, Any]]) -> int:
        """정규화된 행정처분 행을 중복 없이 적재한다(개인정보 필드는 받지 않는다)."""
        if not rows:
            return 0
        stamp = iso(now_kst())
        saved = 0
        with self._lock:
            for row in rows:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO disposition_items("
                    "dataset_id, disposition_seq, industry, disposition_type, confirmed_on, "
                    "disposition_from, disposition_to, violation_summary, law_reference, "
                    "disposition_summary, agency, last_updated, loaded_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(row.get("dataset_id", "")), str(row.get("disposition_seq", "")),
                     str(row.get("industry", "")), str(row.get("disposition_type", "")),
                     str(row.get("confirmed_on", "")), str(row.get("disposition_from", "")),
                     str(row.get("disposition_to", "")), str(row.get("violation_summary", "")),
                     str(row.get("law_reference", "")), str(row.get("disposition_summary", "")),
                     str(row.get("agency", "")), str(row.get("last_updated", "")), stamp),
                )
                saved += 1 if cur.rowcount > 0 else 0
            self.conn.commit()
        return saved

    def disposition_count(self, dataset_id: Optional[str] = None) -> int:
        with self._lock:
            if dataset_id:
                row = self.conn.execute(
                    "SELECT COUNT(*) AS c FROM disposition_items WHERE dataset_id=?",
                    (dataset_id,)).fetchone()
            else:
                row = self.conn.execute("SELECT COUNT(*) AS c FROM disposition_items").fetchone()
        return int(row["c"] if row else 0)

    def disposition_summary(self, dataset_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """위반법령별 건수·비중(마지막 콤마 기준 첫 법령으로 집계)."""
        selected = set(dataset_ids or [])
        with self._lock:
            if selected:
                rows = self.conn.execute(
                    "SELECT law_reference, COUNT(*) AS c FROM disposition_items "
                    "WHERE dataset_id IN (%s) GROUP BY law_reference ORDER BY c DESC"
                    % ",".join("?" for _ in selected), tuple(selected)).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT law_reference, COUNT(*) AS c FROM disposition_items "
                    "GROUP BY law_reference ORDER BY c DESC").fetchall()
        counts: Dict[str, int] = {}
        for row in rows:
            law = str(row["law_reference"] or "").split(",")[0].strip()
            if not law:
                continue
            counts[law] = counts.get(law, 0) + int(row["c"])
        total = sum(counts.values()) or 1
        return [{"law_reference": law, "count": count, "share": round(count / total, 3)}
                for law, count in sorted(counts.items(), key=lambda kv: -kv[1])]

    def search_dispositions(self, *, keyword: str = "", confirmed_on: str = "",
                            dataset_ids: Optional[List[str]] = None,
                            limit: int = 5) -> List[Dict[str, Any]]:
        """로컬 적재분 검색(개인정보 없는 필드만 돌려준다)."""
        clauses: List[str] = []
        params: List[Any] = []
        if keyword:
            probe = f"%{keyword}%"
            clauses.append("(law_reference LIKE ? OR violation_summary LIKE ? "
                           "OR disposition_type LIKE ? OR industry LIKE ?)")
            params.extend([probe, probe, probe, probe])
        if confirmed_on:
            clauses.append("confirmed_on = ?")
            params.append(confirmed_on)
        if dataset_ids:
            clauses.append("dataset_id IN (%s)" % ",".join("?" for _ in dataset_ids))
            params.extend(dataset_ids)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = ("SELECT dataset_id, disposition_seq, industry, disposition_type, confirmed_on, "
               "disposition_from, disposition_to, violation_summary, law_reference, "
               "disposition_summary, agency FROM disposition_items" + where +
               " ORDER BY confirmed_on DESC LIMIT ?")
        params.append(max(1, int(limit)))
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]

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

    # --- 익명 일별 카운터 -----------------------------------------------------
    def bump_usage(self, day: str, kind: str, key: str, amount: int = 1) -> None:
        """일별 카운터 1건 증가. 개인 식별자는 받지 않는다(날짜·경로·툴·판정만)."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO usage_daily(day, kind, key, count, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(day, kind, key) DO UPDATE SET count = count + ?, updated_at = ?",
                (day, kind, key, int(amount), iso(now_kst()), int(amount), iso(now_kst())),
            )
            self.conn.commit()

    def usage_rows(self, start_day: str, end_day: str) -> list:
        """[start, end] 날짜 범위의 집계 행(날짜·종류·키·횟수)."""
        with self._lock:
            cur = self.conn.execute(
                "SELECT day, kind, key, count FROM usage_daily WHERE day BETWEEN ? AND ? "
                "ORDER BY day, kind, key",
                (start_day, end_day),
            )
            return [dict(row) for row in cur.fetchall()]

    def usage_total(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COALESCE(SUM(count), 0) AS c FROM usage_daily").fetchone()
        return int(row["c"])

    def seed_usage_rows(self, rows: List[Dict[str, Any]]) -> int:
        """과거 익명 카운터를 복원한다(재배포 대응). 큰 값만 남기는 멱등 적재.

        - 기존 값보다 작은 값은 쓰지 않는다(`MAX`) — 여러 번 기동해도 카운트가 부풀지 않는다.
        - 받는 키는 날짜ㆍ종류ㆍ경로/툴/판정/플래그 문자열뿐이다(개인 식별자 없음).
        """
        written = 0
        stamp = iso(now_kst())
        with self._lock:
            for row in rows or []:
                day = str(row.get("day") or "").strip()
                kind = str(row.get("kind") or "").strip()
                key = str(row.get("key") or "").strip()
                try:
                    count = int(row.get("count") or 0)
                except (TypeError, ValueError):
                    continue
                if not day or not kind or not key or count <= 0:
                    continue
                self.conn.execute(
                    "INSERT INTO usage_daily(day, kind, key, count, updated_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(day, kind, key) DO UPDATE SET "
                    "count = MAX(count, excluded.count), updated_at = excluded.updated_at",
                    (day[:10], kind[:16], key[:64], count, stamp),
                )
                written += 1
            self.conn.commit()
        return written

    # --- 도입 문의(사전 신청) ------------------------------------------------
    def record_inquiry(self, contact: str, topic: str, message: str = "") -> Dict[str, Any]:
        """CLNS Pro 사전 신청·도입 문의 1건을 저장한다.

        연락처(`contact`)는 회신 목적으로만 보관한다. 공개 집계(usage_daily·/v1/stats)와
        공개 응답에는 연락처·문의 본문을 넘기지 않는다.
        """
        stamp = iso(now_kst())
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO inquiries(contact, topic, message, received_at) VALUES (?,?,?,?)",
                (contact, topic, message, stamp),
            )
            self.conn.commit()
            return {"id": int(cur.lastrowid or 0), "received_at": stamp}

    def count_inquiries(self, since_day: Optional[str] = None) -> int:
        """문의 건수만 센다(선택: KST 날짜 하한 YYYY-MM-DD). 연락처·본문은 읽지 않는다."""
        sql = "SELECT COUNT(*) AS c FROM inquiries"
        params: Tuple[Any, ...] = ()
        if since_day:
            sql += " WHERE received_at >= ?"
            params = (f"{str(since_day)[:10]}T00:00:00",)
        with self._lock:
            row = self.conn.execute(sql, params).fetchone()
        return int(row["c"])


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
        if source_id == "rra_conformity":
            # 적합성평가(전파법)는 인증·등록번호가 있어야 조회되는 소스라, 번호가 없을 때
            # '연결 실패(unavailable)'로 뭉개지 않고 '번호 필요' 상태를 따로 돌려준다.
            return self._rra(query_key, live_query)
        if source_id == "mfds_drug_schedule":
            # 의약품 성분 사전은 법제처 시행령 별표에서 생성한 로컬 인덱스다.
            # 식약처 의약품 계열 API는 활용승인 전이라 '승인 필요'로 사실대로 밝힌다.
            return self._drug_schedule()
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

    # --- 의약품 성분 사전(법제처 시행령 별표 기반 로컬 인덱스) --------------------
    def _drug_schedule(self) -> Dict[str, Any]:
        from . import drugs

        data = drugs.load_schedules()
        return {
            "source_id": "mfds_drug_schedule",
            "state": "local_index",
            "fresh": None,
            "age_hours": None,
            "schedule_version": data.get("schedule_version"),
            "generated_on": data.get("generated_on"),
            "substance_count": len(data.get("substances") or []),
            "precursor_count": len(data.get("precursors") or []),
            "data": None,
            "note_ko": (
                "마약류·원료물질은 법제처 시행령 별표 1~8에서 생성한 로컬 사전으로 대조했습니다. "
                "식약처 의약품 허가정보·e약은요·DUR·마약류 API는 이 계정에 활용승인이 없어 실시간 "
                "전수 대조는 제공하지 않습니다."
            ),
            "api_state": [{"dataset_id": row["dataset_id"], "name_ko": row["name_ko"],
                           "state": row["state"]} for row in drugs.API_CANDIDATES],
        }

    def _age_hours(self, stamp: str) -> float:
        return snapshot_age_hours(stamp)

    # --- 적합성평가(국립전파연구원) ------------------------------------------
    def _rra(self, query_key: str, live_query: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        from .live_api import (
            RRA_OFFICIAL_URL,
            SOURCE_RRA,
            LiveApiError,
            normalize_cert_no,
            normalize_rra_item,
        )

        cert_no = normalize_cert_no((live_query or {}).get("cert_no"))
        base = {
            "source_id": SOURCE_RRA,
            "official_url": RRA_OFFICIAL_URL,
            "lookup_field": "rra_cert_no",
            "note_ko": (
                "적합성평가(적합인증·적합등록)는 인증·등록번호로만 실시간 확인할 수 있습니다. "
                "번호가 없으면 모델명으로 국립전파연구원 적합성평가 현황 검색에서 확인해야 합니다."
            ),
        }
        if not cert_no:
            return {**base, "state": "certificate_number_required", "fresh": None,
                    "age_hours": None, "data": None}
        if self.live is None or not getattr(self.live, "has_rra", False):
            return {**base, "state": "unavailable", "fresh": None, "age_hours": None, "data": None}
        try:
            fetch = self.live.rra_certificate(cert_no)
        except LiveApiError as exc:
            self.store.put_snapshot(SOURCE_RRA, query_key,
                                    {"error": exc.message, "result_code": exc.code}, status="error")
            return {**base, "state": "error", "fresh": False, "age_hours": None, "data": None,
                    "error": exc.message, "result_code": exc.code}
        normalized = [normalize_rra_item(item) for item in fetch.items]
        if fetch.state == "live":
            self.store.put_snapshot(SOURCE_RRA, query_key,
                                    {"items": normalized, "item_count": len(normalized),
                                     "result_code": fetch.result_code})
            return {**base, "state": "live", "fresh": True, "age_hours": 0.0,
                    "fetched_at": fetch.fetched_at, "item_count": len(normalized),
                    "result_code": fetch.result_code, "cert_no": cert_no,
                    "data": {"items": normalized}}
        return {**base, "state": fetch.state if fetch.state != "live" else "error",
                "fresh": True, "age_hours": 0.0, "fetched_at": fetch.fetched_at,
                "item_count": 0, "result_code": fetch.result_code, "cert_no": cert_no,
                "note_ko": (
                    "이 인증·등록번호로 조회된 적합성평가 기록이 없습니다. 0건은 '미인증' 단정이 "
                    "아니라 번호 표기·개정·시스템 반영 차이일 수 있으므로 번호를 다시 확인해야 합니다."
                ), "data": {"items": []}}
