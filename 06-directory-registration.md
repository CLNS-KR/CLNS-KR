# 06 · 검색엔진·MCP 디렉터리 등록 — 실제 확인 결과와 남은 절차

작성: 2026-11-18 · 대상: `https://clns-kr.onrender.com` (저장소 `https://github.com/CLNS-KR/CLNS-KR`)

이 문서는 2026-11-18 13:30~14:00 KST에 **브라우저로 각 사이트의 실제 제출 화면을 직접 열어 확인한 결과**와,
이 저장소에 미리 넣어 둔 준비물(코드·워크플로·환경변수 자리)을 정리한다.

원칙: **완전 익명**. 실명·개인 이메일·전화번호는 어디에도 넣지 않는다. 개인 계정(Google·네이버·GitHub personal)으로
CLNS 디렉터리에 로그인하지 않는다. `CLNS-KR` 조직 신원만 쓴다.

---

## 0. 한눈에 보기

| 채널 | 지금 상태 (실제 화면 확인) | 무료? | 이 저장소가 준비한 것 | 남은 일 |
|---|---|---|---|---|
| 공식 MCP Registry (`registry.modelcontextprotocol.io`) | 게시 = `server.json` + GitHub 인증. 원격(streamable-http) 서버는 패키지 심사 없음 | 무료 | `server.json` + `.github/workflows/publish-mcp-registry.yml` (OIDC) | 저장소 push → 태그 push(또는 Actions 수동 실행) |
| mcp.so | 무료 제출 폼 사라짐. `/submit` 4개 탭 모두 **$39 결제 버튼만** 존재 | 유료($39) 또는 이슈 댓글(무료) | 댓글 초안(§3) | GitHub 계정으로 `chatmcp/mcpso#1` 댓글 |
| Smithery (`smithery.ai`) | **서비스 종료**. MCP Proxy·계정·CLI가 2026-10-31 종료, 사이트는 Arcade 소속 안내 | – | – | 없음(불가) |
| Glama (`glama.ai/mcp/servers`) | `Add Server` → **Sign Up 모달**(Google/GitHub/Discord OAuth 또는 이름·이메일·reCAPTCHA) | 무료 | – | Glama 계정 1개 필요 |
| Google Search Console | 로그인 필수(Google 계정) → URL 접두어 속성 + 소유확인 | 무료 | 메타태그·HTML 파일 라우트 지원(§5) | Google 계정으로 소유확인 1회 |
| 네이버 서치어드바이저 | 로그인 필수(네이버 계정) → 사이트 등록 + 소유확인 | 무료 | 위와 동일 + `robots.txt`에 `Yeti` 허용 이미 있음 | 네이버 계정으로 소유확인 1회 |

> **결론**: 4개 MCP 디렉터리 중 **로그인 없이 바로 제출 가능한 곳은 현재 0곳**이다.
> 대신 "인증 한 번이면 끝나는" 형태로 전부 준비해 두었다(§2·§5).

---

## 1. 공식 MCP Registry — 가장 먼저 할 일

### 확인한 규칙 (2026-11-18 기준 공식 문서)

- 원격 전용 서버는 `packages` 없이 `remotes` 만 쓰면 되고, **패키지 소유검증(npm `mcpName` 등)이 적용되지 않는다.**
  (`modelcontextprotocol.io/registry/remote-servers`)
- 이름 규칙: GitHub 인증이면 `io.github.<org>/<server>` — 우리는 `io.github.CLNS-KR/clns`.
- **org 네임스페이스는 조직 Owner 만** 게시할 수 있고,
  `mcp-publisher login github`(대화형 device flow)로는 **org 게시가 불가능**하다
  (GitHub App 토큰이 조직 멤버십을 못 읽는 알려진 제약, registry #1468).
  → 남은 두 경로: ① **GitHub Actions OIDC**(권장) ② `read:org` 권한 PAT.
- `description` 은 **100자 제한**. (우리 값 87자로 검증 통과)

### 이 저장소에 넣은 것

1. `server.json` — 공식 JSON Schema(`2025-12-11`)로 **검증 통과**(`jsonschema` 4.26):

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.CLNS-KR/clns",
  "title": "CLNS — Korea Import Compliance",
  "description": "Korea import pre-check: clearance requirements, MFDS import history, recalls, statutes.",
  "version": "0.1.3",
  "websiteUrl": "https://clns-kr.onrender.com/",
  "repository": { "url": "https://github.com/CLNS-KR/CLNS-KR", "source": "github" },
  "remotes": [{ "type": "streamable-http", "url": "https://clns-kr.onrender.com/mcp" }]
}
```

2. `.github/workflows/publish-mcp-registry.yml` — 태그 push(`v*`) 또는 수동 실행 시
   테스트 → 원격 엔드포인트 생존 확인(`initialize`) → cosign 으로 `mcp-publisher` 검증 →
   `login github-oidc` → `publish`. 개인 PAT·개인 계정을 쓰지 않는다.

### 절차 (사용자)

1. 이 변경을 `main` 에 push 한다(평소 배포와 같다. Render 가 자동 재배포).
2. `server.json` 의 `version` 과 같은 태그를 만든다. 예: `git tag v0.1.3 && git push origin v0.1.3`
   (또는 GitHub → Actions → `publish-mcp-registry` → **Run workflow**).
3. Actions 로그에서 `Successfully published` 확인.
4. 확인: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.CLNS-KR/clns"`
   또는 <https://registry.modelcontextprotocol.io/?q=CLNS>

