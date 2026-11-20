# 0.3.0 — 질문형 가이드(/guides/)와 일일 시계열 스냅샷

2026-11-20. 이 릴리스는 성장 방식이 "사람 홍보"에서 "AI 인용·검색 유입"으로 옮겨간 뒤의
첫 기능 확장이다. ① 검색·AI 챗봇에 실제로 입력되는 **질문 문장**으로 들어오는 정적 페이지를
36개 늘리고, ② 다른 곳에서 쉽게 따라올 수 없는 **시계열 데이터**(일일 스냅샷·전일 대비·급증)를
쌓는 모듈을 붙였다.

## 1. `/guides/{slug}` — 질문형·규제별 랜딩

### 왜 `/p/` 와 따로 두는가
`/p/{slug}` 는 "품목명"으로 들어오는 유입(무선 미니 선풍기, 보조배터리…)을 받는다. 검색
의도는 두 갈래이고, 두 번째가 훨씬 크다.

1. **객체형**: "무선 미니 선풍기 수입 요건" → 품목 페이지
2. **질문형**: "영양제 몇 병까지", "면세 한도 150인가요 200인가요", "5V는 KC 인증 필요 없나요" → 가이드

질문형 페이지는 H1 이 질문이고, 첫 문단이 답이며, `FAQPage` 구조화 데이터에 같은 질문·답변이
들어간다. AI 검색이 인용하기 좋은 형태(질문-직답-근거-한계)를 페이지 구조 자체로 만든다.

### 카탈로그 (`src/guides_items.json`, 36건)
항목 필드: `slug` · `question_ko` · `title_ko` · `category` · `summary_ko` · `answer_ko` ·
`key_points_ko` · `checkpoints_ko` · `cases` · `basis_keys` · `tags` · `tool` · `tool_example` ·
`keywords` · `related_guides` · `related_items`.

| 분류 | 예 |
|---|---|
| 의약품·영양제 (5) | 영양제 6병 기준, 멜라토닌, 졸피뎀, 아데랄, 휴대 반입 |
| 통관·면세 (5) | $150/$200, 개인통관고유부호, 자가사용품 판매, HS 6 vs 10, 세관장확인 0건 |
| 전기·전파·KC (4) | 5V KC, 내장 배터리, CE·FCC와 전파인증, 전파인증 면제 |
| 어린이제품 (3) | 3유형 구분, 안전인증 면제, 젖병·이유식 용기 |
| 식품·화장품 (7) | 수입신고·영업등록, 한글표시·화장품 기재사항, 배합금지 성분, 소분·샘플, 직구 화장품 판매, 식품용기, 첨가물 |
| 표시·광고 (4) | 과대광고 금지 표현 16종, 건기식 광고심의 |
| 지재권·원산지 (3) | 병행수입, FTA CO |
| 기타 규제 (5) | 니코틴 액상, 생활화학제품, Made in Korea, 의료기기, 위생용품, CBD |

### 근거 조문을 카탈로그에 직접 쓰지 않는 이유
법령 인용은 오탈자 하나로 잘못된 근거가 되고, 개정되면 조용히 구법이 남는다. 그래서 카탈로그는
조문 문안을 갖지 않고 **이 저장소에서 이미 법제처 현행본으로 검증한 상수만 키로 참조**한다.

- `advertising:B_FOOD_8_1_DISEASE` … `advertising.py` 의 `B_*` 상수
- `labeling:B_FOOD_4_1_1`, `labeling:B_COS_10_1` … `labeling.py` 의 `B_*` 상수
- `drugs:BASIS_SELF_USE:0`, `drugs:BASIS_NARCOTIC:2` … `drugs.py` 의 근거 리스트
- `cases: ["TRAP-23"]` … 함정 코퍼스의 케이스(그 케이스의 legal_basis 를 그대로 모아 쓴다)

`load_catalog()` 가 로딩 시 **모든 키·태그·케이스·툴 이름을 해석**하고, 하나라도 실패하면
`GuideCatalogError` 로 서버가 뜨지 않는다. 검증되지 않은 인용이 페이지로 나갈 경로를 없앤다.

### 얇은 페이지 규칙
`is_indexable()`: 답변 80자 이상 + 체크포인트 3개 이상 + 근거(케이스 또는 조문 키) 1개 이상.
미달이면 `noindex,follow` 를 붙이고 사이트맵에서 뺀다(`/p/` 와 같은 규칙).

### 문체 가드
답변·요약·체크포인트·핵심 포인트에 `policy.find_conclusive_phrasing()` 을 돌려 "대상입니다·
면제됩니다·필요 없습니다·100%·확정" 같은 단정 표현이 0건임을 테스트로 강제한다. 판정은
"확인해야 합니다 / ~될 수 있습니다 / 0건은 요건 없음이 아닙니다"로만 쓴다.

### 노출 경로
- `/guides/` 인덱스(카테고리별 그리드) — 홈 푸터에서 링크
- `sitemap.xml` — `/p/` 뒤에 `/guides/`(0.9) + 각 페이지(0.8)
- `llms.txt` — 가이드 개수·경로·`FAQPage` 언급
- 모든 페이지에 `/?q=` 웹 체크 링크 · `/v1/tools/{tool}` · `/mcp` 연결 안내
- 익명 카운터(`usage.path_key`)가 `/guides/{slug}` 를 개별 버킷으로 센다

