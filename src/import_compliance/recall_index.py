"""국가기술표준원 제품안전 리콜 파일데이터 적재·조회.

대상(공공데이터포털, 이용허락범위 제한 없음):
  - 15040696 산업통상부_국가기술표준원_제품안전_국내리콜정보 (CSV, 건별 리콜 이력)
  - 15054301 산업통상부_기술표준통계_제품 리콜처분현황 (CSV, 연도·품목군별 집계)

파일데이터는 인증키 없이 내려받을 수 있지만 **정적 스냅샷**이다. 15040696은
2023-08-09 기준(등록일 2019-10~2022-07)으로 더 이상 갱신되지 않으므로,
실시간 리콜 판정 근거가 아니라 '과거 이력 조회 + 커버리지 고지'용으로만 쓴다.
최신 리콜은 국가기술표준원 제품안전정보센터(safetykorea.kr)에서 확인해야 한다.
"""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .store import KST, Store, iso, now_kst

FILE_INFO_URL = "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?publicDataPk={pk}"
FILE_DOWNLOAD_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do"
    "?atchFileId={atch}&fileDetailSn={sn}&insertDataPrcus=N"
)
USER_AGENT = "Mozilla/5.0 (compatible; clns-kr/0.1; +local-index)"

DATASETS: Dict[str, Dict[str, str]] = {
    "15040696": {
        "name_ko": "산업통상부_국가기술표준원_제품안전_국내리콜정보",
        "kind": "items",
        "page_url": "https://www.data.go.kr/data/15040696/fileData.do",
        "update_cycle": "1회성(2023-08-09 기준)",
    },
    "15054301": {
        "name_ko": "산업통상부_기술표준통계_제품 리콜처분현황",
        "kind": "stats",
        "page_url": "https://www.data.go.kr/data/15054301/fileData.do",
        "update_cycle": "연간(2025년 말 기준)",
    },
}

# 15040696 컬럼 → 내부 필드
ITEM_COLUMNS: Dict[str, str] = {
    "인증번호": "cert_no",
    "모델명": "model",
    "제품명": "product_name",
    "브랜드명": "brand",
    "사업자구분": "business_type",
    "법정제품분류": "category",
    "리콜종류": "recall_type",
    "리콜사업자명": "recall_business",
    "제조국가명": "manufacture_country",
    "제조사명": "manufacturer",
    "제조사국가명": "manufacturer_country",
    "리콜방법": "recall_method",
    "위해유형": "hazard_type",
    "안전성조사명": "safety_inspection",
    "등록일": "registered_on",
}

STAT_CATEGORIES = {
    "생활용품": "생활용품",
    "전기용품": "전기용품",
    "어린이제품": "어린이제품",
}
STAT_DISPOSITIONS = {
    "리콜명령": "리콜명령",
    "리콜권고": "리콜권고",
    "자발적 리콜": "자발적리콜",
}

# 검색 시 가중치(높을수록 강한 일치)
SEARCH_FIELDS: Sequence[tuple] = (
    ("model", 5),
    ("product_name", 4),
    ("brand", 3),
    ("category", 2),
    ("recall_business", 1),
    ("manufacturer", 1),
    ("cert_no", 2),
)


def decode_csv(raw: bytes) -> str:
    """공공데이터포털 CSV는 UTF-8(BOM) 또는 CP949가 섞여 온다."""
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def parse_items(text: str) -> List[Dict[str, str]]:
    """15040696 CSV 텍스트 → 정규화된 레코드 목록."""
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, str]] = []
    for raw in reader:
        record = {field: _clean(raw.get(column, "")) for column, field in ITEM_COLUMNS.items()}
        if not any(record.values()):
            continue
        rows.append(record)
    return rows