> 주의: **현재 라이브 서버는 `serverInfo.version = 0.1.2`** 인데 로컬 코드는 `0.1.3` 이다.
> 0.1.3 배포가 끝난 뒤 태그를 찍거나, 배포 전에 올린다면 `server.json` 의 version 을 `0.1.2` 로 맞춘다.

### (대안) PAT 로 직접 게시

- GitHub **조직 CLNS-KR 의 Owner** 계정으로, `read:org` 스코프의 classic PAT(또는 Members: Read 권한의 fine-grained PAT) 발급.
- `mcp-publisher login github --token=<PAT>` → `mcp-publisher publish`.
- PAT 는 저장소·CI 어디에도 남기지 않는다(1회용으로 쓰고 폐기).

---

## 2. mcp.so — 무료 경로는 GitHub 이슈 댓글뿐

- `/submit` 은 MCP Server / Remote Server / MCP Client / AI Product 4개 탭 모두 **Paid submission $39** 카드 하나만 있다.
  Remote Server 탭에 `https://clns-kr.onrender.com/mcp` + 이름을 채워도 버튼은 "Pay and submit automatically" 뿐이고,
  페이지 어디에도 무료·검토 대기 옵션이 없다(본문에서 `free` 문구 0건).
- 무료 등재는 유지 중인 intake 이슈 **<https://github.com/chatmcp/mcpso/issues/1>** 에 댓글을 다는 방식이다
  (2026-11-18 확인: 상태 open, 최근 갱신 2026-11-18).
- **$39 결제는 하지 않았다**(사용자 승인 없는 지출).

### 붙여넣을 댓글 초안 (익명)

```
CLNS — Korea Import Compliance (MCP server, remote / Streamable HTTP)

한국 수입 규제 사전 점검 MCP 서버. 품목명 + HS 10자리로 세관장확인 요건(관세청),
식약처 수입 이력, 국내 리콜, 근거 법령을 3단계로 판정하고 근거 조항·면책을 함께 반환합니다.
인증 없음 · 무료 · 툴 8종.

Remote endpoint: https://clns-kr.onrender.com/mcp
Server card: https://clns-kr.onrender.com/.well-known/mcp/server-card.json
Repo: https://github.com/CLNS-KR/CLNS-KR
Website: https://clns-kr.onrender.com/
```

---

## 3. Smithery — 신규 등록 불가 (서비스 종료)

- `smithery.ai` 첫 화면: "**Smithery · MCP servers, now part of Arcade**",
  "The Smithery MCP Proxy and managed identity shut down on October 31, 2026."
- `/new`, `/docs`, `/docs/build/publish` → 모두 404 또는 같은 종료 안내로 리다이렉트.
- 남은 것은 Arcade 측이 큐레이션한 검증 서버 목록뿐 → **셀프 등록 경로 없음.**
- 대안: 이 레지스트리를 자동 수집하는 하위 디렉터리(Glama·PulseMCP 등)가 대신 노출한다.

## 4. Glama — 계정 1개만 있으면 무료

- `glama.ai/mcp/servers` → **Add Server** → Sign Up 모달: Google / GitHub / Discord OAuth, 또는 이름+이메일+reCAPTCHA.
- 익명 제출 불가. 단, Glama 는 **GitHub 공개 저장소를 자동 수집**한다.
  (2026-11-18 13:25 기준 "clns-kr" 검색 결과 0건 → 아직 수집 전. 저장소가 공개면 시간이 지나면 자동 등재될 수 있다.)
