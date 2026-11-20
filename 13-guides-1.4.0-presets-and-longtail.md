# 카탈로그 1.4.0 — 대표 품목 원클릭 프리셋 + 롱테일 가이드 17종(68 → 85)

2026-11-21. 1.3.0까지 가이드는 68종이었다. 이번 배치는 두 가지를 같이 한다.

1. **첫 화면 전환율** — `CLNS Check` 입력창 위에 대표 품목 버튼 5개를 두어, 처음 온 사람이
   설명을 읽지 않고 1초 만에 결과를 볼 수 있게 한다.
2. **검색 유입(pSEO)** — 실제로 검색창·AI 챗봇에 입력되는 롱테일 질문 17종을 더해 85종으로 늘린다.

새 페이지도 기존 계약을 그대로 지킨다. **조문 문안은 카탈로그에 쓰지 않고**, 이 저장소에서
검증한 상수(`advertising.py`ㆍ`labeling.py`ㆍ`ecommerce.py`ㆍ`feed.py`ㆍ`drugs.py`의 `B_*`,
`BASIS_*`)와 함정 코퍼스(`traps_20.json`) 케이스만 키로 참조한다. 해석되지 않는 키·케이스가
있으면 카탈로그 로딩 단계에서 서버가 뜨지 않는다(`GuideCatalogError`).

## 1. 대표 품목 원클릭 프리셋 (`web_ui.py`)

`<form id="check-form">` 안, 품목명 입력창 바로 위에 `role="group"` 버튼 5개를 둔다.

| 버튼 | 채우는 값 |
|---|---|
| 멜라토닌 직구 | 미국산 멜라토닌 수면 영양제 · 의약품·영양제 · 미국 · 해외직구 2병 (식약처 의약품 API 실시간 대조) |
| 강아지 간식 | 미국산 강아지 동결건조 간식 · 반려동물 사료 · 미국 · 판매 · HS 2309101000 |
| 수입 화장품 | 미국산 수딩 크림 · 화장품 · 미국 · 판매 · HS 3304992000 |
| 블루투스 이어폰 | 중국산 블루투스 이어폰 · 전자·생활용품 · 중국 · 무선 있음 · HS 8518309000 |
| 유아용 의류 | 베트남산 유아용 의류 · 품목군 자동 판단 · 베트남 · 어린이 대상 |

- 누르면 `applyPreset(key)` 가 품목명·HS·원산지·품목군·무선·어린이·수입 목적을 채우고
  `syncConditionalFields()` 로 조건부 입력(화장품 전성분·의약품·적합성평가 번호)을 맞춘 뒤
  `form.requestSubmit()` 으로 **바로 점검을 실행**한다. 요청Submit 이 없는 환경에서는
  `submit` 이벤트를 직접 던진다.
- 버튼은 `type="button"` 이라 폼 제출과 충돌하지 않고, `min-height:38px`ㆍ`white-space:nowrap`
  으로 모바일에서 누르기 쉽게 두었다. `:focus-visible` 윤곽선으로 키보드 접근도 유지한다.
- 기존 JS id/계약(`check-demo`ㆍ`check-demo-shop`ㆍ`check-demo-feed`ㆍ공유 바)은 건드리지 않았다.
  페이지 인라인 스크립트는 여전히 1개이고, 문자열·주석을 걷어낸 괄호 균형 검사를 통과한다.

## 2. 롱테일 가이드 17종

