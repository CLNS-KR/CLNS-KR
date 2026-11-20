---
title: "06 · 대표 100개 테스트셋과 응답 스키마 0.1.3"
---

# 대표 100개 테스트셋 · 응답 스키마 0.1.3

이 문서는 0.1.3 릴리스에서 반영한 세 가지(대표 100개 품목 테스트셋, 표준 판정 상태·누락 정보, 글로벌 확장 대비 공통 스키마)를 검증 결과와 함께 정리한다. 서비스 식별자는 `CLNS-KR` 하나만 쓰며 개인정보·시크릿은 들어 있지 않다.

## 1. 한눈에

| 항목 | 0.1.2 | 0.1.3 |
|---|---|---|
| 판정 기준 | 함정 20케이스 | 함정 20케이스 + **대표 100품목 테스트셋** |
| 판정 표현 | 3단계 `verdict` | 3단계 `verdict` **유지** + `assessment_status` 5단계 |
| 빠진 스펙 | `findings[].missing_inputs` | + 응답 최상위 `missing_information`(표준 스펙명) |
| 지리·법역 | 없음 | `destination`·`jurisdiction`·`origin`(ISO 3166-1 alpha-2) |
| 규제 태그 | 없음 | `regulation_tags`(20종 어휘, 케이스별) |
| 테스트 | 173건(README 기재 162건 + 검색엔진 소유확인 11건) | **222건** (기존 173 + 신규 49) |

기존 웹 UI·MCP 8개 툴·pSEO 35개·`/v1/stats`의 응답 계약은 그대로 두고 필드만 **추가**했다.

## 2. 대표 100개 테스트셋 (`src/testset_100.json`)

### 2-1. 구성

| 분야(`domain`) | 케이스 | 주로 검증하는 규제 태그 | 판정 분포 |
|---|---|---|---|
| `electrical_electronics` 전기·전자 KC | 16 | `ELECTRICAL_KC`(10) · `CUSTOMS_CHECKPOINT`(6) | check_likely 8 / info_needed 8 |
| `wireless_rf` 무선기기·전파법 | 12 | `RF_CONFORMITY`(11) · `CUSTOMS_CHECKPOINT`(1) | check_likely 9 / low_risk 2 / info_needed 1 |
| `battery` 배터리 | 12 | `BATTERY_SAFETY`(10) · `CUSTOMS_CHECKPOINT`(2) | check_likely 8 / info_needed 4 |
| `children_product` 어린이제품 | 12 | `CHILDREN_PRODUCT_SAFETY`(11) · `KOREAN_LABELING`(1) | info_needed 10 / check_likely 2 |
| `food_health_functional` 식품·건강기능식품 | 16 | `FOOD_IMPORT_DECLARATION`(5) · `HEALTH_FUNCTIONAL_FOOD`(4) · `FOOD_CONTACT_MATERIAL`(3) · `KOREAN_LABELING`(1) · `FOOD_ADDITIVE`(1) · `FOOD_BUSINESS_REGISTRATION`(1) · `CUSTOMS_LOW_VALUE`(1) | check_likely 14 / info_needed 2 |
| `cosmetics` 화장품 | 10 | `COSMETICS_RESPONSIBLE_SALES`(9) · `CUSTOMS_CHECKPOINT`(1) | check_likely 9 / info_needed 1 |
| `household_chemical` 생활화학제품·차량용 방향제 | 10 | `HOUSEHOLD_CHEMICAL`(9) · `CUSTOMS_CHECKPOINT`(1) | check_likely 10 |
| `medical_sanitary` 의료기기·위생용품 | 12 | `CUSTOMS_CHECKPOINT`(10) · `CUSTOMS_LOW_VALUE`(2) | info_needed 10 / check_likely 2 |

### 2-2. 케이스 형식

```json
{
  "case_id": "CASE-081",
  "domain": "household_chemical",
  "domain_ko": "생활화학제품·차량용 방향제",
  "product_ko": "차량용 방향제",
  "query": "차량용 방향제를 수입해 판매",
  "facts": {"product_type": "방향제", "has_cert": "no"},
  "expected_verdict": "check_likely",
  "required_findings": ["HOUSEHOLD_CHEMICAL"],
  "primary_case_id": "TRAP-16",
  "severity": "critical",
  "note_ko": "차량용 방향제도 생활화학제품 안전확인 대상으로 다뤄진다."
}
```

- `required_findings` — 이 케이스에서 **반드시** 나와야 하는 규제 태그. 응답에서 하나라도 빠지면 **중대 규제 누락(FN)**으로 센다.
- `severity` — `critical`(중대 규제) 67건 / `standard` 33건.
- `primary_case_id` — 해당 품목을 담당하는 코퍼스 케이스(검수·문서용).

### 2-3. 검증 결과 (2026-11-18, 네트워크 없이)