## 2. 일일 시계열 스냅샷 (`snapshots.py`)

### 테이블
```sql
compliance_snapshots(day, source, item_key, fingerprint, label, category, event_date,
                     payload_json, origin, taken_at)   -- PK(day, source, item_key)
snapshot_runs(day, taken_at, origin, counts_json, diff_json)
```

`source` 5종: `recall`(국표원 리콜) · `disposition`(식약처 행정처분) ·
`cosmetic_prohibited`(배합금지) · `cosmetic_restricted`(배합한도) · `drug_schedule`(마약류·원료물질).

### 지문(fingerprint)과 키
- 키는 **원본 식별 조합**으로 만든다. `recall` 은 `인증번호|모델명|제품명|브랜드|등록일`,
  `disposition` 은 `dataset_id:전산키`, 성분은 이름.
- 리콜 테이블의 `id` 는 재적재마다 바뀌므로 쓰지 않는다(쓰면 전건이 '신규'로 잡힌다).
- 지문은 항목 내용(브랜드·모델·분류·위해유형·위반법령·처분유형·한도 등)의 sha256 앞 16자리.
  **키는 같고 지문이 다르면 '변경'** — 처분 내용 수정, 한도 기준 변경을 잡아낸다.

### 함수
| 함수 | 역할 |
|---|---|
| `collect(store, cosmetic_catalog=, drug_catalog=)` | 현재 로컬 상태를 소스별 사전으로 수집(네트워크 없음, 테스트 주입점) |
| `take_snapshot(store, day, origin=, export_dir=)` | 그날 스냅샷 적재(멱등) + 전일 대비 요약 + `snapshot_runs` 기록 |
| `daily_diff(store, day, limit=)` | 저장된 두 스냅샷 비교(신규/변경/삭제 + 샘플) |
| `trends(store, days, today, source=, limit=)` | 일별 시계열 + 최근/직전 동일 기간 급증 표 + 참고 창 |
| `backfill_from_history(store, days, end_day=)` | 이벤트 날짜로 과거 누적 상태 재구성(`origin=backfilled`, 관측분은 건너뜀) |
| `export_snapshot(...)` | `data/snapshots/YYYY-MM-DD.json` 요약 내보내기(`--include-items` 로 항목 포함) |

### 추이(trends)의 두 층
1. **스냅샷 층**: `series[]` — 일자별 소스 건수와 전일 대비 신규/변경/삭제. 관측(`observed`)과
   재구성(`backfilled`)을 구분해 표시한다.
2. **이벤트 층**: 리콜 등록일·처분 확정일 기준 최근 N일 vs 직전 N일. 품목군(법정제품분류 첫 구간)·
   위해유형·리콜종류·위반법령·처분유형별 `count`·`previous_count`·`delta`·`ratio` 를 내고
   **증가분이 있는 행을 먼저** 정렬한다.

요청 기간에 이벤트가 0건이면 `reference` 에 데이터의 마지막 이벤트일 기준 같은 길이 창을
계산해 넣는다. "0건 = 급증 없음"으로 단정하지 않기 위한 장치다.

### 노출
- MCP/REST 툴 `get_compliance_trends` (`days` 1~90, `source`, `as_of`, `limit`)
- `GET /v1/trends?days=30` — 같은 계약의 읽기 전용 GET(익명 카운터 버킷 `/v1/trends`)
- `python -m import_compliance.snapshots --take [--export DIR]`(`DIR` 은 실행 위치 기준), `--backfill N`, `--diff`, `--trends N`
- 서버 기동 시 적재: `--snapshot` 또는 `IMPORT_COMPLIANCE_SNAPSHOT=1`(같은 날 재기동은 멱등)

### 정직하게 남긴 한계
- 리콜 파일데이터(15040696)는 2023-08-09 배포본(등록일 2019-10~2022-07)이라 그 이후 신규 리콜은
  관측되지 않는다. 그래서 `coverage` 에 이벤트 범위·소스 상태를 항상 싣는다.
- 리콜 881행은 키 기준으로 묶으면 846건이다(같은 인증번호·모델·제품·브랜드·등록일 중복). 중복은
  스냅샷에서 하나로 센다.
- 무료 플랜은 영구 디스크가 없어 스냅샷이 재배포 시 사라진다. `--export` JSON 을 별도 보관하거나
  영구 볼륨으로 옮겨야 시계열이 자산으로 남는다.

## 3. 테스트
`src/tests/test_guides_trends.py` 31건 — 카탈로그 참조 무결성·문체 가드·36개 페이지 렌더·
`FAQPage` 일치·얇은 페이지 `noindex`·sitemap/llms 노출·스냅샷 멱등·신규/변경/삭제·backfill 이
관측분을 덮지 않음·참고 창·툴/엔드포인트 계약·CLI·익명성 스캔. 전체 **388건** 통과(네트워크 없음).

## 4. 버전
`0.2.0 → 0.3.0`. `version.py` · `server.json` · `Dockerfile` 라벨 · MCP 툴 12종(과금 11종,
`get_service_meta` 제외).
