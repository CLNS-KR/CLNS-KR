"""공공데이터포털(data.go.kr) · 법제처 국가법령정보 Open API 실호출 어댑터.

설계 원칙
---------
1. **키는 `.env`/환경변수에서만 읽는다.** 코드·문서·로그·응답에 키를 남기지 않는다
   (`redact()`가 모든 상태·에러 메시지에서 키를 지운다).
2. **원본 필드명을 외부로 내보내지 않는다.** `normalize_*()`가 `hs_code`,
   `requirement_law`, `law_name` 같은 정규화 필드로 바꾸고, 원본 payload는
   내부 스냅샷(Store.api_snapshots)에만 남긴다.
3. **키 동기화 지연을 정직하게 다룬다.** 방금 발급한 키는 게이트웨이에 아직
   등록되지 않아 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(코드 30)가 날 수 있다.
   이 경우에만 10~20초 대기 후 1회 재시도하고, 그래도 실패하면 코드·사유를
   그대로 보고한다(추정으로 채우지 않는다).
4. **표준 라이브러리만 사용한다.** (urllib, json, xml.etree)
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

KST = timezone(timedelta(hours=9))

# --- 소스 식별자 (store.sources.source_id 와 동일하게 사용) ---------------------
SOURCE_CUSTOMS = "customs_requirements"      # 관세청 세관장확인대상물품 (15101589)
SOURCE_MFDS_PERMIT = "mfds_import_food"      # 식약처 수입식품 허가정보 (15058273)
SOURCE_MFDS_PRODUCT = "mfds_import_product_db"  # 식약처 수입식품 제품DB (15073949)
SOURCE_LAW = "law_api"                        # 법제처 국가법령정보 공동활용
SOURCE_RRA = "rra_conformity"                 # 국립전파연구원 적합성평가(인증·등록번호 조회, 키 불필요)
SOURCE_DISPOSITION_MFG = "mfds_disposition_manufacturing"   # 식약처 행정처분결과(식품제조가공업, 15124560)
SOURCE_DISPOSITION_SALES = "mfds_disposition_sales"         # 식약처 행정처분결과(식품판매업, 15124559)

# --- 검증된 엔드포인트 (2026-11-18 data.go.kr 상세페이지 swagger·요청주소 기준) ---
CUSTOMS_URL = "https://apis.data.go.kr/1220000/retrieveCcctLworCd/getRetrieveCcctLworCd"
MFDS_PERMIT_URL = "https://apis.data.go.kr/1471000/ImportFoodPrmisnInfoService05/getImrtsCnfirmList05"
MFDS_IMPROPER_URL = "https://apis.data.go.kr/1471000/ImportFoodPrmisnInfoService05/getInspctImproptList05"
MFDS_PRODUCT_URL = "https://apis.data.go.kr/1471000/IprtFoodPrdtDBService02/getIprtFoodPrdtDBInq02"
LAW_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

# 식약처 행정처분결과 API (2026-11-19 data.go.kr 상세페이지·실호출로 확인).
# 두 데이터셋은 승인·게이트웨이 전파 상태가 따로 움직인다(한쪽만 코드 30이 나올 수 있다).
MFDS_DISPOSITION_ENDPOINTS: Dict[str, str] = {
    "manufacturing": "https://apis.data.go.kr/1471000/AdmmRsltFoodMnftPrcsService01"
                     "/getAdmmRsltFoodMnftPrcsBssh01",
    "sales": "https://apis.data.go.kr/1471000/AdmmRsltFoodSaleService01"
             "/getAdmmRsltFoodSaleBssh01",
}
MFDS_DISPOSITION_SOURCES: Dict[str, str] = {
    "manufacturing": SOURCE_DISPOSITION_MFG,
    "sales": SOURCE_DISPOSITION_SALES,
}

# 국립전파연구원 적합성평가 Open API — **키가 필요 없는 공개 엔드포인트**.
# data.go.kr 3034183(적합성평가 DB정보)은 '제공형태: LINK' 로, 실제 호출은 아래 주소로 한다.
# 인증·등록번호(mtlCefNo) 하나로 조회하며, 검색용 목록 API 는 제공되지 않는다.
RRA_STATUS_URL = "http://emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthStatus.do"
RRA_INFO_URL = "http://emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthInfo.do"
RRA_OFFICIAL_URL = "https://www.rra.go.kr/ko/license/A_c_search.do"
RRA_DATA_GO_KR_ID = "3034183"
RRA_RESULT_LABEL = {
    "0000": "조회됨",
    "0001": "조회 결과 없음",
    "0098": "요청 파라미터 누락",
}

USER_AGENT = "clns-kr/0.1 (+Korea import compliance verification; contact: operator)"
DEFAULT_TIMEOUT = 20.0
UNREGISTERED_RETRY_SLEEP = 15.0   # 키 동기화 대기 (10~20초 권고 범위)

# 캐시 store.sources 카탈로그(라이선스·갱신주기 근거를 함께 남긴다)
SOURCE_CATALOG = [
    {
        "source_id": SOURCE_CUSTOMS,
        "name_ko": "관세청_세관장확인대상물품(GW)",
        "provider": "관세청",
        "license_scope": "이용허락범위 제한 없음",
        "base_url": "https://apis.data.go.kr/1220000/retrieveCcctLworCd",
        "update_cycle": "realtime",
    },
    {
        "source_id": SOURCE_MFDS_PERMIT,
        "name_ko": "식약처_수입식품 허가 정보",
        "provider": "식품의약품안전처",
        "license_scope": "이용허락범위 제한 없음(data.go.kr 경유)",
        "base_url": "https://apis.data.go.kr/1471000/ImportFoodPrmisnInfoService05",
        "update_cycle": "daily",
    },
    {
        "source_id": SOURCE_MFDS_PRODUCT,
        "name_ko": "식약처_수입식품 제품DB 정보",
        "provider": "식품의약품안전처",
        "license_scope": "이용허락범위 제한 없음(data.go.kr 경유)",
        "base_url": "https://apis.data.go.kr/1471000/IprtFoodPrdtDBService02",
        "update_cycle": "daily",
    },
    {
        "source_id": SOURCE_LAW,
        "name_ko": "법제처 국가법령정보 공동활용 OPEN API",
        "provider": "법제처",
        "license_scope": "출처표시 조건 영리·2차 이용 허용",
        "base_url": "https://www.law.go.kr/DRF/lawSearch.do",
        "update_cycle": "daily",
    },
    {
        "source_id": SOURCE_RRA,
        "name_ko": "국립전파연구원_적합성평가 DB정보(인증·등록번호 조회)",
        "provider": "과학기술정보통신부 국립전파연구원",
        "license_scope": "이용허락범위 제한 없음(data.go.kr 3034183, 키 불필요 공개 API)",
        "base_url": "http://emsit.go.kr/openapi/service/AuthenticationInfoService",
        "update_cycle": "realtime",
    },
    {
        "source_id": SOURCE_DISPOSITION_MFG,
        "name_ko": "식약처_행정처분결과(식품제조가공업)",
        "provider": "식품의약품안전처",
        "license_scope": "이용허락범위 제한 없음(data.go.kr 15124560)",
        "base_url": "https://apis.data.go.kr/1471000/AdmmRsltFoodMnftPrcsService01",
        "update_cycle": "realtime",
    },
    {
        "source_id": SOURCE_DISPOSITION_SALES,
        "name_ko": "식약처_행정처분결과(식품판매업)",
        "provider": "식품의약품안전처",
        "license_scope": "이용허락범위 제한 없음(data.go.kr 15124559)",
        "base_url": "https://apis.data.go.kr/1471000/AdmmRsltFoodSaleService01",
        "update_cycle": "realtime",
    },
]


def register_sources(store: Any) -> None:
    """store.sources 에 4개 소스 카탈로그를 등록한다(없을 때만)."""
    for row in SOURCE_CATALOG:
        store.upsert_source(row["source_id"], row["name_ko"], row["provider"],
                            row["license_scope"], row["base_url"], row["update_cycle"])

# data.go.kr 게이트웨이 오류코드 → (의미, 재시도 가치)
GATEWAY_ERRORS: Dict[str, Tuple[str, bool]] = {
    "10": ("INVALID_REQUEST_PARAMETER_ERROR: 요청 파라미터 오류", False),
    "11": ("NO_MANDATORY_REQUEST_PARAMETERS_ERROR: 필수 파라미터 누락", False),
    "12": ("NO_OPENAPI_SERVICE_ERROR: 해당 오픈API 서비스가 없거나 폐기됨", False),
    "20": ("SERVICE_ACCESS_DENIED_ERROR: 서비스 접근 거부(활용신청 미승인)", False),
    "21": ("TEMPORARILY_DISABLE_THE_SERVICE_KEY_ERROR: 일시적 키 비활성", True),
    "22": ("LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR: 일일 트래픽 초과", False),
    "30": ("SERVICE_KEY_IS_NOT_REGISTERED_ERROR: 등록되지 않은 서비스키(동기화 대기 가능)", True),
    "31": ("DEADLINE_HAS_EXPIRED_ERROR: 활용기간 만료", False),
    "32": ("UNREGISTERED_IP_ERROR: 등록되지 않은 IP", False),
    "99": ("UNKNOWN_ERROR: 기타 오류", False),
}


# ---------------------------------------------------------------------------
# .env 로딩 / 시크릿
# ---------------------------------------------------------------------------
def project_root() -> str:
    """`projects/import-compliance/` 절대경로 (이 파일 기준)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ENV_KEYS = ("DATA_GO_KR_SERVICE_KEY", "LAW_GO_KR_OC")


