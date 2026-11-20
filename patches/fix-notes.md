# CLNS 소소한 버그·개선 4건 메모

> **2026-11-18 반영 완료** — 아래 1~4절 항목은 `src/import_compliance/`(api·store·server·web_ui)
> 와 `src/tests/test_patches_p0_p1.py` 에 반영되었고 137개 테스트가 통과했다.
> 이 문서는 반영 **전** 진단 기록으로 남긴다(증거·측정값 보존용).

점검 중 라이브 응답에서 실제로 확인된 것만 적었다. 각 항목의 증거는
`projects/import-compliance/05-launch-audit-and-growth-plan.md` 1-7절에 있다.

## 1. 실시간 소스가 살아 있는데 "연결 실패"로 표기된다 (P1)

증거: `POST /v1/tools/check_food_cosmetics` 응답에서
`result.food_import_live.state` 는 `"live"`(수입신고 672건·부적합 1건 실제 값)인데,
같은 응답의 `result.data_provenance.sources` 는 `mfds_import_food: {state: "unavailable",
note_ko: "실시간 소스 연결 실패·미연결..."}` 이다. 한 응답이 서로 반대말을 한다.

원인: `engine.assess()` 가 `SourceGateway.get()` 으로 상태를 만들 때 게이트웨이는
`customs_requirements` 만 실호출을 알고(`store.SourceGateway._live`), 나머지는
`_live_query_for()` 가 `None` 을 돌려줘 스냅샷도 없으니 `unavailable` 로 떨어진다.
정작 MFDS·법령 실호출은 `api._mfds_live()` / `api._law_live()` 가 assess 이후에 따로 한다.

고치는 방향(둘 중 하나):
- (권장) `tool_check_food_cosmetics` / `tool_get_legal_basis` 에서 실호출 블록을 만든 뒤
  `data_provenance.sources` 의 해당 항목을 `{"source_id": ..., "state": "live", "fresh": true,
  "fetched_at": <fetch.fetched_at>}` 로 덮어쓴다.
- 또는 `SourceGateway` 에 `mfds_import_food`·`law_api` 실호출을 추가한다(캐시까지 같이 해결됨).

## 2. 식약처 툴이 매 호출 9~13초 (P0, 체감)

측정: `check_food_cosmetics`(비타민D3) 12.85s / 9.21s. 같은 품목 재호출도 9.21s —
캐시가 없다. 내부는 MFDS 3개 오퍼레이션(제품DB·수입신고·부적합)을 순차 호출한다.
화면은 `Promise.all` 로 기다리므로 그동안 결과 카드 전체가 안 뜬다.

고치는 방향:
- `store` 스냅샷 TTL 캐시(문서 03에 이미 설계된 7일)를 MFDS·법령 경로에도 적용한다.
  캐시 히트면 `state: "cached_fallback", fresh: age<=TTL, age_hours: ...` 로 정직하게 표시.
- 3개 오퍼레이션을 `concurrent.futures.ThreadPoolExecutor` 로 병렬화(각 1~3초 → 합 3~4초).
- 화면은 판정 → 세관장확인 → 리콜 → 식약처 순으로 도착하는 대로 그린다(점진 렌더).

## 3. 종합 판정이 세관장확인 요건을 반영하지 않는다 (P0, 신뢰)

증거: `POST /v1/tools/assess_import_case` `{"query":"중국산 무선 선풍기를 수입해 판매하려고 해",
"facts":{"purpose":"resale","hs_code":"8414519000","rf_tx":"no"}}`
→ `verdict.code = "low_risk"`, `answer.headline = "현재 정보상 가능성이 낮은 쟁점: 무선기기의 전파 적합성평가"`,
그런데 같은 응답의 `data_provenance.sources[customs_requirements].item_count = 6`.
같은 HS 로 `lookup_hs_requirements` 를 부르면 6건(전안법 5개 기관 + 전파법 국립전파연구원
방송통신기기인증확인서)이 나오고 판정은 `check_likely` 다.