| 지표 | 결과 |
|---|---|
| 분야별 판정 정확도 | 8개 분야 모두 **100%** (100/100) |
| 중대 규제 누락(FN) | **0건** |
| `NOT_APPLICABLE` 오판 | 0건 (기대 판정이 `low_risk` 가 아닌 케이스가 '미적용'으로 단정된 경우 없음) |
| `APPLICABLE` / `POTENTIALLY_APPLICABLE` / `REVIEW_REQUIRED` / `NOT_APPLICABLE` / `UNKNOWN` | 51 / 11 / 36 / 2 / 0 |

`UNKNOWN` 은 테스트셋 케이스에 나타나지 않는다(100건 모두 담당 카드가 있는 품목이기 때문). `UNKNOWN` 경로는 `tests/test_schema_013.py`의 "우주선 부품" 케이스로 따로 고정한다.

### 2-4. 재현

```bash
cd src
python3 -m import_compliance.cli --check-testset   # 분야별 정확도·FN 출력
python3 tests/test_testset_100.py                  # 구조·정확도·FN·결정성 18건
python3 tools/build_testset_100.py                 # 테스트셋 재생성(수정 시)
```

## 3. 표준 판정 상태와 누락 정보

### 3-1. `assessment_status` 5단계

| 상태 | 의미 | 대응하는 `verdict` |
|---|---|---|
| `APPLICABLE` | 현재 정보로 해당 규제 적용 대상 | `check_likely` (빠진 스펙 없음) |
| `POTENTIALLY_APPLICABLE` | 적용될 수 있으나 스펙이 비어 있음 | `check_likely` + `missing_information` 존재 |
| `REVIEW_REQUIRED` | 쟁점은 확인, 입력만으로 적용 여부를 정할 수 없음 | `info_needed` |
| `NOT_APPLICABLE` | 현재 정보 기준 가능성 낮음 | `low_risk` |
| `UNKNOWN` | 규정 신호를 찾지 못함 | `info_needed` + findings 0건 |

`verdict` 는 하위 호환을 위해 **그대로 유지**한다. 상태는 `verdict`·findings 수·누락 정보에서 계산하며, 실시간 조회로 `verdict` 가 올라가면 API 계층이 상태를 다시 맞춘다.

상태·누락 정보는 assess 계열 응답(`assess_import_case`, `lookup_hs_requirements`, `check_kc_certification`, `check_food_cosmetics`)에 실린다. `lookup_recall`·`get_legal_basis`·`explain_trap`·`get_service_meta` 는 판정 툴이 아니므로 공통 지리 필드만 갖는다.

### 3-2. `missing_information`

응답 최상위 목록은 표준 스펙명(canonical)으로만 나온다. 내부 필드명은 `findings[].missing_inputs` 에 그대로 남겨 기존 클라이언트를 깨지 않는다.

| 내부 필드 | 표준 스펙명 | 예 |
|---|---|---|
| `target_age` | `intended_age` | 어린이제품 대상 연령 |
| `hs_code` | `hs_10_code` | HS 10자리(6자리는 부족) |
| `rf_tx` | `wireless_function` | 무선 송신 기능 유무 |
| `rated_power` | `rated_power` | 정격출력(1kVA 이하 등) |
| `ac_plug` | `ac_plug` | AC 플러그 사용 여부 |
| `has_pccc` | `personal_customs_id` | 개인통관고유부호 |
| `price_usd` | `declared_value_usd` | 신고가액 |
| `food_contact` | `food_contact_use` | 식품 접촉 용도 |
| `has_cert` | `safety_confirmation_certificate` | 안전확인 신고증명서 |

`missing_information_detail` 에는 필드별 `prompt`·`allowed_values`·`case_id` 가 함께 실린다.

```json
"assessment_status": "POTENTIALLY_APPLICABLE",
"assessment_status_label_ko": "적용 가능성 있음",
"missing_information": ["rated_power", "ac_plug"],
"assessment_status_note_ko": "적용될 수 있으나 일부 스펙이 비어 있습니다. missing_information 항목을 채우면 판정이 좁혀집니다."
```

## 4. 글로벌 확장 대비 공통 스키마

```json
"schema_version": "0.1.3",
"destination": "KR",
"jurisdiction": "KR",
"origin": "CN",
"origin_source": "query"
```

- `destination` — 통관 목적국. 현재 엔진이 아는 값은 `KR` 하나이며, 요청에 `destination` 을 주면 그 값이 그대로 실린다.
- `jurisdiction` — 적용 법역. 법령 카드가 한국법 기준이므로 항상 `KR`.
- `origin` — 원산지 ISO 3166-1 alpha-2. 질의문 국가명(한/영)·`facts.origin` 에서 찾고, **찾지 못하면 `null`**(추측 금지). `origin_source` 는 `query` / `facts` / `null`.
- 모든 툴 결과에 같은 4개 필드가 실린다(`api._envelope`). `check_kc_certification` 처럼 assess 를 거치지 않는 경로도 포함된다.