def load_env(path: Optional[str] = None) -> Dict[str, str]:
    """`.env`를 표준 라이브러리만으로 파싱한다. 이미 있는 환경변수를 우선한다.

    컨테이너·PaaS(Render 등)에는 `.env` 파일이 없고 환경변수만 주입되므로,
    파일이 없어도 키 이름이 환경변수에 있으면 그대로 읽는다.
    """
    env_path = path or os.path.join(project_root(), ".env")
    values: Dict[str, str] = {key: os.environ[key] for key in ENV_KEYS if os.environ.get(key)}
    try:
        with open(env_path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in values:
                    values[key] = value
    except (FileNotFoundError, OSError):
        return values
    return values


def from_environment(env: Optional[Dict[str, str]] = None, *, keyless_rra: bool = False,
                     **kwargs: Any) -> Optional["LiveApiClient"]:
    """환경에서 클라이언트를 만든다. 키가 하나도 없으면 None.

    `keyless_rra=True` 이면 키가 없어도 클라이언트를 만든다. 적합성평가(국립전파연구원)
    조회는 키가 필요 없는 공개 엔드포인트이기 때문에, 키 없이도 그 한 축은 실시간으로
    동작하게 하기 위한 선택지다(기본값은 기존과 동일하게 None).
    """
    env = env if env is not None else load_env()
    key = env.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    oc = env.get("LAW_GO_KR_OC", "").strip()
    if not key and not oc:
        return LiveApiClient(service_key="", law_oc="", **kwargs) if keyless_rra else None
    return LiveApiClient(service_key=key, law_oc=oc, **kwargs)


def redact(text: Optional[str], *secrets: str) -> str:
    """로그·에러 문구에서 키를 지운다(키가 4자 이상일 때만 치환)."""
    out = "" if text is None else str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "***REDACTED***")
            out = out.replace(urllib.parse.quote(secret, safe=""), "***REDACTED***")
    return out


