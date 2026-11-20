---
title: "07 · 0.1.4 엔진 보강 — 의료기기·위생용품 카드와 전파 적합성평가 실연동"
---

# 0.1.4 변경 — 의료기기·위생용품 카드, 전파 적합성평가 연동, pSEO 연결 보강

이 문서는 CLNS `0.1.4`(2026-11-18)에서 바뀐 것을 근거와 함께 남긴다. 서비스 식별자는 `CLNS-KR` 하나만 쓰며 개인정보·시크릿은 들어 있지 않다. 모든 법령 조문은 `.env`의 법제처 OC 값으로 `open.law.go.kr` API를 **실호출**해 확인했고, 산출물은 `medical-hygiene-law-verification.json`(키 없음)이다.

## 1. 왜 '현행 조문' 검증이 먼저였나

법제처 `lawSearch`/`lawService`(`target=law`)는 **가장 최근에 공포된 법령**을 돌려준다. 그 법령이 아직 시행 전이면 조문 본문과 `조문시행일자`가 **미래 날짜**다.

실제로 2026-11-18 조회에서 의료기기법의 최신 버전은 **법률 제22105호(공포 2026-10-20, 본문 시행 2027-10-21)** 이었고, 이 버전의 제2·3·6·15·17·19·20조는 모두 `조문시행일자 = 2027-10-21`이었다. 이걸 그대로 인용하면 "아직 시행되지 않은 조문"을 현행 근거로 쓰는 오류가 난다.

그래서 `tools/verify_law_articles.py`를 만들었다. 버전을 시행일 최신순으로 내려가며 **해당 조문의 조문시행일자가 오늘 이하이고 본문이 있는 첫 버전**을 채택하고, 미래 시행 버전은 `skipped_future_versions`에 남긴다.

```bash
cd src
python3 tools/verify_law_articles.py \
  --target '의료기기법:2,3,6,15,17,19,20' \
  --target '위생용품 관리법:2,3,8,10,11,12' \
  --out ../medical-hygiene-law-verification.json
```

### 검증 결과 (2026-11-18 기준)

| 법령 | 인용 조문 | 시행일 | 채택 버전 | 비고 |
|---|---|---|---|---|
| 의료기기법 | 제2조(정의), 제3조(등급분류와 지정), 제6조(제조업 허가), 제15조(수입업허가 등), 제17조(판매업 등의 신고), 제19조(기준규격), 제20조(용기 등의 기재사항) | 2026-10-08 | 법률 제21525호 (MST 285343) | 2026-10-20 공포분(본문 2027-10-21 시행)은 **제외** |
| 위생용품 관리법 | 제2조(정의), 제3조(영업의 신고), 제8조(수입 위생용품의 신고 및 검사), 제10조(기준 및 규격), 제11조(표시기준), 제12조(허위표시 등의 금지) | 2026-05-12 | 법률 제21142호 (MST 279749) | 최신 시행본 |

- 의료기기법 제15조제1항: "의료기기의 수입을 업으로 하려는 자는 식품의약품안전처장의 수입업허가를 받아야 한다."
- 의료기기법 제15조제2항: 수입업자는 수입하려는 의료기기에 대하여 **수입허가 또는 수입인증을 받거나 수입신고**를 하여야 한다.
- 위생용품 관리법 제3조제2항: 위생용품수입업을 하려는 자는 시설을 갖추고 **식품의약품안전처장에게 신고**하여야 한다.
- 위생용품 관리법 제8조: 수입 위생용품은 **수입신고** 대상이며, 식약처장은 **통관 절차가 끝나기 전에 검사**하게 하여야 한다.

## 2. 새 규제 카드 2개 (코퍼스 1.0.5, 22개 쟁점)

| 카드 | 쟁점 | 기본 판정 | 규제 태그 |
|---|---|---|---|
| `TRAP-21` | 미국 FDA·유럽 CE 승인만 받으면 한국에서 의료기기를 팔 수 있다? — 수입업 허가와 품목 허가는 별개 | `check_likely` | `MEDICAL_DEVICE_IMPORT` |
| `TRAP-22` | 위생용품은 세관장확인만 보면 된다? — 수입업 신고·수입신고·검사·기준규격이 따로 있다 | `check_likely` | `HYGIENE_PRODUCT_IMPORT` |

