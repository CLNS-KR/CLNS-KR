---
title: "CLNS — PRODUCT COMPLIANCE INTELLIGENCE · KOREA"
---

# CLNS

PRODUCT COMPLIANCE INTELLIGENCE · KOREA

Clearance, simplified.

복잡한 한국 수입 규제를 10초 만에 확인

**Korea Import Compliance MCP & API** — 한국 수입·구매대행·유통 실무에서 **범용 AI가 자주 틀리는 요건**을 3단계로 판정하고, 근거 법령 조항·시행일·원문 URL과 국/영문 면책을 함께 반환하는 경량 엔진입니다.

- 라이브: **<https://clns-kr.onrender.com>** (무료 베타 · Render free Web Service)
- 결제 없음 · 100% 무료 베타 · 회원가입 없음
- 외부 API 키가 없어도 동작(코퍼스 기반). 키를 넣으면 관세청·식약처·법제처 공공 API를 실시간 호출하고, 실패 시 캐시로 폴백. 전파 적합성평가(국립전파연구원)는 **키가 필요 없는 공개 API**라 번호만 있으면 바로 조회한다
- 원본 API 재전송 없음 — 결합·정규화한 판정만 출력
- 브라우저에서 바로 쓰는 사람용 화면(`GET /`) 포함: 품목명만 넣고 10초 안에 확인 항목·근거 조문·리콜 이력을 본다. 화면은 CLNS Check · CLNS Intelligence · CLNS Ad & Label · CLNS API & MCP 네 축으로 나뉜다.
- **품목별 무료 체크 페이지(pSEO) 35개**: `/p/` 인덱스와 `/p/{slug}` — 무선 미니 선풍기·보조배터리·오메가3·선크림·반려동물 사료 등. JS 없이 크롤러가 읽는 서버 렌더 HTML에 H1·대표 HS·세관장확인 요건 표·**규제 축(소관 기관·확인 카드·MCP 툴)**·KC·전파·식약처 항목·핵심 함정·근거·면책·**API/MCP 연결 안내**·실시간 조회 링크를 담는다(`sitemap.xml` 동적 생성, 얇은 페이지는 `noindex`).
- **익명 일별 통계**: `GET /v1/stats` — IP·User-Agent 원문·쿠키·개인 식별자를 저장하지 않고 날짜별 경로/툴/`verdict.code`/0건·오류 수만 집계
- **규제 카드 24개(0.1.5)** — 0.1.4의 의료기기법(TRAP-21)·위생용품 관리법(TRAP-22)에 이어, **의약품 반입 카드 2개(TRAP-23 마약류·향정·대마 반입 제한, TRAP-24 6병 기준과 성분 제한의 구분)** 를 추가. 마약류·원료물질 목록은 **마약류 관리에 관한 법률 시행령 별표 1~8**을 법제처 API로 받아 파싱한 로컬 사전(마약류 493건 + 원료물질 55건)으로 대조하고, 미래 시행일 개정 조문은 인용하지 않는다
- **의약품·성분 체크(한글·영문)** — `check_drug_import` 툴과 웹 화면에서 성분명·제품명(예: 졸피뎀/Zolpidem, Adderall, CBD)을 넣으면 ① 마약류(마약·향정신성의약품·대마 및 합성품) ② 마약류 원료물질(에페드린·슈도에페드린·에르고타민 등) ③ 국내 전용 성분(멜라토닌·DHEA·요힘빈·실데나필 등 시드) 여부와 ④ 자가사용 인정기준(총 6병, 초과 시 용법상 3개월 복용량)을 함께 대조한다. 휴대 반입 소량 일반의약품은 과탐 없이 `low_risk`, 6병 초과·직구는 `check_likely`
- **과대광고·한글표시 검수(0.2.0)** — `check_ad_labeling` 툴과 웹 화면에서 상세페이지 문구와 라벨 문구를 넣으면 **품목 유형(일반식품·건강기능식품·화장품·기능성화장품)별** 기준으로 질병 효능·의약품 오인·건기식 오인·거짓과장·체험기·비교·비방·보증·기능성 오인·디톡스 표현을 잡고, 근거 법령(식품표시광고법 제8조·화장품법 제13조)·위험도(높음/주의)·대체 표현을 함께 준다. 같은 문구가 유형별로 어떻게 달라지는지 나란히 보여준다
- **한글표시사항 체크리스트(0.2.0)** — 수입식품·건강기능식품·화장품별 필수 표시항목(제품명·원재료명·영업소·소비기한·섭취방법·"건강기능식품" 문자·의약품 아님 표현·전성분·제조번호·가격 등)을 조문 근거와 함께 대조해 누락 항목을 짚는다
- **식약처 행정처분 연동(0.2.0)** — `lookup_mfds_disposition` 툴로 행정처분결과(식품제조가공업 15124560 · 식품판매업 15124559)를 조회한다. 승인 전파 전·오프라인이면 2026-11-19 스냅샷에서 집계한 **업종별 빈발 위반 패턴**으로 폴백한다. 원본의 업소명·대표자·연락처·주소·인허가번호는 **읽지 않고 버린다**
- **대표 100개 품목 테스트셋(1.0.1 그대로)** — 8개 분야(전기·전자 KC / 무선·전파 / 배터리 / 어린이제품 / 식품·건기식 / 화장품 / 생활화학·차량용 방향제 / 의료기기·위생용품) 100건으로 분야별 정확도와 **중대 규제 누락(FN) 0건**을 검증(`--check-testset`). 0.1.5에서 의약품 기능을 더해도 이 100건 세트는 손대지 않았고(1.0.1·100건·FN 0 유지), 의약품은 **별도 `drug_testset.json` 14건**(`--check-drugs`)으로 관리한다
- **응답 스키마 0.1.3(0.1.5에서도 유지)** — 기존 3단계 `verdict` 위에 표준 5단계 `assessment_status`(APPLICABLE·NOT_APPLICABLE·POTENTIALLY_APPLICABLE·REVIEW_REQUIRED·UNKNOWN), `missing_information`, `destination`·`jurisdiction`·`origin`(ISO), `regulation_tags` 를 추가
- **MCP 두 가지 전송**: HTTP(`POST /mcp`) + **stdio**(`python -m import_compliance.mcp_stdio`) — 로컬 실행형 MCP 디렉터리(Glama·mcp.so 등) 등록용
- 무료 클라우드 배포 사본 제공: `Dockerfile`(python:3.12-slim) + `render.yaml`(Render free Web Service)
- GitHub Actions CI(`.github/workflows/test.yml`) — Python 3.11·3.12 에서 `--check-corpus` + `--check-testset` + 전체 테스트 자동 실행
- 라이선스: **MIT** (`LICENSE`, `Copyright (c) 2026 CLNS-KR`)