# ---------------------------------------------------------------------------
# 응답 모델
# ---------------------------------------------------------------------------
@dataclass
class LiveFetch:
    """한 번의 실API 호출 결과(원본 items 는 내부 스냅샷용, 외부 노출 금지)."""

    source_id: str
    ok: bool
    state: str                       # live | error
    http_status: Optional[int] = None
    result_code: Optional[str] = None
    result_msg: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False
    total_count: Optional[int] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    raw: Any = None
    fetched_at: str = ""
    elapsed_ms: int = 0
    attempts: int = 1
    request_echo: Dict[str, Any] = field(default_factory=dict)

    def status(self) -> Dict[str, Any]:
        """외부로 내보내도 되는 상태 블록(원본 items·raw 제외)."""
        out = {
            "source_id": self.source_id,
            "state": self.state,
            "fresh": True if self.state == "live" else False,
            "age_hours": 0.0 if self.state == "live" else None,
            "fetched_at": self.fetched_at,
            "item_count": len(self.items),
            "attempts": self.attempts,
        }
        if self.total_count is not None:
            out["total_count"] = self.total_count
        if self.http_status is not None:
            out["http_status"] = self.http_status
        if self.result_code is not None:
            out["result_code"] = self.result_code
        if self.result_msg:
            out["result_msg"] = self.result_msg
        if self.error:
            out["error"] = self.error
        return out


class LiveApiError(RuntimeError):
    def __init__(self, source_id: str, message: str, *, code: Optional[str] = None,
                 http_status: Optional[int] = None, retryable: bool = False) -> None:
        super().__init__(f"{source_id}: {message}")
        self.source_id = source_id
        self.message = message
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------
def _as_list(node: Any) -> List[Any]:
    if node is None:
        return []
    if isinstance(node, list):
        return node
    return [node]


def parse_gateway_error(body: str) -> Optional[Dict[str, str]]:
    """data.go.kr 공통 오류 응답을 판별한다.

    실제 호출에서 같은 오류가 **XML(400)** 로도, **JSON(403)** 으로도 온다
    (예: `{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"returnReasonCode": "30" …}}}`).
    두 형식을 모두 처리해야 재시도·오류코드 보고가 빠지지 않는다.
    """
    if "cmmMsgHeader" in body:
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            header: Any = None
        else:
            header = root.find("./cmmMsgHeader")
            if header is None:
                header = root.find(".//cmmMsgHeader")
            if header is not None:
                return {
                    "errMsg": (header.findtext("errMsg") or "").strip(),
                    "authMsg": (header.findtext("returnAuthMsg") or "").strip(),
                    "reasonCode": (header.findtext("returnReasonCode") or "").strip(),
                }
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    node = payload
    if isinstance(payload, dict) and "OpenAPI_ServiceResponse" in payload:
        node = payload["OpenAPI_ServiceResponse"]
    if not isinstance(node, dict):
        return None
    header = node.get("cmmMsgHeader")
    if not isinstance(header, dict):
        return None
    return {
        "errMsg": str(header.get("errMsg", "")).strip(),
        "authMsg": str(header.get("returnAuthMsg", "")).strip(),
        "reasonCode": str(header.get("returnReasonCode", "")).strip(),
    }


def parse_customs_xml(body: str) -> Tuple[Dict[str, str], List[Dict[str, str]], Optional[int]]:
    """관세청 세관장확인대상물품 XML → (header, items, totalCount)."""
    root = ET.fromstring(body)
    header = {
        "resultCode": (root.findtext("./header/resultCode") or "").strip(),
        "resultMsg": (root.findtext("./header/resultMsg") or "").strip(),
    }
    items: List[Dict[str, str]] = []
    for item in root.findall("./body/items/item"):
        items.append({child.tag: (child.text or "").strip() for child in item})
    total = root.findtext("./body/totalCount")
    return header, items, int(total) if total and total.strip().isdigit() else None


def parse_mfds_json(payload: Dict[str, Any]) -> Tuple[Dict[str, str], List[Dict[str, Any]], Optional[int]]:
    header_raw = payload.get("header") or {}
    header = {
        "resultCode": str(header_raw.get("resultCode", "")).strip(),
        "resultMsg": str(header_raw.get("resultMsg", "")).strip(),
    }
    body = payload.get("body") or {}
    items = [dict(x) for x in _as_list(body.get("items")) if isinstance(x, dict)]
    total = body.get("totalCount")
    return header, items, int(total) if isinstance(total, (int, float)) else None


# 인증·등록번호 표기: KCC-REM-MJT-MJT, R-LARN-00-0210, MSIP-REM-XXX-1234, 적합등록 KCC-EMC-…
RRA_CERT_RE = re.compile(
    r"\b(?:KCC|MSIP|RCC|SIP|R|S|KC)-[A-Z0-9]{2,6}(?:-[A-Z0-9]{2,10}){1,4}\b",
    re.IGNORECASE,
)


