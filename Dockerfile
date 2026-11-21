# CLNS
# PRODUCT COMPLIANCE INTELLIGENCE · KOREA
# Clearance, simplified.
# Korea Import Compliance MCP & API · 무료 티어 클라우드(Render/Koyeb/Fly 등) 배포용 이미지
# 표준 라이브러리만 쓰므로 pip install 단계가 없다(빌드 수십 초, 이미지 ~150MB).
FROM python:3.12-slim

LABEL org.opencontainers.image.title="CLNS" \
      org.opencontainers.image.description="PRODUCT COMPLIANCE INTELLIGENCE · KOREA · Korea Import Compliance MCP & API (웹 UI + JSON API)" \
      org.opencontainers.image.version="0.5.7"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8787 \
    IMPORT_COMPLIANCE_DB=/app/data/app.sqlite

WORKDIR /app

# 비루트 사용자. SQLite 파일에 써야 하므로 data 디렉터리 소유권을 함께 준다.
RUN adduser --disabled-password --gecos "" --uid 10001 app \
    && mkdir -p /app/data

COPY --chown=app:app src/ /app/src/
# 리콜 로컬 인덱스(881건, 2026-11-18 적재)를 이미지에 포함한다. 기동 시 작업 DB로 복사된다.
COPY --chown=app:app data/recalls.sqlite /app/data/recalls.sqlite
# 0원 영속화 시드 — 일일 스냅샷 JSON 과 익명 사용 통계. 기동 시 seed_persistence() 가 복원한다.
COPY --chown=app:app data/snapshots/ /app/data/snapshots/
COPY --chown=app:app data/usage/ /app/data/usage/
# 공유 미리보기 이미지(1200×630, og:image) — `GET /static/og.png` 로 서빙한다.
COPY --chown=app:app static/ /app/static/

RUN chown -R app:app /app/data
USER app

EXPOSE 8787

# curl 없는 슬림 이미지이므로 표준 라이브러리로 헬스체크한다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8787')+'/healthz', timeout=4)"

# API 키는 이미지에 절대 넣지 않는다. 런타임 환경변수(DATA_GO_KR_SERVICE_KEY, LAW_GO_KR_OC)로만 받는다.
CMD ["python", "-m", "import_compliance.server"]
