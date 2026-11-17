"""실API 4종 라이브 검증 스크립트.

키는 `.env`(또는 환경변수)에서만 읽고, 출력·산출물에는 키를 남기지 않는다.

    cd src
    python3 tools/verify_live_apis.py                       # 기본 4종 전부
    python3 tools/verify_live_apis.py --hs 3307903000 --law-query 관세법
    python3 tools/verify_live_apis.py --encoding-check       # 인코딩/디코딩 키 동작 비교
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from import_compliance import live_api  # noqa: E402
from import_compliance.live_api import (  # noqa: E402
    LiveApiClient,
    LiveApiError,
    LiveFetch,
    normalize_customs_item,
    normalize_law_article,
    normalize_law_item,
    normalize_mfds_permit_item,
    normalize_mfds_product_item,
)

KST = timezone(timedelta(hours=9))


def mask(secret: str) -> str:
    if not secret:
        return "(없음)"
    if len(secret) <= 8:
        return "*" * len(secret) + f" (len={len(secret)})"
    return f"{secret[:4]}…{secret[-4:]} (len={len(secret)})"


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def show_fetch(label: str, fetch: LiveFetch) -> None:
    print(f"[{label}] state={fetch.state} http={fetch.http_status} code={fetch.result_code} "
          f"items={len(fetch.items)} total={fetch.total_count} "
          f"{fetch.elapsed_ms}ms attempts={fetch.attempts}")
    if fetch.result_msg:
        print(f"  resultMsg: {fetch.result_msg}")
    if fetch.request_echo:
        print(f"  요청: {fetch.request_echo}")


def run(env: Dict[str, str], args: argparse.Namespace) -> Dict[str, Any]:
    key = env.get("DATA_GO_KR_SERVICE_KEY", "")
    oc = env.get("LAW_GO_KR_OC", "")
    client = LiveApiClient(service_key=key, law_oc=oc, retry_sleep=args.retry_sleep)
    report: Dict[str, Any] = {
        "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
        "keys": {
            "DATA_GO_KR_SERVICE_KEY": mask(key),
            "LAW_GO_KR_OC": mask(oc),
        },
        "capabilities": client.capabilities(),
        "endpoints": {},
    }

    # 1) 관세청 세관장확인대상물품
    section("1) 관세청 세관장확인대상물품 (data.go.kr 15101589)")
    try:
        fetch = client.customs_checkpoint(args.hs, args.direction)
        show_fetch("customs", fetch)
        normalized = [normalize_customs_item(item) for item in fetch.items]
        for row in normalized[:5]:
            print("  ·", json.dumps(row, ensure_ascii=False))
        report["endpoints"]["customs_checkpoint"] = {
            "status": fetch.status(), "request": fetch.request_echo, "samples": normalized[:5],
        }
        if not normalized:
            print("  → 0건: '요건 없음'이 아니라 '이 HS·방향으로 조회되지 않음'이다.")
    except LiveApiError as exc:
        print(f"  ERROR code={exc.code} http={exc.http_status} retryable={exc.retryable}: {exc.message}")
        report["endpoints"]["customs_checkpoint"] = {
            "status": {"source_id": exc.source_id, "state": "error", "result_code": exc.code,
                       "http_status": exc.http_status, "error": exc.message},
        }

    # 2) 식약처 수입식품 허가정보
    section("2) 식약처 수입식품 허가정보 (data.go.kr 15058273)")
    try:
        fetch = client.mfds_import_permit(product_name=args.product or None, rows=3)
        show_fetch("mfds_permit", fetch)
        normalized = [normalize_mfds_permit_item(item) for item in fetch.items]
        for row in normalized[:3]:
            print("  ·", json.dumps(row, ensure_ascii=False))
        report["endpoints"]["mfds_import_permit"] = {
            "status": fetch.status(), "request": fetch.request_echo, "samples": normalized[:3],
        }
    except LiveApiError as exc:
        print(f"  ERROR code={exc.code} http={exc.http_status} retryable={exc.retryable}: {exc.message}")
        report["endpoints"]["mfds_import_permit"] = {
            "status": {"source_id": exc.source_id, "state": "error", "result_code": exc.code,
                       "http_status": exc.http_status, "error": exc.message},
        }

    # 3) 식약처 수입식품 제품DB
    section("3) 식약처 수입식품 제품DB 정보 (data.go.kr 15073949)")
    try:
        fetch = client.mfds_product_db(product_name=args.product_db or None, rows=3)
        show_fetch("mfds_product_db", fetch)
        normalized = [normalize_mfds_product_item(item) for item in fetch.items]
        for row in normalized[:3]:
            print("  ·", json.dumps(row, ensure_ascii=False))
        report["endpoints"]["mfds_product_db"] = {
            "status": fetch.status(), "request": fetch.request_echo, "samples": normalized[:3],
        }
    except LiveApiError as exc:
        print(f"  ERROR code={exc.code} http={exc.http_status} retryable={exc.retryable}: {exc.message}")
        report["endpoints"]["mfds_product_db"] = {
            "status": {"source_id": exc.source_id, "state": "error", "result_code": exc.code,
                       "http_status": exc.http_status, "error": exc.message},
        }

    # 4) 법제처 국가법령정보
    section(f"4) 법제처 국가법령정보 공동활용 lawSearch (query={args.law_query})")
    try:
        fetch = client.law_search(args.law_query, display=3)
        show_fetch("law_search", fetch)
        normalized = [normalize_law_item(item) for item in fetch.items]
        for row in normalized[:3]:
            print("  ·", json.dumps(row, ensure_ascii=False))
        report["endpoints"]["law_search"] = {
            "status": fetch.status(), "request": fetch.request_echo, "samples": normalized[:3],
        }
        if normalized:
            mst = normalized[0]["mst"]
            section(f"4b) 법령 본문 조문 조회 (MST={mst}, {args.law_article}조)")
            body = client.law_articles(mst, article=args.law_article)
            show_fetch("law_articles", body)
            articles = [normalize_law_article(unit) for unit in body.items]
            for row in articles[:3]:
                text = row["text"][:180] + ("…" if len(row["text"]) > 180 else "")
                print(f"  · {row['article']} {row['title']} (시행 {row['effective_from']})")
                print(f"    {text}")
                for paragraph in row["paragraphs"][:2]:
                    print(f"    - {paragraph[:200]}")
            report["endpoints"]["law_articles"] = {
                "status": body.status(), "request": body.request_echo,
                "samples": [{"article": a["article"], "title": a["title"],
                             "effective_from": a["effective_from"],
                             "text_excerpt": a["text"][:200],
                             "paragraphs": [p[:300] for p in a["paragraphs"][:3]]}
                            for a in articles[:3]],
            }
    except LiveApiError as exc:
        print(f"  ERROR code={exc.code} http={exc.http_status} retryable={exc.retryable}: {exc.message}")
        report["endpoints"]["law_search"] = {
            "status": {"source_id": exc.source_id, "state": "error", "result_code": exc.code,
                       "http_status": exc.http_status, "error": exc.message},
        }

    if args.encoding_check:
        section("5) 인코딩/디코딩 키 처리 확인")
        plain = LiveApiClient(service_key=key, law_oc=oc)
        encoded_key = urllib.parse.quote(key, safe="")
        encoded = LiveApiClient(service_key=encoded_key, law_oc=oc)
        results = {}
        for label, candidate in (("raw", plain), ("urlencoded", encoded)):
            try:
                fetch = candidate.customs_checkpoint(args.hs, args.direction,
                                                     retry_on_unregistered=False)
                results[label] = {"state": fetch.state, "result_code": fetch.result_code,
                                  "items": len(fetch.items),
                                  "same_key_when_hex": encoded_key == key}
                print(f"  {label}: state={fetch.state} code={fetch.result_code} items={len(fetch.items)}")
            except LiveApiError as exc:
                results[label] = {"state": "error", "result_code": exc.code, "error": exc.message}
                print(f"  {label}: ERROR {exc.code} {exc.message}")
        print(f"  키가 영숫자만으로 이루어져 인코딩 결과 동일: {encoded_key == key}")
        report["encoding_check"] = results

    report["call_log"] = client.call_log
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="공공 API 4종 라이브 검증")
    parser.add_argument("--env", help=".env 경로(기본: 프로젝트 루트 .env)")
    parser.add_argument("--hs", default="3307903000", help="HS 10자리 (기본 3307903000)")
    parser.add_argument("--direction", default="import", choices=["import", "export"])
    parser.add_argument("--product", default="", help="수입식품 허가정보 제품명 필터")
    parser.add_argument("--product-db", dest="product_db", default="", help="제품DB 제품명 필터")
    parser.add_argument("--law-query", dest="law_query", default="관세법")
    parser.add_argument("--law-article", dest="law_article", default="226")
    parser.add_argument("--retry-sleep", dest="retry_sleep", type=float,
                        default=live_api.UNREGISTERED_RETRY_SLEEP)
    parser.add_argument("--encoding-check", action="store_true")
    parser.add_argument("--out", help="검증 결과 JSON 저장 경로(키 없음)")
    args = parser.parse_args(argv)

    env = live_api.load_env(args.env)
    if not env.get("DATA_GO_KR_SERVICE_KEY") and not env.get("LAW_GO_KR_OC"):
        print("FAIL: .env 또는 환경변수에 DATA_GO_KR_SERVICE_KEY / LAW_GO_KR_OC 가 없습니다.")
        return 2

    print("키 로드 확인:", {k: mask(v) for k, v in env.items() if k.endswith("KEY") or k.endswith("OC")})
    report = run(env, args)

    failed = [name for name, block in report["endpoints"].items()
              if block.get("status", {}).get("state") != "live"]
    print("\n" + "-" * 78)
    print(f"결과: {len(report['endpoints']) - len(failed)}/{len(report['endpoints'])} 라이브 성공"
          + (f" · 실패: {failed}" if failed else ""))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f"결과 저장: {args.out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
