#!/usr/bin/env python3
"""법제처 국가법령정보 OPEN API로 '지금 시행 중인' 조문만 골라 검증한다.

왜 이 도구가 필요한가
---------------------
`lawSearch`/`lawService`(target=law)는 **가장 최근에 공포된 법령**을 돌려준다.
그 법령이 아직 시행 전이면(예: 공포 후 1년 뒤 시행) 조문 본문은 미래 시행일
개정문이고, 조문별 `조문시행일자`도 미래 날짜로 온다. 이걸 그대로 인용하면
"아직 시행되지 않은 조문"을 현행 근거로 쓰는 오류가 난다.

그래서 버전을 최신순으로 내려가며 **해당 조문의 조문시행일자가 오늘 이하이고
본문이 있는 첫 버전**을 채택한다. 미래 시행 버전은 `skipped_future_versions`에
남겨 근거를 투명하게 보인다.

사용
----
    cd src
    python3 tools/verify_law_articles.py \
        --target '의료기기법:2,3,6,15,17,19,20' \
        --target '위생용품 관리법:2,3,8,10,11,12' \
        --out ../medical-hygiene-law-verification.json

키는 `.env`(LAW_GO_KR_OC)에서만 읽고, 출력에는 키를 남기지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from import_compliance.live_api import (  # noqa: E402
    LAW_SEARCH_URL,
    LiveApiError,
    _clean,
    from_environment,
    normalize_law_article,
    redact,
)

KST = timezone(timedelta(hours=9))
LAW_URL = "https://www.law.go.kr/법령/"


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _flatten_text(node, out: list) -> None:
    """조문단위의 항·호·목 본문을 순서대로 평탄화한다(정의 조문은 호·목에만 본문이 있다)."""
    if isinstance(node, str):
        text = " ".join(node.split())
        if text:
            out.append(text)
        return
    if isinstance(node, list):
        for item in node:
            _flatten_text(item, out)
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("조문번호", "조문가지번호", "조문여부", "조문시행일자", "조문키",
                       "조문변경여부", "조문이동이전", "조문이동이후", "조문제목"):
                continue
            if isinstance(value, str) and "내용" not in key:
                continue
            _flatten_text(value, out)


def _full_text(unit: dict) -> str:
    out: list = []
    _flatten_text(unit, out)
    return " ".join(out)


def _digits(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:8]


def list_versions(client, law_name: str) -> list:
    """시행일 기준 법령 버전 목록(시행예정 포함)을 최신 시행일 순으로 돌려준다."""
    url = client._url(LAW_SEARCH_URL, {"OC": client._law_oc, "target": "eflaw", "type": "JSON",
                                       "query": law_name, "display": 40, "page": 1})
    _, body, _ = client._transport(url, 25)
    payload = json.loads(body)
    rows = (payload.get("LawSearch") or {}).get("law") or []
    out = {}
    for row in rows:
        name = _clean(row.get("법령명한글"))
        if name.replace(" ", "") != law_name.replace(" ", ""):
            continue  # 시행령·시행규칙·타법 제외
        mst = _clean(row.get("법령일련번호"))
        if not mst:
            continue
        key = (mst, _digits(row.get("시행일자")))
        out.setdefault(key, {
            "mst": mst,
            "name": name,
            "law_type": _clean(row.get("법령구분명")),
            "promulgated_on": _digits(row.get("공포일자")),
            "effective_from": _digits(row.get("시행일자")),
            "status": _clean(row.get("현행연혁코드")),
            "promulgation_no": _clean(row.get("공포번호")),
        })
    return sorted(out.values(), key=lambda r: (r["effective_from"], r["mst"]), reverse=True)


def resolve_articles(client, law_name: str, articles: list, today: str) -> dict:
    """오늘 시행 중인 조문 본문을 버전 최신순으로 확정한다."""
    versions = list_versions(client, law_name)
    result = {"law": law_name, "checked_on": today, "articles": [], "skipped_future_versions": [],
              "versions_seen": versions}
    pending = [str(a).strip().lstrip("제").replace("조", "") for a in articles]
    fetched = {}
    for version in versions:
        if not pending:
            break
        if version["effective_from"] > today.replace("-", "") and version["status"] != "현행":
            continue
        mst = version["mst"]
        if mst not in fetched:
            try:
                body = client.law_articles(mst)
            except LiveApiError as exc:
                fetched[mst] = exc
                continue
            fetched[mst] = {(_clean(u.get("조문번호")) + ("의" + _clean(u.get("조문가지번호"))
                            if _clean(u.get("조문가지번호")) not in ("", "0") else "")): u
                            for u in body.items if _clean(u.get("조문여부")) == "조문"}
            basic = (body.raw.get("법령") or {}).get("기본정보") or {}
            version.update({
                "law_id": _clean(basic.get("법령ID")),
                "promulgated_on": _digits(basic.get("공포일자")) or version["promulgated_on"],
                "effective_from": _digits(basic.get("시행일자")) or version["effective_from"],
                "promulgation_no": _clean(basic.get("공포번호")) or version["promulgation_no"],
                "article_effective_map": _clean(basic.get("조문시행일자문자열")),
            })
        units = fetched.get(mst)
        if isinstance(units, Exception) or units is None:
            continue
        still = []
        for number in pending:
            unit = units.get(number)
            if unit is None:
                still.append(number)
                continue
            article = normalize_law_article(unit)
            effective = article["effective_from"] or ""
            if effective and effective > today:
                # 이 버전에서는 아직 시행 전인 조문 → 더 이전 버전에서 찾는다
                result["skipped_future_versions"].append({
                    "law": law_name, "article": article["article"], "mst": mst,
                    "effective_from": effective,
                    "note_ko": "이 버전의 해당 조문은 시행일이 미래여서 채택하지 않았습니다.",
                })
                still.append(number)
                continue
            result["articles"].append({
                "law": law_name,
                "article": article["article"],
                "title": article["title"],
                "effective_from": effective or f"{version['effective_from'][:4]}-{version['effective_from'][4:6]}-{version['effective_from'][6:]}",
                "text": article["text"],
                "paragraphs": article["paragraphs"],
                "text_full": _full_text(unit),
                "mst": mst,
                "promulgation_no": version.get("promulgation_no", ""),
                "promulgated_on": version.get("promulgated_on", ""),
                "status": version.get("status", ""),
                "url": LAW_URL + law_name,
                "source": "법제처 국가법령정보센터",
            })
        pending = still
    result["unresolved"] = pending
    result["articles"].sort(key=lambda row: _article_sort_key(row["article"]))
    return result


def _article_sort_key(label: str):
    text = str(label).lstrip("제").replace("조", "")
    main, _, branch = text.partition("의")
    try:
        return (int(main), int(branch or 0))
    except ValueError:
        return (9999, 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="현행 시행 중 조문 검증(법제처 OPEN API)")
    parser.add_argument("--target", action="append", required=True, metavar="법령명:조문,조문",
                        help="예: --target '의료기기법:2,3,6,15' (여러 번 지정 가능)")
    parser.add_argument("--out", help="결과 JSON 저장 경로")
    args = parser.parse_args(argv)
    targets = []
    for raw in args.target:
        law, _, numbers = raw.partition(":")
        if not law.strip() or not numbers.strip():
            parser.error(f"--target 형식 오류: {raw!r} (법령명:조문,조문)")
        targets.append((law.strip(), [n for n in numbers.replace(" ", "").split(",") if n]))

    client = from_environment()
    if client is None or not client.has_law:
        print("LAW_GO_KR_OC 없음(.env). 검증하려면 키가 필요합니다.")
        return 2
    today = today_kst()
    payload = {"checked_on": today, "source": "법제처 국가법령정보 공동활용 OPEN API",
               "rule_ko": "조문시행일자가 오늘 이하인 최신 버전의 조문 본문만 채택", "laws": []}
    ok = True
    for law, articles in targets:
        try:
            block = resolve_articles(client, law, articles, today)
        except (LiveApiError, json.JSONDecodeError) as exc:
            print(f"FAILED {law}: {redact(str(exc))}")
            ok = False
            continue
        payload["laws"].append(block)
        if block["unresolved"]:
            ok = False
        print(f"== {law} (오늘 {today})")
        for row in block["articles"]:
            print(f"   {row['article']} {row['title']} | 시행 {row['effective_from']} "
                  f"| MST {row['mst']} | 공포 {row['promulgated_on']}")
        for skip in block["skipped_future_versions"]:
            print(f"   (제외) {skip['article']} 시행 {skip['effective_from']} — 미래 시행")
        if block["unresolved"]:
            print(f"   (미확인) {block['unresolved']}")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"저장: {os.path.abspath(args.out)}")
    else:
        print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
