"""대표 수입 품목 3건 라이브 실전 테스트 러너.

`projects/import-compliance/.env`의 실API 키로 코퍼스 판정·세관장확인·식약처·법제처·
로컬 리콜 인덱스를 한 번에 호출하고, 키를 제거한 결과 JSON을 만든다.

실행:
    cd src
    python3 tools/run_live_scenarios.py --out ../live-scenario-results-2026-11-18.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from import_compliance import recall_index  # noqa: E402
from import_compliance.api import call_tool  # noqa: E402
from import_compliance.engine import assess  # noqa: E402
from import_compliance.live_api import from_environment, load_env, project_root, register_sources  # noqa: E402
from import_compliance.store import Store  # noqa: E402

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "S1-중국산 USB-C 충전식 리튬배터리 소형가전": {
        "query": "중국산 USB-C 충전식 리튬배터리 내장 무선 미니 선풍기를 수입해 판매하려고 해",
        "facts": {"purpose": "resale", "hs_code": "8507609000", "rf_tx": "no"},
        "hs_codes": ["8507609000", "8414511000", "8414519000"],
        "kc": {"product_name": "USB-C 충전식 무선 미니 선풍기", "battery": "리튬이온 팩 내장",
               "ac_plug": "yes", "rf_tx": "no"},
        "recall": [
            {"brand": "무선 미니 선풍기", "product_name": "선풍기"},
            {"brand": "전지", "category": "전지"},
            {"brand": "직류전원장치", "category": "직류전원장치"},
        ],
        "legal": [("관세법", "226"), ("전기용품 및 생활용품 안전관리법", "별표 3")],
    },
    "S2-미국산 오메가3·비타민D3 건강기능식품": {
        "query": "미국산 오메가3와 비타민D3 건강기능식품을 수입해 판매하려고 해",
        "facts": {"purpose": "resale", "hs_code": "1504200000", "functional": "yes"},
        "hs_codes": ["1504200000", "2106909000", "2936299000"],
        "food": [
            {"product_name": "오메가3", "kind": "health_functional", "purpose": "resale", "functional": "yes"},
            {"product_name": "비타민 D3", "kind": "health_functional", "purpose": "resale", "functional": "yes"},
        ],
        "recall": [{"brand": "오메가3", "product_name": "오메가3"}],
        "legal": [("수입식품안전관리 특별법", "제20조"), ("건강기능식품에 관한 법률", "제16조")],
    },
    "S3-미국산 수딩크림 화장품": {
        "query": "미국산 수딩크림 화장품을 수입해 판매하려고 해",
        "facts": {"purpose": "resale", "hs_code": "3304991000"},
        "hs_codes": ["3304991000", "3307903000"],
        "food": [
            {"product_name": "수딩크림", "kind": "cosmetics", "purpose": "resale"},
            {"product_name": "크림", "kind": "cosmetics", "purpose": "resale"},
        ],
        "recall": [{"brand": "수딩크림", "product_name": "수딩크림"}],
        "legal": [("화장품법", "제3조")],
    },
}


def timed(fn: Callable[[], Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        value = fn()
        error = None
    except Exception as exc:  # 실패도 결과로 남긴다
        value = None
        error = {"type": type(exc).__name__, "message": str(exc)[:400]}
    elapsed = round((time.perf_counter() - started) * 1000)
    return {"elapsed_ms": elapsed, "value": value, "error": error}


def run_scenario(name: str, spec: Dict[str, Any], store: Store, live: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"name": name, "query": spec["query"], "facts": spec["facts"], "calls": {}}
    out["calls"]["assess"] = timed(lambda: call_tool(
        "assess_import_case", {"query": spec["query"], "facts": spec["facts"], "limit": 3}, store, live=live))
    out["calls"]["hs"] = {
        hs: timed(lambda hs=hs: call_tool("lookup_hs_requirements", {"hs_code": hs, "direction": "import"},
                                          store, live=live))
        for hs in spec.get("hs_codes", [])
    }
    if spec.get("kc"):
        out["calls"]["kc"] = timed(lambda: call_tool("check_kc_certification", spec["kc"], store, live=live))
    out["calls"]["food_cosmetics"] = [
        timed(lambda args=args: call_tool("check_food_cosmetics", args, store, live=live))
        for args in spec.get("food", [])
    ]
    out["calls"]["recall"] = [
        timed(lambda args=args: call_tool("lookup_recall", dict(args, limit=5), store, live=live))
        for args in spec.get("recall", [])
    ]
    out["calls"]["legal"] = {
        f"{law} {article}": timed(lambda law=law, article=article: call_tool(
            "get_legal_basis", {"law": law, "article": article}, store, live=live))
        for law, article in spec.get("legal", [])
    }
    out["calls"]["assess_live_probe"] = timed(lambda: assess(
        spec["query"], spec["facts"], store=store, limit=3, live=live))
    return out


def scrub(payload: Any, secrets) -> Any:
    text = json.dumps(payload, ensure_ascii=False)
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "***")
    return json.loads(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(project_root(), "live-scenario-results-2026-11-18.json"))
    parser.add_argument("--db", default=recall_index.default_index_path())
    args = parser.parse_args(argv)

    env = load_env()
    secrets = [env.get("DATA_GO_KR_SERVICE_KEY", ""), env.get("LAW_GO_KR_OC", "")]
    live = from_environment()
    if live is None:
        print("실API 키가 없습니다.")
        return 2
    store = Store(args.db)  # 리콜 인덱스가 적재된 DB를 그대로 쓴다
    register_sources(store)
    report: Dict[str, Any] = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "capabilities": live.capabilities(),
        "recall_index": recall_index.summary(store),
        "scenarios": {},
    }
    errors: Dict[str, int] = {}
    for name, spec in SCENARIOS.items():
        result = run_scenario(name, spec, store, live)
        report["scenarios"][name] = result
        errs = [k for k, v in result["calls"].items() if isinstance(v, dict) and v.get("error")]
        if errs:
            errors[name] = len(errs)
    report["errors"] = errors
    clean = scrub(report, secrets)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(clean, handle, ensure_ascii=False, indent=2)
    store.close()
    print(f"wrote {args.out} ({os.path.getsize(args.out)} bytes); errors={errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
