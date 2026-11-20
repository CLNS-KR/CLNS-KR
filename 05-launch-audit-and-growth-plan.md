---
title: "🔎 05. CLNS 런치 전수 점검 · 성장 전략 (2026-11-18)"
---

# 05. CLNS 런치 전수 점검 · 성장 전략

> 점검 시각 2026-11-18 03:01~03:06 KST. 대상은 라이브 `https://clns-kr.onrender.com`(Render free·Singapore)와 공개 저장소 `https://github.com/CLNS-KR/CLNS-KR`(`main`@`fcd7836`). 응답시간은 워밍 상태 3회 측정값이다. API 키 값은 이 문서와 점검 산출물 어디에도 없다.

## 0. 세 문장 결론

1. **데이터는 진짜로 붙는다.** 세관장확인(관세청 15101589)·식약처 수입식품(15058273·15073949)·법제처 법령 3종 모두 실호출에 성공했고, 값도 문서 04의 기록과 일치한다. HS `8414519000` 요건 6건, 오메가3 수입신고 672건·부적합 1건, 관세법 제226조 시행일 2026-10-02까지 그대로 나온다.
2. **MCP는 아직 MCP가 아니다.** `GET /v1/mcp`는 JSON 매니페스트 한 장이고 `POST /v1/mcp`(initialize)는 404다. 이대로 Smithery·Cursor·Claude에 올리면 "목록에는 보이는데 연결은 안 되는 서버"가 된다. 고치는 데 반나절이면 충분하다(`patches/mcp_http.py`).
3. **유입 장치가 0이다.** `robots.txt`·`sitemap.xml`·`llms.txt` 전부 404, OG 태그 없음, 계측 없음, 저장소에 라이선스·라이브 URL 없음. 지금은 "만들었는데 아무도 못 찾는" 상태이고, 이걸 채우는 게 MCP 등록보다 먼저다.

## 1. 라이브 서버 점검

### 1-1. 엔드포인트

```table
title: 엔드포인트 점검 (03:01 KST, 각 3회)
headers: [경로, 응답, 시간, 판정]
rows:
  - ["/", "200 · 46,033B · brotli", "0.23s", "정상 · 단일 페이지"]
  - ["/healthz", "200 · {live:true}", "0.22s", "정상"]
  - ["/v1/meta", "200 · 2.1KB", "0.22s", "정상 · 코퍼스 1.0.3·20케이스"]
  - ["/v1/mcp", "GET 200 · 3.9KB, POST 404", "0.22s", "JSON-RPC 불가 ← 핵심 결함"]
  - ["/robots.txt", "404 JSON", "0.22s", "없음"]
  - ["/llms.txt", "404 JSON", "0.22s", "없음"]
  - ["/sitemap.xml", "404 JSON", "0.22s", "없음"]
  - ["/mcp · /.well-known/*", "404", "0.22s", "없음"]
  - ["OPTIONS /v1/tools/*", "501", "0.22s", "CORS 미지원"]
```

- 지연은 문제없다. 한국에서 0.22초, HTTP/2 + brotli 압축이 걸려 있고 HTML은 46KB다.
- 404 본문이 `{"ok": false, "error": "not_found"}` JSON인 점은 로봇 파일에는 불리하다. 크롤러는 `text/plain` 404를 받아도 "파일 없음"으로 처리하지만, 사람이 보면 API 에러처럼 보인다.
- `/favicon.ico`는 204(빈 응답)로 처리되고 실제 아이콘은 data URI SVG다. 동작은 한다.

### 1-2. 실제 품목 2건 실호출 결과

**품목 A — 중국산 무선 선풍기, HS `8414519000`, 판매 목적, 무선 송신 없음**

- `assess_import_case` → 종합 `low_risk`(0.50s). 잡힌 쟁점은 TRAP-06 하나, 사실관계 `rf_tx=no`로 `low_risk` 판정. 이유 문구도 정확하다.
- 같은 HS로 `lookup_hs_requirements` → 세관장확인 **6건**(0.79s, `result_code 00`). 전기용품 및 생활용품 안전관리법 5개 기관(기술표준원·KTR·KTL·KTC·한국제품안전협회, 요건확인서, 2024-07-30) + 전파법(국립전파연구원, 방송통신기기인증확인서, 2020-04-06). 판정은 `check_likely`로 올라간다.
- `8414511000`(같은 6자리, 다른 10자리)로는 0건 + `info_needed`. TRAP-19(“6자리로 끝”) 방어가 실데이터로 증명된다.
- **여기서 결함이 하나 드러난다(1-4절).** `assess_import_case`는 같은 HS를 받고도 요건 6건을 응답에 담지 않고, 종합 판정을 `low_risk`로 남긴다.

**품목 B — 미국산 오메가3 건강기능식품, HS `1504200000`, 판매 목적**