## 문서

| 파일 | 내용 |
|---|---|
| `01-api-sources-and-legal.md` | 실제 쓸 공공 API 목록, 신청 방법, 확인한 약관 원문, 상업적 가공 안전성 판정, **2026-11-18 실호출 검증 결과** |
| `02-ai-trap-corpus-20.md` | 일반 AI가 틀리는 함정 24개(상황·오답·정답·근거·판정 로직). 파일명은 초기 20건 기준이며, 0.1.5에서 TRAP-23·24를 더해 `tools/build_corpus_doc.py`로 재생성했다 |
| `03-mvp-spec-and-risk-mitigation.md` | 5대 리스크 대응, 아키텍처, 캐시 DB, 8개 툴, 무료/유료 경계, 면책 |
| `live-api-verification-2026-11-18.json` | 라이브 검증 산출물(정규화 샘플·상태, **키 없음**) |
| `live-scenario-results-2026-11-18.json` | 대표 3품목 라이브 판정 산출물(응답시간·요건·리콜 포함, **키 없음**) |
| `09-ad-labeling-0.2.0.md` | 0.2.0 설계 — 유형별 광고 기준 차이, 탐지 규칙 16종, 한글표시 체크리스트, 행정처분 연동·폴백·개인정보 처리 |
| `04-live-scenario-report-2026-11-18.md` | 대표 3품목 라이브 판정 사람용 리포트 |
| `.env.example` | 키 템플릿(`.env`는 커밋 금지) |
| `LICENSE` | MIT 라이선스(`Copyright (c) 2026 CLNS-KR`) |
| `.github/workflows/test.yml` | CI: `--check-corpus` + `--check-testset` + 전체 테스트 + stdio MCP 스모크(Python 3.11·3.12) |

출시 전 감사·성장 계획(05), 테스트셋·스키마 설계(06), 0.1.4 변경 상세(07), 0.1.5 변경 상세(08), 법령·API 실조회 검증 산출물(`medical-hygiene-law-verification.json`·`drug-law-verification.json`·`drug-api-verification-2026-11-18.json`·`ad-label-law-verification.json`·`food-sanitation-law-verification.json`·`disposition-api-verification-2026-11-19.json`)은 내부 문서로 두고 공개 저장소에는 포함하지 않는다.

## 실행

```bash
cd src
python3 -m import_compliance.cli --check-corpus
python3 -m import_compliance.cli --check-testset     # 100건 분야별 정확도·규제 누락 FN
python3 -m import_compliance.cli --check-drugs       # 의약품·영양제 14건(금지성분·자가사용 기준)
python3 -m import_compliance.cli --drug 졸피뎀 --channel online --quantity 30
python3 -m import_compliance.cli --drug-schedules    # 성분 사전 상태(별표 개정일·건수·미승인 API)
python3 -m import_compliance.cli "중국산 블루투스 스피커를 수입해 판매하려고 해"
python3 -m import_compliance.cli "150달러 이하 의류 목록통관"
python3 -m import_compliance.cli --trap TRAP-15
python3 -m import_compliance.cli --mcp

# 국표원 리콜 파일데이터 적재·조회(인증키 불필요, 네트워크 필요)
python3 -m import_compliance.cli --fetch-recalls          # data/raw CSV + data/recalls.sqlite
python3 -m import_compliance.cli --db ../data/recalls.sqlite --recall "전지"
python3 -m import_compliance.cli --db ../data/recalls.sqlite --recall-stats
```

### 실API 모드 (`.env` 키 필요)

`.env`(프로젝트 루트)에 `DATA_GO_KR_SERVICE_KEY`, `LAW_GO_KR_OC`를 넣으면 실호출이 켜집니다.
`.env`는 `.gitignore`에 들어 있고, 코드·문서·로그·응답에는 키가 남지 않습니다.

