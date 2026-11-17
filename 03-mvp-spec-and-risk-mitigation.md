---
title: "03. MVP 설계와 5대 리스크 대응"
project: 수입·유통 컴플라이언스 검증 엔진
phase: Phase 1 (무료 베타 · 결제창 없음)
checked_on: 2026-11-17
---

# 03. MVP 설계와 5대 리스크 대응

## 0. 한 장 요약

- **무엇을 파는가**: 여러 기관에 흩어진 공공데이터를 결합·정규화해 **"이 품목·상황에서 확인해야 할 요건"을 3단계로 정리하고 근거 조항을 붙인 판정 결과**.
- **무엇을 팔지 않는가**: 원본 API 재전송, HS 확정, 인증 대행, 통관 대리, 법률 자문.
- **지금 상태**: 로컬에서 도는 Python 엔진 + 8개 툴 + 49개 회귀 테스트 통과. 4개 공공 API 실호출 어댑터가 붙어 있고(키는 `.env`에만), 키가 없으면 코퍼스·캐시만으로 동작. 도메인·결제 없음.
- **다음 관문**: ① 유료화 전 식약처·관세청 사전 확인 ② 도메인·배포 ③ 운영 트래픽 한도 확인

---

## 1. 5대 리스크 → 설계 대응 → 검증

| # | 리스크 | 설계 대응 | 검증(테스트) |
|---|---|---|---|
| 1 | **관세사법·오답 손해배상** | 3단계 판정만 사용, "면제/대상 확정" 금지, 근거 조항·시행일·URL 강제, 국·영문 면책 강제, `determinative=false` | `test_disclaimer_and_no_conclusive_phrasing`, `test_every_finding_carries_law_article_date_url`, `test_determinative_flag_false`, 코퍼스 검사 |
| 2 | **공공데이터 재배포 약관** | 원본 1:1 재전송 금지, 다기관 결합 판정만 출력, 원본 필드명 비노출, 출처 표시, 개인정보 API 미사용 | `test_no_raw_api_passthrough`, 문서 01의 소스별 판정표 |
| 3 | **겸업 금지·사업자 표시** | 100% 무료(0원)·결제창 없음, 유료는 "오픈 예정 · 대기자 등록"만, 대기자 정보는 이메일 1개 | `test_paid_tier_is_waitlist_only`, `test_server_has_no_payment_route` |
| 4 | **무료만 쓰고 유료로 안 넘어옴** | 무료: 단건 요약·월 250콜·대량/PDF/알림 없음. 유료: 대량 일괄·개정 웹훅·근거 포함 PDF | `test_free_tier_250_calls`, `test_billable_tools_exclude_meta`, 경계표(6절) |
| 5 | **정부 API 장애·변경** | 자체 캐시 DB + 스냅샷 + 72시간 신선도 규칙 + 판정 강등 + 소스 상태 노출 | `test_stale_snapshot_downgrades_verdict`, `test_fresh_snapshot_keeps_verdict`, `test_missing_source_reports_unavailable` |

### 1-1. 리스크 ①: 판정 언어를 구조로 묶는다

문장으로 "조심하겠습니다"라고 쓰는 대신, **응답 스키마 자체가 단정을 불가능하게** 만들었다.

```
verdict.code ∈ {check_likely, info_needed, low_risk}   # 다른 값은 코드에서 거부
verdict.determinative = false                          # 항상 false (테스트로 고정)
evidence[].law / article / effective_date / url        # 비면 테스트 실패
disclaimer.ko / disclaimer.en                          # 항상 포함
```

추가로 `policy.find_conclusive_phrasing()`이 생성 문장에서 `확정`, `면제됩니다`, `대상입니다`, `필요 없습니다`, `100%` 등을 찾아내고, 부정·한정 문맥(`확정하지 않습니다`)이 아니면 문장을 폐기한다. **"대상/면제 확정" 표현은 물리적으로 출력되지 않는다.**

### 1-2. 리스크 ②: 원본을 팔지 않는다

- `api_snapshots` 테이블은 **내부 보존용**이다. API 응답에는 스냅샷의 `data`/`payload_json`이 들어가지 않는다(테스트로 확인).
- 응답에 나가는 것은 `findings`(정규화된 판정), `evidence`(조항 요지+URL), `data_provenance`(소스 상태)뿐이다.
- 원본 필드명(`hsSgn`, `imexTpcd`, `DCLR_PRDT_DIVS_NM`)은 외부 스키마에 등장하지 않고 `hs_code`, `direction`, `product_type`으로 정규화한다.
- 개인통관고유부호 검증 API는 **아예 연동하지 않는다**. 개인정보를 받을 이유가 없으면 받지 않는 것이 가장 안전한 설계다.

