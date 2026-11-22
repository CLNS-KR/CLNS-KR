"""CLNS 시계열 데이터 해자 — 일일 리콜·행정처분·금지성분 기준 스냅샷.

무엇을 하는가
-------------
1. **하루치 상태를 통째로 남긴다.** 리콜 이력, 식약처 행정처분, 화장품 배합금지·한도
   원료, 마약류 성분 사전의 항목별 지문(fingerprint)을 `compliance_snapshots` 에
   일자 단위로 적재한다. 같은 날 다시 실행하면 그날 스냅샷을 덮어쓴다(멱등).
2. **전일 대비 변화를 센다.** 신규(new)·변경(changed)·삭제(removed) 건수를 소스별로
   계산한다. '변경'은 항목 키는 같고 지문이 다른 경우다(예: 처분 내용·한도 기준 수정).
3. **최근 7일·30일 급증을 요약한다.** 리콜은 등록일, 행정처분은 확정일을 기준으로
   직전 동일 기간과 비교해 품목군·위해유형·위반법령별 증감을 낸다.

정직하게 밝히는 한계
--------------------
- 리콜 파일데이터(15040696)는 2023-08-09 배포본으로 갱신이 멈춘 정적 스냅샷이라,
  그 이후 날짜의 '신규 리콜'은 관측되지 않는다. 그래서 추이 응답은 `coverage` 에
  데이터 기준일과 소스별 상태를 함께 적고, 요청 기간에 이벤트가 0건이면 데이터의
  마지막 이벤트일을 기준으로 한 참고 창을 `reference` 로 따로 돌려준다(0건을
  '급증 없음'으로 단정하지 않는다).
- `backfill_from_history()` 는 이벤트 날짜로 과거 시점의 누적 상태를 **재구성**한다.
  실제 그날 관측한 값이 아니므로 `origin="backfilled"` 로 구분해 남긴다.
- 스냅샷은 서버 작업 DB(SQLite)에 쌓인다. Render 무료 플랜처럼 영구 디스크가 없는
  환경에서는 재배포 시 사라지므로, `--export` 로 만든 JSON 을 저장소(`data/snapshots/`)에
  커밋해 두고 기동 시 `seed_snapshots()` 로 다시 적재한다(0원 영속화). 외부 유료 DB 없이도
  날짜별 지문이 유지되고, 같은 날짜는 덮어쓰지 않아 멱등이다.

0원 영속화(재배포·서버 슬립 대응)
--------------------------------
- `data/snapshots/YYYY-MM-DD.json` (항목 포함 내보내기) → 기동 시 `seed_persistence()` 가
  DB 에 없던 날짜만 적재한다.
- `data/usage/stats.json`(`/v1/stats` 응답 그대로 또는 행 목록) → 지난 날짜의 익명 카운터를
  복원한다(오늘 행은 새 트래픽과 겹치지 않게 건너뛴다. 값은 MAX 로만 키운다).
- `.github/workflows/daily-snapshot.yml` 이 매일 04:00 KST 에 스냅샷을 만들어 커밋하고,
  라이브 서버의 `/v1/stats` 를 받아 함께 저장한다.
- 외부 Postgres 를 쓰려면 `DATABASE_URL` 이 아니라 이 저장소의 SQLite 경로와 백업 파일을
  쓰는 구조다(표준 라이브러리만 쓰는 배포 이미지 전제). 즉시 DB 를 붙이는 경로는
  `data/` 디렉터리를 영구 볼륨으로 마운트하는 것이다.

쓰는 법
-------
    python -m import_compliance.snapshots --take --export data/snapshots --include-items
    python -m import_compliance.snapshots --take --backfill 30
    python -m import_compliance.snapshots --trends 30
    python -m import_compliance.snapshots --diff 2026-11-20
    python -m import_compliance.snapshots --seed data/snapshots --seed-usage data/usage/stats.json

네트워크를 쓰지 않는다. 입력은 이미 적재된 로컬 DB·카탈로그뿐이라 결과가 결정적이다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .store import Store, iso, now_kst

SNAPSHOT_SCHEMA = "clns.snapshots/1"
TRENDS_SCHEMA = "clns.trends/1"
SNAPSHOT_VERSION = "1.0.0"

SOURCES: Tuple[str, ...] = ("recall", "disposition", "cosmetic_prohibited",
                            "cosmetic_restricted", "drug_schedule")
SOURCE_LABEL_KO: Dict[str, str] = {
    "recall": "국내 리콜(국가기술표준원)",
    "disposition": "식약처 행정처분",
    "cosmetic_prohibited": "화장품 배합금지 원료",
    "cosmetic_restricted": "화장품 배합한도 원료",
    "drug_schedule": "마약류·원료물질 성분 사전",
}
ORIGIN_OBSERVED = "observed"
ORIGIN_BACKFILLED = "backfilled"
ORIGIN_SEED = "seed"
ORIGIN_SOURCES = (ORIGIN_OBSERVED, ORIGIN_BACKFILLED, ORIGIN_SEED)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_SEED_DIR = os.path.join(PROJECT_ROOT, "data", "snapshots")
DEFAULT_USAGE_SEED = os.path.join(PROJECT_ROOT, "data", "usage", "stats.json")
USAGE_SEED_SCHEMA = "clns.usage_seed/1"

# 기동 시 적재 결과(엔드포인트 `/v1/meta` 가 같은 프로세스에서 읽는다).
_LAST_SEED: Dict[str, Any] = {}

MAX_TREND_DAYS = 90
DEFAULT_TREND_DAYS = 30
TOP_LIMIT = 8


# --- 공통 헬퍼 ---------------------------------------------------------------
def _day(value: Any = None) -> str:
    """YYYY-MM-DD 로 정규화한다(빈 값이면 KST 오늘)."""
    if value in (None, ""):
        return now_kst().strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    raw = str(value).strip().replace(".", "-").replace("/", "-")
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("day_must_be_yyyy_mm_dd") from exc


def _shift(day: str, delta_days: int) -> str:
    base = datetime.strptime(day, "%Y-%m-%d")
    return (base + timedelta(days=delta_days)).strftime("%Y-%m-%d")


def _digest(*parts: Any) -> str:
    raw = "\u241f".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _label(value: Any, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _top_category(value: Any) -> str:
    """'완구>기타완구>기타' 같은 계층 분류를 첫 구간으로 줄인다."""
    text = str(value or "").strip()
    if not text:
        return "미분류"
    return text.split(">")[0].strip() or "미분류"


def _top_law(value: Any) -> str:
    """'식품위생법 제36조(시설기준), …' 같은 위반법령 문자열을 첫 법령으로 줄인다."""
    text = str(value or "").strip()
    if not text:
        return "미분류"
    return text.split(",")[0].split("(")[0].strip() or "미분류"


# --- 수집 -------------------------------------------------------------------
def _recall_entries(store: Store) -> Dict[str, Dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT dataset_id, cert_no, model, product_name, brand, business_type, category,"
        " recall_type, recall_business, manufacture_country, manufacturer, recall_method,"
        " hazard_type, safety_inspection, registered_on FROM recall_items"
    ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        # 전산 id 는 재적재마다 바뀌므로 쓰지 않는다. 원본 식별 조합으로 키를 만든다.
        key = "|".join(str(item.get(field) or "") for field in
                       ("cert_no", "model", "product_name", "brand", "registered_on"))
        key = key.strip("|") or _digest(item.get("product_name"), item.get("model"))
        out[key] = {
            "label": _label(item.get("product_name") or item.get("model")),
            "category": _top_category(item.get("category")),
            "event_date": str(item.get("registered_on") or ""),
            "payload": {
                "brand": item.get("brand") or "",
                "model": item.get("model") or "",
                "category": item.get("category") or "",
                "hazard_type": item.get("hazard_type") or "",
                "recall_type": item.get("recall_type") or "",
                "manufacture_country": item.get("manufacture_country") or "",
                "dataset_id": item.get("dataset_id") or "",
            },
            "fingerprint": _digest(item.get("brand"), item.get("model"), item.get("category"),
                                   item.get("hazard_type"), item.get("recall_type"),
                                   item.get("recall_method"), item.get("manufacturer")),
        }
    return out


def _disposition_entries(store: Store) -> Dict[str, Dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT dataset_id, disposition_seq, industry, disposition_type, confirmed_on,"
        " violation_summary, law_reference, disposition_summary, agency FROM disposition_items"
    ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        key = f"{item.get('dataset_id') or ''}:{item.get('disposition_seq') or ''}"
        out[key] = {
            "label": _label(item.get("violation_summary")),
            "category": _top_law(item.get("law_reference")),
            "event_date": str(item.get("confirmed_on") or ""),
            "payload": {
                "industry": item.get("industry") or "",
                "disposition_type": item.get("disposition_type") or "",
                "law_reference": item.get("law_reference") or "",
                "disposition_summary": item.get("disposition_summary") or "",
                "agency": item.get("agency") or "",
            },
            "fingerprint": _digest(item.get("industry"), item.get("disposition_type"),
                                   item.get("confirmed_on"), item.get("violation_summary"),
                                   item.get("law_reference"), item.get("disposition_summary")),
        }
    return out


def _cosmetic_entries(prohibited: bool) -> Dict[str, Dict[str, Any]]:
    from . import cosmetic_ingredients

    rows = (cosmetic_ingredients.PROHIBITED_INGREDIENTS if prohibited
            else cosmetic_ingredients.RESTRICTED_INGREDIENTS)
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("ko") or "").strip()
        if not name:
            continue
        inci = list(row.get("inci") or [])
        limit = row.get("limit") or row.get("limit_ko") or ""
        out[name] = {
            "label": _label(name),
            "category": "배합금지" if prohibited else "배합한도",
            "event_date": "",
            "payload": {"inci": inci, "reason": row.get("reason") or "",
                        "basis": row.get("basis") or "", "limit": str(limit)},
            "fingerprint": _digest(sorted(inci), row.get("reason"), row.get("basis"), limit),
        }
    return out


def _drug_entries() -> Dict[str, Dict[str, Any]]:
    from . import drugs

    data = drugs.load_schedules()
    out: Dict[str, Dict[str, Any]] = {}
    for kind, rows in (("substance", data.get("substances") or []),
                       ("precursor", data.get("precursors") or [])):
        for row in rows:
            name = str(row.get("name_ko") or row.get("name_en") or "").strip()
            if not name:
                continue
            key = f"{kind}:{name}"
            out[key] = {
                "label": _label(name),
                "category": str(row.get("class_ko") or row.get("class") or kind),
                "event_date": "",
                "payload": {
                    "name_en": row.get("name_en") or "",
                    "class": row.get("class") or "",
                    "reference": row.get("reference") or "",
                    "table": row.get("table") or "",
                },
                "fingerprint": _digest(row.get("name_en"), row.get("class"),
                                       row.get("reference"), row.get("table")),
            }
    return out


def collect(store: Store, *, cosmetic_catalog: Optional[Dict[str, Any]] = None,
            drug_catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """현재 로컬 데이터로 소스별 항목 사전을 만든다(네트워크 없음).

    `cosmetic_catalog`/`drug_catalog` 는 테스트·검증용 주입점이다(없으면 저장소 상수).
    """
    cosmetic = cosmetic_catalog or {}
    if cosmetic:
        prohibited = cosmetic.get("prohibited") or {}
        restricted = cosmetic.get("restricted") or {}
    else:
        prohibited = _cosmetic_entries(True)
        restricted = _cosmetic_entries(False)
    if drug_catalog is not None:
        drug = drug_catalog
    else:
        drug = _drug_entries()
    return {
        "recall": _recall_entries(store),
        "disposition": _disposition_entries(store),
        "cosmetic_prohibited": prohibited,
        "cosmetic_restricted": restricted,
        "drug_schedule": drug,
    }


# --- 저장·조회 ---------------------------------------------------------------
def latest_day(store: Store, before: Optional[str] = None) -> Optional[str]:
    """가장 최근 스냅샷 일자. `before` 가 있으면 그 **이전** 날짜만 본다."""
    with store._lock:  # noqa: SLF001 - 스냅샷 테이블 전용 조회
        if before:
            row = store.conn.execute(
                "SELECT MAX(day) AS day FROM compliance_snapshots WHERE day < ?", (before,)
            ).fetchone()
        else:
            row = store.conn.execute(
                "SELECT MAX(day) AS day FROM compliance_snapshots").fetchone()
    return row["day"] if row and row["day"] else None


def days(store: Store, *, start: str = "", end: str = "") -> List[str]:
    clauses: List[str] = []
    params: List[Any] = []
    if start:
        clauses.append("day >= ?")
        params.append(start)
    if end:
        clauses.append("day <= ?")
        params.append(end)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with store._lock:  # noqa: SLF001
        rows = store.conn.execute(
            "SELECT day, COUNT(*) AS n FROM compliance_snapshots" + where +
            " GROUP BY day ORDER BY day", tuple(params)).fetchall()
    return [row["day"] for row in rows if int(row["n"] or 0) > 0]


def items_for(store: Store, day: str, source: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """해당 일자 스냅샷의 항목(키 → 지문·라벨·분류·이벤트일)."""
    clauses = ["day = ?"]
    params: List[Any] = [_day(day)]
    if source:
        clauses.append("source = ?")
        params.append(source)
    with store._lock:  # noqa: SLF001
        rows = store.conn.execute(
            "SELECT source, item_key, fingerprint, label, category, event_date"
            " FROM compliance_snapshots WHERE " + " AND ".join(clauses), tuple(params)).fetchall()
    return {f"{row['source']}:{row['item_key']}": {
        "source": row["source"], "item_key": row["item_key"], "fingerprint": row["fingerprint"],
        "label": row["label"], "category": row["category"], "event_date": row["event_date"],
    } for row in rows}


def _diff_maps(current: Dict[str, Dict[str, Any]],
               previous: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    new_keys = [key for key in current if key not in previous]
    removed_keys = [key for key in previous if key not in current]
    changed_keys = [key for key in current
                    if key in previous and current[key]["fingerprint"] != previous[key]["fingerprint"]]
    return {"new": new_keys, "removed": removed_keys, "changed": changed_keys}


def _count_by_source(entries: Dict[str, Dict[str, Dict[str, Any]]],
                     keys: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for key in keys:
        source = str(entries[key].get("source") or "")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _sample(entries_by_key: Dict[str, Dict[str, Any]], keys: List[str],
            limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in keys[:limit]:
        row = entries_by_key.get(key) or {}
        out.append({"key": key, "label": row.get("label") or "",
                    "category": row.get("category") or "",
                    "event_date": row.get("event_date") or ""})
    return out


def _upsert(store: Store, day: str, snapshot: Dict[str, Dict[str, Dict[str, Any]]],
            *, origin: str, taken_at: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    with store._lock:  # noqa: SLF001 - 일자 단위 교체(멱등)
        store.conn.execute("DELETE FROM compliance_snapshots WHERE day = ?", (day,))
        for source, entries in snapshot.items():
            counts[source] = len(entries)
            store.conn.executemany(
                "INSERT INTO compliance_snapshots(day, source, item_key, fingerprint, label,"
                " category, event_date, payload_json, origin, taken_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(day, source, key, entry["fingerprint"], entry.get("label"),
                  entry.get("category"), entry.get("event_date"),
                  json.dumps(entry.get("payload") or {}, ensure_ascii=False), origin, taken_at)
                 for key, entry in entries.items()],
            )
        store.conn.commit()
    return counts


def _flatten(snapshot: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for source, entries in snapshot.items():
        for key, entry in entries.items():
            row = dict(entry)
            row["source"] = source
            row["item_key"] = key
            out[f"{source}:{key}"] = row
    return out


def take_snapshot(store: Store, day: Any = None, *, origin: str = ORIGIN_OBSERVED,
                  export_dir: str = "", include_items: bool = False,
                  cosmetic_catalog: Optional[Dict[str, Any]] = None,
                  drug_catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """오늘(또는 지정일) 상태를 스냅샷으로 적재하고 전일 대비 변화를 돌려준다."""
    if origin not in ORIGIN_SOURCES:
        raise ValueError("origin_must_be_observed_or_backfilled")
    target = _day(day)
    taken_at = iso(now_kst())
    snapshot = collect(store, cosmetic_catalog=cosmetic_catalog, drug_catalog=drug_catalog)
    previous_day = latest_day(store, before=target)
    previous = items_for(store, previous_day) if previous_day else {}
    counts = _upsert(store, target, snapshot, origin=origin, taken_at=taken_at)
    current = _flatten(snapshot)
    diff_keys = _diff_maps(current, previous)
    summary = {
        "schema": SNAPSHOT_SCHEMA,
        "version": SNAPSHOT_VERSION,
        "day": target,
        "taken_at": taken_at,
        "origin": origin,
        "previous_day": previous_day,
        "counts": counts,
        "total": sum(counts.values()),
        "diff": {
            "new": len(diff_keys["new"]),
            "changed": len(diff_keys["changed"]),
            "removed": len(diff_keys["removed"]),
            "new_by_source": _count_by_source(current, diff_keys["new"]),
            "changed_by_source": _count_by_source(current, diff_keys["changed"]),
            "removed_by_source": _count_by_source(previous, diff_keys["removed"]),
            "new_samples": _sample(current, diff_keys["new"]),
            "changed_samples": _sample(current, diff_keys["changed"]),
            "removed_samples": _sample(previous, diff_keys["removed"]),
            # 첫 관측(비교할 전일이 없음)이면 위 신규 건수는 "하루 사이 늘어난 양"이 아니라
            # 기준선 전체다. 추이 응답이 이 값을 신규로 읽지 않도록 함께 남긴다.
            "baseline": previous_day is None,
        },
        "first_observation": previous_day is None,
    }
    with store._lock:  # noqa: SLF001 - 실행 이력(전일 대비 요약 보관)
        store.conn.execute(
            "INSERT INTO snapshot_runs(day, taken_at, origin, counts_json, diff_json)"
            " VALUES (?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET taken_at=excluded.taken_at,"
            " origin=excluded.origin, counts_json=excluded.counts_json,"
            " diff_json=excluded.diff_json",
            (target, taken_at, origin, json.dumps(counts, ensure_ascii=False),
             json.dumps(summary["diff"], ensure_ascii=False)),
        )
        store.conn.commit()
    if export_dir:
        path = export_snapshot(summary, export_dir, include_items=include_items,
                               items=current)
        summary["export_path"] = path
    return summary


def export_snapshot(summary: Dict[str, Any], export_dir: str, *,
                    include_items: bool = False,
                    items: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """`{export_dir}/YYYY-MM-DD.json` 로 저장한다(기본은 요약만)."""
    os.makedirs(export_dir, exist_ok=True)
    payload = dict(summary)
    payload.pop("export_path", None)
    if include_items and items:
        by_source: Dict[str, List[Dict[str, Any]]] = {}
        for row in items.values():
            by_source.setdefault(str(row.get("source") or ""), []).append({
                "key": row.get("item_key"), "label": row.get("label"),
                "category": row.get("category"), "event_date": row.get("event_date"),
                "fingerprint": row.get("fingerprint"),
            })
        payload["items"] = by_source
    path = os.path.join(export_dir, f"{payload['day']}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def daily_diff(store: Store, day: Any = None, *, limit: int = 5) -> Dict[str, Any]:
    """저장된 스냅샷 두 개를 비교해 전일 대비 신규/변경/삭제를 돌려준다."""
    target = _day(day)
    previous_day = latest_day(store, before=target)
    current = items_for(store, target)
    if not current:
        return {"schema": SNAPSHOT_SCHEMA, "day": target, "state": "no_snapshot",
                "previous_day": previous_day, "note_ko":
                "이 날짜의 스냅샷이 없습니다. 스냅샷을 먼저 적재해야 전일 대비를 계산할 수 있습니다."}
    previous = items_for(store, previous_day) if previous_day else {}
    keys = _diff_maps(current, previous)
    by_source_current = {src: sum(1 for row in current.values() if row["source"] == src)
                         for src in SOURCES}
    by_source_previous = {src: sum(1 for row in previous.values() if row["source"] == src)
                          for src in SOURCES}
    return {
        "schema": SNAPSHOT_SCHEMA,
        "day": target,
        "state": "ok",
        "previous_day": previous_day,
        "baseline": previous_day is None,
        "counts": by_source_current,
        "previous_counts": by_source_previous,
        "new": len(keys["new"]),
        "changed": len(keys["changed"]),
        "removed": len(keys["removed"]),
        "new_by_source": _count_by_source(current, keys["new"]),
        "changed_by_source": _count_by_source(current, keys["changed"]),
        "removed_by_source": _count_by_source(previous, keys["removed"]),
        "new_samples": _sample(current, keys["new"], limit),
        "changed_samples": _sample(current, keys["changed"], limit),
        "removed_samples": _sample(previous, keys["removed"], limit),
    }


# --- 기동 시 시드 복원(0원 영속화) -------------------------------------------
def _has_day(store: Store, day: str) -> bool:
    with store._lock:  # noqa: SLF001 - 스냅샷 테이블 전용 조회
        row = store.conn.execute(
            "SELECT 1 AS present FROM compliance_snapshots WHERE day = ? LIMIT 1", (day,)
        ).fetchone()
    return bool(row)


def seed_snapshots(store: Store, seed_dir: str = "") -> Dict[str, Any]:
    """저장소에 커밋된 일일 스냅샷 JSON 을 DB 로 복원한다(멱등).

    - 항목(`items`)이 들어 있는 내보내기만 복원한다(요약만 있으면 전일 대비를 계산할 수 없다).
    - 이미 DB 에 그 날짜 기록이 있으면 덮어쓰지 않는다(오늘 관측분을 과거 파일로 되돌리지 않는다).
    - 원본 `origin`(observed/backfilled)을 보존하고, 알 수 없으면 `seed` 로 남긴다.
    """
    directory = seed_dir or DEFAULT_SEED_DIR
    result: Dict[str, Any] = {"seed_dir": directory, "days": [], "skipped": [],
                              "unreadable": [], "counts_only": [], "rows": 0, "counts": {}}
    if not os.path.isdir(directory):
        return result
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            result["unreadable"].append(name)
            continue
        if not isinstance(payload, dict):
            result["unreadable"].append(name)
            continue
        try:
            day = _day(payload.get("day"))
        except ValueError:
            result["unreadable"].append(name)
            continue
        items = payload.get("items") or {}
        if not isinstance(items, dict):
            items = {}
        if not items:
            # `origin="backfilled"` 재구성 파일(2026-10-23~11-19)과 과거 형식의 요약 파일은
            # 항목이 없어 시드로 복원할 수 없다. 이는 **오류가 아니라** 설계상 복원 대상이
            # 아닌 참고용 파일이다(과거 날짜의 누적 상태를 이벤트 날짜로 다시 만든 것).
            # `unreadable` 로 분류하면 점검할 때 진짜 손상된 파일과 구분할 수 없다.
            result["counts_only"].append(day)
            continue
        if _has_day(store, day):
            result["skipped"].append(day)
            continue
        subset: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for source, rows in items.items():
            if source not in SOURCES or not isinstance(rows, list):
                continue
            bucket: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("key") or "").strip()
                if not key:
                    continue
                bucket[key] = {
                    "label": _label(row.get("label")),
                    "category": _label(row.get("category")),
                    "event_date": str(row.get("event_date") or ""),
                    "fingerprint": str(row.get("fingerprint") or "") or _digest(key),
                    "payload": {},
                }
            if bucket:
                subset[source] = bucket
        if not subset:
            result["unreadable"].append(name)
            continue
        origin = str(payload.get("origin") or ORIGIN_SEED)
        if origin not in ORIGIN_SOURCES:
            origin = ORIGIN_SEED
        taken_at = str(payload.get("taken_at") or iso(now_kst()))
        counts = _upsert(store, day, subset, origin=origin, taken_at=taken_at)
        diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else {}
        with store._lock:  # noqa: SLF001 - 실행 이력(내보낸 요약을 그대로 되살린다)
            store.conn.execute(
                "INSERT INTO snapshot_runs(day, taken_at, origin, counts_json, diff_json)"
                " VALUES (?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET taken_at=excluded.taken_at,"
                " origin=excluded.origin, counts_json=excluded.counts_json,"
                " diff_json=excluded.diff_json",
                (day, taken_at, origin, json.dumps(counts, ensure_ascii=False),
                 json.dumps(diff, ensure_ascii=False)),
            )
            store.conn.commit()
        result["days"].append(day)
        result["rows"] += sum(counts.values())
        for source, value in counts.items():
            result["counts"][source] = result["counts"].get(source, 0) + int(value)
    return result


def seed_snapshot_usage(store: Store, path: str = "") -> Dict[str, Any]:
    """`/v1/stats` 응답(또는 행 목록)을 `usage_daily` 로 복원한다.

    카운터는 누적값이 아니라 '그날의 총 호출수'이고 새 프로세스는 0에서 +1 씩 더하므로,
    복원값 위에 새 트래픽이 더해져도 이중 계상되지 않는다. 여러 번 복원해도 `MAX` 로만
    키우므로 값이 줄거나 부풀지 않는다.
    """
    target = path or DEFAULT_USAGE_SEED
    result: Dict[str, Any] = {"path": target, "rows": 0, "days": 0}
    if not target or not os.path.isfile(target):
        return result
    try:
        with open(target, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return result
    rows = usage_rows_from_payload(payload)
    result["rows"] = store.seed_usage_rows(rows)
    result["days"] = len({row["day"] for row in rows})
    return result


def usage_rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    """`/v1/stats` 응답·행 목록을 (day, kind, key, count) 행으로 평탄화한다."""
    rows: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return rows
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        rows.append({"day": str(row.get("day") or ""), "kind": str(row.get("kind") or ""),
                     "key": str(row.get("key") or ""), "count": int(row.get("count") or 0)})
    mapping = {"paths": "path", "tools": "tool", "verdicts": "verdict", "flags": "flag"}
    for day_row in payload.get("days") or []:
        if not isinstance(day_row, dict):
            continue
        day = str(day_row.get("date") or day_row.get("day") or "")
        if not day:
            continue
        for field, kind in mapping.items():
            for key, value in (day_row.get(field) or {}).items():
                try:
                    count = int(value)
                except (TypeError, ValueError):
                    continue
                rows.append({"day": day, "kind": kind, "key": str(key), "count": count})
    return [row for row in rows if row["day"] and row["kind"] and row["key"] and row["count"] > 0]


def seed_persistence(store: Store, seed_dir: str = "", usage_path: str = "") -> Dict[str, Any]:
    """기동 시 시드 복원을 한 번에 수행하고 결과를 기억한다(`/v1/meta` 가 읽는다)."""
    snap = seed_snapshots(store, seed_dir)
    usage_info = seed_snapshot_usage(store, usage_path)
    summary = {
        "seeded_at": iso(now_kst()),
        "seed_dir": snap.get("seed_dir"),
        "seeded_days": list(snap.get("days") or []),
        "skipped_days": list(snap.get("skipped") or []),
        "unreadable_files": list(snap.get("unreadable") or []),
        "counts_only_days": list(snap.get("counts_only") or []),
        "seeded_rows": int(snap.get("rows") or 0),
        "usage": usage_info,
    }
    _LAST_SEED.clear()
    _LAST_SEED.update(summary)
    return summary


def persistence_status() -> Dict[str, Any]:
    """지금 프로세스에서 확인된 영속화 상태(시드가 없으면 그대로 밝힌다)."""
    info = dict(_LAST_SEED)
    info.setdefault("seeded_at", None)
    info.setdefault("seed_dir", DEFAULT_SEED_DIR)
    info.setdefault("seeded_days", [])
    info.setdefault("skipped_days", [])
    info.setdefault("counts_only_days", [])
    info.setdefault("seeded_rows", 0)
    knowledge = {
        "mode": "repo_seed + sqlite",
        "seed_dir": info.get("seed_dir"),
        "seed_present": bool(info.get("seeded_days") or info.get("skipped_days")),
        "seeded_days": info.get("seeded_days") or [],
        "snapshot_days_skipped": info.get("skipped_days") or [],
        # 2026-10-23~11-19 의 `origin="backfilled"` 요약 파일 — 실관측이 아니고 항목이
        # 없어 복원 대상이 아니다. 손상된 파일(unreadable)과 구분해 밝힌다.
        "counts_only_days": info.get("counts_only_days") or [],
        "counts_only_note_ko": (
            "`origin=\"backfilled\"` 로 표시된 과거 재구성 파일입니다(이벤트 날짜로 되살린 누적 "
            "건수만 있고 항목이 없음). 실제 관측분이 아니며 시드 복원·전일 대비 계산에 쓰지 않습니다."
        ),
        "seeded_rows": info.get("seeded_rows") or 0,
        "seeded_at": info.get("seeded_at"),
        "usage_seed": info.get("usage") or {},
        "workflow": ".github/workflows/daily-snapshot.yml",
        "note_ko": (
            "무료 플랜은 영구 디스크가 없어 재배포 시 작업 DB 가 초기화됩니다. 그래서 저장소에 "
            "커밋된 일일 스냅샷(data/snapshots)과 익명 사용 통계(data/usage/stats.json)를 기동 시 "
            "다시 적재합니다. 복원은 DB 에 없는 날짜만 채우고, 카운터는 큰 값만 남깁니다."
        ),
    }
    return knowledge


# --- 추이 -------------------------------------------------------------------
def _event_rows(store: Store, start: str, end: str) -> Dict[str, List[Dict[str, str]]]:
    """기간 내 이벤트(리콜 등록일·처분 확정일)를 소스별로 모은다."""
    with store._lock:  # noqa: SLF001
        recalls = store.conn.execute(
            "SELECT category, hazard_type, recall_type FROM recall_items"
            " WHERE registered_on BETWEEN ? AND ?", (start, end)).fetchall()
        dispositions = store.conn.execute(
            "SELECT law_reference, disposition_type FROM disposition_items"
            " WHERE confirmed_on BETWEEN ? AND ?", (start, end)).fetchall()
    return {
        "recall": [{"category": _top_category(row["category"]),
                    "hazard": str(row["hazard_type"] or "미분류"),
                    "type": str(row["recall_type"] or "미분류")} for row in recalls],
        "disposition": [{"law": _top_law(row["law_reference"]),
                         "type": str(row["disposition_type"] or "미분류")}
                        for row in dispositions],
    }


def _bucket(rows: Iterable[Dict[str, str]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = row.get(key) or "미분류"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _spike(rows: List[Dict[str, str]], prev_rows: List[Dict[str, str]], key: str,
           limit: int = TOP_LIMIT) -> List[Dict[str, Any]]:
    """현재 창과 직전 동일 기간을 비교한 증감표(급증 우선, 없으면 최다)."""
    current = _bucket(rows, key)
    previous = _bucket(prev_rows, key)
    table: List[Dict[str, Any]] = []
    for name in set(current) | set(previous):
        now_count = current.get(name, 0)
        before_count = previous.get(name, 0)
        delta = now_count - before_count
        ratio = round(now_count / before_count, 2) if before_count else None
        table.append({"key": name, "count": now_count, "previous_count": before_count,
                      "delta": delta, "ratio": ratio})
    table.sort(key=lambda row: (-row["delta"], -row["count"], str(row["key"])))
    rising = [row for row in table if row["delta"] > 0]
    return (rising or table)[:limit]


def _window_events(store: Store, anchor: str, days: int) -> Dict[str, Any]:
    start = _shift(anchor, -(days - 1))
    prev_end = _shift(start, -1)
    prev_start = _shift(prev_end, -(days - 1))
    rows = _event_rows(store, start, anchor)
    prev_rows = _event_rows(store, prev_start, prev_end)
    return {
        "start": start,
        "end": anchor,
        "previous_start": prev_start,
        "previous_end": prev_end,
        "recall_total": len(rows["recall"]),
        "disposition_total": len(rows["disposition"]),
        "previous_recall_total": len(prev_rows["recall"]),
        "previous_disposition_total": len(prev_rows["disposition"]),
        "by_category": _spike(rows["recall"], prev_rows["recall"], "category"),
        "by_hazard": _spike(rows["recall"], prev_rows["recall"], "hazard"),
        "by_recall_type": _spike(rows["recall"], prev_rows["recall"], "type"),
        "by_law": _spike(rows["disposition"], prev_rows["disposition"], "law"),
        "by_disposition_type": _spike(rows["disposition"], prev_rows["disposition"], "type"),
    }


def _event_bounds(store: Store) -> Dict[str, Any]:
    with store._lock:  # noqa: SLF001
        recall = store.conn.execute(
            "SELECT MIN(registered_on) AS lo, MAX(registered_on) AS hi, COUNT(*) AS n"
            " FROM recall_items WHERE registered_on IS NOT NULL AND registered_on != ''"
        ).fetchone()
        disposition = store.conn.execute(
            "SELECT MIN(confirmed_on) AS lo, MAX(confirmed_on) AS hi, COUNT(*) AS n"
            " FROM disposition_items WHERE confirmed_on IS NOT NULL AND confirmed_on != ''"
        ).fetchone()
    return {
        "recall": {"first": recall["lo"], "last": recall["hi"], "count": int(recall["n"] or 0)},
        "disposition": {"first": disposition["lo"], "last": disposition["hi"],
                        "count": int(disposition["n"] or 0)},
    }


def trends(store: Store, days: int = DEFAULT_TREND_DAYS, today: Any = None, *,
           source: str = "all", limit: int = TOP_LIMIT) -> Dict[str, Any]:
    """최근 N일 스냅샷 변화 + 이벤트 기준 급증 품목·유형을 함께 돌려준다."""
    window = max(1, min(int(days or DEFAULT_TREND_DAYS), MAX_TREND_DAYS))
    limit = max(1, min(int(limit or TOP_LIMIT), 20))
    anchor = _day(today)
    start = _shift(anchor, -(window - 1))

    series: List[Dict[str, Any]] = []
    with store._lock:  # noqa: SLF001
        runs = store.conn.execute(
            "SELECT day, taken_at, origin, counts_json, diff_json FROM snapshot_runs"
            " WHERE day BETWEEN ? AND ? ORDER BY day", (start, anchor)).fetchall()
    for row in runs:
        try:
            counts = json.loads(row["counts_json"] or "{}")
            diff = json.loads(row["diff_json"] or "{}")
        except ValueError:
            counts, diff = {}, {}
        if source != "all":
            counts = {source: counts.get(source, 0)}
            diff = {key: (value.get(source, 0) if isinstance(value, dict) else value)
                    for key, value in diff.items()}
        series.append({
            "day": row["day"],
            "origin": row["origin"],
            "counts": counts,
            "total": sum(int(v or 0) for v in counts.values()),
            "new": int(diff.get("new") or 0),
            "changed": int(diff.get("changed") or 0),
            "removed": int(diff.get("removed") or 0),
            # 기준선(baseline)인 날의 new 는 그날 늘어난 양이 아니라 적재된 전체 건수다.
            "baseline": bool(diff.get("baseline")),
        })
    observed_days = [row for row in series if row["origin"] == ORIGIN_OBSERVED]

    bounds = _event_bounds(store)
    current_window = _window_events(store, anchor, window)
    reference: Optional[Dict[str, Any]] = None
    latest_event = max([value for value in (
        bounds["recall"]["last"] or "", bounds["disposition"]["last"] or "") if value] or [""])
    if current_window["recall_total"] == 0 and current_window["disposition_total"] == 0 and latest_event:
        reference = {"as_of": latest_event, "reason_ko": (
            "요청 기간에 이벤트가 0건이라, 데이터의 마지막 이벤트일을 기준으로 같은 길이의 "
            "창을 다시 계산했습니다. 0건을 '급증 없음'으로 단정하지 않습니다."),
            **_window_events(store, latest_event, window)}

    coverage = {
        "snapshot_available_days": len(series),
        "observed_days": len(observed_days),
        "first_day": series[0]["day"] if series else None,
        "last_day": series[-1]["day"] if series else None,
        "event_bounds": bounds,
        "sources": {src: SOURCE_LABEL_KO[src] for src in SOURCES},
        "note_ko": (
            "신규/변경/삭제는 저장된 일일 스냅샷의 전일 대비 값이고, 급증 표는 리콜 등록일·"
            "처분 확정일을 기준으로 직전 동일 기간과 비교한 값입니다. 리콜 파일데이터는 "
            "2023-08-09 배포본이라 그 이후 등록분은 관측되지 않습니다."
        ),
    }
    return {
        "schema": TRENDS_SCHEMA,
        "version": SNAPSHOT_VERSION,
        "window_days": window,
        "anchor_day": anchor,
        "generated_at": iso(now_kst()),
        "source": source,
        "series": series,
        "last_observed_diff": ({"day": series[-1]["day"], "new": series[-1]["new"],
                                "changed": series[-1]["changed"], "removed": series[-1]["removed"],
                                "baseline": series[-1].get("baseline", False),
                                "loaded": series[-1]["total"]}
                               if series else None),
        "current_window": current_window,
        "reference": reference,
        "coverage": coverage,
    }


def backfill_from_history(store: Store, days: int = DEFAULT_TREND_DAYS, *,
                          end_day: Any = None, export_dir: str = "") -> Dict[str, Any]:
    """이벤트 날짜로 과거 N일의 누적 상태를 재구성해 스냅샷을 채운다.

    실제 관측값이 아니므로 `origin="backfilled"` 로 남긴다. 이벤트 날짜가 없는 소스
    (금지성분·성분 사전)는 모든 날짜에 같은 상태로 들어간다.
    """
    window = max(1, min(int(days or DEFAULT_TREND_DAYS), MAX_TREND_DAYS))
    anchor = _day(end_day)
    start = _shift(anchor, -(window - 1))
    snapshot = collect(store)
    full = _flatten(snapshot)
    taken_at = iso(now_kst())
    written: List[str] = []
    with store._lock:  # noqa: SLF001 - 실제 관측 스냅샷은 재구성으로 덮지 않는다
        observed = {row["day"] for row in store.conn.execute(
            "SELECT day FROM snapshot_runs WHERE origin = ? AND day BETWEEN ? AND ?",
            (ORIGIN_OBSERVED, start, anchor)).fetchall()}
    skipped: List[str] = []
    for offset in range(window):
        day = _shift(start, offset)
        if day in observed:
            skipped.append(day)
            continue
        subset: Dict[str, Dict[str, Dict[str, Any]]] = {src: {} for src in SOURCES}
        for key, row in full.items():
            event_date = str(row.get("event_date") or "")
            if event_date and event_date > day:
                continue
            subset.setdefault(str(row["source"]), {})[str(row["item_key"])] = row
        _upsert(store, day, subset, origin=ORIGIN_BACKFILLED, taken_at=taken_at)
        summary = {"schema": SNAPSHOT_SCHEMA, "day": day, "taken_at": taken_at,
                   "origin": ORIGIN_BACKFILLED,
                   "counts": {src: len(rows) for src, rows in subset.items()}}
        if export_dir:
            export_snapshot(summary, export_dir)
        written.append(day)
    # 마지막 날과 그 전날을 실제로 비교해 실행 이력도 채운다.
    totals: Dict[str, int] = {}
    for day in written:
        result = daily_diff(store, day, limit=3)
        totals[day] = int(result.get("new") or 0) + int(result.get("changed") or 0)
        with store._lock:  # noqa: SLF001
            store.conn.execute(
                "INSERT INTO snapshot_runs(day, taken_at, origin, counts_json, diff_json)"
                " VALUES (?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET taken_at=excluded.taken_at,"
                " origin=excluded.origin, counts_json=excluded.counts_json,"
                " diff_json=excluded.diff_json",
                (day, taken_at, ORIGIN_BACKFILLED,
                 json.dumps(result.get("counts") or {}, ensure_ascii=False),
                 json.dumps({key: result.get(key) or 0 for key in
                             ("new", "changed", "removed", "new_by_source",
                              "changed_by_source", "removed_by_source")}, ensure_ascii=False)),
            )
            store.conn.commit()
    return {"schema": SNAPSHOT_SCHEMA, "origin": ORIGIN_BACKFILLED,
            "start": start, "end": anchor, "days": len(written),
            "skipped_observed_days": skipped,
            "last_diff": daily_diff(store, anchor, limit=5)}


# --- CLI --------------------------------------------------------------------
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m import_compliance.snapshots",
        description="CLNS 일일 리콜·행정처분·금지성분 스냅샷 적재와 추이 조회",
    )
    parser.add_argument("--db", default="", help="SQLite 경로(기본 data/app.sqlite)")
    parser.add_argument("--take", action="store_true", help="오늘 스냅샷을 적재한다")
    parser.add_argument("--day", default="", help="적재 기준일 YYYY-MM-DD(기본 오늘)")
    parser.add_argument("--backfill", type=int, default=0,
                        help="이벤트 날짜로 과거 N일 스냅샷을 재구성한다")
    parser.add_argument("--end-day", default="", help="재구성 기준 종료일(기본 오늘)")
    parser.add_argument("--export", default="",
                        help="스냅샷 JSON 저장 폴더(경로는 실행 위치 기준. 예: ../data/snapshots)")
    parser.add_argument("--include-items", action="store_true",
                        help="내보내기 JSON에 항목 목록 포함(기본은 요약)")
    parser.add_argument("--diff", nargs="?", const="", default=None,
                        help="지정일(또는 최근) 전일 대비 변화")
    parser.add_argument("--trends", type=int, default=0, help="최근 N일 추이 요약")
    parser.add_argument("--seed", nargs="?", const=DEFAULT_SEED_DIR, default=None,
                        help="저장소에 커밋된 스냅샷 JSON 을 DB 로 복원(기본 data/snapshots)")
    parser.add_argument("--seed-usage", nargs="?", const=DEFAULT_USAGE_SEED, default=None,
                        help="익명 사용 통계(/v1/stats 응답)를 DB 로 복원(기본 data/usage/stats.json)")
    args = parser.parse_args(argv)

    db_path = args.db or os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "data", "app.sqlite")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    store = Store(db_path)
    try:
        from . import recall_index

        try:  # 배포 이미지에 든 리콜 인덱스를 작업 DB로 복사한다(이미 있으면 0).
            recall_index.load_from_index(store)
        except Exception:  # noqa: BLE001 - 인덱스가 없어도 스냅샷은 동작해야 한다
            pass
        if args.backfill:
            _print(backfill_from_history(store, args.backfill, end_day=args.end_day or None,
                                         export_dir=args.export))
        if args.seed is not None or args.seed_usage is not None:
            _print(seed_persistence(store, args.seed or "", args.seed_usage or ""))
        if args.take:
            _print(take_snapshot(store, args.day or None, export_dir=args.export,
                                 include_items=args.include_items))
        if args.diff is not None:
            _print(daily_diff(store, args.diff or None))
        if args.trends:
            _print(trends(store, args.trends))
        if not (args.take or args.backfill or args.trends or args.diff is not None
                or args.seed is not None or args.seed_usage is not None):
            _print(trends(store, DEFAULT_TREND_DAYS))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
