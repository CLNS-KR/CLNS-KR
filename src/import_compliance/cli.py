"""CLI: 수동 확인 및 코퍼스 자기검증."""
from __future__ import annotations

import argparse
import json
import sys

from .api import call_tool, mcp_manifest
from .corpus import load_corpus
from .engine import assess
from .live_api import from_environment, register_sources
from .policy import find_conclusive_phrasing
from .store import Store


def run_corpus_checks() -> int:
    corpus = load_corpus()
    problems = []
    if len(corpus.traps) != 20:
        problems.append(f"trap count is {len(corpus.traps)}, expected 20")
    for trap in corpus.traps:
        if trap.default_verdict not in ("check_likely", "info_needed", "low_risk"):
            problems.append(f"{trap.id}: bad verdict {trap.default_verdict}")
        if not trap.legal_basis:
            problems.append(f"{trap.id}: no legal basis")
        for basis in trap.legal_basis:
            if not basis.url.startswith("http"):
                problems.append(f"{trap.id}: bad url {basis.url}")
            if not basis.effective_date:
                problems.append(f"{trap.id}: missing effective_date")
        if not trap.signals:
            problems.append(f"{trap.id}: no signals")
        hits = find_conclusive_phrasing(trap.correct_answer)
        if hits:
            problems.append(f"{trap.id}: conclusive phrasing in correct_answer {hits}")
    if problems:
        print("FAILED")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK corpus_version={corpus.version} cases={len(corpus.traps)} verified_on={corpus.verified_on}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="import-compliance engine")
    parser.add_argument("query", nargs="*", help="자연어 질의")
    parser.add_argument("--trap", help="함정 케이스 해설 (예: TRAP-06)")
    parser.add_argument("--mcp", action="store_true", help="MCP 툴 매니페스트 출력")
    parser.add_argument("--check-corpus", action="store_true", help="코퍼스 무결성 점검")
    parser.add_argument("--full", action="store_true", help="전체 JSON 출력")
    parser.add_argument("--live", action="store_true",
                        help="실API 호출 모드(.env 키 사용). 없으면 코퍼스·캐시만")
    parser.add_argument("--hs", help="--live 와 함께 쓰면 HS 10자리 세관장확인 실조회")
    parser.add_argument("--db", help="SQLite 저장소 경로(기본 :memory:, --serve 시 data/recalls.sqlite)")
    parser.add_argument("--serve", action="store_true",
                        help="HTTP 서버(사람용 웹 UI + JSON API) 기동. 배포는 python -m import_compliance.server 권장")
    parser.add_argument("--host", help="--serve 바인드 주소(기본 0.0.0.0, 환경변수 HOST)")
    parser.add_argument("--port", type=int, help="--serve 포트(환경변수 PORT 우선)")
    parser.add_argument("--fetch-recalls", nargs="?", const="", metavar="RAW_DIR",
                        help="국표원 리콜 파일데이터 2종을 내려받아 로컬 인덱스(recall_items/recall_stats) 적재")
    parser.add_argument("--recall", metavar="QUERY", help="로컬 리콜 인덱스 검색(브랜드·모델·제품명)")
    parser.add_argument("--recall-stats", action="store_true", help="연도·품목군별 리콜처분현황 집계 출력")
    args = parser.parse_args(argv)

    if args.check_corpus:
        return run_corpus_checks()
    if args.mcp:
        print(json.dumps(mcp_manifest(), ensure_ascii=False, indent=2))
        return 0
    if args.serve:
        from .server import config_from_env, serve

        cfg = config_from_env()
        live_client = None
        if args.live or cfg["live_mode"]:
            live_client = from_environment()
            if live_client is None:
                print("경고: 실API 모드지만 키가 없습니다. 코퍼스 근거로만 동작합니다.")
            else:
                print(f"실API 모드: {live_client.capabilities()}")
        serve(host=args.host or cfg["host"],
              port=args.port if args.port is not None else cfg["port"],
              db_path=args.db or cfg["db_path"],
              live=live_client)
        return 0

    if args.fetch_recalls is not None:
        from . import recall_index

        out = recall_index.build_index(args.db or recall_index.default_index_path(),
                                       args.fetch_recalls or recall_index.default_raw_dir())
        pretty_print(out)
        return 0

    store = Store(args.db or ":memory:")
    live = None
    if args.live:
        live = from_environment()
        if live is None:
            print("실API 키가 없습니다(.env의 DATA_GO_KR_SERVICE_KEY / LAW_GO_KR_OC).")
        else:
            register_sources(store)
            print(f"실API 모드: {live.capabilities()}")
    if args.trap:
        out = call_tool("explain_trap", {"case_id": args.trap}, store, live=live)
        pretty_print(out)
        return 0 if out.get("ok") else 1
    if args.recall_stats:
        from . import recall_index

        pretty_print({"summary": recall_index.summary(store), "stats": recall_index.stats_table(store)})
        return 0
    if args.recall:
        out = call_tool("lookup_recall", {"brand": args.recall}, store, live=live)
        pretty_print(out)
        return 0 if out.get("ok") else 1
    if args.hs:
        out = call_tool("lookup_hs_requirements", {"hs_code": args.hs}, store, live=live)
        pretty_print(out)
        return 0 if out.get("ok") else 1

    query = " ".join(args.query).strip()
    if not query:
        parser.print_help()
        return 2
    result = assess(query, store=store, limit=3, live=live)
    pretty_print(result if args.full else summarize(result))
    return 0


def summarize(result):
    return {
        "verdict": result["verdict"],
        "headline": result["answer"]["headline"],
        "findings": [
            {"case_id": f["case_id"], "title": f["title"], "verdict": f["verdict"], "confidence": f["confidence"]}
            for f in result["findings"]
        ],
        "missing_inputs": [m["field"] for f in result["findings"] for m in f["missing_inputs"]],
        "evidence": [f'{e["law"]} {e["article"]} (시행 {e["effective_date"]})' for e in result["evidence"]],
        "disclaimer_ko": result["disclaimer"]["ko"],
    }


def pretty_print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