### 1-3. 리스크 ③: 돈을 받는 순간을 늦춘다

- FREE 티어는 `price_krw=0`, `payment_wall=false`.
- 서버 라우트에 결제·체크아웃 경로가 없다(`test_server_has_no_payment_route`).
- 유료 티어는 `status="오픈 예정 · 대기자 등록만"`으로만 존재하고, 대기자 등록은 **이메일 1개**만 받는다(이름·전화·사업자번호 없음).
- 이 구조에서는 유료 판매가 없으므로 통신판매업 신고·사업자 정보 표시 의무가 발생하지 않는다. **유료화 직전에 이 판단을 다시 검토**한다(7절).

### 1-4. 리스크 ④: 무료의 천장을 명확히

무료는 "한 건을 요약해서 보여주는 것"까지. 대량·자동화·산출물은 유료 영역으로 남긴다(6절 표). 무료에서도 판정의 질은 떨어뜨리지 않는다 — 품질이 아니라 **처리량과 산출물 형식**을 경계로 둔다. 그래야 "무료로 충분하다"는 인식과 "업무에 쓰려면 유료"가 동시에 성립한다.

### 1-5. 리스크 ⑤: 장애를 숨기지 않는다

- 실시간 호출 실패 → 최신 스냅샷 폴백.
- 스냅샷 나이 > 72시간 → **판정을 `info_needed`로 강등**하고 이유를 문장으로 출력.
- 스냅샷조차 없음 → `state="unavailable"`, 판정은 코퍼스 근거만으로 수행하고 "실시간 미연결"을 명시.
- **없는 것을 있는 것처럼 말하지 않는다.** `lookup_recall`이 대표 예: 소스 미연결이면 "조회 불가"와 공식 확인 URL을 준다.

---

## 2. 시스템 아키텍처

```
[사용자 / AI 에이전트]
        │  자연어 질의 or MCP tool call
        ▼
┌────────────────────────────────────────────────────────────┐
│ API 계층 (api.py)  8 tools · 무료 쿼터 · 입력검증            │
└───────────────┬────────────────────────────────────────────┘
                ▼
┌────────────────────────────────────────────────────────────┐
│ 판정 엔진 (engine.py)                                       │
│  1) 질의 정규화 → 사실 추론(purpose/channel/HS/가격 등)      │
│  2) 코퍼스 매칭(1차 신호 3개 또는 2개 이상 일치)             │
│  3) 3단계 판정 + 필요입력 누락 시 강등                       │
│  4) 신선도 규칙 적용(스냅샷 72h 초과 → info_needed)          │
│  5) 근거·면책·한계 조립 + 단정 표현 가드                     │
└───────┬───────────────────────────────┬────────────────────┘
        ▼                               ▼
┌───────────────────────┐      ┌─────────────────────────────┐
│ 코퍼스 (traps_20.json) │      │ 소스 게이트웨이 (store.py)   │
│ 20 케이스 · 근거 54건(고유 URL 41개)  │      │ live → 실패 시 cache fallback│
└───────────────────────┘      └────────────┬────────────────┘
                                            ▼
                               ┌─────────────────────────────┐
                               │ SQLite/Postgres 캐시 DB      │
                               │ sources / api_snapshots      │
                               │ derived_findings/assessments │
                               │ quota_usage / webhooks       │
                               └─────────────────────────────┘
```

**설계상 중요한 두 가지**

1. **판정 지식(코퍼스)과 데이터(캐시)를 분리**했다. API가 죽어도 판정은 계속되고, 대신 "근거 데이터가 오래됐다"고 말한다.
2. **툴 계약은 MCP와 HTTP가 동일**하다. `mcp_manifest()`가 그대로 MCP 툴 목록이 되고, 같은 이름이 `/v1/tools/{name}`으로 노출된다.

---

## 3. 판정 규칙

### 3-1. 3단계 정의