def parse_stats(text: str) -> List[Dict[str, Any]]:
    """15054301 CSV(가로형 집계) → (연도, 품목군, 처분, 건수) 세로형."""
    reader = csv.DictReader(io.StringIO(text))
    out: List[Dict[str, Any]] = []
    for raw in reader:
        year = _clean(raw.get("연도", ""))
        if not year:
            continue
        for column, value in raw.items():
            if not column or column == "연도":
                continue
            category = disposition = None
            for cat in STAT_CATEGORIES:
                for disp_key, disp in STAT_DISPOSITIONS.items():
                    if column.replace(" ", "").startswith(cat) and disp_key.replace(" ", "") in column.replace(" ", ""):
                        category, disposition = STAT_CATEGORIES[cat], disp
            if not category or not disposition:
                continue
            try:
                count = int(_clean(value) or 0)
            except ValueError:
                continue
            out.append({"year": year, "category": category, "disposition": disposition, "count": count})
    return out


def download_dataset(dataset_id: str, dest_dir: str, *, timeout: float = 60.0) -> Dict[str, Any]:
    """파일데이터를 인증키 없이 내려받아 dest_dir에 저장하고 메타를 돌려준다."""
    if dataset_id not in DATASETS:
        raise ValueError(f"unknown_dataset:{dataset_id}")
    os.makedirs(dest_dir, exist_ok=True)
    info_url = FILE_INFO_URL.format(pk=dataset_id)
    with urllib.request.urlopen(
        urllib.request.Request(info_url, headers={"User-Agent": USER_AGENT}), timeout=timeout
    ) as response:
        info = json.loads(response.read().decode("utf-8", errors="replace"))
    atch = info.get("atchFileId")
    sn = info.get("fileDetailSn") or 1
    if not atch or not info.get("status"):
        raise RuntimeError(f"file_info_unavailable:{dataset_id}:{info.get('status')}")
    download_url = FILE_DOWNLOAD_URL.format(atch=urllib.parse.quote(str(atch)), sn=sn)
    with urllib.request.urlopen(
        urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT}), timeout=timeout
    ) as response:
        raw = response.read()
    path = os.path.join(dest_dir, f"recall_{dataset_id}.csv")
    with open(path, "wb") as handle:
        handle.write(raw)
    return {
        "dataset_id": dataset_id,
        "path": path,
        "bytes": len(raw),
        "atch_file_id": str(atch),
        "file_detail_sn": sn,
        "downloaded_at": iso(now_kst()),
    }


def load_items(store: Store, text: str, *, dataset_id: str = "15040696") -> int:
    rows = parse_items(text)
    source_url = DATASETS.get(dataset_id, {}).get("page_url", "")
    loaded_at = iso(now_kst())
    with store._lock:  # noqa: SLF001 - 같은 모듈 계열 저장소를 한 번에 적재
        store.conn.execute("DELETE FROM recall_items WHERE dataset_id = ?", (dataset_id,))
        store.conn.executemany(
            "INSERT INTO recall_items(dataset_id, cert_no, model, product_name, brand, business_type,"
            " category, recall_type, recall_business, manufacture_country, manufacturer,"
            " manufacturer_country, recall_method, hazard_type, safety_inspection, registered_on,"
            " source_url, loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    dataset_id, r["cert_no"], r["model"], r["product_name"], r["brand"],
                    r["business_type"], r["category"], r["recall_type"], r["recall_business"],
                    r["manufacture_country"], r["manufacturer"], r["manufacturer_country"],
                    r["recall_method"], r["hazard_type"], r["safety_inspection"],
                    r["registered_on"], source_url, loaded_at,
                )
                for r in rows
            ],
        )
        store.conn.commit()
    return len(rows)


def load_stats(store: Store, text: str, *, dataset_id: str = "15054301") -> int:
    rows = parse_stats(text)
    with store._lock:  # noqa: SLF001
        store.conn.execute("DELETE FROM recall_stats WHERE dataset_id = ?", (dataset_id,))
        store.conn.executemany(
            "INSERT OR REPLACE INTO recall_stats(dataset_id, year, category, disposition, count)"
            " VALUES (?,?,?,?,?)",
            [(dataset_id, r["year"], r["category"], r["disposition"], r["count"]) for r in rows],
        )
        store.conn.commit()
    return len(rows)