```bash
cd src
python3 tools/verify_live_apis.py --encoding-check        # 4개 엔드포인트 라이브 검증
python3 tools/verify_live_apis.py --hs 8507609000 --law-query 관세법 --law-article 226 \
        --out ../live-api-verification.json
python3 -m import_compliance.cli --live --hs 3307903000   # HS 10자리 세관장확인 실조회
IMPORT_COMPLIANCE_LIVE=1 python3 -m import_compliance.server   # HTTP 서버도 live 모드
```

| 실API 소스 | 엔드포인트 | 툴에서 보이는 곳 |
|---|---|---|
| 관세청 세관장확인대상물품(15101589) | `apis.data.go.kr/1220000/retrieveCcctLworCd/getRetrieveCcctLworCd` | `lookup_hs_requirements.hs_requirements_live` |
| 식약처 수입식품 허가정보(15058273) | `apis.data.go.kr/1471000/ImportFoodPrmisnInfoService05/getImrtsCnfirmList05` | `check_food_cosmetics.food_import_live` |
| 식약처 수입식품 제품DB(15073949) | `apis.data.go.kr/1471000/IprtFoodPrdtDBService02/getIprtFoodPrdtDBInq02` | `check_food_cosmetics.food_import_live` |
| 법제처 국가법령정보(lawSearch/lawService) | `www.law.go.kr/DRF/lawSearch.do`, `lawService.do` | `get_legal_basis.law_live` |
| 국립전파연구원 적합성평가 DB정보(3034183) | `emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthInfo.do` (키 불필요) | `assess_import_case.rra_conformity_live`, `check_kc_certification.rra_conformity_live` |
| 식약처 의약품 계열 5종(15058963·15058041·15095677·15075057·15059486) | `apis.data.go.kr/1471000/...` | **이 계정은 활용승인 전(코드 30)** → `drug_screening.api_candidates` 에 `approval_required` 로 표시. 성분 대조는 시행령 별표 로컬 사전으로 수행 |

HTTP 서버(웹 UI + JSON API + MCP):

```bash
cd src
python3 -m import_compliance.server              # http://0.0.0.0:8787 · 작업 DB는 ../data/app.sqlite
python3 -m import_compliance.server --port 9000 --db /tmp/tck.sqlite
curl -s localhost:8787/v1/mcp | head             # 툴 매니페스트(사람이 읽는 JSON)
curl -s -X POST localhost:8787/v1/tools/assess_import_case \
  -H 'Content-Type: application/json' \
  -d '{"query":"합성니코틴 액상형 전자담배를 수입해 판매"}'

# MCP(JSON-RPC 2.0) — POST /mcp 또는 POST /v1/mcp
curl -s -X POST localhost:8787/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}'
curl -s -X POST localhost:8787/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"assess_import_case","arguments":{"query":"중국산 무선 선풍기를 수입해 판매"}}}'
curl -s localhost:8787/.well-known/mcp/server-card.json | head
curl -sI -X OPTIONS localhost:8787/v1/tools/assess_import_case   # 204 + CORS
curl -s localhost:8787/robots.txt; curl -s localhost:8787/llms.txt; curl -s localhost:8787/sitemap.xml
curl -s localhost:8787/p/ | head -40               # 품목별 페이지 인덱스(35개)
curl -s localhost:8787/p/usb-mini-fan | head -60   # 품목별 무료 체크(서버 렌더 HTML)
curl -s localhost:8787/v1/stats | head -60         # 익명 일별 통계(IP·UA 미저장)
```

### MCP 연결 — HTTP 와 stdio

같은 9개 툴을 두 가지 전송으로 제공합니다(로직은 `mcp_http.py` 한 곳).

```bash
# 1) HTTP(Streamable HTTP · JSON-RPC 2.0, 무인증, application/json 한 덩어리)
#    POST https://clns-kr.onrender.com/mcp   (= /v1/mcp)

# 2) stdio(로컬 실행형 MCP 디렉터리용) — 한 줄에 JSON-RPC 한 건
cd src
python3 -m import_compliance.mcp_stdio \
  <<'JSON'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lookup_hs_requirements","arguments":{"hs_code":"8414519000"}}}
JSON
```

MCP 클라이언트 설정 예시(`claude_desktop_config.json` 등):

```json
{
  "mcpServers": {
    "clns": {
      "command": "python",
      "args": ["-m", "import_compliance.mcp_stdio"],
      "env": { "PYTHONPATH": "/path/to/clns/src" }
    }
  }
}
```

- stdio 는 stdout 에 JSON-RPC 응답만 쓰고 로그는 stderr 로 보냅니다. notification 에는 아무것도 쓰지 않습니다.
- 상태를 저장하지 않으므로 `initialize` 없이 `tools/call` 을 바로 보내도 동작합니다.

### 툴 11종