- 두 카드 모두 **필수 입력 없이** `check_likely`가 유지된다(수입업 허가·신고는 등급·성분과 무관하게 걸리는 축이기 때문). 등급(1~4등급)은 세부 절차(수입허가/인증/신고)만 가른다.
- 카드의 `notes`에 **법령 경계**를 명시했다: 생리대·탐폰·생리컵과 KF·비말차단·수술용 마스크는 **의약외품(약사법)**, 기저귀·팬티라이너는 위생용품, 다회용 포크·나이프는 식품용 기구, 일회용 포크·나이프는 위생용품.
- `engine.SOURCE_MAP`에 `medical`·`hygiene` 축을 추가해 `customs_requirements`·`law_api` 상태를 함께 남긴다(식약처 의료기기·위생용품 공개 API는 현재 없어서 통관·법령 축으로 확인하고 그 한계를 응답에 밝힌다).
- `policy.SCOPE_LIMITS_KO`를 실제 반영 상태로 갱신: 22개 쟁점, 의료기기·위생용품 카드 범위, 의약외품·의약품은 범위 밖(통관 축만), 적합성평가는 인증번호 필요.

## 3. 전파 적합성평가(RRA) 실연동

### 확인한 것

| 항목 | 값 |
|---|---|
| data.go.kr 데이터셋 | 과학기술정보통신부 국립전파연구원_적합성평가 DB정보 (**3034183**, 제공형태 `LINK`, 이용허락범위 제한 없음) |
| 실제 호출 주소 | `http://emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthInfo.do?mtlCefNo={인증·등록번호}` |
| 키 필요 여부 | **불필요** — `serviceKey` 없이 HTTP 200 응답(2026-11-18 실측) |
| 결과 코드 | `0000` 조회됨 · `0001` 조회 결과 없음 · `0098` 파라미터 누락 |
| 응답 필드(정규화) | `cert_no`, `company`, `equipment_name`, `base_model`, `derivative_models`, `manufacturer`, `manufacture_country`, `certified_on`, `remarks` |

실측 예: `R-LARN-00-0210` → 기자재명 `특정소출력무선기기(무선조정용)`, 기본모델 `HSC-T80`, 인증일 `2000-11-23`.
(`getAuthStatus.do`는 인증 여부 Y/N만 주는 경량 엔드포인트로, 필요할 때만 쓴다.)

### 엔진에서 달라진 점

- 예전: 전파(무선) 쟁점이면 `data_provenance.sources`에 `rra_conformity: unavailable`만 남았다.
- 지금:
  - 인증·등록번호가 있으면(`facts.rra_cert_no`, 또는 질의문의 `R-LARN-00-0210` 같은 표기) **실시간 조회**해 `rra_conformity_live` 블록과 `data_provenance`(`state: live`, `cert_no`, `item_count`)를 채운다.
  - 번호가 없으면 `state: "certificate_number_required"` + `lookup_field: "rra_cert_no"` + `official_url`로 안내한다("미연결"이 아니라 "번호를 주면 조회 가능").
  - 조회 결과 0건은 `state: "not_found"`로 두고 **"0건 ≠ 미인증"** 문구를 함께 반환한다.
  - 실패는 `state: "error"` + 코드로 남기고, 전파 쟁점 판정은 코퍼스·법령 근거로만 유지한다.
- 캐시: **7일 TTL**(`CACHE_TTL_HOURS = 168`). 재호출은 `state: "cached_fallback"` + `age_hours`·`cache_note_ko`로 시점을 밝힌다.
- 같은 요청에서 엔진과 툴이 같은 API를 두 번 부르지 않도록, 엔진 `SOURCE_MAP`의 전파 축은 `customs_requirements`·`law_api`만 두고 **RRA 실호출은 api 계층이 단독 수행**한다.
- 라이브 모드에서 다른 키가 없어도 RRA는 켜진다(`from_environment(keyless_rra=True)` — 서버·CLI 기본).

## 4. 테스트셋 100건 승격 (1.0.1)

의료기기·위생용품 12건 중 10건은 필수 태그를 승격했고, 2건(생리대)은 **법령상 의약외품**이라 위생용품으로 승격하지 않고 `must_not_find`로 오분류를 막았다. 분야 정확도 12/12, 전체 100/100, FN 0.