| # | slug | 질문 | 카테고리 | 주 근거(코퍼스) |
|---|---|---|---|---|
| 1 | `perfume-60ml-direct-buy` | 향수는 60mL까지 면세로 살 수 있나요? | 통관·면세 | TRAP-12, TRAP-02 · 화장품법 제10조① |
| 2 | `wine-liquor-direct-buy` | 와인·위스키는 150달러 이하면 세금이 없나요? | 통관·면세 | TRAP-12, TRAP-01 · 수입식품법 제15조① |
| 3 | `order-multiple-aggregate` | 여러 건으로 나눠 주문하면 세금이 합산되나요? | 통관·면세 | TRAP-12(고시 별표 1ㆍ관세법 시행규칙 제45조②) |
| 4 | `used-luxury-brand-ip` | 중고 명품, 정품이면 통관에 문제없나요? | 지재권·원산지 | TRAP-20(관세법 제235조ㆍ지재권 고시 제5조) |
| 5 | `contact-lens-medical-device` | 콘택트렌즈·미용렌즈도 의료기기 허가가 필요한가요? | 기타 규제 | TRAP-21(의료기기법 제15ㆍ17ㆍ20조) |
| 6 | `vape-device-import` | 전자담배 기기만 직구하면 담배 규제를 피할 수 있나요? | 기타 규제 | TRAP-15(담배사업법 제2조①), TRAP-16 |
| 7 | `quarantine-meat-dairy` | 육포·치즈·육가공품은 동물검역 신고를 해야 하나요? | 기타 규제 | TRAP-12 · 가축전염병 예방법 제31조③ㆍ제34조①ㆍ제36조①ㆍ제39조① |
| 8 | `stroller-carseat-kc` | 유모차·카시트는 KC 안전인증 없이 들여올 수 있나요? | 어린이제품 | TRAP-03(어린이제품 안전특별법 제17ㆍ18ㆍ22ㆍ25조) |
| 9 | `led-multitap-kc` | LED 조명·멀티탭도 KC 인증 대상인가요? | 전기·전파·KC | TRAP-04(전기용품법 시행규칙 제3조①ㆍ별표 3) |
| 10 | `kitchen-appliance-110v-kc` | 미국 직구 에어프라이어, 110V는 어떻게 봐야 하나요? | 전기·전파·KC | TRAP-04 |
| 11 | `wearable-health-device` | 혈압·심전도 스마트워치는 의료기기인가 전파인증인가? | 전기·전파·KC | TRAP-21, TRAP-06(전파법 제58조의2) |
| 12 | `roasted-coffee-tea-import` | 원두커피·차는 식약처 수입신고를 해야 하나요? | 식품·화장품 | TRAP-01, TRAP-12 · 수입식품법 제15ㆍ20조 |
| 13 | `tumbler-food-contact` | 스테인리스 텀블러·보온병도 식품용 기구 신고 대상인가요? | 식품·화장품 | TRAP-11(수입식품법 제2조①, 식품위생법 제9조) |
| 14 | `cosmetics-quality-inspection` | 수입 화장품 품질검사는 언제 면제되나요? | 식품·화장품 | TRAP-02(화장품법 제3조①ㆍ제16조①, 품질검사 면제 규정) |
| 15 | `food-purchase-agency-registration` | 수입식품 구매대행을 하려면 어떤 영업등록이 필요한가요? | 식품·화장품 | TRAP-01, TRAP-07 · 수입식품법 제15ㆍ20조 |
| 16 | `food-expiry-labeling` | 원포장 그대로 팔 때 한글 소비기한은 어떻게 표시하나요? | 표시·광고 | TRAP-10(식품표시광고법 제4조, 통합공고 제52조) |
| 17 | `purchase-agency-withdrawal` | 해외 구매대행 상품도 청약철회·반품이 되나요? | 국내 이커머스·공정위 | 전자상거래법 제17조①②③⑥ㆍ제18조⑨ㆍ시행령ㆍ지침 |

- 카테고리 8종에 흩어져 있고, 질문 85개는 모두 문장이 다르다(중복 질문 금지 테스트).
- 모든 항목이 `cases` 또는 `basis_keys` 중 하나 이상을 실제로 해석한다. 근거가 비면
  `is_indexable()` 이 False 가 되어 `noindex` 로 떨어지고, 테스트가 먼저 실패한다.
- `find_conclusive_phrasing()` 0건: "확정"ㆍ"대상입니다"ㆍ"필요 없습니다"ㆍ"100%" 를 쓰지 않고
  "확인해야 합니다"ㆍ"검토합니다" 로 쓴다.
- 새 페이지가 고립되지 않게 기존 인기 페이지(면세 한도ㆍ목록통관 배제ㆍ직구 화장품ㆍ의료기기ㆍ어린이제품ㆍKCㆍ식품 수입신고ㆍ식품용 기구ㆍ한글표시ㆍ병행수입ㆍ니코틴ㆍ청약철회)에서 관련 링크를 걸어, 17종 모두 유입 링크 1개 이상을 갖는다.
- 60mL(향수)ㆍ110V(전압)ㆍ7일ㆍ3개월ㆍ30일(청약철회)처럼 조문 인용이 아닌 사실 서술은
  근거 문장과 분리해 적고, 판단이 갈리는 조건은 체크포인트로 남겼다.

## 3. 계약 유지

| 항목 | 값 |
|---|---|
| `catalog_version` | 1.3.0 → **1.4.0** |
| `verified_on` | 2026-11-20 → **2026-11-21** |
| 가이드 수 | 68 → **85** |
| 색인 URL(sitemap) | 106 → **123** (홈 1 + 품목 36 + 가이드 86) |
| 기존 버전 핀 테스트 | `test_share_and_longtail_guides.py`ㆍ`test_ecommerce_ftc.py` 를 1.4.0/85 로 동기화 |

새 파일 `src/tests/test_guides_140_presets.py` 가 17종의 근거ㆍ태그ㆍ툴ㆍ문안 규칙과
프리셋 5개(HTMLㆍCSSㆍJSㆍquickjs 실행)를 검증한다.

## 4. 실행한 검증 (2026-11-21)

```
PYTHONPATH=src python3 -m unittest discover -s src/tests -q     # 555 tests OK
PYTHONPATH=src python3 -m import_compliance.cli --check-corpus   # 25 cases OK
PYTHONPATH=src python3 -m import_compliance.cli --check-testset  # 100 cases, FN=0
PYTHONPATH=src python3 -m import_compliance.cli --check-drugs    # 14/14
```

익명성: 새로 만든 파일(`add_guides_v140.py`ㆍ`test_guides_140_presets.py`ㆍ`guides_items.json`
항목)과 렌더 페이지에 이름ㆍ연락처ㆍ이메일ㆍ사업자 정보ㆍ토큰 모양이 없다(테스트로 강제).