| 코드 | 국문 라벨 | 영문 라벨 | 의미 |
|---|---|---|---|
| `check_likely` | 확인 대상 가능성 높음 | Likely requires review | 법령·고시에 해당 품목군이 열거되어 있거나 요건 신호가 일치. **요건이 있을 가능성이 높으니 확인이 필요** |
| `info_needed` | 추가 정보 필요 | More information needed | 열거는 있으나 연령·전력·재질·수량 등에 따라 갈리거나, 입력이 부족하거나, 근거 데이터가 오래됨 |
| `low_risk` | 현재 정보로는 가능성 낮음 | Low likelihood on current information | 고시가 명시적으로 제외했거나(예: 적외선 리모컨), 자가소비 직접구매처럼 요건 적용 자체가 다른 경우. **다른 법령의 가능성은 남음** |

### 3-2. 전이 규칙

| 상황 | 결과 |
|---|---|
| 코퍼스 신호 일치 없음 | `info_needed` (품목·HS·목적 보강 요청) |
| 기본 `check_likely` + 필수 입력 누락 | `info_needed` |
| `low_risk` 조건 충족 | `low_risk` (다른 케이스가 더 높으면 전체는 상향) |
| 스냅샷 72시간 초과 | 전체 판정 `info_needed` + 사유 문장 |
| 스냅샷 미연결(Phase 1 기본) | 강등하지 않음. `data_provenance`에 "미연결" 표시 |
| HS 6자리만 입력 | `info_needed` (`sufficient_for_checkpoint=false`) |

우선순위: `check_likely > info_needed > low_risk`. 여러 케이스가 걸리면 **가장 보수적인 판정**을 전체 판정으로 올린다.

---

## 4. 캐시 DB와 동기화·폴백

전체 DDL은 `src/schema.sql`(Postgres)와 `src/import_compliance/store.py`(SQLite)에 있다.

| 테이블 | 역할 | 핵심 컬럼 |
|---|---|---|
| `sources` | 소스 카탈로그 | `source_id`, `license_scope`, `update_cycle`, `last_ok_at` |
| `api_snapshots` | 원본 응답 보존(내부용) | `source_id`, `query_key`, `payload_json`, `fetched_at` |
| `derived_findings` | 가공 판정 이력 | `trap_id`, `verdict`, `confidence`, `evidence_json` |
| `assessments` | 응답 감사 로그 | `assessment_id`, `client_id`, `response_json` |
| `quota_usage` | 월별 호출 수 | `client_id`, `period`, `used` |
| `webhook_subscriptions` | (유료) 개정 알림 | `event_type`, `target_url`, `secret_hash` |

**동기화 정책(Phase 2)**

| 소스 | 주기 | 방식 |
|---|---|---|
| 세관장확인대상물품 | 1일 1회 + 온디맨드 | HS 10자리 단위 캐시, 7일 TTL |
| 제품 안전인증·리콜 | 1일 1회 | 전체 목록 증분 동기화 |
| 수입식품 계열 | 1일 1회 | 제품·원료·규격 테이블 증분 |
| 법령·행정규칙 | 1일 1회 | 개정 이력 API로 변경분만, 변경 감지 시 웹훅 이벤트 생성 |
| 리콜 | 6시간 | 신규 리콜만 푸시 |

**폴백 규칙**: live 실패 → 최신 스냅샷 → 72h 이내면 판정 유지, 초과면 `info_needed`. 캐시도 없으면 "미연결"로 정직하게 표시.

**실API 게이트웨이 구현(2026-11-18)**: `SourceGateway(store, live=client)`로 주입한다.

- 호출 성공 → 정규화 결과를 `api_snapshots`에 저장(`status='ok'`)하고 `state="live"` 반환
- 호출 실패 → `status='error'`로 기록하되 폴백은 성공한 스냅샷만 사용(`latest_snapshot`이 status='ok'만 읽음), 스냅샷이 없으면 `unavailable`
- `live`를 주입하지 않으면 기존과 동일하게 동작한다(테스트는 실제 네트워크를 타지 않는다)
- 실호출은 `hs_code` 10자리가 있는 세관장확인만 기본 경로에 붙고, 식약처·법령 실호출은 해당 툴(`check_food_cosmetics`, `get_legal_basis`)에서 수행한다

---

## 5. API / MCP 툴 8종

