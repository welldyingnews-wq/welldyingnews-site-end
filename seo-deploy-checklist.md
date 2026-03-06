# 웰다잉뉴스 SEO 변경사항 배포 점검 체크리스트

## 1. 301 리다이렉트

- [ ] `/v2/xxx` → `/xxx` 한 번에 도달하는지 (체인 없이)
- [ ] `/data/` → `/data` 한 번에 도달하는지
- [ ] `/v2/data/` → `/data` 이중 체인 안 생기는지
- [ ] 리다이렉트 응답 헤더에 `Location`이 최종 canonical URL인지 확인
- [ ] 테스트 방법: `curl -I -L [URL]` 으로 홉 수 확인

## 2. canonical / og:url 정합성

- [ ] `<link rel="canonical">` 과 `<meta property="og:url">` 이 동일한 `canonical_url` 변수 사용
- [ ] 트래킹 파라미터(`utm_*`, `fbclid` 등) 붙인 URL 접속 시 canonical에 파라미터 없는 URL 출력되는지
- [ ] canonical URL이 절대 경로(https://welldyingnews.com/...)인지

## 3. meta description

- [ ] 홈: 기본 description 출력 확인
- [ ] 기사 상세: `summary_text` 기반 고유 description 출력
- [ ] 기사 목록: 섹션별 고유 description 출력
- [ ] 데이터 페이지: 고유 description 출력
- [ ] 한글 기준 길이 제한 적용 확인 (103자 이내, `len()` 기준)
- [ ] description 없는 기사에서 fallback 처리되는지

## 4. noindex 처리

- [ ] 검색결과(`sc_word` 파라미터 있을 때) → `<meta name="robots" content="noindex">`
- [ ] 기사목록 2페이지 이후(`page=2~`) → `<meta name="robots" content="noindex, follow">` 적용 확인
- [ ] noindex 페이지가 sitemap에 포함되지 않는지

## 5. sitemap

- [ ] `/data` 페이지 URL 추가됐는지
- [ ] 서브섹션 목록 URL 추가됐는지
- [ ] 모든 `<loc>`가 절대 URL인지
- [ ] `<lastmod>` 날짜 정상 출력
- [ ] 삭제/리다이렉트된 URL(`/v2/...`) 이 sitemap에서 제거됐는지
- [ ] sitemap 접속 확인: `curl https://welldyingnews.com/sitemap.xml`

## 6. robots.txt

- [x] 트래킹 파라미터 URL 차단 규칙 추가 완료
  - `Disallow: /*?*utm_`, `Disallow: /*?*fbclid=`, `Disallow: /*?*gclid=`
- [ ] `/v2/` 경로 차단 여부 결정 (301이 있으니 선택사항)
- [ ] sitemap 경로 선언: `Sitemap: https://welldyingnews.com/sitemap.xml`

## 7. 네이버 뉴스 파트너십

- [ ] 네이버 뉴스 파트너 관리 페이지에서 RSS/제휴 URL 패턴 확인
- [ ] 기존 송고된 기사 URL이 301로 최종 URL에 도달하는지
- [ ] 네이버 서치어드바이저에서 사이트 URL 설정 확인
- [ ] 변경 후 네이버 크롤링 정상 여부 모니터링 (1~2주)

## 8. 인덱싱 확인 (배포 후)

- [ ] Google Search Console → URL 검사로 주요 페이지 크롤링 요청
- [ ] Google Search Console → 색인 > 페이지에서 `/v2/` URL 감소 추이 확인
- [ ] 네이버 서치어드바이저 → 웹페이지 수집 요청
- [ ] `site:welldyingnews.com/v2` 검색해서 잔존 색인 모니터링
- [ ] `site:welldyingnews.com inurl:utm` 검색해서 파라미터 URL 색인 확인

## 9. 보안 취약점 스캔 (Pentest-Tools Website Scanner)

로그인·글쓰기 기능이 있으므로 XSS·SQLi·CSRF 등 인증 후 취약점을 검사합니다.

**도구:** [Pentest-Tools Website Scanner](https://pentest-tools.com/website-vulnerability-scanning/website-scanner) (무료 Full scan 가능)

**사용법:**
1. 무료 계정 생성 후 Website Scanner 열기
2. 타겟 URL에 로그인 페이지 입력: `https://www.welldyingnews.com/member/login.html`
3. Authentication → Automatic → 로그인 URL, username, password 입력
4. Check Authentication 클릭 → 성공 시 스크린샷 확인
5. Full scan 시작 → 로그인 유지하며 게시판·글쓰기 영역까지 크롤링

**점검 항목 (75+ 항목 자동 검사):**
- [ ] XSS (JavaScript 인젝션) 취약점 없는지
- [ ] SQL Injection 취약점 없는지
- [ ] CSRF 토큰 누락 폼 없는지
- [ ] 세션 관리 취약점 (세션 고정, 만료 미설정 등) 없는지
- [ ] 민감정보 평문 노출 (비밀번호, 이메일 등) 없는지
- [ ] 디렉토리 리스팅/정보 노출 없는지

**관리자 CMS도 별도 스캔:**
- [ ] 타겟 URL: `https://www.welldyingnews.com/admin/login`
- [ ] 관리자 계정(`.env` 참고)으로 Authentication 설정 후 Full scan

**리포트:**
- [ ] 스캔 완료 후 리포트 다운로드 (스크린샷·재현 방법 포함)
- [ ] Critical/High 취약점 발견 시 즉시 수정

> 무료 계정은 Full scan 횟수 제한 있음. 테스트 계정으로 먼저 시도.

---

**점검일:** ____년 __월 __일
**점검자:** ________________
**비고:**