| 케이스 | 품목 | 기대 판정 | 필수 태그 |
|---|---|---|---|
| CASE-089~093, 098 | 전자혈압계·체온계·의료용 장갑·콘택트렌즈·의료기기 9018.90 | `check_likely` | `MEDICAL_DEVICE_IMPORT` + `CUSTOMS_CHECKPOINT` |
| CASE-095~097 | 기저귀·위생용 면봉·칫솔 | `check_likely` | `HYGIENE_PRODUCT_IMPORT` + `CUSTOMS_CHECKPOINT` |
| CASE-099 | 150달러 이하 콘택트렌즈 직구 | `check_likely` | `CUSTOMS_LOW_VALUE` + `MEDICAL_DEVICE_IMPORT` |
| CASE-094, 100 | 생리대(의약외품) | `info_needed` / `check_likely` | `CUSTOMS_CHECKPOINT` / `CUSTOMS_LOW_VALUE` + **`must_not_find`** |

`--check-testset` 결과:

```
battery 12/12 · children_product 12/12 · cosmetics 10/10 · electrical_electronics 16/16
food_health_functional 16/16 · household_chemical 10/10 · medical_sanitary 12/12 · wireless_rf 12/12
OK testset_version=1.0.1 cases=100 false_negatives=0 verdict_mismatch=0
```

## 5. pSEO 35개 페이지 연결 보강 (카탈로그 1.0.1)

모든 품목 페이지에 같은 형식으로 다음을 넣었다.

- **이 품목에 걸리는 규제 축** — 태그별 `규제 축 · 소관 기관 · 확인 카드(TRAP-xx) · MCP 툴` 표
- **HS 요건 ≠ 법령상 품목 분류** — 세관장확인 표는 HS 10자리 단위 요건이라 다른 품목 요건이 섞일 수 있고, 표에 없다고 법 적용이 없는 것은 아니라는 설명(의료기기·위생용품 페이지에는 의약외품 경계 문장 추가)
- **API·MCP로 이 품목 자동 조회** — 이 품목에 실제로 쓸 툴만 골라 HTTP·MCP·stdio 경로를 안내
- **해외직구·목록통관으로 들여올 때** — TRAP-12·13 내용을 모든 페이지에 공통으로 안내

법령 검증 결과에 맞춰 잘못 적혀 있던 분류 문구도 고쳤다.

- 1회용 마스크: KF 보건용 **+ 비말차단용·수술용**은 의약외품, 일반 마스크는 위생용품 목록에 없어 공산품 축 → 카테고리 `의약외품·공산품·어린이제품`
- 아기 젖병: 위생용품 목록에 없음 → 카테고리 `어린이제품·식품용 기구`
- 전동칫솔: 칫솔모·헤드는 구강관리용품(위생용품) → `TRAP-22` 연결
- 마사지건: HS 9019.10(마사지용 기구) → `TRAP-21`(의료기기 해당·등급 확인) 연결
- 올리브오일: `TRAP-17`(FTA 원산지) 연결

## 6. 테스트 결과

```
python3 -m unittest discover -s tests   # Ran 247 tests — OK
python3 -m import_compliance.cli --check-corpus
  OK corpus_version=1.0.5 cases=22 verified_on=2026-11-18
python3 -m import_compliance.cli --check-testset
  OK testset_version=1.0.1 cases=100 false_negatives=0 verdict_mismatch=0
```

새 테스트 `src/tests/test_medical_hygiene_rra.py`(25건)가 다음을 고정한다.

1. 검증 산출물의 모든 조문 시행일 ≤ 검증일, 미래 시행 조문은 `skipped_future_versions`에 존재, 코퍼스 카드의 시행일·URL·검증일이 산출물과 일치
2. 의료기기·위생용품 쟁점 검출, **생리대는 위생용품·의료기기 태그가 붙지 않음**
3. RRA XML 파싱(0000/0001/0098), 키 없는 클라이언트, 번호 탐지, 7일 TTL 캐시, 번호 없음/0건/실패 상태의 정직한 표기, `data_provenance` 반영
4. pSEO 35개 페이지의 규제 축·근거·면책·MCP 안내 존재, 태그·카드 어휘 정합

## 7. 남은 한계

- **의료기기·위생용품은 공개 API가 없다.** 식약처 의료기기 허가·위생용품 수입신고를 실시간 조회하는 공개 API가 없어, 카드는 법령 근거와 통관 축으로 안내한다. 유료화 전에는 식약처 서면 확인과 별도 API 검토가 필요하다.
- **RRA는 인증·등록번호 단위 조회만** 제공한다(모델명 검색 API 없음). 모델명으로 찾으려면 국립전파연구원 적합성평가 현황 검색 화면을 안내한다.
- **의약외품·의약품은 범위 밖**이다(생리대 단독 질의는 카드가 없어 "특정하지 못함"으로 나온다). 필요하면 별도 카드로 확장한다.