| # | 툴 | 입력 | 하는 일 | 무료 |
|---|---|---|---|---|
| 1 | `assess_import_case` | `query`, `facts?`, `limit?` | 종합 판정(최대 3케이스) | ✅ |
| 2 | `lookup_hs_requirements` | `hs_code`, `direction` | HS 10자리 세관장확인 요건 | ✅ |
| 3 | `check_kc_certification` | `product_name`, `target_age?`, `rf_tx?`, `battery?`, `ac_plug?` | KC·전파 인증 유형 | ✅ |
| 4 | `check_food_cosmetics` | `product_name`, `kind`, `purpose?`, `functional?` | 식약처 요건·표시·광고 | ✅ |
| 5 | `lookup_recall` | `brand`, `model?` | 리콜 이력(미연결 시 불가 고지) | ✅ |
| 6 | `get_legal_basis` | `law`, `article?` | 근거 조항 요지·시행일·URL | ✅ |
| 7 | `explain_trap` | `case_id` | 케이스 해설(오답/정답/근거) | ✅ |
| 8 | `get_service_meta` | — | 코퍼스 버전·경계·잔여 콜 | ✅ (쿼터 미적용) |

`mcp_manifest()`는 위 8개를 MCP `tools` 배열로 그대로 변환한다. HTTP는 `POST /v1/tools/{name}`, `GET /v1/mcp`, `GET /v1/meta`, `GET /healthz`.

### 5-2. 실API가 붙는 위치(8개 툴 계약은 그대로)

| 툴 | 실API 블록 | 규칙 |
|---|---|---|
| `lookup_hs_requirements` | `hs_requirements_live` | 요건 1건 이상 → `check_likely`, 0건 → `info_needed`(『요건 없음』으로 말하지 않음), 호출 실패 → 판정 근거는 코퍼스만 쓰고 실패 코드를 명시 |
| `check_food_cosmetics` | `food_import_live` | 제품DB·수입신고 이력 건수와 샘플만. 0건은 "이력 없음"이 아니라 "조회되지 않음" |
| `get_legal_basis` | `law_live` | 법령명 **정확 일치** 우선, 시행일·소관부처·공포일 확인. `article`이 있으면 조문 본문(항 단위 포함)까지 인용. 외부 주소에는 OC 미포함 |
| `assess_import_case` | `data_provenance.sources` | 실호출 성공 시 `state="live"`·`fetched_at`·`item_count`만 노출(원본 payload 제외) |
| `get_service_meta` | `live_sources` | 어떤 소스가 연결됐는지만 boolean으로 노출(키 값 없음) |

출처 표기는 실API 블록마다 문장으로 박아 둔다: "관세청_세관장확인대상물품(data.go.kr 15101589, 이용허락범위 제한 없음)", "출처: 법제처 국가법령정보센터".

### 5-3. 표준 응답(실제 출력)

```json
{
  "assessment_id": "asm_5f72cdb6ea3f48b8",
  "engine": {"name": "import-compliance", "version": "1.0.0", "corpus_verified_on": "2026-11-17"},
  "verdict": {
    "code": "check_likely",
    "label_ko": "확인 대상 가능성 높음",
    "label_en": "Likely requires review",
    "determinative": false,
    "note_ko": "판정은 확률적 검토 결과이며, 법적 확정 판단이 아닙니다."
  },
  "answer": {
    "headline": "확인이 필요한 쟁점: 무선기기의 전파 적합성평가",
    "guidance": ["무선전파를 송신하는 기자재는 전파법 제58조의2에 따른 적합성평가 대상이며 …"]
  },
  "findings": [{
    "case_id": "TRAP-06",
    "issue_ko": "무선기기의 전파 적합성평가",
    "verdict": "check_likely",
    "confidence": 0.69,
    "missing_inputs": [],
    "legal_basis": [{
      "law": "전파법", "article": "제58조의2", "effective_date": "2026-01-01",
      "url": "https://www.rra.go.kr/ko/license/A_a_about.do",
      "quote": "방송통신기자재 등을 제조 또는 판매하거나 수입하려는 자는 … 적합성평가를 받아야 한다.",
      "verified_on": "2026-11-17"
    }]
  }],
  "disclaimer": {"ko": "본 결과는 사전 참고용입니다. …", "en": "This output is preliminary reference information only. …"},
  "data_provenance": {"policy": "원본 API 1:1 재전송 금지 …", "sources": [{"state": "unavailable"}]},
  "tier": {"name": "free", "boundaries": {"price_krw": 0, "monthly_calls": 250, "pdf_report": false}}
}
```

---

## 6. 무료 / 유료 기능 경계