- `assess_import_case` → `info_needed`(0.53s). TRAP-01(수입·판매업 등록) + TRAP-09(표시·광고 심의).
- `lookup_hs_requirements` → 세관장확인 **2건**: 야생생물 보호법(국제적멸종위기 동식물 수입허가서) + 수입식품안전관리 특별법(수입신고확인증). 공개 저장소 산출물의 2건과 일치.
- `check_food_cosmetics`(오메가3, 건강기능식품) → `food_import_live.state = "live"`. 수입신고 이력 **672건**(오메가3-프로/캐나다/2023-06-28/접수 202300400281 등), 검사부적합 **1건**(초임계 rTG 오메가3/미국/LIFEBLOOM CORP./EPA·DHA 합 58%, 기준 80~120%), 제품DB **0건**(한국어 질의 한계 — 영문 제품명으로 넣어야 걸린다).
- `get_legal_basis`(관세법 제226조) → `law_live.state = "live"`, 시행 **2026-10-02 현행**, 조문 3개 항 본문까지 반환(4.59s).
- `lookup_recall`(전지) → 로컬 인덱스 5건 표시(전체 22건), `fresh:false` + 등록일 범위 고지 정상.

**결론: 공공 API 3종은 “오류 없이 붙고, 결과 품질도 쓸 만하다.”** 다만 그 값을 사용자에게 전달하는 경로(종합 판정·화면)에 구멍이 있다.

### 1-3. 실API 상태 요약

```table
title: 실시간 공공 API 3종 (라이브 응답 기준)
headers: [소스, 상태, 실측값, 지연]
rows:
  - ["관세청 15101589 세관장확인", "live (00)", "8414519000 → 6건", "0.79s"]
  - ["식약처 15058273·15073949", "live", "오메가3 신고 672건·부적합 1건", "9.2~12.9s"]
  - ["법제처 lawSearch/lawService", "live", "관세법 226조 시행 2026-10-02", "2.3~4.6s"]
```

### 1-4. 판정과 근거가 어긋나는 지점 (P0)

`POST /v1/tools/assess_import_case`에 HS 10자리를 넣어도, 응답에는 요건 목록이 없고 판정은 요건을 보지 않는다.

- 실제 응답: `verdict.code = "low_risk"`, `answer.headline = "현재 정보상 가능성이 낮은 쟁점: 무선기기의 전파 적합성평가"`, 그런데 `data_provenance.sources[customs_requirements] = {state: "live", item_count: 6}`.
- 같은 HS를 `lookup_hs_requirements`로 물으면 6건이 나오고 판정은 `check_likely`. **같은 엔진이 같은 HS에 서로 다른 결론을 낸다.**
- 원인은 코드에 있다. `engine.assess()`는 게이트웨이가 받은 실데이터를 응답에서 버리고(`data` 키 제외) 상태만 남기며, `tool_assess_import_case`는 `_customs_live()`를 부르지 않는다. `lookup_hs_requirements`만 `hs_requirements_live`를 붙이고 판정을 올린다.
- 사용자 관점: 품목명만 넣고 화면을 쓰면 아래 “세관장확인 요건” 표가 따로 떠서 보이지만(웹 UI가 `lookup_hs_requirements`를 별도 호출), **API·MCP로 쓰는 쪽은 요건 6건을 영영 못 본다.** AI가 이 API를 부르면 “가능성 낮음”만 인용한다.

### 1-5. 성능 — 식약처 툴만 느리다

- 판정 0.50s, HS 조회 0.79s, 리콜 0.25s, 법령 2.3~4.6s. 이 넷은 문제없다.
- **`check_food_cosmetics`는 9.21s / 12.85s.** 같은 품목을 다시 불러도 9.21s — 캐시가 없다. 내부에서 MFDS 3개 오퍼레이션(제품DB·수입신고·부적합)을 순차 호출한다.
- 화면은 `Promise.all`로 네 요청을 다 기다린 뒤 한 번에 그린다. 그래서 식품·건기식·화장품 품목은 **결과 카드 전체가 10초 뒤에** 나타난다. “10초 리스크 체크”라는 문구와 정면으로 충돌한다.
- 문서 03에 이미 설계된 7일 TTL 캐시가 MFDS·법령 경로에는 적용되지 않은 상태다.

### 1-6. MCP 표준 호환성 — 지금은 매니페스트, MCP 아님

확인한 사실:

- `GET /v1/mcp` → 200, 3,923B. 최상위 키가 `name`·`version`·`description`·`serverInfo`·`tools`뿐이다. `jsonrpc`·`protocolVersion`·`capabilities` 없음.
- `POST /v1/mcp`에 `initialize`(JSON-RPC 2.0, `Accept: application/json, text/event-stream`) → **404 `{"ok":false,"error":"not_found"}`**. 서버의 `do_POST`는 `/v1/tools/*`만 받는다.
- `/mcp`, `/.well-known/mcp/server-card.json`, `/.well-known/glama.json` → 전부 404. Smithery가 스캔 실패 때 쓰는 정적 카드 경로도 없다.
- `OPTIONS /v1/tools/assess_import_case` → 501. CORS 헤더가 없어 브라우저 기반 클라이언트(Glama 플레이그라운드 등)는 호출 자체가 막힌다.
- 툴 8종의 스키마는 깔끔하다(`assess_import_case`, `lookup_hs_requirements`, `check_kc_certification`, `check_food_cosmetics`, `lookup_recall`, `get_legal_basis`, `explain_trap`, `get_service_meta`). **스키마는 준비됐고 전송 계층만 없다.**