| 툴 | 하는 일 | 주요 인자 |
|---|---|---|
| `assess_import_case` | 품목·상황 자연어 → 수입요건·인증·표시·통관 함정 3단계 판정 + 근거·면책 | `query`(필수), `facts`, `limit` |
| `lookup_hs_requirements` | HS 10자리 → 세관장확인대상 여부·법령·기관·확인시점 | `hs_code`(필수), `direction` |
| `check_kc_certification` | 전기용품·생활용품·어린이제품·전파 적합성평가 중 걸리는 절차 판정 | `product_name`, `target_age`, `rf_tx`, `battery`, `ac_plug` |
| `check_food_cosmetics` | 식품·건기식·화장품·기구용기: 수입신고·영업등록·한글표시·광고심의 | `product_name`, `kind`(필수) |
| `check_drug_import` | 의약품·영양제 성분 대조: 마약류·원료물질·국내 전용 성분 + 자가사용 인정기준(6병·3개월분) | `product_name`(필수), `channel`, `quantity`, `unit`, `prescription`, `purpose` |
| `check_ad_labeling` | 상세페이지·상품명 문구와 라벨 문구를 유형별 기준으로 검수: 위험 표현·근거·대체 표현 + 한글표시사항 누락 | `product_type`, `ad_copy`, `label_text`, `label_items`, `functional`, `imported` |
| `lookup_mfds_disposition` | 식약처 행정처분 이력(식품제조가공업·식품판매업) + 업종별 빈발 위반 패턴(개인정보 필드 폐기) | `industry`, `keyword`, `license_no`, `confirmed_on`, `rows`, `limit` |
| `lookup_recall` | 브랜드·모델명·제품명으로 국내 리콜 이력(국표원 15040696 로컬 인덱스) | `brand`, `model`, `product_name`, `category` |
| `get_legal_basis` | 코퍼스 수록 법령 조항 요지·시행일·원문 URL | `law`(필수), `article` |
| `explain_trap` | 함정 케이스(TRAP-01~24) 시나리오·흔한 오답·정답·근거 | `case_id`(필수) |
| `get_service_meta` | 코퍼스 버전·판정 등급·무료/유료 경계·잔여 호출 | – |

무료 한도는 브라우저/클라이언트 ID 당 월 250회이며 `get_service_meta` 는 차감되지 않습니다.

### 응답 스키마 0.1.3 — 표준 상태 · 누락 정보 · 공통 필드

기존 3단계 `verdict`(`check_likely`/`info_needed`/`low_risk`)는 **그대로** 두고, 판정 상태·빠진 스펙·지리 정보를 추가했다. 필드만 늘었으므로 기존 클라이언트는 수정 없이 동작한다.

| 필드 | 값 | 설명 |
|---|---|---|
| `assessment_status` | `APPLICABLE` · `NOT_APPLICABLE` · `POTENTIALLY_APPLICABLE` · `REVIEW_REQUIRED` · `UNKNOWN` | 표준 판정 상태(`verdict`·findings 수·누락 정보에서 계산) |
| `missing_information` | `["hs_10_code", "intended_age", ...]` | 판정을 좁히려면 필요한 **표준 스펙명** 목록 |
| `missing_information_detail` | `[{field, prompt, allowed_values, case_id}]` | 같은 목록의 상세(질문·허용값·케이스) |
| `destination` | `"KR"` | 통관 목적국 |
| `jurisdiction` | `"KR"` | 적용 법역(법령 카드가 한국법 기준) |
| `origin` | `"CN"` · `null` | 원산지 ISO 3166-1 alpha-2. 확인되지 않으면 `null`(추측하지 않음) |
| `origin_source` | `"query"` · `"facts"` · `null` | 원산지를 어디서 확인했는지 |
| `regulation_tags` | `["ELECTRICAL_KC", ...]` | 케이스·응답 단위 규제 태그(25종 어휘) |
| `schema_version` | `"0.1.3"` | 응답 스키마 버전 |

상태와 기존 판정의 대응: `check_likely` → `APPLICABLE`(빠진 스펙이 있으면 `POTENTIALLY_APPLICABLE`), `info_needed` → `REVIEW_REQUIRED`, `low_risk` → `NOT_APPLICABLE`, 쟁점 0건 → `UNKNOWN`. 상태·누락 정보는 판정 툴(assess 계열) 응답에 실리고, 나머지 툴은 공통 지리 필드만 갖는다. 실제 판정은 인증·통관 확정이 아니므로 `verdict.determinative` 는 항상 `false` 다.

```json
{
  "schema_version": "0.1.3", "destination": "KR", "jurisdiction": "KR",
  "origin": "CN", "origin_source": "query",
  "verdict": {"code": "check_likely", "label_ko": "확인 대상 가능성 높음", "determinative": false},
  "assessment_status": "POTENTIALLY_APPLICABLE",
  "assessment_status_label_ko": "적용 가능성 있음",
  "missing_information": ["rated_power", "ac_plug"],
  "regulation_tags": ["ELECTRICAL_KC"]
}
```

## 대표 100개 품목 테스트셋

`src/testset_100.json` — 8개 분야 100건. 각 케이스는 `domain`(분야) · `expected_verdict`(기대 판정) · `required_findings`(필수 규제 태그)를 가지며, 필수 태그가 응답에서 빠지면 **중대 규제 누락(FN)**으로 센다.