| 기능 | 무료 (현재) | 유료 (오픈 예정 · 대기자) |
|---|---|---|
| 단건 요건 요약 판정 | ✅ | ✅ |
| 근거 조항·시행일·URL | ✅ | ✅ |
| 월 호출 | **250콜** | 협의(트래픽 상향) |
| 한 번에 여러 케이스 | 최대 3건 | 무제한 |
| 대량 일괄 체크(CSV/엑셀 업로드) | ❌ | ✅ |
| 법령·고시 개정 웹훅 알림 | ❌ | ✅ |
| 근거 조항 포함 PDF 판정서 | ❌ | ✅ |
| API 키·SLA | ❌ | ✅ |
| 가격 | **0원** | 미정(오픈 시 공지) |
| 결제 | 없음 | Polar/Paddle 등 해외 MoR 검토 |

**왜 이 선인가**: 무료 사용자는 "한 건 확인"으로 가치를 느끼고, 실제 업무에 쓰는 사용자는 ① 여러 건을 한 번에 ② 개정되면 자동으로 알림 ③ 감사·보고용 PDF가 필요해진다. 이 세 가지는 **자동화·산출물**이지 판정 품질이 아니므로, 무료 사용자에게 품질을 숨기는 인상을 주지 않는다.

---

## 7. 면책·표현 가드

### 7-1. 표준 면책(국문) — 모든 응답에 강제 포함

> 본 결과는 사전 참고용입니다. 법적 효력이 없으며, 최종 법적 판단과 통관·인증 가능 여부는 관세사, 관세청, 국가기술표준원·인증기관, 식품의약품안전처 등 소관 기관의 확인이 필요합니다. 본 서비스는 관세사법상 관세 상담·대리 업무를 수행하지 않습니다.

### 7-2. Standard disclaimer (English)

> This output is preliminary reference information only. It has no legal effect and is not customs advice. Final determinations on classification, clearance, certification and labeling must be confirmed with a licensed customs broker and the competent Korean authorities (Korea Customs Service, KATS/certification bodies, MFDS).

### 7-3. 금지 표현 목록 (`policy.CONCLUSIVE_PATTERNS`)

`확정`, `면제됩니다`, `면제입니다`, `면제이다`, `대상입니다`, `대상이다`, `대상이 아닙니다`, `대상이 아니다`, `필요 없습니다`, `필요없`, `보장합니다`, `100%`

부정·한정 문맥(`확정하지`, `단정`, `아니`, `않습니다`, `금지`, `제외`, `불가`, `어렵`)은 허용한다. 이 가드는 ① 코퍼스 정답 문장 ② 엔진이 생성한 headline/guidance ③ next_actions에 적용되고, 테스트가 20케이스 전부를 검사한다.

### 7-4. 범위 한계 문구(항상 포함)

- 품목분류(HS) 확정, 인증 대행, 통관 대리, 법률 자문을 수행하지 않습니다.
- 공공데이터 원본을 그대로 중계하지 않고, 결합·정규화한 판정 결과만 제공합니다.
- API 장애·개정 지연 시 캐시 시점을 명시하고 판정을 '추가 정보 필요'로 낮춥니다.
- 확인되지 않은 고시·별표는 추정으로 채우지 않습니다.

### 7-5. 유료화 전 재검토 (겸업 금지 대응)

지금은 무료라서 매출·세금계산서·사업자 표시가 없다. 유료화 직전에 반드시 확인할 것:

1. 회사 규정상 겸업 금지 범위 — 사업자 등록 없이 해외 MoR(Polar 등)로 개인 수령이 가능한지, 소득 신고 형태.
2. 통신판매업 신고·사업자 정보 표시 의무 발생 시점.
3. 실명·주소 노출 최소화(사업자 등록 시 주소가 공개될 수 있음).
4. 세무 처리(부가세·원천징수) — 유료화 전 세무사 확인.

이 4개는 **돈을 받기 전에** 결정해야 하며, 엔진 코드와 무관하게 진행할 수 있다.

---

## 8. 검증 결과

실행:

```bash
cd projects/import-compliance/src
python3 tests/test_engine.py     # 24 tests
python3 tests/test_http.py       # 3 tests (실제 소켓)
python3 tests/test_live_api.py   # 22 tests (네트워크 없이 고정 응답)
python3 -m import_compliance.cli --check-corpus
```

결과(2026-11-18 실행):

```
Ran 24 tests ... OK
Ran 3 tests ... OK
Ran 22 tests ... OK
OK corpus_version=1.0.0 cases=20 verified_on=2026-11-17
```