def load_files(store: Store, paths: Dict[str, str]) -> Dict[str, Any]:
    """{'15040696': path, '15054301': path} → 적재 결과."""
    out: Dict[str, Any] = {}
    for dataset_id, path in paths.items():
        with open(path, "rb") as handle:
            text = decode_csv(handle.read())
        if DATASETS.get(dataset_id, {}).get("kind") == "stats":
            out[dataset_id] = {"stats_rows": load_stats(store, text, dataset_id=dataset_id)}
        else:
            out[dataset_id] = {"items": load_items(store, text, dataset_id=dataset_id)}
    return out


def summary(store: Store) -> Dict[str, Any]:
    """로컬 인덱스 커버리지(건수·등록일 범위·적재시각)."""
    row = store.conn.execute(
        "SELECT COUNT(*) AS n, MIN(registered_on) AS lo, MAX(registered_on) AS hi,"
        " MAX(loaded_at) AS loaded_at FROM recall_items"
    ).fetchone()
    stats = store.conn.execute("SELECT COUNT(*) AS n, MIN(year) AS lo, MAX(year) AS hi FROM recall_stats").fetchone()
    item_count = int(row["n"] or 0)
    return {
        "items": item_count,
        "first_registered_on": row["lo"],
        "last_registered_on": row["hi"],
        "loaded_at": row["loaded_at"],
        "stats_rows": int(stats["n"] or 0),
        "stats_years": [stats["lo"], stats["hi"]] if stats["n"] else [],
        "dataset": "15040696" if item_count else None,
        "coverage_note_ko": (
            "국내리콜 파일데이터는 2023-08-09 배포본(등록일 2019-10~2022-07)으로 갱신이 멈춘 정적 스냅샷입니다. "
            "0건은 '리콜 이력 없음'을 뜻하지 않으며, 최신 리콜은 제품안전정보센터에서 확인해야 합니다."
        ),
    }


def _terms(query: str) -> List[str]:
    cleaned = query.replace(",", " ").replace("|", " ").replace("/", " ")
    return [t for t in (part.strip() for part in cleaned.split()) if len(t) >= 1]