| 분야 | 케이스 | 예 |
|---|---|---|
| 전기·전자 KC | 16 | USB-C 65W 충전기, 노트북 어댑터, 에어프라이어 8516.60 |
| 무선기기·전파법 | 12 | 블루투스 스피커, 와이파이 공유기, 적외선 리모컨(저위험) |
| 배터리 | 12 | 보조배터리, 전동공구 배터리 팩, 드론 배터리 |
| 어린이제품 | 12 | PPSU 젖병, 유모차, 카시트, 무선 RC 완구 |
| 식품·건강기능식품 | 16 | 구매대행 과자, 건강기능식품 광고, 식품용 도마 |
| 화장품 | 10 | 수딩크림, 선크림(기능성), 향수 |
| 생활화학제품·차량용 방향제 | 10 | 주방 세정제, 차량용·겔 방향제, 디퓨저 |
| 의료기기·위생용품 | 12 | 전자혈압계·체온계·생리대 HS 요건, 소액 직구 |

검증 결과: 분야별 판정 정확도 **100%(100/100)**, 중대 규제 누락 **0건**, `NOT_APPLICABLE` 오판 0건(2026-11-18, 네트워크 없이). 의료기기·위생용품은 0.1.4에서 TRAP-21·22 카드로, 의약품은 0.1.5에서 TRAP-23·24 카드와 별도 14건 세트로 검증한다. 남은 한계(공개 API 부재·활용승인 전)는 응답의 `scope_limits_ko` 에도 표시한다.

```bash
cd src
python3 -m import_compliance.cli --check-testset     # 분야별 정확도·FN
python3 tests/test_testset_100.py                    # 구조·정확도·FN 18건
python3 tools/build_testset_100.py                   # 테스트셋 재생성
```

## 의약품·영양제 반입 체크 (0.1.5)

해외직구·휴대 반입하려는 의약품·영양제의 **성분**을 기준으로 판정한다. 질의문·성분명은 한글·영문 모두 대조한다(예: `졸피뎀`/`Zolpidem`, `CBD`/`칸나비디올`/`Cannabidiol`, 제품명 `Adderall`→암페타민).

| 축 | 데이터·근거 | 판정 |
|---|---|---|
| 마약류(마약·향정신성의약품·대마 및 합성품) | 마약류 관리에 관한 법률 제2조·제4조·제18조, 시행령 별표 1~7의2(로컬 사전 493건) | `check_likely` — 처방전·수량과 무관하게 개인 반입이 인정되기 어렵다 |
| 마약류 원료물질(에페드린·슈도에페드린·에르고타민 등) | 같은 법 제2조제6호·제6조의2, 시행령 별표 8(55건), 「수입통관 사무처리에 관한 고시」 별표 11 | `check_likely` — 함유 단일완제의약품은 요건확인 대상 |
| 국내 전용 성분(멜라토닌·DHEA·요힘빈·실데나필 등) | 고시 별표 11·약사법 제42조(대표 시드 목록) | `check_likely` — 건강기능식품으로 반입 불가, 의약품 수입 절차 필요 |
| 자가사용 인정기준(총 6병, 초과 시 용법상 3개월 복용량) | 고시 제67조·별표 11 | 휴대 반입 소량 일반의약품 `low_risk` · 6병 초과·직구 `check_likely` |

- 성분 사전은 `src/tools/fetch_drug_schedules.py`가 법제처 API로 **시행령 별표 1~8을 파싱해** 생성한다(`src/drug_schedules.json`, 출처: 법제처 국가법령정보센터). 손으로 적은 추정 목록이 아니며, 별표에 없다고 마약류가 아니라고 단정하지 않는다(임시마약류·개정 시차).
- 식약처 의약품 허가정보·e약은요·DUR·마약류 API(15058963·15058041·15095677·15075057·15059486)는 **이 계정에 활용승인이 없어(코드 30)** 실시간 전수 대조를 제공하지 않는다. 응답의 `drug_screening.api_candidates` 와 `/v1/meta` 의 `drug_schedules.api_candidates` 에 상태를 그대로 표시한다(`drug-api-verification-2026-11-18.json`).
- 의약품 테스트셋: `src/drug_testset.json` 14건(마약류 6·원료물질 2·국내 성분 1·직구 1·자가사용 경계 2·과탐 방지 2). 판정 일치 14/14, 금지 태그 0.

## 과대광고·한글표시 검수 (0.2.0)

상세페이지 문구와 라벨(한글표시사항) 문구를 **품목 유형별** 기준으로 본다. 같은 문구도 유형에 따라
허용 범위가 다르므로, 엔진은 4개 유형에 각각 적용해 결과를 나란히 보여준다.

| 문구 | 일반식품 | 건강기능식품 | 일반화장품 | 기능성화장품 |
|---|---|---|---|---|
| "체지방 감소에 도움을 줄 수 있음" | 금지 위험(건기식 오인) | 인정 원료·함량 범위 내 허용 | – | – |
| "미백", "주름개선", "자외선 차단" | – | – | 금지 위험(기능성 오인) | 심사·보고 범위 내 허용 |
| "아토피 치료", "항암 효과" | 금지 위험 | 금지 위험 | 금지 위험 | 금지 위험 |
| "100%", "즉시", "최고" | 과장 위험 | 과장 위험 | 과장 위험 | 과장 위험 |