필요한 보완(우선순위 순):

1. `POST /v1/mcp`(또는 `/mcp`)에서 JSON-RPC 2.0 처리: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`. 응답은 `application/json` 한 덩어리로 충분하다(SSE 스트리밍은 선택). 초안은 `patches/mcp_http.py`에 있다 — 그대로 붙이면 된다.
2. `GET /.well-known/mcp/server-card.json` 정적 카드(초안: `patches/server-card.json`).
3. CORS 헤더(`OPTIONS` + 모든 응답에 `Access-Control-Allow-Origin: *`).
4. 툴 메타데이터 보강: `title`, `annotations`(`readOnlyHint: true`, `openWorldHint: true`, `destructiveHint: false`), 가능하면 `outputSchema`. Glama는 이걸 점수로 매기고, Claude 커넥터 심사도 대조한다.
5. `GET /v1/mcp`는 405로 바꾸고 매니페스트는 `/v1/mcp/manifest`로 옮긴다. GET이 매니페스트인 서버는 스캐너를 헷갈리게 한다.

지금 상태로 각 채널에 올리면: 공식 레지스트리는 **메타데이터만 등록되고**(URL 접근성은 검사하지 않는다) 클라이언트가 붙을 때 실패한다. Smithery는 `initialize` 스캔에서 404를 받고 실패한다. Glama는 Docker로 띄운 뒤 `tools/list` 인트로스펙션을 해야 목록에 오르는데(문서상 빌드 실패 시 배포 보류), 우리 서버는 그 교환에 응답하지 못한다. mcp.so는 저장소 기반이라 등록은 되지만 “연결 안 되는 서버”로 남는다. → **등록은 MCP 전송 계층 구현 다음에 하는 게 맞다.**

### 1-7. 화면·UX (데스크톱 1919px / 모바일 390px 실측)

- **모바일 레이아웃은 정상.** 1열로 접히고 폼·버튼·카드가 깨지지 않는다. 다만 **상단 탭 3번째가 `CLNS API & MC…`로 잘린다.** 가로 스크롤 영역이지만 스크롤 가능하다는 표시가 없다. 390px에서 탭 폭을 줄이거나 2줄 허용을 권한다.
- **표는 모바일에서 가로 스크롤.** `table{min-width:520px}` + 래퍼 `overflow-x:auto`라 넘치지는 않지만, 5열 요건 표는 폰에서 옆으로 밀어야 한다. 요건 표는 모바일에서 2행 카드형(법령/기관/서류/시작일)으로 바꾸는 게 읽기 좋다.
- **결과 상단 문장이 중복된다.** 화면에 `입력한 품목: 중국산 무선 선풍기를 수입해 판매하려고 해 수입해서 판매`로 나온다. `buildQuery()`가 뒤에 붙인 `수입해서 판매`가 그대로 다시 출력되기 때문이다.
- **판정 요지와 아래 표가 따로 논다.** 위에는 “무선기기의 전파 적합성평가”만, 아래에는 “요건 6건” 표. 처음 보는 사람은 둘의 관계를 모른다. 판정 요지 첫 줄에 “세관장확인 요건 6건이 조회되었습니다(전안법·전파법)”를 넣어야 한다.
- **대기 10초 동안 화면이 비어 있다.** 스피너 한 줄만 돌고, 도착한 섹션부터 그리지 않는다.
- 무료 한도 배지는 “확인 중” → “이번 달 무료 호출 250회 남음”으로 정상 치환된다(1초 내). 다만 이 숫자는 서버 재시작마다 초기화되므로 사실상 보장이 아니다.
- 접근성 기본기는 갖췄다(`role="tab"`/`tablist`, 라디오 그룹, `:focus-visible`, `sr` 클래스). 다만 라디오마다 `radio`와 `clickable`이 중복 노출되는 마크업이라 스크린리더에서 같은 항목이 두 번 읽힐 수 있다.

### 1-8. 잘 된 점 (유지할 것)

- **보안 기본기**: CSP `default-src 'none'`(인라인만 허용), `X-Frame-Options: DENY`, `referrer-policy: no-referrer`, `nosniff`. 외부 CDN 0개.
- **개인정보 설계**: 이름·연락처·이메일을 받지 않고, `log_message`를 꺼서 접속 IP를 앱 로그에 남기지 않는다. 저장은 `client_id`(브라우저 난수) + 품목 텍스트뿐. 화면 문구와 실제 동작이 일치한다.
- **정직한 0건 처리**: “0건은 요건·이력 없음이 아니다”가 응답과 화면 양쪽에 붙는다. 이건 경쟁 서비스에 잘 없는 차별점이다.
- **리콜 스냅샷 고지**: `fresh:false` + 등록일 범위(2019-10~2022-07) + 배포본 날짜를 항상 함께 표시.
- **법령 근거의 완성도**: 조문·시행일·원문 URL·`verified_on`이 붙고, 관세법 제226조는 시행일까지 법제처 현행과 일치.
- **엔지니어링**: 표준 라이브러리만 사용, 96개 테스트 통과(27+3+24+12+30), `--check-corpus` OK(1.0.3/20케이스), 비루트 Docker + HEALTHCHECK, `.dockerignore`가 `.env` 차단.

### 1-9. 고칠 것 목록

**P0 — 오늘 안에 (반나절~1일)**

- **P0-1 MCP 전송 계층 없음.** `POST /v1/mcp` 404. → `patches/mcp_http.py` 붙이기 + server-card + CORS.
- **P0-2 식약처 툴 9~13초, 캐시 없음.** → 7일 TTL 캐시 + 3개 오퍼레이션 병렬화 + 화면 점진 렌더.
- **P0-3 종합 판정이 세관장확인 요건을 무시.** HS 10자리가 있으면 `hs_requirements_live`를 붙이고 `requirement_count > 0`이면 최소 `check_likely`로 올린다.

**P1 — 이번 주**

- **P1-1 로봇 파일 3종 없음**(robots/llms/sitemap). 초안 3개를 `patches/`에 넣어 뒀다.
- **P1-2 OG·canonical·JSON-LD 없음.** 공유 미리보기 비고, `/index.html` 중복 색인 위험.
- **P1-3 실시간 소스가 살아 있는데 “연결 실패”로 표기.** `check_food_cosmetics` 응답에서 `food_import_live.state="live"`인데 `data_provenance`는 `mfds_import_food: unavailable("실시간 소스 연결 실패")`. 한 응답이 서로 반대말을 한다.
- **P1-4 화면 입력 문장 중복**(위 1-7절).
- **P1-5 MCP 안내 문구 과장** — “툴 목록을 그대로 등록할 수 있습니다”. 구현 전까지 “툴 정의 JSON(참고용)”으로.

**P2 — 시간 될 때**

- 에러를 HTTP 200으로 반환(`invalid_argument`, `unknown_tool`). 모니터링이 실패를 성공으로 읽는다.
- `OPTIONS` 501 → CORS 응답.
- 무료 한도(250회/월)가 사실상 무집행(컨테이너 SQLite 초기화 + 클라이언트 지정 ID). 문구를 낮추거나 서버측 세션으로.
- HTML `Cache-Control: no-cache` → `public, max-age=60, s-maxage=300, stale-while-revalidate`로 엣지 캐시. 슬립 중 첫 방문자에게 캐시된 HTML을 주는 효과가 크다.
- 콜드스타트 안내 없음(Render 무료 15분 유휴 후 슬립, 첫 요청 30~60초). 안내 문구 + 타임아웃 + 재시도.
- `_mfds_live()`가 `has_customs`로 게이트된다(`has_mfds` 없음). 지금은 같은 키라 동작하지만 의미상 어긋난다.
- findings가 비었을 때 `_freshness_cap`의 안내가 덮어써진다(`engine.assess` 239~240줄).

## 2. GitHub 공개 저장소

### 2-1. 검증한 것

- **공개 상태**: `public`, 2026-11-17 17:25Z 생성, 커밋 1개(`fcd7836`, 17:35Z), 파일 30개, 스타·포크 0, 이슈 0. 기본 브랜치 `main`.
- **시크릿**: `.env` 없음. 로컬 `.env`의 실제 키 값 2종(`DATA_GO_KR_SERVICE_KEY` 64자, `LAW_GO_KR_OC` 8자)을 저장소 30개 파일 본문과 전부 대조 → **일치 0건**. 코드·문서·산출물에는 변수명과 `serviceKey` 파라미터 이름만 남아 있다.
- **개인정보**: 오너 이름·전화·메일·사업자 정보 없음. 나온 주소는 공공기관 문의처(`safetykorea@korea.kr`)뿐이다.
- **코드 동일성**: 공개 blob SHA 30개를 로컬 워킹트리와 전부 비교 → **불일치 0개**. 배포본 동작(툴 8종·코퍼스 1.0.3)도 같아서 라이브와 저장소 코드는 사실상 같은 것으로 본다(커밋 SHA만 다름 — 커밋 메타 차이).
- 이미지 위생: `.dockerignore`가 `.env`·테스트·도구·원본 CSV를 제외, Dockerfile은 비루트 + HEALTHCHECK, `render.yaml`은 `sync: false`로 키를 저장소에 두지 않는다. **이 부분은 손댈 필요 없다.**

### 2-2. 빠진 것 (등록·유입에 직접 걸리는 것들)

- **LICENSE 없음.** Glama·mcp.so는 라이선스를 목록 요건으로 보고, 없으면 재사용·평가가 막힌다. MIT 한 장이면 끝난다. (어떤 라이선스인지는 사용자가 정할 문제 — 아래 4절 결정 사항)
- **저장소 메타 비어 있음**: description, homepage, topics 모두 없음. mcp.so는 homepage가 없으면 GitHub만 링크하고, 검색으로 발견될 구실이 사라진다.
- **README에 라이브 URL이 없다.** `<서비스>.onrender.com` 플레이스홀더만 있다. “지금 돌아가는 서비스”를 한 줄도 안 알려준다. 스크린샷도 없다.
- **CI 없음**(`.github/` 없음). 테스트 96개가 있는데 아무도 자동으로 안 돌린다.
- **불필요한 커밋 산출물**: `data/raw/recall_15040696.csv`(180KB)·`recall_15054301.csv`(300B)·`live-scenario-results-2026-11-18.json`(364KB). 동작에는 문제없다. 다만 원본 CSV는 이 프로젝트의 “원본 API 재전송 금지” 문구와 헷갈릴 수 있으니(공공데이터라 법적으로는 문제없음), 굳이 저장소에 둘 이유는 약하다.
- **문서 불일치**: 04 문서는 “전체 테스트 63건(test_engine 27·test_http 3·test_live_api 23·test_recall_index 10)”이라고 적었지만 실제는 96건(test_web 30 포함)이다. README는 96으로 맞다. 04만 갱신하면 된다.

## 3. 다음 단계 성장·유입 전략 (2026-11 실측)

### 3-1. 채널 지도

```table
title: 유입 채널 — 2026-11-18 확인 조건
headers: [채널, 지금 상태, 조건(실측), 익명성]
rows:
  - ["공식 MCP Registry", "등록 가능", "remotes.streamable-http + 공개 URL, 네임스페이스 소유확인", "개인 핸들 · 또는 조직/도메인"]
  - ["Smithery", "불가", "initialize 응답 필수, 스캔 UA SmitheryBot", "핸들로 가능"]
  - ["Glama", "불가", "GitHub 권한 확인 + Docker 빌드 + tools/list", "조직 계정으로 가능"]
  - ["mcp.so", "등록 가능", "저장소 URL 필수, 무료(심사) 또는 $39", "조직 계정으로 가능"]
  - ["PulseMCP", "중단", "2026-09-03부터 제출 중단, 레지스트리 자동 수집", "—"]
  - ["구글 서치콘솔", "가능", "URL 접두사 + HTML/메타 소유확인(DNS 불가)", "—"]
  - ["네이버 서치어드바이저", "가능", "호스트 단위 등록 + head 메타/HTML 파일", "—"]
  - ["커스텀 도메인", "없음", "Render Hobby 2개 무료, 도메인 값 별도", "WHOIS 프라이버시"]
