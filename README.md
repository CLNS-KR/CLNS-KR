---
title: "CLNS — PRODUCT COMPLIANCE INTELLIGENCE · KOREA"
---

# CLNS

PRODUCT COMPLIANCE INTELLIGENCE · KOREA

Clearance, simplified.

복잡한 한국 수입 규제를 10초 만에 확인

**Korea Import Compliance MCP & API** — 한국 수입·구매대행·유통 실무에서 **범용 AI가 자주 틀리는 요건**을 3단계로 판정하고, 근거 법령 조항·시행일·원문 URL과 국/영문 면책을 함께 반환하는 경량 엔진입니다.

- 결제 없음 · 100% 무료 베타
- 외부 API 키가 없어도 동작(코퍼스 기반). 키를 넣으면 4개 공공 API를 실시간 호출하고, 실패 시 캐시로 폴백
- 원본 API 재전송 없음 — 결합·정규화한 판정만 출력
- 브라우저에서 바로 쓰는 사람용 화면(`GET /`) 포함: 품목명만 넣고 10초 안에 확인 항목·근거 조문·리콜 이력을 본다. 화면은 CLNS Check · CLNS Intelligence · CLNS API & MCP 세 축으로 나뉜다.
- 무료 클라우드 배포 사본 제공: `Dockerfile`(python:3.12-slim) + `render.yaml`(Render free Web Service)

## 문서

| 파일 | 내용 |
|---|---|
| `01-api-sources-and-legal.md` | 실제 쓸 공공 API 목록, 신청 방법, 확인한 약관 원문, 상업적 가공 안전성 판정, **2026-11-18 실호출 검증 결과** |
| `02-ai-trap-corpus-20.md` | 일반 AI가 틀리는 함정 20개(상황·오답·정답·근거·판정 로직) |
| `03-mvp-spec-and-risk-mitigation.md` | 5대 리스크 대응, 아키텍처, 캐시 DB, 8개 툴, 무료/유료 경계, 면책 |
| `live-api-verification-2026-11-18.json` | 라이브 검증 산출물(정규화 샘플·상태, **키 없음**) |
| `live-scenario-results-2026-11-18.json` | 대표 3품목 라이브 판정 산출물(응답시간·요건·리콜 포함, **키 없음**) |
| `04-live-scenario-report-2026-11-18.md` | 대표 3품목 라이브 판정 사람용 리포트 |
| `.env.example` | 키 템플릿(`.env`는 커밋 금지) |

## 실행

```bash
cd src
python3 -m import_compliance.cli --check-corpus
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

HTTP 서버(웹 UI + JSON API):

```bash
cd src
python3 -m import_compliance.server              # http://0.0.0.0:8787 · 작업 DB는 ../data/app.sqlite
python3 -m import_compliance.server --port 9000 --db /tmp/tck.sqlite
curl -s localhost:8787/v1/mcp | head
curl -s -X POST localhost:8787/v1/tools/assess_import_case \
  -H 'Content-Type: application/json' \
  -d '{"query":"합성니코틴 액상형 전자담배를 수입해 판매"}'
```

브라우저로 `http://localhost:8787/` 을 열면 사람용 화면(CLNS Check · CLNS Intelligence · CLNS API & MCP)이 나온다.

### 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `HOST` | `0.0.0.0` | 바인드 주소(`--host` 로 덮어쓰기) |
| `PORT` | `8787` | 포트. Render/Koyeb는 이 값을 자동 주입한다(`--port` 로 덮어쓰기) |
| `IMPORT_COMPLIANCE_DB` | `data/app.sqlite` | 작업 SQLite(판정 이력·쿼터·캐시). 없으면 기동 시 생성 |
| `IMPORT_COMPLIANCE_LIVE` | `0` | `1`이면 `.env` 또는 환경변수의 키로 실API 조회 |
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

- 영구 디스크가 없어 작업 DB(판정 이력·쿼터 카운터)는 재시작 시 초기화된다. 리콜 인덱스는 이미지에 있어 매 기동마다 다시 적재된다.
- 미접속 시 슬립되어 첫 요청이 30~60초 걸릴 수 있다.
- `.dockerignore`가 `.env`·`__pycache__`·테스트·도구·원본 CSV를 제외하므로 이미지에 API 키가 들어가지 않는다.
- 페이지는 외부 CDN 없이 인라인 CSS/JS만 쓰고 CSP(`default-src 'none'`)로 외부 로드를 막는다.
- 무료 쿼터는 브라우저별 클라이언트 ID(`localStorage`)당 250회/월이다. IP 단위 제한은 없으므로, 공개 트래픽이 커지면 리버스 프록시 단계의 레이트리밋이 필요하다.

## 테스트

```bash
cd src
python3 tests/test_engine.py      # 27 tests
python3 tests/test_http.py        # 3 tests (실제 소켓)
python3 tests/test_live_api.py    # 24 tests (네트워크 없이 고정 응답)
python3 tests/test_recall_index.py # 12 tests (리콜 CSV 파싱·적재·검색·인덱스 복사)
python3 tests/test_web.py         # 30 tests (브랜드·웹 UI·별칭·환경변수·모듈 엔트리포인트·키 비노출·UI 계약·레거시 브랜드 잔재)
```

합계 96건. 네트워크 없이 전부 통과한다.

## 구조

```
src/
  import_compliance/
    engine.py     판정 파이프라인(3단계·신선도·가드)
    corpus.py     코퍼스 로드·정규화
    models.py     데이터 모델
    policy.py     면책·금지 표현·티어 경계
    store.py      SQLite 캐시·쿼터·폴백·실API 게이트웨이
    live_api.py   공공 API 4종 어댑터(파싱·정규화·재시도·키 리댁션)
    recall_index.py  국표원 리콜 파일데이터(15040696·15054301) 적재·검색
    api.py        8개 툴 + MCP 매니페스트
    web_ui.py     사람용 단일 HTML 화면(외부 CDN 0, 인라인 CSS/JS)
    server.py     stdlib HTTP 서버(웹 UI·JSON API·배포용 환경변수)
    cli.py        CLI·코퍼스 자기검증·`--serve`
  traps_20.json   함정 20케이스(근거 54건)
  schema.sql      Postgres 이관용 DDL
  tests/
  tools/verify_live_apis.py   실API 4종 라이브 검증
  tools/run_live_scenarios.py 대표 3품목 라이브 실전 테스트 러너
  tools/build_corpus_doc.py   문서 자동 생성
Dockerfile        무료 클라우드 배포 이미지(python:3.12-slim)
render.yaml       Render Blueprint(free Web Service, 키는 sync:false)
.dockerignore     .env·캐시·테스트 제외(키가 이미지에 구워지지 않게)
```

## 갱신 규칙

코퍼스를 고치면 `python3 tools/build_corpus_doc.py`로 `02-ai-trap-corpus-20.md`를 다시 생성하고, 세 테스트를 모두 통과시킨 뒤 반영합니다.
