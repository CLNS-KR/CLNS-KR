-- 한국 수입·유통 컴플라이언스 엔진 캐시 DB (SQLite / Postgres 공통 논리 스키마)
-- Phase 1 구현은 SQLite(src/import_compliance/store.py)이며, 아래는 Postgres 이관용 DDL.

CREATE TABLE sources (
    source_id       TEXT PRIMARY KEY,
    name_ko         TEXT NOT NULL,
    provider        TEXT NOT NULL,
    license_scope   TEXT NOT NULL,          -- 예: '이용허락범위 제한 없음', '공공누리 제1유형'
    base_url        TEXT NOT NULL,
    update_cycle    TEXT NOT NULL,          -- realtime | daily | monthly | manual
    last_ok_at      TIMESTAMPTZ
);

CREATE TABLE api_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    query_key       TEXT NOT NULL,          -- 정규화된 조회키(HS10 | 품목명 | 법령ID:조문)
    payload_json    JSONB NOT NULL,         -- 원본 응답 보존(내부용, 외부 재전송 금지)
    status          TEXT NOT NULL DEFAULT 'ok',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_snapshots_lookup ON api_snapshots(source_id, query_key, fetched_at DESC);

CREATE TABLE derived_findings (
    id              BIGSERIAL PRIMARY KEY,
    query_hash      TEXT NOT NULL,
    trap_id         TEXT NOT NULL,
    verdict         TEXT NOT NULL CHECK (verdict IN ('check_likely','info_needed','low_risk')),
    confidence      NUMERIC(3,2) NOT NULL,
    evidence_json   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_findings_trap ON derived_findings(trap_id, created_at DESC);

CREATE TABLE assessments (
    id              BIGSERIAL PRIMARY KEY,
    assessment_id   TEXT UNIQUE NOT NULL,
    client_id       TEXT NOT NULL,
    tier            TEXT NOT NULL DEFAULT 'free',
    query_text      TEXT NOT NULL,
    overall_verdict TEXT NOT NULL,
    response_json   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_assessments_client ON assessments(client_id, created_at DESC);

CREATE TABLE quota_usage (
    client_id       TEXT NOT NULL,
    period          TEXT NOT NULL,          -- 'YYYY-MM'
    used            INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (client_id, period)
);

-- 국표원 리콜 파일데이터 적재분(15040696 건별 이력, 15054301 연도별 집계)
CREATE TABLE recall_items (
    id                   BIGSERIAL PRIMARY KEY,
    dataset_id           TEXT NOT NULL,          -- '15040696'
    cert_no              TEXT,
    model                TEXT,
    product_name         TEXT,
    brand                TEXT,
    business_type        TEXT,
    category             TEXT,                   -- 법정제품분류
    recall_type          TEXT,
    recall_business      TEXT,
    manufacture_country  TEXT,
    manufacturer         TEXT,
    manufacturer_country TEXT,
    recall_method        TEXT,
    hazard_type          TEXT,
    safety_inspection    TEXT,
    registered_on        DATE,
    source_url           TEXT,
    loaded_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_recall_items_model ON recall_items(model);
CREATE INDEX idx_recall_items_product ON recall_items(product_name);
CREATE INDEX idx_recall_items_brand ON recall_items(brand);

CREATE TABLE recall_stats (
    dataset_id   TEXT NOT NULL,                  -- '15054301'
    year         TEXT NOT NULL,
    category     TEXT NOT NULL,                  -- 생활용품·전기용품·어린이제품
    disposition  TEXT NOT NULL,                  -- 리콜명령·리콜권고·자발적리콜
    count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, year, category, disposition)
);

CREATE TABLE webhook_subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    client_id       TEXT NOT NULL,
    event_type      TEXT NOT NULL,          -- law_amended | notice_amended | recall_added
    target_url      TEXT NOT NULL,
    secret_hash     TEXT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 운영 원칙
-- 1) api_snapshots는 내부 근거 보존용이며 API 응답으로 그대로 내보내지 않는다.
-- 2) /v1 응답은 derived_findings + assessments의 가공 결과만 사용한다.
-- 3) 스냅샷 신선도(72시간) 초과 시 판정을 info_needed로 강등한다.

-- 익명 일별 사용 카운터(GET /v1/stats). 개인 식별자는 저장하지 않는다.
CREATE TABLE usage_daily (
    day         TEXT NOT NULL,              -- YYYY-MM-DD (Asia/Seoul)
    kind        TEXT NOT NULL,              -- path | tool | verdict | flag
    key         TEXT NOT NULL,              -- 서버가 아는 경로·툴명·verdict.code·flag
    count       INTEGER NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, kind, key)
);