```

### 3-2. MCP 채널 — 지금 결제할 수 있는 곳과 순서

- **공식 MCP Registry**(`registry.modelcontextprotocol.io`)는 아직 preview지만 무료·무심사이고, PulseMCP가 재개하면 여기서 자동 수집한다. remote-only 서버는 `packages` 없이 `remotes`만으로 등록된다. `name`은 GitHub 인증이면 `io.github.CLNS-KR/clns` 형식, 도메인이 있으면 DNS/HTTP 인증으로 `com.example/...` 형식. description은 **100자 제한**, version은 배포마다 새 값(불변). 등록 자체는 URL 접근성을 검사하지 않지만, **클라이언트는 붙으려다 실패한다** → MCP 전송 계층 먼저.
- **Smithery**는 URL 게시형이다. 요건은 ① 공개 HTTPS ② Streamable HTTP ③ 무인증 `initialize` 응답. 스캔이 403/404면 실패하고, 그때 `/.well-known/mcp/server-card.json` 정적 카드로 우회할 수 있다. 지금 우리 서버는 ①만 만족.
- **Glama**는 GitHub OAuth로 저장소 쓰기 권한을 확인하고, Dockerfile로 빌드·실행한 뒤 `tools/list`를 실제로 호출해 스키마를 수집한다. 문서가 명시한 실패 조건은 “재현 가능한 빌드 실패”이고, 그때는 프로필만 남고 목록·검색에서 빠진다 — 우리 서버는 빌드는 되지만 프로토콜 교환이 안 되므로 같은 결과를 예상해야 한다. 조직 저장소라 `glama.json`으로 소유권을 주장해야 하고, 툴 설명 품질(TDQS)이 공개 점수로 붙는다 — 우리 툴 설명은 길고 근거가 있어 이 점수는 잘 나올 재료다.
- **mcp.so**는 저장소 URL 하나로 목록을 만든다. README가 곧 목록이므로 라이선스·설치 스니펫·툴 목록·스크린샷을 README에 넣고 제출한다. 무료는 심사, $39는 즉시+ verified.
- **Claude 커넥터·ChatGPT 커넥터**는 지금 단계에서 권하지 않는다. OAuth 구현, 개인정보 처리방침, 심사, 도메인 소유 증명(`.well-known/openai-apps-challenge`)이 필요하다. **익명 운영 원칙과 정면으로 부딪힌다**(연락 이메일·사업자 정보 요구). 매출이 확인된 뒤의 일이다.
- **익명 유지 관점(중요)**: 공식 레지스트리 네임스페이스는 인증 방식이 정한다. `mcp-publisher login github`은 **개인 네임스페이스(`io.github.<개인핸들>`)만** 준다(디바이스 플로가 GitHub App 토큰이라 조직 멤버십을 읽지 못하는 알려진 제한, 이슈 #1468). 조직 네임스페이스(`io.github.CLNS-KR/*`)는 GitHub Actions OIDC나 조직 read 권한 PAT로만 발급된다. 도메인을 사면 DNS TXT(에이펙스) 인증으로 `kr.clns/*` 같은 도메인 네임스페이스를 쓸 수 있어 **개인 핸들이 전혀 드러나지 않는다.** → 익명을 지키려면 ① 조직 네임스페이스 + GitHub Actions 경로, 또는 ② 도메인 인증이 맞다.
- **stdio 병행이 필요하다.** Glama·mcp.so의 기본 목록은 “로컬에서 실행되는 서버”를 기대한다. `python -m import_compliance.mcp_stdio` 같은 stdio 엔트리포인트를 하나 더 두면 HTTP 서버 하나로 양쪽 목록에 다 들어간다(코드 30줄 수준).

### 3-3. 검색 유입 — 페이지가 하나뿐인 게 근본 문제

- **구글**: 도메인 속성은 DNS가 필요해 불가하지만 URL 접두사 속성은 HTML 파일 업로드나 메타태그로 확인할 수 있다. 우리는 서버를 직접 고칠 수 있으므로 `/google{토큰}.html` 라우트 하나만 추가하면 즉시 등록된다. 사이트맵 제출은 그다음.
- **네이버**: 사이트 등록이 **호스트 단위**이고, 소유확인은 ① head 안의 메타태그 ② 루트의 HTML 파일 두 가지다. 자바스크립트·meta refresh 리다이렉트는 인정하지 않는데, 우리 페이지는 서버가 내려주는 정적 HTML이라 문제없다. 네이버는 robots.txt를 직접 요구하고 사이트맵 링크가 상대경로거나 호스트가 다르면 수집하지 않는다 — 절대 URL로 넣어야 한다.
- **`.onrender.com` 제약**: 두 검색엔진 모두 “호스트 단위” 등록이라 기술적으로는 등록된다. 문제는 ① 무료 플랜 슬립(첫 요청 30~60초, 크롤러가 기다리지 않는다) ② 공유 호스트라 브랜드 신뢰가 약함 ③ 나중에 도메인을 바꾸면 색인·등록을 처음부터 다시 해야 함. **지금 잡을 유입의 대부분이 검색이라면 도메인은 선택이 아니라 비용이다.**
- **정직한 전제**: 지금 사이트는 URL이 하나다. 색인돼도 “CLNS”라는 이름으로만 걸린다. 한국 셀러가 검색하는 말은 “선풍기 수입 요건”, “오메가3 수입신고”, “세관장확인” 같은 **품목 단어**다. 검색 유입은 콘텐츠를 늘리기 전엔 거의 0이다 → 3-4절.

### 3-4. pSEO — 품목별 무료 체크 페이지

구조 제안(서버 렌더링, JS 없이 본문이 보이게):

- `/p/{품목-slug}` — 예: `/p/usb-mini-fan`. H1 “무선 선풍기 수입 요건”, 본문: 세관장확인 요건 표, KC 인증 유형, 전파법 해당 여부, 식약처 이력 건수(해당 시), 리콜 건수, 근거 조문과 시행일, “최종 확인 2026-11-18”, 면책.
- `/hs/{10자리}` — 예: `/hs/8414519000`. “HS 8414519000 세관장확인 요건 6건”. 요건 표 + 같은 6자리에서 0건/6건이 갈리는 예시(TRAP-19 교육 콘텐츠로도 쓸 수 있다).
- 첫 배치는 30~50개. 한국 수입 신고가 많은 품목군(건기식·화장품·전자담배·완구·배터리·식품용기·마스크·선풍기·가습기·조명)으로 시작하고, 이후 네이버 키워드도구·데이터랩에서 실제 검색량이 확인된 품목만 늘린다.
- 데이터는 조회 시점에 실API + 7일 TTL 캐시로 만들고, 페이지에 `lastmod`를 노출한다. 품목이 늘어도 손이 안 가는 구조다.
- **주의 3가지**: ① 04·01 문서의 “원본 1:1 재전송 금지” 원칙과 충돌해 보인다 — 다만 15101589는 data.go.kr 기준 **이용허락범위 제한 없음**이고, 요건 표는 가공·정규화한 판정이라는 성격이 강하다. 정책 문구를 “판정 결과 + 근거 요건 표(출처 표시)”로 한 줄 정리하면 정합적이다. ② 식약처 계열은 문서 01의 결론대로 **유료화 전 사전 승낙**이 필요하니, pSEO에 식약처 데이터를 싣는 건 무료 베타 범위에서 하고 유료 전환 시 재확인. ③ 얇은 중복 페이지가 대량 생산되면 색인 품질이 떨어진다 — 요건 0건 페이지는 `noindex`로 두는 게 안전하다.

### 3-5. 경쟁 구도 (공식 레지스트리 실측, 2026-11-18)

- `search=korea` 20건, `search=customs` 20건, `search=tariff` 20건을 훑었다. **한국 수입 “요건·인증·리콜”을 다루는 서버는 없다.**
- 가장 가까운 경쟁: `ai.seldons/korea-business-trade` (v1.2.0, 2026-09-02 등록). 국세·공정위 등록정보 + HS + landed cost. 툴 10개 중 2개 무료, 나머지는 크레딧(Starter $29/3,000, Team $149/20,000, Scale $599/100,000). streamable-http로 이미 붙어 있다. **가격·과금 모델의 선례**로 삼을 만하다.
- 인접: `app.sallim/korea-realty`(부동산), `com.koreanics/korea-law-acts-and-bills`(법안·법령 영문), `dev.workers.deanhiki.krtools/korean-tools`(주소·사업자번호).
- CLNS의 빈틈은 분명하다: **“세관장확인 요건 + 식약처 수입 이력 + 국내 리콜 + 근거 조문”을 한 번에, 무료로, 익명으로.** 다만 이 우위는 “MCP로 실제 붙는 순간”에만 생긴다 — 지금은 붙지 않는다.

### 3-6. 계측 — 지금은 유입을 셀 방법이 없다

- `log_message`를 완전히 껐고 분석 도구도 없다. 유일한 지표는 Render 대시보드 로그(플랫폼 레벨, IP 포함)다.
- 개인정보 원칙을 지키면서 최소 계측: IP 없이 **일별 카운터**(경로, 툴, 판정 코드, 0건/실패 여부)를 SQLite에 남기고 `GET /v1/stats`로 공개. 재배포 시 초기화되는 한계는 “일별”이면 감수할 만하다.
- 이 카운터가 곧 상품 개선의 입력이 된다 — “어떤 품목을 넣다가 0건을 맞는지”가 pSEO 우선순위이고, “어떤 툴이 실패하는지”가 장애 감지다.

## 4. 우선순위 로드맵

**이번 주 (총 1~1.5일)**

1. `POST /v1/mcp` JSON-RPC + server-card + CORS (반나절). 끝나면 `curl`로 `initialize`/`tools/list`/`tools/call` 3종 자체 검증.
2. `robots.txt`·`sitemap.xml`·`llms.txt` 라우트 + head에 canonical·OG·JSON-LD (2시간).
3. 식약처 7일 캐시 + 병렬 호출 + 화면 점진 렌더 (반나절). 9초 → 1~4초.
4. `assess_import_case`에 `hs_requirements_live` 포함 + 요건 건수를 판정에 반영 (2시간).

**2주**

5. `/p/{slug}` pSEO 30개 + 사이트맵 자동 생성 + `noindex` 규칙.
6. 일별 카운터 + `/v1/stats`.
7. README 정비(라이브 URL·스크린샷·툴 표·설치 스니펫) + LICENSE + 저장소 description/homepage/topics + GitHub Actions로 테스트 96개 자동 실행.
8. 구글 서치콘솔·네이버 서치어드바이저 등록, 사이트맵·수집 요청.

**1개월**

9. 공식 MCP Registry 등록(`io.github.CLNS-KR/clns`) → Smithery URL 게시 → Glama 제출(`glama.json` + 라이선스) → mcp.so 제출. 등록 문구(이름·100자 설명·아이콘·스크린샷)는 한 벌로 통일.
10. stdio 엔트리포인트 추가로 “로컬 MCP 서버” 목록에도 노출.
11. 커스텀 도메인 전환 + 서치콘솔 도메인 속성, onrender 주소는 canonical로 정리.
12. 유료 전환 실험: 대기자 폼(이메일만) 또는 크레딧 모델 — 다만 이건 개인정보 수집을 새로 시작하는 결정이라 사용자 판단이 먼저다.

**유입 확인 후 3단계 확장 로드맵 (2026-11-18 사용자 요청·합의)**

11/21 이후 검색·MCP 유입이 확인되면 새 서비스를 또 열기보다 CLNS에 레고 블록처럼 다음 3가지를 순차 결합한다.
1. **앞단(입력 편의)**: 알리·타오바오·아마존·아이허브 상품 URL을 넣으면 품목명·성분·원산지를 자동 추출해 CLNS 체크로 연결.
2. **옆단(비용·세금)**: 인증·통관 체크 옆에 예상 관세·부가세, 목록통관 한도($150/$200), 인증 대략 비용·소요 기간 안내 추가.
3. **뒷단(수익화 연결)**: 체크 완료 유저 대상 인증 대행·관세사 상담 제휴 연결(리드) — 단, 실제 수익·제휴 진행 전 겸업 금지 및 식약처·관세청 사전 확인 필수.

**사용자가 정해야 하는 것 3가지** (제가 임의로 정하지 않았다)

- **도메인 구매**: 연 1~2만 원 + WHOIS 프라이버시. 검색·MCP 등록의 전제. 이름은 익명 유지 가능(“clns.kr” 등).
- **라이선스**: MIT(가장 무난, Glama·mcp.so 요건 충족) vs 소스 공개·재사용 제한. 회사 겸업 규정과 무관하게 익명 조직 명의로 가능.
- **연락 창구**: 지금은 문의 수단이 0이다. 디렉터리 다수가 연락 이메일을 요구하고, 사용자 문의도 받을 곳이 없다. 익명용 메일 하나(예: 전용 Gmail)를 열 것인지 결정 필요. 열지 않으면 Claude·ChatGPT 커넥터는 포기하는 셈이다.

## 5. 바로 붙일 수 있는 파일 (아직 배포 안 함)

`projects/import-compliance/patches/`에 초안을 넣어 뒀다. 저장소·라이브에는 **아무것도 반영하지 않았다.**

- `robots.txt` — 검색 로봇 허용 + AI 크롤러 허용 + 사이트맵 링크.
- `sitemap.xml` — 현재 1개 URL. pSEO 붙일 때 동적 생성으로 교체.
- `llms.txt` — AI 크롤러용 진입점(서비스 요약·엔드포인트·읽는 법).
- `head_meta.html` — canonical, OG, X 카드, JSON-LD, 검색 소유확인 태그 자리.
- `mcp_http.py` — Streamable HTTP JSON-RPC 최소 구현(initialize/tools/list/tools/call) + server.py 라우팅 6줄.
- `server-card.json` — Smithery 스캔 실패 시 쓰는 정적 카드.
- `fix-notes.md` — 1-4·1-5절 결함의 원인 코드 위치와 수정 방향 4건.

## 6. 한계·미확인 (추정으로 채우지 않은 것)

- **콜드스타트는 직접 못 봤다.** 점검 중 서버가 계속 워밍 상태였다(0.22초). Render 문서 기준 15분 유휴 후 슬립·첫 요청 30~60초이며, 실측하지 않았다.
- **검색 색인 여부 미확인.** 배포 1시간 뒤라 어떤 검색엔진에도 안 잡힌 상태이고, `site:` 조회로는 판정할 수 없었다. 등록 후 2~4주 관찰이 필요하다.
- **모바일은 외부 렌더러(390px)로 캡처**했다. 실제 iOS Safari·안드로이드 크롬에서의 키보드 동작, 100vh 처리, 하단 탭 가림은 별도 확인 필요.
- **Glama가 HTTP 서버를 어떻게 실행하는지 문서에 명시가 없다.** 저장소를 클론해 Dockerfile로 빌드·실행 후 인트로스펙션한다는 것까지만 확인. stdio 엔트리포인트를 같이 두는 이유다.
- **식약처 유료화 사전 승낙, 관세청 재가공 문의**는 여전히 미완(문서 01의 체크리스트 그대로). 유료 전환 전에 끝내야 한다.
- 04 문서의 테스트 건수(63→96), 02 문서의 코퍼스 표기 등 문서 간 불일치는 04만 고치면 정리된다.

## 7. 재현

라이브 점검은 아래로 다시 돌릴 수 있다(모두 자격증명 불필요).

- `curl -s -o /dev/null -w "%{http_code} %{time_total}\n" https://clns-kr.onrender.com/{healthz,v1/meta,v1/mcp,robots.txt,llms.txt,sitemap.xml}`
- `curl -s -X POST https://clns-kr.onrender.com/v1/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0.1"}}}'` → 현재 404
- `curl -s -X POST https://clns-kr.onrender.com/v1/tools/lookup_hs_requirements -H 'Content-Type: application/json' -d '{"hs_code":"8414519000"}'`
- `curl -s -X POST https://clns-kr.onrender.com/v1/tools/check_food_cosmetics -H 'Content-Type: application/json' -d '{"product_name":"오메가3","kind":"health_functional","purpose":"resale"}'`
- 저장소 검증: `git hash-object`로 로컬 30개 파일 SHA를 GitHub API `git/trees/main`의 blob SHA와 비교(전부 일치), 로컬 `.env` 값으로 저장소 본문 grep(일치 0).
- 로컬 테스트: `cd src && python3 tests/test_engine.py && python3 tests/test_http.py && python3 tests/test_live_api.py && python3 tests/test_recall_index.py && python3 tests/test_web.py` → 96건 OK, `python3 -m import_compliance.cli --check-corpus` → OK.
