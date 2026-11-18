"""pSEO 카탈로그의 HS 세관장확인 요건 표만 관세청 API 로 다시 채운다.

문안(요약·확인 항목·함정 연결)은 손으로 관리하고, 변동이 잦은 HS 요건 표만
실조회 결과로 갱신한다. 키가 없으면 아무것도 쓰지 않고 종료한다.

사용:
    cd src
    python3 tools/refresh_pseo_hs.py            # 전체 품목
    python3 tools/refresh_pseo_hs.py --only usb-mini-fan power-bank
    python3 tools/refresh_pseo_hs.py --dry-run  # 결과만 출력

동작 원칙
- 기관별 중복 응답은 (요건확인서, 근거 법령) 으로 묶고 기관은 배열로 합친다.
- 실패한 품목은 기존 값을 지우지 않는다(부분 실패로 카탈로그를 비우지 않음).
- 조회 시점(`hs_checked_at`)을 항목별로 남겨 페이지가 "언제 확인한 값"인지 밝힌다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from import_compliance.live_api import from_environment, normalize_customs_item  # noqa: E402

CATALOG_PATH = os.path.join(SRC, "pseo_items.json")


def dedupe(rows):
    merged = {}
    for row in rows:
        document = row.get("requirement_document") or ""
        law = row.get("requirement_law") or ""
        entry = merged.setdefault((document, law), {
            "requirement_document": document,
            "requirement_law": law,
            "agencies": [],
            "timing": row.get("timing") or "",
            "applies_from": row.get("applies_from") or "",
        })
        agency = row.get("requirement_agency") or ""
        if agency and agency not in entry["agencies"]:
            entry["agencies"].append(agency)
    return sorted(merged.values(), key=lambda e: (e["requirement_law"],
                                                  e["requirement_document"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools/refresh_pseo_hs.py",
                                     description="pSEO 카탈로그 HS 요건 표 재적재")
    parser.add_argument("--only", nargs="*", default=None, help="특정 slug 만 갱신")
    parser.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    parser.add_argument("--catalog", default=CATALOG_PATH, help="카탈로그 경로")
    args = parser.parse_args(argv)

    if not os.path.exists(args.catalog):
        print(f"카탈로그가 없습니다: {args.catalog}", file=sys.stderr)
        return 2
    with open(args.catalog, encoding="utf-8") as handle:
        catalog = json.load(handle)

    live = from_environment()
    if live is None or not getattr(live, "has_customs", False):
        print("관세청 키(DATA_GO_KR_SERVICE_KEY)가 없어 갱신하지 않습니다.", file=sys.stderr)
        return 1

    targets = set(args.only or [])
    updated, failed, checked_at = 0, [], ""
    for item in catalog.get("items") or []:
        if targets and item.get("slug") not in targets:
            continue
        try:
            fetch = live.customs_checkpoint(str(item["hs_code"]), "import")
            rows = [normalize_customs_item(row) for row in fetch.items]
            checked_at = fetch.fetched_at or checked_at
        except Exception as exc:  # noqa: BLE001 - 품목별 실패를 따로 보고
            failed.append((item.get("slug"), str(getattr(exc, "message", exc))))
            continue
        item["hs_requirements"] = dedupe(rows)
        item["hs_requirement_count"] = len(rows)
        item["hs_checked_at"] = fetch.fetched_at
        updated += 1
        print(f"{item.get('slug'):26s} {item['hs_code']}  rows={len(rows):2d}  "
              f"groups={len(item['hs_requirements'])}")

    if failed:
        for slug, message in failed:
            print(f"실패 {slug}: {message}", file=sys.stderr)
    if args.dry_run:
        print(json.dumps({"updated": updated, "failed": len(failed)},
                         ensure_ascii=False))
        return 0 if not failed else 1
    if updated:
        catalog["hs_checked_at"] = checked_at or catalog.get("hs_checked_at", "")
        with open(args.catalog, "w", encoding="utf-8") as handle:
            json.dump(catalog, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"저장: {args.catalog} (갱신 {updated}건, 실패 {len(failed)}건)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