원인: `assess()` 는 게이트웨이가 받은 실데이터를 응답에서 버리고(`filter` 로 `data` 제외),
`tool_assess_import_case` 는 `_customs_live()` 를 부르지 않는다. `lookup_hs_requirements` 만
`hs_requirements_live` 를 붙이고 판정을 `check_likely` 로 올린다.

고치는 방향:
- `tool_assess_import_case` 에서도 HS 10자리가 있으면 `_customs_live()` 를 호출해
  `hs_requirements_live` 를 붙이고, `requirement_count > 0` 이면 종합 판정을
  최소 `check_likely` 로 올린다(`lookup_hs_requirements` 와 같은 규칙).
- 최소한 `answer.guidance` 에 "세관장확인 요건 N건(법령·기관·서류)이 조회되었습니다" 를 넣는다.
  지금은 AI/사람 모두 이 6건을 볼 방법이 없다.

## 4. 자잘한 것

- **화면 문장 중복**: 결과 상단이 `입력한 품목: 중국산 무선 선풍기를 수입해 판매하려고 해 수입해서 판매`.
  `web_ui.buildQuery()` 가 뒤에 `"수입해서 판매"` 를 붙인 문자열을 그대로 다시 출력한다.
  → `data.product`(사용자가 친 원문)를 보여주거나 라벨을 `입력 요약` 으로 바꾼다.
- **MCP 안내 문구 과장**: "MCP 클라이언트에는 .../v1/mcp 의 툴 목록을 그대로 등록할 수 있습니다".
  클라이언트는 매니페스트를 등록하는 게 아니라 JSON-RPC 엔드포인트에 붙는다. 실제 구현 전까지는
  "툴 정의 JSON(참고용)" 으로 고쳐 쓴다.
- **에러를 HTTP 200 으로 반환**: `{"query":""}` → 200 + `{"ok":false,"error":"invalid_argument"}`,
  모르는 툴 → 200 + `unknown_tool`. API 소비자·모니터링이 실패를 성공으로 읽는다.
  400/404 로 바꾸고 본문은 그대로 두는 편이 안전하다.
- **CORS 없음**: `OPTIONS /v1/tools/...` → 501. 브라우저에서 도는 MCP 클라이언트(Glama 플레이그라운드 등)가
  호출할 수 없다. `do_OPTIONS` 에서 `Access-Control-Allow-Origin: *`,
  `Allow-Methods: POST, GET, OPTIONS`, `Allow-Headers: Content-Type, X-Client-Id` 를 돌려준다.
- **무료 한도가 사실상 안 걸린다**: 쿼터 카운터가 컨테이너 SQLite에 있어 재배포·재시작마다 0이 되고,
  `X-Client-Id` 는 클라이언트가 임의로 정한다. "월 250회" 를 그대로 쓰려면 영구 저장(유료 디스크)이나
  서버측 세션 쿠키가 필요하다. 당장은 문구를 "브라우저별 권장 사용량" 정도로 낮추는 게 정직하다.
- **HTML 캐시 헤더 `no-cache`**: 정적 페이지인데 매 요청 Render 오리진까지 간다.
  `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=86400` 을 주면
  Cloudflare 엣지가 슬립 중에도 HTML 을 대신 내려줘 콜드스타트 첫인상이 크게 좋아진다.
- **콜드스타트 안내 없음**: Render 무료는 15분 유휴 후 슬립, 첫 요청 30~60초. 지금 화면은
  "판정과 공공데이터를 조회하고 있습니다…" 만 돌고, 사용자는 멈춘 줄 안다. 안내 문구 + 60초 타임아웃
  + 재시도 버튼을 넣는다.
- **접속 로그를 완전히 껐다**(`log_message` → return). 개인정보에는 좋지만 유입 계측이 0이 된다.
  IP 없이 일별 카운터(경로·툴·판정 코드)만 남기고 `GET /v1/stats` 로 공개하는 쪽을 권한다.