- 규칙 16종(`AD-01`~`AD-16`)을 위험도(높음/주의)와 함께 적용하고, finding마다 근거 조문(식품표시광고법 제8조제1항 각 호, 화장품법 제13조, 건강기능식품법 제15조제2항 등)·시행일·원문 URL·대체 표현을 붙인다.
- 화장품은 2026-10-20 시행 화장품법 제13조제1항제4호(AI 생성 전문가 보증 광고)를 별도 규칙으로 잡는다.
- 한글표시사항은 유형별 필수항목(식품 9·건기식 13·화장품 8, 조건부 3~3·2)을 조문 근거와 대조하고, 조건부 항목(영양표시·알레르기·수입 한글표시·기능성 표시·1차 포장)은 해당 제품에만 적용한다. 세부 서식은 「식품등의 표시기준」·「화장품법 시행규칙」 확인 대상으로 남긴다.
- 라벨 사진 인식(OCR)은 하지 않는다. 텍스트로 옮긴 라벨 또는 항목 체크만 대조하며, "누락"은 입력에서 그 항목을 찾지 못했다는 뜻이다.

```bash
curl -s -X POST https://clns-kr.onrender.com/v1/tools/check_ad_labeling \
  -H 'Content-Type: application/json' \
  -d '{"product_type":"general_food","ad_copy":"먹기만 하면 100% 다이어트, 항암 효과 입증",
       "label_text":"제품명 다이어트 환 / 소비기한 2027.03.15"}'
```

## 식약처 행정처분 이력 (0.2.0)

| 데이터셋 | 업종 | 상태(2026-11-19) |
|---|---|---|
| `15124560` | 식품제조가공업(주류 포함) | 실호출 성공(`resultCode 00`, 249건) |
| `15124559` | 식품판매업 | 승인 후 전파 전(코드 30) — 붙으면 자동 사용 |

- 조회 순서: **실시간 API → 로컬 적재분(`disposition_items`) → 내장 대표 적발 패턴**. 승인 전파 전·키 없음·오프라인에서도 같은 형태로 답한다.
- 내장 패턴은 2026-11-19 스냅샷 249건의 위반법령 분포(시설기준 94·영업허가 변경 37·자가품질검사 16·표시기준 4·부당광고 1 등)를 집계한 것으로, 개별 업소 이력을 담지 않는다.
- 원본의 **업소명·대표자명·전화번호·주소·인허가번호는 읽지 않고 버린다**. 위반내용의 전화번호·주민번호·긴 숫자도 마스킹한다. 인허가번호는 조회 조건으로만 쓰고 응답·저장에 남기지 않는다.

| 경로 | 내용 |
|---|---|
| `GET /` | 사람용 웹 UI(CLNS Check · CLNS Intelligence · CLNS Ad & Label · CLNS API & MCP) |
| `GET /p/` | 품목별 수입 요건 인덱스(35개, 크롤러 진입점) |
| `GET /p/{slug}` | 품목별 무료 체크 페이지(서버 렌더 HTML · JS 없음 · 얇은 페이지는 `noindex`). 없는 slug 는 404 |
| `GET /v1/stats` | 익명 일별 통계 JSON(`?days=7`). IP·User-Agent·쿠키·개인 식별자 미저장 |
| `GET /healthz` | 헬스체크 |
| `POST /mcp` · `POST /v1/mcp` | MCP JSON-RPC 2.0: `initialize`·`notifications/initialized`·`ping`·`tools/list`·`tools/call`. notification은 202(본문 없음), 표준 에러 코드(-32700/-32600/-32601/-32602), SSE 스트리밍 없음 |
| `GET /.well-known/mcp/server-card.json` | MCP 서버 카드(인증 없음·툴 11종 스키마) |
| `GET /v1/mcp` | 툴 매니페스트(사람이 읽는 JSON). `GET /mcp` 는 405(스트리밍 미지원) |
| `POST /v1/tools/{tool}` | REST JSON 11종 |
| `GET /robots.txt`·`/llms.txt`·`/sitemap.xml` | 검색·AI 크롤러용 공개 파일(`sitemap.xml` 은 `/` + `/p/` + 전 품목 URL 동적 생성) |
| `GET /static/og.png` | 공유 미리보기 이미지(1200×630) |
| `GET /<확인파일>.html` | 검색엔진 소유확인 파일(`SITE_VERIFICATION_FILES` 로만 열린다. 없으면 404) |
| `OPTIONS *` | CORS preflight 204. 모든 응답에 `Access-Control-Allow-Origin: *` |

브라우저로 `http://localhost:8787/` 을 열면 사람용 화면(CLNS Check · CLNS Intelligence · CLNS Ad & Label · CLNS API & MCP)이 나온다.

### 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `HOST` | `0.0.0.0` | 바인드 주소(`--host` 로 덮어쓰기) |
| `PORT` | `8787` | 포트. Render/Koyeb는 이 값을 자동 주입한다(`--port` 로 덮어쓰기) |
| `IMPORT_COMPLIANCE_DB` | `data/app.sqlite` | 작업 SQLite(판정 이력·쿼터·캐시). 없으면 기동 시 생성 |
| `IMPORT_COMPLIANCE_LIVE` | `0` | `1`이면 `.env` 또는 환경변수의 키로 실API 조회 |
| `PUBLIC_BASE_URL` | `https://clns-kr.onrender.com` | robots·llms·sitemap·pSEO canonical 의 공개 주소 |
| `GOOGLE_SITE_VERIFICATION` | – | 구글 서치콘솔 소유확인 토큰 → `<meta name="google-site-verification">` |
| `NAVER_SITE_VERIFICATION` | – | 네이버 서치어드바이저 소유확인 토큰 → `<meta name="naver-site-verification">` |
| `SITE_VERIFICATION_FILES` | – | 소유확인 HTML 파일(JSON). 예: `{"google1a2b.html":"google-site-verification: google1a2b.html"}` — 루트 경로로 서빙 |
| `DATA_GO_KR_SERVICE_KEY` | – | 공공데이터포털 인증키(Decoding) |
| `LAW_GO_KR_OC` | – | 법제처 OC 값 |