def search(
    store: Store,
    keywords: Iterable[str],
    *,
    model: str = "",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """키워드 OR 검색 + 필드 가중치 점수. 결과는 점수·등록일 역순."""
    terms = [t for t in dict.fromkeys(_terms(" ".join(keywords)))]
    if not terms:
        return []
    where: List[str] = []
    params: List[Any] = []
    for term in terms:
        clause = " OR ".join(f"IFNULL({field}, '') LIKE ?" for field, _ in SEARCH_FIELDS)
        where.append(f"({clause})")
        params.extend([f"%{term}%"] * len(SEARCH_FIELDS))
    sql = (
        "SELECT * FROM recall_items WHERE " + " AND ".join(where) +
        " ORDER BY registered_on DESC LIMIT 200"
    )
    rows = store.conn.execute(sql, params).fetchall()
    scored: List[Dict[str, Any]] = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        score = 0
        matched: List[str] = []
        for field, weight in SEARCH_FIELDS:
            value = str(item.get(field) or "").lower()
            if not value:
                continue
            for term in terms:
                if term.lower() in value:
                    score += weight
                    matched.append(f"{field}:{term}")
        if model:
            if model.lower() == str(item.get("model") or "").lower():
                score += 20
                matched.append("model:exact")
            elif model.lower() in str(item.get("model") or "").lower():
                score += 8
                matched.append("model:partial")
        if score:
            item["score"] = score
            item["matched"] = matched
            scored.append(item)
    scored.sort(key=lambda it: (-it["score"], str(it.get("registered_on") or "")))
    return scored[:limit]


def stats_table(store: Store) -> List[Dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT year, category, disposition, count FROM recall_stats ORDER BY year DESC, category, disposition"
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def default_index_path() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "data", "recalls.sqlite")


ITEM_FIELDS = tuple(ITEM_COLUMNS.values())


def load_from_index(store: Store, index_path: str = "", *, dataset_id: str = "15040696") -> int:
    """이미 빌드해 둔 인덱스 SQLite(recalls.sqlite)의 리콜 행을 작업 DB로 복사한다.

    배포 환경에서는 작업 DB(SQLite)가 재시작마다 비어 있으므로, 이미지에 넣어 둔
    인덱스를 읽기 전용으로 열어 옮긴다. 원본 인덱스 파일은 절대 쓰지 않는다
    (쿼터·판정 이력이 섞이지 않게 하기 위함).
    """
    import sqlite3

    index_path = index_path or default_index_path()
    if not os.path.exists(index_path):
        return 0
    if os.path.abspath(index_path) == os.path.abspath(str(getattr(store, "path", ""))):
        return 0
    if summary(store)["items"] > 0:
        return 0
    src = sqlite3.connect("file:" + index_path.replace("?", "%3F") + "?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in src.execute(
            "SELECT " + ", ".join(ITEM_FIELDS) + " FROM recall_items")]
        stats = [dict(row) for row in src.execute(
            "SELECT year, category, disposition, count FROM recall_stats")]
    except sqlite3.Error:
        return 0
    finally:
        src.close()
    if not rows:
        return 0
    loaded_at = iso(now_kst())
    source_url = DATASETS.get(dataset_id, {}).get("page_url", "")
    columns = (
        "dataset_id, cert_no, model, product_name, brand, business_type, category, recall_type,"
        " recall_business, manufacture_country, manufacturer, manufacturer_country, recall_method,"
        " hazard_type, safety_inspection, registered_on, source_url, loaded_at"
    )
    values = [
        (
            dataset_id, r.get("cert_no", ""), r.get("model", ""), r.get("product_name", ""),
            r.get("brand", ""), r.get("business_type", ""), r.get("category", ""),
            r.get("recall_type", ""), r.get("recall_business", ""),
            r.get("manufacture_country", ""), r.get("manufacturer", ""),
            r.get("manufacturer_country", ""), r.get("recall_method", ""),
            r.get("hazard_type", ""), r.get("safety_inspection", ""),
            r.get("registered_on", ""), source_url, loaded_at,
        )
        for r in rows
    ]
    with store._lock:  # noqa: SLF001
        store.conn.execute("DELETE FROM recall_items WHERE dataset_id = ?", (dataset_id,))
        store.conn.executemany(
            "INSERT INTO recall_items(" + columns + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
        if stats:
            store.conn.execute("DELETE FROM recall_stats WHERE dataset_id = ?", ("15054301",))
            store.conn.executemany(
                "INSERT OR REPLACE INTO recall_stats(dataset_id, year, category, disposition, count)"
                " VALUES (?,?,?,?,?)",
                [("15054301", s["year"], s["category"], s["disposition"], s["count"]) for s in stats],
            )
        store.conn.commit()
    return len(rows)


def default_raw_dir() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "data", "raw")


def build_index(index_path: str = "", raw_dir: str = "", *, timeout: float = 60.0) -> Dict[str, Any]:
    """두 파일데이터를 내려받아 SQLite 인덱스를 새로 만든다(네트워크 필요)."""
    index_path = index_path or default_index_path()
    raw_dir = raw_dir or default_raw_dir()
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    downloads = {dataset_id: download_dataset(dataset_id, raw_dir, timeout=timeout) for dataset_id in DATASETS}
    store = Store(index_path)
    try:
        loaded = load_files(store, {dataset_id: meta["path"] for dataset_id, meta in downloads.items()})
        info = summary(store)
    finally:
        store.close()
    return {
        "index_path": index_path,
        "downloaded": {k: {kk: vv for kk, vv in v.items() if kk != "atch_file_id"} for k, v in downloads.items()},
        "loaded": loaded,
        "summary": info,
        "built_at": datetime.now(KST).isoformat(timespec="seconds"),
    }
