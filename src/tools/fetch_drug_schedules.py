#!/usr/bin/env python3
"""마약류 관리에 관한 법률 시행령 별표 1~8을 법제처 API로 받아 성분 목록을 만든다.

왜 이 도구가 필요한가
---------------------
'한국 반입 금지 성분'을 우리가 손으로 적으면 추정이 섞인다. 마약류의 정의와 목록은
**마약류 관리에 관한 법률 제2조 + 시행령 별표 1~8**이 정하고, 이 별표가 곧 금지·제한
성분의 1차 근거다. 그래서 별표 표를 파싱해 이름(한글·영문)만 뽑아 로컬 사전
(`src/drug_schedules.json`)으로 만든다. 원문 문장은 저장하지 않고, 인용이 필요하면
법제처 API를 다시 호출한다(출처: 법제처 국가법령정보센터).

무엇을 뽑는가
-------------
- 별표 1~6, 7의2: 마약 / 향정신성의약품(가~라목) / 대마와 동일한 화학적합성품
- 별표 8: 마약류 원료물질(에페드린·슈도에페린 등) — 마약류는 아니지만 수출입 허가 대상

사용
----
    cd src
    python3 tools/fetch_drug_schedules.py --out drug_schedules.json

키는 `.env`(LAW_GO_KR_OC)에서만 읽고, 출력에는 키를 남기지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from import_compliance.live_api import (  # noqa: E402
    LAW_SERVICE_URL,
    LiveApiError,
    _clean,
    from_environment,
    normalize_law_article,
    redact,
)

KST = timezone(timedelta(hours=9))
DECREE_NAME = "마약류 관리에 관한 법률 시행령"

# 별표 번호 → (분류 코드, 분류 한글, 법 조문 참조)
TABLE_CLASS = {
    "0001": ("NARCOTIC", "마약", "법 제2조제2호라목"),
    "0002": ("NARCOTIC", "마약", "법 제2조제2호마목"),
    "0003": ("PSYCHOTROPIC", "향정신성의약품(가목)", "법 제2조제3호가목"),
    "0004": ("PSYCHOTROPIC", "향정신성의약품(나목)", "법 제2조제3호나목"),
    "0005": ("PSYCHOTROPIC", "향정신성의약품(다목)", "법 제2조제3호다목"),
    "0006": ("PSYCHOTROPIC", "향정신성의약품(라목)", "법 제2조제3호라목"),
    "0007": ("CANNABIS_SYNTHETIC", "대마와 동일한 화학적합성품", "법 제2조제4호다목"),
    "0008": ("PRECURSOR", "마약류 원료물질", "법 제2조제6호"),
}


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _yyyymmdd(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) >= 8 else ""


def _flatten(node, out: list) -> None:
    if isinstance(node, str):
        out.append(node)
        return
    if isinstance(node, list):
        for item in node:
            _flatten(item, out)
        return
    if isinstance(node, dict):
        for value in node.values():
            _flatten(value, out)


def _parse_table_rows(lines: list) -> list:
    """박스 문자(│ ├ ┌ └) 표를 행 단위로 되살린다.

    별표는 셀 폭에 맞춰 줄바꿈되어 있어서, 첫 칸(번호)이 비어 있는 줄은
    앞 행의 이어짐으로 붙인다. 영문명이 중간에 끊겨도 여기서 다시 합쳐진다.
    """
    rows: list = []
    current = None
    for line in lines:
        text = line.strip()
        if not text.startswith("│") or text.startswith(("├", "└", "┌")):
            continue
        cells = [cell.strip() for cell in text.strip("│").split("│")]
        if len(cells) < 2:
            continue
        if "품명" in cells[1] or cells[0] in ("구분", "구", "번호", "구 분"):
            continue
        if current is not None and (cells[0] == "" or not cells[0].isdigit()):
            for index, cell in enumerate(cells):
                if cell and index < len(current):
                    current[index] = (current[index] + " " + cell).strip()
            continue
        if current is not None:
            rows.append(current)
        current = list(cells)
    if current is not None:
        rows.append(current)
    return rows


def _split_name(cell: str) -> tuple:
    """'코카인(Cocaine)' → ('코카인', 'Cocaine'). 괄호가 없으면 영문명은 빈 값."""
    text = " ".join(cell.split())
    match = re.search(r"\(([^()]*)\)", text)
    if not match:
        return text.strip(), ""
    korean = (text[: match.start()] + " " + text[match.end():]).strip()
    korean = re.sub(r"\s{2,}", " ", korean)
    return korean.strip(" ,ㆍ·"), match.group(1).strip()


def fetch_decree(client) -> dict:
    url = client._url(LAW_SERVICE_URL, {"OC": client._law_oc, "target": "law",
                                        "MST": client._law_mst, "type": "JSON"})
    status, body, _ = client._transport(url, 60)
    if status >= 400:
        raise LiveApiError("law_api", f"HTTP {status}")
    payload = json.loads(body)
    return payload.get("법령") or {}


def _decree_mst(client) -> str:
    """시행령 현행 법령일련번호를 찾는다(법령명 정확 일치만)."""
    url = client._url("https://www.law.go.kr/DRF/lawSearch.do",
                      {"OC": client._law_oc, "target": "eflaw", "type": "JSON",
                       "query": DECREE_NAME, "display": 40, "page": 1})
    status, body, _ = client._transport(url, 30)
    if status >= 400:
        raise LiveApiError("law_api", f"HTTP {status}")
    rows = (json.loads(body).get("LawSearch") or {}).get("law") or []
    best = None
    for row in rows:
        name = _clean(row.get("법령명한글"))
        if name.replace(" ", "") != DECREE_NAME.replace(" ", ""):
            continue
        effective = "".join(ch for ch in _clean(row.get("시행일자")) if ch.isdigit())
        candidate = (effective, _clean(row.get("현행연혁코드")), _clean(row.get("법령일련번호")))
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None or not best[2]:
        raise LiveApiError("law_api", "시행령을 찾지 못했습니다")
    return best[2]


def build(client) -> dict:
    mst = _decree_mst(client)
    client._law_mst = mst  # noqa: SLF001 - 이 도구 안에서만 쓰는 임시 보관
    law = fetch_decree(client)
    basic = law.get("기본정보") or {}
    units = ((law.get("별표") or {}).get("별표단위")) or []
    tables: list = []
    substances: list = []
    precursors: list = []
    for unit in units:
        number = _clean(unit.get("별표번호"))
        title = _clean(unit.get("별표제목"))
        if number not in TABLE_CLASS:
            continue
        # 별표 7은 '혼합물질·혼합제제' 서술이라 목록이 없다 → 건너뛴다.
        if number == "0007" and "화학적합성품" not in title:
            continue
        class_code, class_ko, reference = TABLE_CLASS[number]
        lines: list = []
        _flatten(unit.get("별표내용"), lines)
        rows = _parse_table_rows(lines)
        entries = []
        revised_on = _revision_date(" ".join(lines[:3]))
        for row in rows:
            name_cell = row[1] if len(row) > 1 else ""
            name_ko, name_en = _split_name(name_cell)
            if not name_ko or name_ko in ("품명", "구분"):
                continue
            # 서술형 각주("…유사체. 다만, …")는 성분명이 아니다. 뒤의 단서만 떼어낸다.
            if "다만" in name_ko:
                name_ko = name_ko.split(".")[0].strip()
            if any(marker in name_ko for marker in ("유사체", "유도체", "유사 체", "유도 체", "제외")):
                continue
            if not name_ko or len(name_ko) > 60 or not re.search(r"[가-힣A-Za-z]", name_ko):
                continue
            entry = {
                "name_ko": name_ko,
                "name_en": name_en,
                "class": class_code,
                "class_ko": class_ko,
                "reference": reference,
                "table": f"별표 {number.lstrip('0')}",
                "no": row[0].strip(),
            }
            entries.append(entry)
        tables.append({
            "table": f"별표 {number.lstrip('0')}",
            "title": title,
            "class": class_code,
            "class_ko": class_ko,
            "reference": reference,
            "row_count": len(entries),
            "revised_on": revised_on,
        })
        (precursors if class_code == "PRECURSOR" else substances).extend(entries)
    counts = {}
    for entry in substances:
        counts[entry["class"]] = counts.get(entry["class"], 0) + 1
    counts["PRECURSOR"] = len(precursors)
    return {
        "schedule_version": "1.0.0",
        "generated_on": today_kst(),
        "law": "마약류 관리에 관한 법률",
        "decree": DECREE_NAME,
        "decree_mst": mst,
        "decree_promulgated_on": _yyyymmdd(_clean(basic.get("공포일자"))),
        "decree_effective_from": _yyyymmdd(_clean(basic.get("시행일자"))),
        "decree_promulgation_no": _clean(basic.get("공포번호")),
        "attribution_ko": "출처: 법제처 국가법령정보센터 — 마약류 관리에 관한 법률 시행령 별표 1~8",
        "note_ko": (
            "별표 표에서 이름(한글·영문)만 추출한 로컬 사전입니다. 조문 원문·별표 전체 내용은 "
            "법제처 국가법령정보센터에서 확인해야 하며, 이 사전에 없다고 마약류가 아니라고 "
            "단정할 수 없습니다(임시마약류 지정·개정 반영 시차)."
        ),
        "tables": tables,
        "counts": counts,
        "substances": substances,
        "precursors": precursors,
    }


def _revision_date(title: str) -> str:
    match = re.search(r"(?:개정|신설)\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", title or "")
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="마약류 시행령 별표 성분 목록 생성(법제처 API)")
    parser.add_argument("--out", help="저장 경로(기본 src/drug_schedules.json)")
    args = parser.parse_args(argv)

    client = from_environment()
    if client is None or not client.has_law:
        print("LAW_GO_KR_OC 없음(.env). 별표를 받으려면 법제처 OC가 필요합니다.")
        return 2
    try:
        payload = build(client)
    except (LiveApiError, json.JSONDecodeError) as exc:
        print(f"FAILED {redact(str(exc))}")
        return 1

    out = args.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "drug_schedules.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(f"OK schedule_version={payload['schedule_version']} generated_on={payload['generated_on']}")
    for table in payload["tables"]:
        print(f"  {table['table']:8} {table['class_ko']:22} {table['row_count']:4}건 "
              f"(개정 {table['revised_on'] or '-'})")
    print(f"  합계: 마약류 {len(payload['substances'])}건 + 원료물질 {len(payload['precursors'])}건")
    print(f"저장: {os.path.abspath(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