def normalize_cert_no(value: Any) -> str:
    """인증·등록번호를 조회 가능한 형태로 정리한다(공백 제거·대문자, '-'는 유지)."""
    text = "".join(str(value or "").split()).upper()
    return text


def detect_cert_no(text: str) -> Optional[str]:
    """질의문에서 적합성평가 인증·등록번호를 찾는다. 없으면 None(추측 금지)."""
    if not text:
        return None
    match = RRA_CERT_RE.search(str(text))
    return normalize_cert_no(match.group(0)) if match else None


def parse_rra_xml(body: str) -> Tuple[Dict[str, str], Optional[Dict[str, str]], Any]:
    """적합성평가 Open API XML → (header, item, raw).

    응답은 단건이라 items 가 아니라 필드 나열이다. 결과코드 0000=조회됨,
    0001=조회 결과 없음, 0098=파라미터 누락.
    """
    root = ET.fromstring(body)
    data = {child.tag: (child.text or "").strip() for child in root}
    header = {"resultCode": data.get("resultCode", ""), "resultMsg": data.get("resultMsg", "")}
    item = None
    if header["resultCode"] == "0000" and (data.get("mtlCefNo") or data.get("mtlNm")):
        item = {key: value for key, value in data.items()
                if key not in ("resultCode", "resultMsg")}
    return header, item, data


def normalize_rra_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """적합성평가 조회 결과 정규화(원본 태그명은 외부로 내보내지 않는다)."""
    return {
        "cert_no": _clean(item.get("mtlCefNo")),
        "company": _clean(item.get("bsmNm")),
        "equipment_name": _clean(item.get("mtlNm")),
        "base_model": _clean(item.get("matlBscMdlNm")),
        "derivative_models": _clean(item.get("matlDerivMdlNm")),
        "manufacturer": _clean(item.get("matlMfrNm")),
        "manufacture_country": _clean(item.get("dtlInfCdNm")),
        "certified_on": _clean(item.get("cvaPcsYmd")),
        "remarks": _clean(item.get("matlEtcMtr")),
        "type": rra_cert_type(_clean(item.get("mtlCefNo"))),
    }


def rra_cert_type(cert_no: str) -> str:
    """번호 접두로 적합성평가 유형을 추정한다(추정값임을 호출부가 밝힌다)."""
    prefix = normalize_cert_no(cert_no).split("-")[0]
    return {
        "KCC": "적합등록/적합인증(구 표기)",
        "MSIP": "적합등록/적합인증",
        "R": "적합인증",
        "S": "적합등록",
    }.get(prefix, "미상")


def parse_law_json(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """법제처 lawSearch JSON → (items, totalCount)."""
    search = payload.get("LawSearch") or payload
    rows: List[Dict[str, Any]] = []
    for key, value in search.items():
        if key in ("totalCnt", "page", "numOfRows", "resultCode", "resultMsg"):
            continue
        for row in _as_list(value):
            if isinstance(row, dict):
                rows.append(row)
    total = search.get("totalCnt")
    try:
        total_int = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_int = None
    return rows, total_int


# ---------------------------------------------------------------------------
# 정규화 (원본 필드명 → 내부 표준 필드)
# ---------------------------------------------------------------------------
TIMING_LABEL = {"1": "사전확인", "2": "사후확인", "3": "실시간확인"}


def normalize_customs_item(item: Dict[str, Any]) -> Dict[str, Any]:
    timing_code = str(item.get("bfhnAffcRtmTpcd", "") or "")
    return {
        "hs_code": str(item.get("hsSgn", "") or ""),
        "requirement_law": str(item.get("dcerCfrmLworNm", "") or ""),
        "requirement_agency": str(item.get("reqApreIttNm", "") or ""),
        "requirement_document": str(item.get("reqCfrmIstmNm", "") or ""),
        "applies_from": _yyyymmdd(str(item.get("aplyStrtDt", "") or "")),
        "timing": TIMING_LABEL.get(timing_code, timing_code),
    }


def normalize_mfds_permit_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "product_name_ko": _clean(item.get("GOODS_KOR_NAME")),
        "product_name_en": _clean(item.get("GOODS_ENG_NAME")),
        "product_type": _clean(item.get("ITEM_NAME")),
        "import_category": _clean(item.get("NOTICE_GOODS_NAME")),
        "manufacturer": _clean(item.get("MANUFAC_NAME")),
        "manufacture_country": _clean(item.get("MANUFAC_COUNTRY_NAME")),
        "export_country": _clean(item.get("XPORT_COUNTRY_NAME")),
        "accepted_on": _yyyymmdd(_clean(item.get("ACCEPT_DATE"))),
        "receipt_no": _clean(item.get("RECEIPT_NO")),
    }


def normalize_mfds_product_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "product_name": _clean(item.get("PRDT_NM")),
        "product_category": _clean(item.get("DCLR_PRDT_DIVS_NM")),
        "manufacture_country": _clean(item.get("MNFT_NATN_NM")),
        "manufacture_country_code": _clean(item.get("MNFT_NATN_CD")),
        "item_name": _clean(item.get("PRDLST_NM")),
        "item_code": _clean(item.get("PRDLST_CD")),
    }