## 5. 이번에 함께 고친 엔진 동작 (테스트셋이 드러낸 것)

100건을 돌려 보니 **미탐(신호 하나로는 안 걸림)** 과 **오탐(범용 단어 2개로 엉뚱한 카드가 걸림)** 이 함께 나왔다. 코퍼스에 `strong_signals`(품목을 특정하는 단어) · `exclude_signals`(명시적 제외) 를 두고, 매칭 규칙에 범용 단어 목록(`GENERIC_SIGNALS`)을 넣어 아래를 고쳤다.

| 유형 | 질의 | 수정 전 | 수정 후 |
|---|---|---|---|
| 미탐 | `PPSU 젖병을 수입해 판매` | 쟁점 없음 | `TRAP-03` 어린이제품 |
| 미탐 | `섬유유연제를 수입해 판매` | 쟁점 없음 | `TRAP-16` 생활화학제품 |
| 미탐 | `홍삼 제품을 수입해 판매` | 쟁점 없음 | `TRAP-09` 건강기능식품 |
| 미탐 | `적외선 리모컨을 수입해 판매` | 쟁점 없음 | `TRAP-06` + `low_risk`(송신 없음) |
| 오탐 | `150달러 이하 보조배터리를 해외직구로 반입` | `TRAP-14` 의약품까지 | `TRAP-12`·`TRAP-05` 만 |
| 오탐 | `미백 기능성 화장품을 수입해 판매` | `TRAP-09` 건기식까지 | `TRAP-02` 만 |
| 오탐 | `식품용 밀폐용기를 수입해 판매` | `TRAP-01` 식품·`TRAP-07` 영업등록까지 | `TRAP-11` 기구·용기만 |

기존 20케이스 판정은 모두 그대로다(회귀 테스트 27건 통과). 코퍼스 버전은 `1.0.3 → 1.0.4`.

## 6. 남은 과제

1. **의료기기·위생용품 전용 규제 카드 없음** — 테스트셋의 이 분야 12건은 세관장확인(HS 10자리)·목록통관 축에서만 검증했다. 응답의 `scope_limits_ko` 에도 이 한계를 표시한다.
   - 카드를 추가하려면 근거 조문의 **현행 시행일 검증**이 먼저다. 법제처 API에서 의료기기법 제15조는 시행일이 `2027-10-21`(개정 예정)로 나와, 지금 넣으면 시행 전 조문을 현행으로 인용할 위험이 있다. 위생용품 관리법은 수입업 신고가 제3조, 표시가 제12조 계열이라 조문 번호 확인 후 넣어야 한다.
   - 추가 시 `standards.CASE_REGULATION_TAGS` 에 태그를 붙이고 테스트셋 `required_findings` 를 `MEDICAL_DEVICE_LICENSE`·`SANITARY_PRODUCT` 로 승격하면 된다.
2. **pSEO 35개 품목과 테스트셋 100건의 연결** — 지금은 별도 자산이다. 품목 slug ↔ case_id 매핑을 두면 pSEO 페이지에 "이 품목의 판정 요약"을 붙일 수 있다.
3. **글로벌 확장** — `destination`·`jurisdiction` 은 필드만 표준화했다. 실제 다법역 판정은 법령 카드의 `jurisdiction` 분리와 국가별 상태 어휘 확장이 선행돼야 한다.

## 7. 변경 파일

| 파일 | 내용 |
|---|---|
| `src/testset_100.json` | 대표 100개 테스트셋(신규) |
| `src/tools/build_testset_100.py` | 테스트셋 생성·구조 검증(신규) |
| `src/import_compliance/standards.py` | 상태 5단계·규제 태그·표준 스펙명·국가코드(신규) |
| `src/import_compliance/engine.py` | 상태·누락 정보·지리 필드·태그 산출, 강한 신호 매칭 |
| `src/import_compliance/models.py` | `strong_signals`·`exclude_signals`·`regulation_tags` |
| `src/import_compliance/api.py` | 모든 툴 응답 공통 필드, 상태 재계산, 메타 확장 |
| `src/import_compliance/policy.py` | 의료기기·위생용품 범위 한계 문구 |
| `src/import_compliance/web_ui.py` | 표준 상태·빠진 정보·목적지/원산지 표시 |
| `src/import_compliance/cli.py` | `--check-testset` |
| `src/traps_20.json` | `strong_signals`·`exclude_signals`, corpus 1.0.4 |
| `src/tests/test_testset_100.py` | 테스트셋 검증 18건(신규) |
| `src/tests/test_schema_013.py` | 스키마·하위 호환·익명성 31건(신규) |
| `version.py`·`Dockerfile`·`web_ui.SERVICE_VERSION` | `0.1.3` |
