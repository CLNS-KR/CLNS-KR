"""CLI: 수동 확인 및 코퍼스 자기검증."""
from __future__ import annotations

import argparse
import json
import sys

from .api import call_tool, mcp_manifest
from .corpus import load_corpus
from .standards import CASE_REGULATION_TAGS, REGULATION_TAGS
from .engine import assess
from .live_api import from_environment, register_sources
from .policy import find_conclusive_phrasing
from .store import Store


# 코퍼스 기대 케이스(번호가 비면 카드 누락이다). 0.5.0 에서 TRAP-25(반려동물 사료) 추가.
EXPECTED_CASE_IDS = tuple(f"TRAP-{index:02d}" for index in range(1, 26))


def run_corpus_checks() -> int:
    corpus = load_corpus()
    problems = []
    if len(corpus.traps) != len(EXPECTED_CASE_IDS):
        problems.append(f"trap count is {len(corpus.traps)}, expected {len(EXPECTED_CASE_IDS)}")
    missing_ids = [case_id for case_id in EXPECTED_CASE_IDS
                   if corpus.by_id(case_id) is None]
    if missing_ids:
        problems.append("missing cases: " + ", ".join(missing_ids))
    extra_ids = [trap.id for trap in corpus.traps if trap.id not in EXPECTED_CASE_IDS]
    if extra_ids:
        problems.append("unexpected cases: " + ", ".join(extra_ids))
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


def run_testset_checks() -> int:
    """대표 100개 테스트셋 자기검증: 구조 + 분야별 정확도 + 중대 규제 누락(FN).

    CI 에서 엔진 회귀를 한 줄로 확인하기 위한 경로다(엔진 전체를 실제로 돌린다).
    """
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "testset_100.json")
    problems = []
    try:
        with open(path, encoding="utf-8") as handle:
            testset = json.load(handle)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"FAILED testset not readable: {exc}")
        return 1
    cases = testset.get("cases") or []
    if len(cases) != 100:
        problems.append(f"case count is {len(cases)}, expected 100")
    corpus_ids = {trap.id for trap in load_corpus().traps}
    per_domain = {}
    total_fn = 0
    mismatched = 0
    store = Store(":memory:")
    try:
        for case in cases:
            domain = case.get("domain", "?")
            bucket = per_domain.setdefault(domain, {"cases": 0, "verdict_ok": 0, "fn": 0})
            bucket["cases"] += 1
            if not case.get("required_findings"):
                problems.append(f"{case.get('case_id')}: no required_findings")
            if case.get("primary_case_id") not in corpus_ids:
                problems.append(f"{case.get('case_id')}: unknown primary_case_id")
            for tag in case.get("required_findings") or []:
                if tag not in REGULATION_TAGS:
                    problems.append(f"{case.get('case_id')}: unknown tag {tag}")
            result = assess(case["query"], case.get("facts") or {}, store=store, limit=3)
            tags = set()
            for finding in result["findings"]:
                tags.update(finding.get("regulation_tags") or [])
            if result["verdict"]["code"] == case.get("expected_verdict"):
                bucket["verdict_ok"] += 1
            else:
                mismatched += 1
            missing = set(case.get("required_findings") or []) - tags
            if missing:
                bucket["fn"] += 1
                total_fn += 1
                problems.append(f"{case.get('case_id')}: missing findings {sorted(missing)}")
    finally:
        store.close()
    for domain, bucket in sorted(per_domain.items()):
        accuracy = bucket["verdict_ok"] / bucket["cases"] if bucket["cases"] else 0
        print(f"  {domain}: {bucket['verdict_ok']}/{bucket['cases']} "
              f"({accuracy:.0%}), FN={bucket['fn']}")
    if problems:
        print("FAILED")
        for problem in problems:
            print(" -", problem)
        return 1
    print(f"OK testset_version={testset.get('testset_version')} cases={len(cases)} "
          f"false_negatives={total_fn} verdict_mismatch={mismatched}")
    return 0