def normalize_mfds_improper_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """수입식품 검사부적합 검색 결과 정규화(15058273 오퍼레이션 2)."""
    return {
        "receipt_no": _clean(item.get("RECEIPT_NO")),
        "product_name_ko": _clean(item.get("GOODS_KOR_NAME")),
        "product_name_en": _clean(item.get("GOODS_ENG_NAME")),
        "product_type": _clean(item.get("ITEM_NAME")),
        "import_category": _clean(item.get("NOTICE_GOODS_NAME")),
        "manufacture_country": _clean(item.get("MANUFAC_COUNTRY_NAME")),
        "export_country": _clean(item.get("EXPORT_COUNTRY_NAME")),
        "manufacturer": _clean(item.get("NOTICE_MANUFAC_NAME")),
        "inspection_office": _clean(item.get("INSTT_NAME")),
        "accepted_on": _yyyymmdd(_clean(item.get("ACCEPT_DATE"))),
        "fail_reason": _squash(_clean(item.get("FAIL_REASON_DETAIL"))),
    }


def normalize_law_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """법령 검색 결과 정규화.

    법제처가 주는 `법령상세링크`에는 OC(사용자 식별자)가 붙어 있어 그대로 외부에
    내보내면 키가 노출된다. 외부에는 OC가 없는 사람용 고정주소만 준다.
    """
    name = _clean(item.get("법령명한글"))
    return {
        "law_name": name,
        "law_type": _clean(item.get("법령구분명")),
        "ministry": _clean(item.get("소관부처명")),
        "promulgated_on": _yyyymmdd(_clean(item.get("공포일자"))),
        "effective_from": _yyyymmdd(_clean(item.get("시행일자"))),
        "status": _clean(item.get("현행연혁코드")),
        "law_id": _clean(item.get("법령ID")),
        "mst": _clean(item.get("법령일련번호")),
        "url": "https://www.law.go.kr/법령/" + urllib.parse.quote(name),
        "source": "법제처 국가법령정보센터",
    }