기동 시 `data/recalls.sqlite`(리콜 로컬 인덱스)를 작업 DB로 복사한다 — 원본 인덱스 파일은 쓰지 않는다.

## 무료 클라우드 배포

`Dockerfile`(python:3.12-slim, 비루트 실행, 헬스체크 포함)과 `render.yaml`(Render Blueprint)이 준비되어 있다.

**Render 무료 플랜** — 서비스 이름 `clns-kr`

1. 이 프로젝트를 GitHub 저장소에 올린다(`.env`는 `.gitignore`로 제외, `data/recalls.sqlite`는 커밋 대상).
2. Render → **New > Blueprint** → 저장소 선택 → `render.yaml` 인식 → Apply.
3. 대시보드에서 `DATA_GO_KR_SERVICE_KEY`, `LAW_GO_KR_OC` 입력(`sync: false`라 저장소에는 값이 없다. 비워 두면 코퍼스 모드로 뜬다).
4. `https://<서비스>.onrender.com/` 접속 → 웹 UI, `/healthz` → 헬스체크.

**Docker로 직접**

```bash
docker build -t clns-kr .
docker run -p 8787:8787 -e IMPORT_COMPLIANCE_LIVE=1 \
  -e DATA_GO_KR_SERVICE_KEY=*** -e LAW_GO_KR_OC=*** clns-kr
```

**무료 플랜 주의**

- 영구 디스크가 없어 작업 DB(판정 이력·쿼터 카운터·**일별 통계**)는 재시작 시 초기화된다. 리콜 인덱스는 이미지에 있어 매 기동마다 다시 적재된다.
- 미접속 시 슬립되어 첫 요청이 30~60초 걸릴 수 있다.
- `.dockerignore`가 `.env`·`__pycache__`·테스트·도구·원본 CSV를 제외하므로 이미지에 API 키가 들어가지 않는다.
- 페이지는 외부 CDN 없이 인라인 CSS/JS만 쓰고 CSP(`default-src 'none'`)로 외부 로드를 막는다.
- 무료 쿼터는 브라우저별 클라이언트 ID(`localStorage`)당 250회/월이다. IP 단위 제한은 없으므로, 공개 트래픽이 커지면 리버스 프록시 단계의 레이트리밋이 필요하다.

## 테스트

```bash
cd src
python3 tests/test_ad_labeling.py  # 37 tests (유형별 광고 기준 차이·위험도·근거 조문·한글표시 체크리스트·웹 UI)
python3 tests/test_mfds_disposition.py # 20 tests (15124560·15124559 연동·개인정보 제거·폴백 3단계·코드 30·스키마·HTTP)
python3 tests/test_engine.py      # 27 tests
python3 tests/test_http.py        # 3 tests (실제 소켓)
python3 tests/test_live_api.py    # 24 tests (네트워크 없이 고정 응답)
python3 tests/test_recall_index.py # 12 tests (리콜 CSV 파싱·적재·검색·인덱스 복사)
python3 tests/test_web.py         # 30 tests (브랜드·웹 UI·별칭·환경변수·모듈 엔트리포인트·키 비노출·UI 계약·레거시 브랜드 잔재)
python3 tests/test_patches_p0_p1.py # 41 tests (MCP JSON-RPC·CORS·크롤러 파일·HS 10자리 판정·식약처 캐시·head 메타·모바일 탭)
python3 tests/test_pseo_stats.py  # 25 tests (pSEO 35개 페이지·동적 sitemap·익명 카운터·stdio MCP·MIT·CI·시크릿 미포함)
python3 tests/test_site_verification.py # 11 tests (검색엔진 소유확인 파일 서빙)
python3 tests/test_testset_100.py # 18 tests (100건 구조·분야별 정확도·중대 규제 누락 FN·결정성)
python3 tests/test_medical_hygiene_rra.py # 25 tests (의료기기·위생용품 카드·현행 조문 검증·적합성평가 실연동·pSEO 연결)
python3 tests/test_schema_013.py  # 31 tests (표준 상태 5단계·누락 정보·지리 필드·규제 태그·하위 호환·익명성)
```

합계 **351건**. 네트워크 없이 전부 통과한다(실호출은 `tools/verify_live_apis.py`로 따로 검증).
CI 에서는 같은 스위트를 `python3 -m unittest discover -s tests` 로 한 번에 돌리고, 그 앞에 `--check-corpus`·`--check-testset` 자기검증을 둔다.

## 익명 통계 (`GET /v1/stats`)

무엇을 저장하는가 — **날짜(YYYY-MM-DD, Asia/Seoul) · 경로 · 툴 이름 · `verdict.code` · 0건/오류 여부의 호출 수**뿐입니다.