| 테스트 묶음 | 확인하는 것 |
|---|---|
| `TrapVerdictTest` (6) | 함정 20케이스 전부 기대 판정 일치, low_risk 경로, 입력 누락 강등, 미매칭 시 비생성, HS 10자리 |
| `RiskGuardTest` (4) | 면책 국·영문, 단정 표현 0건, 근거 4요소, 원본 미중계, determinative=false |
| `CacheFallbackTest` (3) | 72h 초과 강등, 신선 스냅샷 유지, 미연결 시 정직한 불가 |
| `QuotaAndTierTest` (5) | 250콜 한도, 메타 미과금, 툴 8개, 대기자 전용 티어, 결제 라우트 없음 |
| `ToolContractTest` (5) | 잘못된 툴/인자, 케이스 해설, 근거 필터, HS 6자리 부족, 응답 필수키 |
| `CorpusTest` (2) | 20케이스·근거 URL·시행일·금지표현 |
| `HttpSmokeTest` (3) | healthz, MCP 8툴, HTTP 판정, 404 |
| `test_live_api.py` (22) | `.env` 로딩·환경변수 우선, 키 repr/에러 리댁션, 4개 응답 파싱(XML·JSON·단일 객체), 필드 정규화, OC 미노출, 코드 30만 15초 재시도 1회(400/XML·403/JSON 두 형식), 실패 시 코드·사유 노출, live→스냅샷 폴백(실패 스냅샷 제외), 툴 응답에 원본 필드명 미노출, live 미주입 시 네트워크 0회 |

---

## 9. 배포·운영 계획

| 단계 | 내용 | 비용 |
|---|---|---|
| **Phase 1.5 (현재)** | 로컬 stdlib 서버, SQLite, 코퍼스 20케이스, 무료, **4개 공공 API 실호출(키는 .env)** | 0원 |
| Phase 2 | 도메인 1개(연 1.5~2.5만원), Cloudflare Workers 또는 소형 VPS, D1/Postgres, 공공 API 키 | 월 0~2만원 |
| Phase 3 | MCP 레지스트리 등록, GitHub 공개 SDK, Polar 결제(유료 오픈 시) | 수수료만 |

**키 관리**: 모든 키는 환경변수/시크릿으로만. 코드·문서·로그에 남기지 않는다. `X-Client-Id`는 익명 식별자로만 쓰고 개인정보와 연결하지 않는다.

---

## 10. 다음 단계 — 운영자가 하실 일

엔진은 지금 상태로도 돌지만, 실제 데이터·배포·유료화는 본인 확인이 필요하다.

1. **공공데이터포털 API 활용신청** — 15101589(완료·2026-11-18 실호출 성공), 15058273·15073949(완료), 15116894·15111777·15111776·15110214(미신청, 남은 작업).
2. **법제처 공동활용 신청 + 서버 IP/도메인 등록** (10분) — 자동승인.
3. **유료화 전 서면 확인 2건** — 식약처 상업적 활용 사전 승낙, 관세청 재가공 문의. (돈 받기 전 필수)
4. **도메인·배포 결정** — Phase 2 예산 2만원 이하.
5. **첫 고객 5명 인터뷰** — 무료 베타로 20케이스 중 어떤 것이 실제로 걸리는지 확인. 이 결과로 코퍼스 21~40을 늘린다.

**제가 결정을 대신하지 않은 것**: 도메인 이름, 유료 가격, 결제 사업자, 사업자 등록 여부. 이 네 가지는 운영자의 사업 형태·겸업 규정과 직결된다.

---

## 11. 가정과 미확인

- 실API는 `live` 클라이언트를 주입할 때만 호출된다. 키가 없으면 Phase 1과 동일하게 코퍼스·캐시로만 동작하며, 그 사실을 `data_provenance`에 `corpus_only`로 표시한다.
- 실호출 트래픽 한도(개발계정 기준)는 포털 마이페이지에서 확인해야 한다. 2026-11-18 검증에서는 호출량이 적어 제한에 닿지 않았다.
- 「이용허락범위 제한 없음」은 2026-11-17 포털 표시 기준이다. 포털이 라이선스를 바꾸면 재확인해야 한다.
- 테스트는 코퍼스·룰·가드의 회귀를 검증한다. **법령 해석의 정확성을 증명하지 않는다.** 그래서 면책과 기관 확인 안내가 제품의 일부다.
- TRAP-14의 2026-11-12 제도 변경, TRAP-15의 2026-04-24 시행은 시행 초기라 세부 운영 기준이 추가될 수 있다. 분기별 재확인 대상으로 표시해 두었다.