def normalize_law_article(unit: Dict[str, Any]) -> Dict[str, Any]:
    """lawService JSON의 조문단위 → 조문 요지(항·호 본문 포함)."""
    no = _clean(unit.get("조문번호"))
    branch = _clean(unit.get("조문가지번호"))
    label = f"제{no}조" if no else ""
    if branch and branch != "0":
        label += f"의{branch}"
    paragraphs: List[str] = []
    raw_hang = unit.get("항")
    hang_units = raw_hang.get("항단위") if isinstance(raw_hang, dict) else raw_hang
    for hang in _as_list(hang_units):
        if isinstance(hang, dict):
            text = _squash(_clean(hang.get("항내용")))
            if text:
                paragraphs.append(text)
    body = _squash(_clean(unit.get("조문내용")))
    return {
        "article": label,
        "title": _clean(unit.get("조문제목")),
        "text": body,
        "paragraphs": paragraphs,
        "effective_from": _yyyymmdd(_clean(unit.get("조문시행일자"))),
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _clean(value.get("content"))
    return str(value).strip()


def _squash(text: str) -> str:
    return " ".join(text.split())


def _yyyymmdd(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) < 8:
        return ""
    return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"


# ---------------------------------------------------------------------------
# 클라이언트
# ---------------------------------------------------------------------------
class LiveApiClient:
    """4개 라이브 엔드포인트 호출기.

    transport 를 주입하면 네트워크 없이 단위 테스트할 수 있다.
    transport(url, timeout) -> (http_status, body_text, content_type)
    """

    def __init__(
        self,
        service_key: str = "",
        law_oc: str = "",
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Optional[Callable[[str, float], Tuple[int, str, str]]] = None,
        sleep: Callable[[float], None] = time.sleep,
        retry_sleep: float = UNREGISTERED_RETRY_SLEEP,
        max_attempts: int = 2,
        user_agent: str = USER_AGENT,
    ) -> None:
        self._service_key = (service_key or "").strip()
        self._law_oc = (law_oc or "").strip()
        self.timeout = timeout
        self._transport = transport or self._http_get
        self._sleep = sleep
        self.retry_sleep = retry_sleep
        self.max_attempts = max(1, max_attempts)
        self.user_agent = user_agent
        self.call_log: List[Dict[str, Any]] = []

    # --- 상태 ---------------------------------------------------------------
    @property
    def has_customs(self) -> bool:
        """관세청 세관장확인대상물품 조회 가능 여부(data.go.kr 서비스키)."""
        return bool(self._service_key)

    @property
    def has_mfds(self) -> bool:
        """식약처 수입식품 계열 조회 가능 여부.

        같은 data.go.kr 서비스키를 쓰지만 의미는 다르므로 따로 둔다. 예전 `_mfds_live()`
        가 `has_customs` 로 게이트되던 것을 이 속성으로 바꿨다.
        """
        return bool(self._service_key)

    @property
    def has_law(self) -> bool:
        return bool(self._law_oc)

    @property
    def has_rra(self) -> bool:
        """적합성평가 조회 가능 여부 — **키가 필요 없는 공개 엔드포인트**라 항상 True."""
        return True

    def capabilities(self) -> Dict[str, bool]:
        return {
            "customs_checkpoint": self.has_customs,
            "mfds_import_permit": self.has_mfds,
            "mfds_product_db": self.has_mfds,
            "law_search": self.has_law,
            "rra_conformity": self.has_rra,
            "mfds_disposition": self.has_mfds,
        }

    def __repr__(self) -> str:  # 키가 repr 로 새지 않게 고정 문자열
        return f"LiveApiClient(customs={self.has_customs}, law={self.has_law}, rra={self.has_rra})"

    # --- 저수준 HTTP --------------------------------------------------------
    @staticmethod
    def _http_get(url: str, timeout: float) -> Tuple[int, str, str]:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
                return response.status, body, response.headers.get_content_type()
        except urllib.error.HTTPError as exc:  # 4xx/5xx 도 본문에 단서가 있다
            body = exc.read().decode("utf-8", errors="replace")
            return exc.code, body, (exc.headers.get_content_type() if exc.headers else "")
        except urllib.error.URLError as exc:
            raise LiveApiError("network", redact(f"URLError: {exc.reason}")) from exc
        except TimeoutError as exc:
            raise LiveApiError("network", "timeout") from exc

    @staticmethod
    def _url(base: str, params: Dict[str, Any]) -> str:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        # quote_via=quote → 공백이 '+'가 아니라 %20이 되고, 키의 특수문자도 안전하게 인코딩된다.
        return f"{base}?{urllib.parse.urlencode(clean, quote_via=urllib.parse.quote, safe='')}"

    # --- 공통 호출 루프 -----------------------------------------------------
    def _call(self, source_id: str, url: str, *, parse: Callable[[str], Any],
              retry_on_unregistered: bool = True) -> Tuple[Any, LiveFetch]:
        started = time.monotonic()
        last_error: Optional[LiveApiError] = None
        for attempt in range(1, self.max_attempts + 1):
            status, body, content_type = self._transport(url, self.timeout)
            gateway_error = parse_gateway_error(body)
            if gateway_error:
                code = gateway_error["reasonCode"]
                label, retryable = GATEWAY_ERRORS.get(code, (gateway_error["errMsg"] or "UNKNOWN", False))
                message = redact(f"{gateway_error['errMsg']} | {gateway_error['authMsg']} (code {code})")
                last_error = LiveApiError(source_id, message, code=code, http_status=status,
                                          retryable=retryable)
                # 30(미등록 키)일 때만 동기화 대기 후 1회 재시도
                if retry_on_unregistered and code == "30" and attempt < self.max_attempts:
                    self._log(source_id, url, status, code, attempt, "retry_after_unregistered")
                    self._sleep(self.retry_sleep)
                    continue
                self._log(source_id, url, status, code, attempt, "error")
                raise last_error
            if status >= 400:
                last_error = LiveApiError(source_id, redact(f"HTTP {status}: {body[:200]}"),
                                          http_status=status)
                self._log(source_id, url, status, None, attempt, "http_error")
                raise last_error
            try:
                header, items, total, raw = parse(body)
            except ET.ParseError as exc:
                raise LiveApiError(source_id, redact(f"응답 파싱 실패: {exc}"), http_status=status) from exc
            except (json.JSONDecodeError, ValueError) as exc:
                raise LiveApiError(source_id, redact(f"응답 파싱 실패: {exc} | {body[:120]}"),
                                   http_status=status) from exc
            code = header.get("resultCode", "")
            ok = code in ("00", "0", "NORMAL SERVICE.", "NORMAL_SERVICE", "INFO-0", "")
            self._log(source_id, url, status, code, attempt, "ok" if ok else "service_error")
            fetch = LiveFetch(
                source_id=source_id,
                ok=ok,
                state="live" if ok else "error",
                http_status=status,
                result_code=code or None,
                result_msg=redact(header.get("resultMsg")),
                total_count=total,
                items=items,
                raw=raw,
                fetched_at=datetime.now(KST).isoformat(timespec="seconds"),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                attempts=attempt,
            )
            if not ok:
                raise LiveApiError(source_id, redact(f"{code} {header.get('resultMsg')}"),
                                   code=code, http_status=status)
            return header, fetch
        raise last_error or LiveApiError(source_id, "unknown")

    def _log(self, source_id: str, url: str, status: int, code: Optional[str],
             attempt: int, outcome: str) -> None:
        safe_url = redact(url, self._service_key, self._law_oc)
        self.call_log.append({
            "at": datetime.now(KST).isoformat(timespec="seconds"),
            "source_id": source_id,
            "http_status": status,
            "result_code": code,
            "attempt": attempt,
            "outcome": outcome,
            "path": urllib.parse.urlparse(safe_url).path,
        })

    # --- 1) 관세청 세관장확인대상물품 (15101589) ----------------------------
    def customs_checkpoint(self, hs_code: str, direction: str = "import",
                           *, retry_on_unregistered: bool = True) -> LiveFetch:
        if not self.has_customs:
            raise LiveApiError(SOURCE_CUSTOMS, "서비스키 없음(DATA_GO_KR_SERVICE_KEY)")
        imex = "2" if direction == "import" else "1"
        url = self._url(CUSTOMS_URL, {"serviceKey": self._service_key,
                                      "hsSgn": hs_code, "imexTpcd": imex})
        _, fetch = self._call(SOURCE_CUSTOMS, url, parse=self._parse_customs,
                              retry_on_unregistered=retry_on_unregistered)
        fetch.request_echo = {"hs_code": hs_code, "direction": direction}
        return fetch

    @staticmethod
    def _parse_customs(body: str):
        header, items, total = parse_customs_xml(body)
        return header, items, total, None

    # --- 2) 식약처 수입식품 허가정보 (15058273) ----------------------------
    def mfds_import_permit(self, *, product_name: Optional[str] = None,
                           importer: Optional[str] = None, page: int = 1,
                           rows: int = 5, retry_on_unregistered: bool = True) -> LiveFetch:
        if not self.has_customs:
            raise LiveApiError(SOURCE_MFDS_PERMIT, "서비스키 없음(DATA_GO_KR_SERVICE_KEY)")
        params = {"serviceKey": self._service_key, "pageNo": page, "numOfRows": rows, "type": "json"}
        # 15058273의 요청변수는 소문자다(swagger parameters 기준): goods_kor_name, bsn_ofc_name …
        if product_name:
            params["goods_kor_name"] = product_name
        if importer:
            params["bsn_ofc_name"] = importer
        url = self._url(MFDS_PERMIT_URL, params)
        _, fetch = self._call(SOURCE_MFDS_PERMIT, url, parse=self._parse_json,
                              retry_on_unregistered=retry_on_unregistered)
        fetch.request_echo = {"product_name": product_name or "", "importer": importer or "",
                              "page": page, "rows": rows}
        return fetch

    def mfds_improper(self, *, product_name: Optional[str] = None,
                      receipt_no: Optional[str] = None, category: Optional[str] = None,
                      page: int = 1, rows: int = 5,
                      retry_on_unregistered: bool = True) -> LiveFetch:
        """수입식품 검사부적합 검색(15058273 오퍼레이션 2)."""
        if not self.has_customs:
            raise LiveApiError(SOURCE_MFDS_PERMIT, "서비스키 없음(DATA_GO_KR_SERVICE_KEY)")
        params = {"serviceKey": self._service_key, "pageNo": page, "numOfRows": rows, "type": "json"}
        if product_name:
            params["goods_kor_name"] = product_name
        if receipt_no:
            params["receipt_no"] = receipt_no
        if category:
            params["notice_goods_name"] = category
        url = self._url(MFDS_IMPROPER_URL, params)
        _, fetch = self._call(SOURCE_MFDS_PERMIT, url, parse=self._parse_json,
                              retry_on_unregistered=retry_on_unregistered)
        fetch.request_echo = {"product_name": product_name or "", "receipt_no": receipt_no or "",
                              "category": category or "", "page": page, "rows": rows}
        return fetch

    # --- 3) 식약처 수입식품 제품DB (15073949) ------------------------------
    def mfds_product_db(self, *, product_name: Optional[str] = None,
                        item_name: Optional[str] = None, country: Optional[str] = None,
                        category: Optional[str] = None, page: int = 1, rows: int = 5,
                        retry_on_unregistered: bool = True) -> LiveFetch:
        if not self.has_customs:
            raise LiveApiError(SOURCE_MFDS_PRODUCT, "서비스키 없음(DATA_GO_KR_SERVICE_KEY)")
        params = {"serviceKey": self._service_key, "pageNo": page, "numOfRows": rows, "type": "json"}
        # 15073949의 요청변수는 대문자다(요청변수 표 기준): PRDT_NM, PRDLST_NM, MNFT_NATN_NM …
        if product_name:
            params["PRDT_NM"] = product_name
        if item_name:
            params["PRDLST_NM"] = item_name
        if country:
            params["MNFT_NATN_NM"] = country
        if category:
            params["DCLR_PRDT_DIVS_NM"] = category
        url = self._url(MFDS_PRODUCT_URL, params)
        _, fetch = self._call(SOURCE_MFDS_PRODUCT, url, parse=self._parse_json,
                              retry_on_unregistered=retry_on_unregistered)
        fetch.request_echo = {"product_name": product_name or "", "item_name": item_name or "",
                              "country": country or "", "category": category or ""}
        return fetch

    @staticmethod
    def _parse_json(body: str):
        payload = json.loads(body)
        header, items, total = parse_mfds_json(payload)
        return header, items, total, payload

    # --- 3-1) 식약처 행정처분결과 (15124560 / 15124559) --------------------
    def mfds_disposition(self, dataset: str = "manufacturing", *, license_no: Optional[str] = None,
                         confirmed_on: Optional[str] = None, updated_after: Optional[str] = None,
                         page: int = 1, rows: int = 20,
                         retry_on_unregistered: bool = True) -> LiveFetch:
        """행정처분결과를 조회한다. 데이터셋별로 승인 상태가 달라 코드 30이 날 수 있다.

        승인 전파 전에는 `LiveApiError(code="30")`이 나고, 호출부는 이를
        `approval_pending` 상태로 내보낸 뒤 내장 패턴 사전으로 폴백한다.
        """
        key = str(dataset or "").strip().lower()
        if key not in MFDS_DISPOSITION_ENDPOINTS:
            raise LiveApiError("mfds_disposition", f"알 수 없는 데이터셋: {dataset}")
        source_id = MFDS_DISPOSITION_SOURCES[key]
        if not self.has_mfds:
            raise LiveApiError(source_id, "서비스키 없음(DATA_GO_KR_SERVICE_KEY)")
        params: Dict[str, Any] = {"serviceKey": self._service_key, "pageNo": page,
                                  "numOfRows": max(1, min(int(rows), 100)), "type": "json"}
        if license_no:
            params["LCNS_NO"] = str(license_no).strip()
        if confirmed_on:
            params["DSPS_DCSNDT"] = "".join(ch for ch in str(confirmed_on) if ch.isdigit())[:8]
        if updated_after:
            params["LAST_UPDT_DTM"] = str(updated_after).strip()
        url = self._url(MFDS_DISPOSITION_ENDPOINTS[key], params)
        _, fetch = self._call(source_id, url, parse=self._parse_disposition,
                              retry_on_unregistered=retry_on_unregistered)
        # 인허가번호는 요청 메타에도 남기지 않는다(개인ㆍ사업자 식별정보).
        fetch.request_echo = {"dataset": key, "page": page, "rows": rows}
        return fetch

    @staticmethod
    def _parse_disposition(body: str):
        payload = json.loads(body)
        header, items, total = parse_mfds_json(payload)
        return header, items, total, None

    # --- 4) 법제처 국가법령정보 공동활용 ----------------------------------
    def law_search(self, query: str, *, target: str = "law", display: int = 5,
                   page: int = 1) -> LiveFetch:
        if not self.has_law:
            raise LiveApiError(SOURCE_LAW, "OC 값 없음(LAW_GO_KR_OC)")
        url = self._url(LAW_SEARCH_URL, {"OC": self._law_oc, "target": target,
                                         "type": "JSON", "query": query,
                                         "display": display, "page": page})
        _, fetch = self._call(SOURCE_LAW, url, parse=self._parse_law, retry_on_unregistered=False)
        fetch.request_echo = {"query": query, "target": target}
        return fetch

    @staticmethod
    def _parse_law(body: str):
        payload = json.loads(body)
        rows, total = parse_law_json(payload)
        header = {"resultCode": "00", "resultMsg": "NORMAL SERVICE."} if rows else {}
        if not rows and isinstance(payload, dict):
            message = payload.get("message") or payload.get("resultMsg") or ""
            if message:
                raise ValueError(str(message)[:200])
        return header, rows, total, payload

    def law_articles(self, mst: str, *, article: Optional[str] = None) -> LiveFetch:
        """법령 본문(조문) 조회. article 예: '226' → 제226조만 남긴다."""
        if not self.has_law:
            raise LiveApiError(SOURCE_LAW, "OC 값 없음(LAW_GO_KR_OC)")
        url = self._url(LAW_SERVICE_URL, {"OC": self._law_oc, "target": "law", "MST": mst,
                                          "type": "JSON"})
        _, fetch = self._call(SOURCE_LAW, url, parse=self._parse_law_body, retry_on_unregistered=False)
        if article:
            wanted = article.lstrip("제").replace("조", "").strip()
            fetch.items = [u for u in fetch.items
                           if _clean(u.get("조문여부")) == "조문"
                           and _clean(u.get("조문번호")).lstrip("0") == wanted.lstrip("0")]
        fetch.request_echo = {"mst": mst, "article": article or ""}
        return fetch

    @staticmethod
    def _parse_law_body(body: str):
        payload = json.loads(body)
        law = payload.get("법령") or {}
        units = _as_list(((law.get("조문") or {}) if isinstance(law, dict) else {}).get("조문단위"))
        items = [u for u in units if isinstance(u, dict)]
        total = len(items)
        return {"resultCode": "00", "resultMsg": "NORMAL SERVICE."}, items, total, payload

    # --- 5) 국립전파연구원 적합성평가 (3034183, 키 불필요) -------------------
    def rra_certificate(self, cert_no: str) -> LiveFetch:
        """인증·등록번호로 적합성평가 이력을 조회한다.

        키가 필요 없는 공개 엔드포인트라 별도 활용심의 없이 호출한다.
        결과코드 0001(조회 결과 없음)은 오류가 아니라 '해당 번호 기록 없음'이며,
        0098(파라미터 누락)은 빈 번호로 호출했다는 뜻이다. 둘 다 예외로 올리지 않고
        상태로 돌려줘 호출부가 정직하게 표시하게 한다.
        """
        if not self.has_rra:
            raise LiveApiError(SOURCE_RRA, "적합성평가 조회 비활성")
        number = normalize_cert_no(cert_no)
        url = self._url(RRA_INFO_URL, {"mtlCefNo": number})
        started = time.monotonic()
        try:
            status, body, _ = self._transport(url, self.timeout)
        except LiveApiError as exc:
            self._log(SOURCE_RRA, url, 0, None, 1, "network_error")
            raise LiveApiError(SOURCE_RRA, exc.message, retryable=True) from exc
        if status >= 400:
            self._log(SOURCE_RRA, url, status, None, 1, "http_error")
            raise LiveApiError(SOURCE_RRA, redact(f"HTTP {status}: {body[:200]}"), http_status=status)
        try:
            header, item, raw = parse_rra_xml(body)
        except ET.ParseError as exc:
            self._log(SOURCE_RRA, url, status, None, 1, "parse_error")
            raise LiveApiError(SOURCE_RRA, redact(f"응답 파싱 실패: {exc}"), http_status=status) from exc
        code = header["resultCode"]
        state = {"0000": "live", "0001": "not_found", "0098": "invalid_request"}.get(code, "error")
        self._log(SOURCE_RRA, url, status, code, 1, state)
        fetch = LiveFetch(
            source_id=SOURCE_RRA,
            ok=state == "live",
            state=state,
            http_status=status,
            result_code=code or None,
            result_msg=header["resultMsg"] or RRA_RESULT_LABEL.get(code, ""),
            items=[item] if item else [],
            raw=raw,
            fetched_at=datetime.now(KST).isoformat(timespec="seconds"),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            attempts=1,
            request_echo={"cert_no": number},
        )
        return fetch

    def rra_status(self, cert_no: str) -> Optional[bool]:
        """적합성평가 여부(Y/N)만 필요할 때 쓰는 경량 조회. 실패하면 None."""
        number = normalize_cert_no(cert_no)
        if not number:
            return None
        url = self._url(RRA_STATUS_URL, {"mtlCefNo": number})
        status, body, _ = self._transport(url, self.timeout)
        if status >= 400:
            return None
        header, _item, raw = parse_rra_xml(body)
        if header["resultCode"] != "0000":
            return None
        flag = str(raw.get("authYn", "")).strip().upper()
        return flag == "Y" if flag else None