- 계정을 만들 경우 **표시 이름은 `CLNS`**, 이메일은 개인 주소가 아닌 CLNS 전용 주소를 쓴다.

---

## 5. 검색엔진 — 코드는 준비 완료, 계정 인증만 남음

### 우리 서버가 이미 갖춘 것

- `robots.txt`: 전체 허용 + `Yeti`(네이버)·`Googlebot` 명시 허용, `/v1/` 만 차단
- `sitemap.xml`: `/`, `/p/`, 전 품목 URL 동적 생성
- `llms.txt`, `canonical`, OpenGraph, JSON-LD
- **(신규)** 소유확인 지원 — `src/import_compliance/site_verification.py`
  - `GOOGLE_SITE_VERIFICATION` → 모든 HTML `<head>` 에 `<meta name="google-site-verification" content="…">`
  - `NAVER_SITE_VERIFICATION` → `<meta name="naver-site-verification" content="…">`
  - `SITE_VERIFICATION_FILES` → `{"google1a2b.html":"google-site-verification: google1a2b.html"}` 처럼
    루트 경로에 HTML 확인 파일 서빙(파일명 화이트리스트·경로 이탈 차단)
  - 회귀 테스트 11개: `python3 src/tests/test_site_verification.py`

### 구글 서치콘솔 (Google 계정 1회)

1. <https://search.google.com/search-console> → **속성 추가** → **URL 접두어**에 `https://clns-kr.onrender.com/`
   (도메인 속성은 DNS 제어가 필요한데 onrender.com 서브도메인은 불가)
2. 소유확인 방법에서 **HTML 태그** 선택 → `content="..."` 안의 토큰만 복사
3. Render 대시보드 → 서비스 `clns-kr` → **Environment** → `GOOGLE_SITE_VERIFICATION` = 토큰 → 저장(자동 재배포)
4. 서치콘솔에서 **확인** 클릭
5. **Sitemaps** → `https://clns-kr.onrender.com/sitemap.xml` 제출
6. (선택) URL 검사 → `https://clns-kr.onrender.com/` 색인 생성 요청

> HTML 파일 방식이 편하면: 서치콘솔이 주는 `google….html` 파일 이름과 내용을
> `SITE_VERIFICATION_FILES` 에 JSON 으로 넣으면 같은 경로로 서빙된다.

### 네이버 서치어드바이저 (네이버 계정 1회)

1. <https://searchadvisor.naver.com> → 로그인 → **웹마스터 도구** → 사이트 등록에 `https://clns-kr.onrender.com/`
2. 소유확인 방법 선택
   - **HTML 태그**: 토큰을 `NAVER_SITE_VERIFICATION` 에 넣는다
   - **HTML 파일 업로드**: 받은 `naver….html` 의 파일명·내용을 `SITE_VERIFICATION_FILES` 에 넣는다
3. Render Environment 저장 → 재배포 후 **소유확인** 클릭(보안문자 입력)
4. **요청 → 사이트맵 제출**: `https://clns-kr.onrender.com/sitemap.xml`
5. **요청 → 웹페이지 수집**: `https://clns-kr.onrender.com/`, `https://clns-kr.onrender.com/p/`
6. (권장) **검증 → robots.txt** 확인

> 확인 파일·메타태그는 등록 후에도 **지우지 않는다**(지우면 소유확인이 풀린다).
> 환경변수는 값이 없으면 아무 것도 출력하지 않으므로, 넣기 전후로 기존 응답은 완전히 동일하다.

---

## 6. 체크리스트

- [ ] `server.json` · 워크플로를 `main` 에 push (Render 자동 재배포)
- [ ] `git tag v0.1.3 && git push origin v0.1.3` → Actions `publish-mcp-registry` 성공 확인
- [ ] `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.CLNS-KR/clns"` 로 게시 확인
- [ ] Google 서치콘솔: URL 접두어 속성 → `GOOGLE_SITE_VERIFICATION` → 확인 → sitemap 제출
- [ ] 네이버 서치어드바이저: 사이트 등록 → `NAVER_SITE_VERIFICATION`(또는 파일) → 확인 → 사이트맵·수집 요청
- [ ] mcp.so: (무료) `chatmcp/mcpso#1` 댓글 / (유료 $39 는 사용자 결정)
- [ ] Glama: CLNS 계정으로 Add Server (선택)
- [ ] Smithery: 조치 없음(종료)
