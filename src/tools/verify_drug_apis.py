#!/usr/bin/env python3
"""식약처 의약품 계열 data.go.kr API 활용승인 상태를 실호출로 확인한다.

무엇을 확인하는가
-----------------
`.env`의 서비스키로 후보 엔드포인트를 실제 호출해 **이 계정이 그 데이터셋을 쓸 수 있는지**를
판정한다. 게이트웨이 오류코드는 다음을 뜻한다.

- `00`/정상 → 활용승인 있음(호출 성공)
- `20` SERVICE_ACCESS_DENIED_ERROR → 서비스 접근 거부(활용신청 미승인)
- `30` SERVICE_KEY_IS_NOT_REGISTERED_ERROR → 이 서비스에 등록되지 않은 키(활용신청 없음)
- `12` NO_OPENAPI_SERVICE_ERROR → 경로 오류·폐기

출력에는 키를 남기지 않는다(`redact`). 원본 응답 본문도 저장하지 않고 상태만 남긴다.

사용
----
    cd src
    python3 tools/verify_drug_apis.py --out ../drug-api-verification-2026-11-18.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from import_compliance.drugs import API_CANDIDATES, VERIFIED_ON  # noqa: E402
from import_compliance.live_api import (  # noqa: E402
    from_environment,
    parse_gateway_error,
    redact,
)

KST = timezone(timedelta(hours=9))

# 데이터셋별 대표 요청 파라미터(문서의 요청변수 기준).
PROBE_PARAMS = {
    "15058963": {"pageNo": "1", "numOfRows": "1", "type": "json"},
    "15058041": {"pageNo": "1", "numOfRows": "1", "type": "json"},
    "15095677": {"pageNo": "1", "numOfRows": "1", "type": "json", "item_name": "타이레놀"},
    "15075057": {"pageNo": "1", "numOfRows": "1", "type": "json", "itemName": "타이레놀"},
    "15059486": {"pageNo": "1", "numOfRows": "1", "type": "json", "itemName": "타이레놀"},
}


def probe(client, candidate) -> dict:
    params = dict(PROBE_PARAMS.get(candidate["dataset_id"]) or {})
    params["serviceKey"] = client._service_key  # noqa: SLF001 - 키는 아래에서 지운다
    url = client._url(candidate["endpoint"], params)
    started = time.monotonic()
    try:
        status, body, _content_type = client._transport(url, 25)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001 - 네트워크 실패도 상태로 남긴다
        return {
            "dataset_id": candidate["dataset_id"],
            "name_ko": candidate["name_ko"],
            "endpoint": candidate["endpoint"],
            "http_status": None,
            "state": "network_error",
            "message": redact(str(exc), client._service_key),
        }
    elapsed_ms = int((time.monotonic() - started) * 1000)
    gateway = parse_gateway_error(body)
    row = {
        "dataset_id": candidate["dataset_id"],
        "name_ko": candidate["name_ko"],
        "endpoint": candidate["endpoint"],
        "http_status": status,
        "elapsed_ms": elapsed_ms,
    }
    if gateway:
        code = gateway.get("reasonCode") or ""
        row.update({
            "gateway_code": code,
            "gateway_message": redact(gateway.get("errMsg") or "", client._service_key),
            "state": "approval_required" if code in ("20", "30") else "endpoint_error",
        })
        return row
    row["state"] = "live" if status < 400 else "http_error"
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="식약처 의약품 API 활용승인 상태 실호출 확인")
    parser.add_argument("--out", help="결과 JSON 저장 경로")
    args = parser.parse_args(argv)

    client = from_environment()
    if client is None or not client.has_customs:
        print("DATA_GO_KR_SERVICE_KEY 없음(.env). 실호출 확인에는 키가 필요합니다.")
        return 2

    rows = []
    for candidate in API_CANDIDATES:
        row = probe(client, candidate)
        rows.append(row)
        print(f"{row['dataset_id']} {row['name_ko']}: "
              f"HTTP {row.get('http_status')} code={row.get('gateway_code', '-')} → {row['state']}")

    payload = {
        "checked_on": VERIFIED_ON,
        "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "공공데이터포털(data.go.kr) 실호출 · 마약류/의약품 계열 5종",
        "note_ko": (
            "이 계정의 서비스키로 후보 엔드포인트를 호출한 결과만 남긴다. 코드 30은 "
            "'해당 서비스에 등록되지 않은 키'로, 그 데이터셋에 대한 활용신청이 없다는 뜻이다"
            "(같은 키가 관세청·수입식품 API에서는 정상 동작함을 별도 확인). 키·원본 응답은 저장하지 않는다."
        ),
        "results": rows,
        "summary": {
            "total": len(rows),
            "live": sum(1 for row in rows if row["state"] == "live"),
            "approval_required": sum(1 for row in rows if row["state"] == "approval_required"),
        },
        "apply_urls": [{"dataset_id": row["dataset_id"], "name_ko": row["name_ko"],
                        "apply_url": row["apply_url"]} for row in API_CANDIDATES],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"저장: {os.path.abspath(args.out)}")
    else:
        print(text)
    return 0 if payload["summary"]["live"] else 1


if __name__ == "__main__":
    sys.exit(main())