무엇을 저장하지 않는가 — IP(및 `X-Forwarded-For` 같은 전달 헤더), User-Agent 원문, 쿠키, Referer, 세션 ID, 질의문 원문. 알 수 없는 경로는 `/404` 한 칸으로 합산해 임의 문자열이 통계에 남지 않게 합니다.

```bash
curl -s 'https://clns-kr.onrender.com/v1/stats?days=7'
```

```json
{
  "ok": true, "timezone": "Asia/Seoul", "window_days": 7,
  "privacy": {"stores_ip": false, "stores_user_agent": false,
              "stores_cookies": false, "stores_identifiers": false},
  "days": [{"date": "2026-11-18", "requests": 42,
            "paths": {"/": 12, "/p/usb-mini-fan": 5, "/mcp": 3},
            "tools": {"lookup_hs_requirements": 7},
            "verdicts": {"check_likely": 4, "info_needed": 3},
            "flags": {"zero_results": 1, "errors": 0}}],
  "totals": {"requests": 42, "paths": {}, "tools": {}, "verdicts": {}, "flags": {}}
}
```

이 카운터가 상품 개선의 입력입니다 — “어떤 품목을 넣다가 0건을 맞는지”가 pSEO 우선순위, “어떤 툴이 실패하는지”가 장애 감지입니다.

## 라이선스

MIT — `LICENSE` 참고. 저작권자는 익명 운영 주체 **CLNS-KR** 하나만 표기합니다(개인 이름·연락처 없음).

## 구조

```
src/
  import_compliance/
    engine.py     판정 파이프라인(3단계·표준 상태·신선도·가드·강한 신호 매칭)
    corpus.py     코퍼스 로드·정규화
    models.py     데이터 모델(strong_signals·exclude_signals 포함)
    standards.py  표준 상태 5단계·규제 태그 25종·표준 스펙명·국가코드(ISO)
    policy.py     면책·금지 표현·티어 경계
    store.py      SQLite 캐시·쿼터·폴백·TTL 캐시·실API 게이트웨이·일별 카운터
    live_api.py   공공 API 6종 어댑터(파싱·정규화·재시도·키 리댁션)
    recall_index.py  국표원 리콜 파일데이터(15040696·15054301) 적재·검색
    api.py        11개 툴 + MCP 매니페스트·툴 정의(병렬 호출·7일 캐시·provenance 보정·툴 호출 계측)
    advertising.py 과대광고·부당표시 탐지 규칙 16종(유형별 적용·위험도·대체 표현·근거 조문)
    labeling.py    한글표시사항 필수항목 체크리스트(식품·건기식·화장품)와 누락 판정
    mfds_dispositions.py 식약처 행정처분(15124560·15124559) 연동·개인정보 제거·캐시·패턴 폴백
    mcp_http.py   MCP Streamable HTTP(JSON-RPC 2.0) 처리기
    mcp_stdio.py  같은 로직을 쓰는 stdio 엔트리포인트(줄 단위 JSON-RPC)
    pseo.py       품목별 페이지(35개) 서버 렌더러 · noindex/사이트맵 규칙
    usage.py      익명 일별 카운터(경로·툴·판정·0건/오류) + /v1/stats 페이로드
    static_files.py robots.txt·llms.txt·동적 sitemap.xml·MCP 서버 카드·og 이미지
    web_ui.py     사람용 단일 HTML 화면(외부 CDN 0, 인라인 CSS/JS)
    server.py     stdlib HTTP 서버(웹 UI·pSEO·JSON API·MCP·CORS·배포용 환경변수)
    cli.py        CLI·코퍼스 자기검증·`--serve`
  traps_20.json   함정 24케이스(의료기기·위생용품·의약품 포함, corpus 1.0.6)
  testset_100.json 대표 100품목 테스트셋(8분야·필수 규제 태그)
  pseo_items.json 품목 35개 카탈로그(1.0.1) + 관세청 실조회 요건 표(2026-11-18)
  schema.sql      Postgres 이관용 DDL
  tests/
  tools/verify_live_apis.py   실API 4종 라이브 검증
  tools/run_live_scenarios.py 대표 3품목 라이브 실전 테스트 러너
  tools/refresh_pseo_hs.py    pSEO 카탈로그의 HS 요건 표만 실API로 재적재
  tools/build_corpus_doc.py   문서 자동 생성
  tools/build_testset_100.py  대표 100개 테스트셋 생성·구조 검증
  tools/make_og_image.py      공유 미리보기 PNG 생성(Pillow, 생성 시점에만)
static/og.png     1200×630 공유 미리보기(og:image)
LICENSE           MIT (Copyright (c) 2026 CLNS-KR)
.github/workflows/test.yml  CI(3.11·3.12, --check-corpus + --check-testset + 전체 테스트 + stdio 스모크)
Dockerfile        무료 클라우드 배포 이미지(python:3.12-slim)
render.yaml       Render Blueprint(free Web Service, 키는 sync:false)
.dockerignore     .env·캐시·테스트 제외(키가 이미지에 구워지지 않게)
```

## 갱신 규칙

코퍼스를 고치면 `python3 tools/build_corpus_doc.py`로 `02-ai-trap-corpus-20.md`를 다시 생성하고, 세 테스트를 모두 통과시킨 뒤 반영합니다.