def run_drug_testset_checks() -> int:
    """의약품·영양제 반입 테스트셋(별도 관리) 점검: 판정 일치·필수 태그·금지 태그."""
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "drug_testset.json")
    problems = []
    try:
        with open(path, encoding="utf-8") as handle:
            testset = json.load(handle)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"FAILED drug testset not readable: {exc}")
        return 1
    cases = testset.get("cases") or []
    if len(cases) != testset.get("case_count"):
        problems.append(f"case count mismatch: {len(cases)} != {testset.get('case_count')}")
    corpus_ids = {trap.id for trap in load_corpus().traps}
    store = Store(":memory:")
    matched = 0
    try:
        for case in cases:
            if case.get("primary_case_id") not in corpus_ids:
                problems.append(f"{case.get('case_id')}: unknown primary_case_id")
            for tag in case.get("required_findings") or []:
                if tag not in REGULATION_TAGS:
                    problems.append(f"{case.get('case_id')}: unknown tag {tag}")
            result = assess(case["query"], case.get("facts") or {}, store=store, limit=3)
            tags = set()
            for finding in result["findings"]:
                tags.update(finding.get("regulation_tags") or [])
            if result["verdict"]["code"] == case.get("expected_verdict"):
                matched += 1
            else:
                problems.append(f"{case.get('case_id')}: verdict {result['verdict']['code']} "
                                f"!= {case.get('expected_verdict')}")
            missing = set(case.get("required_findings") or []) - tags
            if missing:
                problems.append(f"{case.get('case_id')}: missing findings {sorted(missing)}")
            forbidden = set(case.get("must_not_find") or []) & tags
            if forbidden:
                problems.append(f"{case.get('case_id')}: forbidden findings {sorted(forbidden)}")
    finally:
        store.close()
    if problems:
        print("FAILED")
        for problem in problems:
            print(" -", problem)
        return 1
    print(f"OK drug_testset_version={testset.get('testset_version')} cases={len(cases)} "
          f"verdict_match={matched}/{len(cases)} forbidden=0")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="import-compliance engine")
    parser.add_argument("query", nargs="*", help="자연어 질의")
    parser.add_argument("--trap", help="함정 케이스 해설 (예: TRAP-06)")
    parser.add_argument("--mcp", action="store_true", help="MCP 툴 매니페스트 출력")
    parser.add_argument("--check-corpus", action="store_true", help="코퍼스 무결성 점검")
    parser.add_argument("--check-testset", action="store_true",
                        help="대표 100개 테스트셋 점검(분야별 정확도·규제 누락 FN)")
    parser.add_argument("--check-drugs", action="store_true",
                        help="의약품·영양제 반입 테스트셋 점검(금지성분·자가사용 기준)")
    parser.add_argument("--drug", metavar="성분·제품명",
                        help="의약품 성분 스크리닝(예: --drug 졸피뎀 --channel online --quantity 30)")
    parser.add_argument("--channel", choices=["carry", "online", "unknown"],
                        help="--drug 의 반입 경로(휴대/직구)")
    parser.add_argument("--quantity", type=int, help="--drug 의 수량(6병 기준 대조)")
    parser.add_argument("--drug-schedules", action="store_true",
                        help="마약류·원료물질 성분 사전 상태 출력")
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
    if args.check_testset:
        return run_testset_checks()
    if args.check_drugs:
        return run_drug_testset_checks()
    if args.drug_schedules:
        from . import drugs

        data = drugs.load_schedules()
        pretty_print({
            "schedule_version": data.get("schedule_version"),
            "generated_on": data.get("generated_on"),
            "decree": data.get("decree"),
            "decree_promulgated_on": data.get("decree_promulgated_on"),
            "counts": data.get("counts"),
            "tables": data.get("tables"),
            "attribution_ko": data.get("attribution_ko"),
            "api_candidates": [{"dataset_id": row["dataset_id"], "name_ko": row["name_ko"],
                                "state": row["state"], "apply_url": row["apply_url"]}
                               for row in drugs.API_CANDIDATES],
        })
        return 0
    if args.drug:
        store = Store(args.db or ":memory:")
        payload = {"product_name": args.drug}
        if args.channel:
            payload["channel"] = args.channel
        if args.quantity:
            payload["quantity"] = args.quantity
        out = call_tool("check_drug_import", payload, store,
                        live=from_environment(keyless_rra=True) if args.live else None)
        pretty_print(out)
        return 0 if out.get("ok") else 1
    if args.mcp:
        print(json.dumps(mcp_manifest(), ensure_ascii=False, indent=2))
        return 0
    if args.serve:
        from .server import config_from_env, serve

        cfg = config_from_env()
        live_client = None
        if args.live or cfg["live_mode"]:
            live_client = from_environment(keyless_rra=True)
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
        live = from_environment(keyless_rra=True)
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
