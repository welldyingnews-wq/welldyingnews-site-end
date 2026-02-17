# TODO.md

원본 사이트(welldyingnews.com) 대비 미구현/차이점 목록.

---

## 1. 기사 상세 페이지 (Article View)

### SNS 공유
- [x] ~~카카오톡, 카카오스토리, 밴드(Band), 텔레그램~~ — 원본도 미렌더링 (JS만 존재, kakaojavascriptkey 비어있음)
- [x] "다른 공유" 버튼 클릭 시 전체 공유 옵션 모달
- [x] 스크랩(북마크) 버튼
- [x] 공유 버튼 레이아웃 원본 일치 (email/다른공유/스크랩 우측 정렬)

### Sticky 스크롤 헤더
- [x] quick-tool 버튼 (글자크기 조절, 인쇄, URL복사) — info-group에 구현 완료
- [x] 프로그레스바 — 원본과 동일 패턴 (aht-bar, border-top #5e1985)

### 댓글
- [x] 로그인 회원 연동 (회원 로그인 시 작성자명 자동 표시, 비밀번호 불필요)
- [x] 댓글 정렬 옵션 (최신순/등록순)
- [x] BEST 댓글 표시 (추천 3개 이상, 상단 최대 3개)
- [x] 대댓글(답글) 기능 (parent_id 기반 nested reply)
- [x] 댓글 추천/비추천 투표 기능 (AJAX, IP/회원 중복 방지)
- [x] "더보기" 페이지네이션 (5개씩 더보기 버튼)
- [x] 댓글 수정 기능 (비밀번호/회원 확인 후 인라인 수정)
- [ ] 작성자 프로필 이미지 표시 누락
- [x] 작성자 IP 부분 숨김 표시 (123.456.***.***)

### 사이드바
- [x] 탭 플러그인 (커스텀 JS로 tabslet 동일 동작 구현)
- [x] 사이드바 배너 위치/순서 (sort_order 기반 정렬 구현)

---

## 2. 설문조사 (Poll)

- [x] 상태 배지 (진행중/완료 — poll-view-state.going)
- [x] 투표 기간 표시 (시작일 ~ 종료일 — poll-view-dated)
- [x] "결과보기" 버튼 (투표 전에도 result=1 파라미터로 미리보기)
- [x] 라디오 버튼 커스텀 스타일 (원본 CSS: hidden radio + label::before 원형 체크)
- [x] 결과 막대그래프 원본 스타일 (graph 오버레이 바 + inner/result-more 구조)
- [x] 1위 항목 하이라이트 (max_votes에 user-bg 클래스 적용)
- [x] 소수점 1자리 정밀도 (`'%.1f'|format(pct)`)

---

## 3. 게시판 (BBS)

### 목록 페이지
- [x] 검색 영역 레이아웃 (flex-end 우측 정렬 — 원본과 동일)
- [x] 테이블 접근성 속성 (`scope="col"`, `summary`, `caption`, `show-for-medium/large`)
- [x] 비밀글(secret post) 옵션 (is_secret + 비밀번호 확인 페이지)
- [x] 페이지네이션 스타일 (`pagin-group`, `pagination-start/end`, `current user-bg`)

### 상세/글쓰기
- [x] 답글(reply-to-post) 기능 (parent_post_id 기반, [Re] 표시)
- [x] 글 수정 모드 (비밀번호 확인 후 수정 폼)
- [x] 게시판 댓글 nested 답글 지원 (parent_id 기반)
- [x] 게시판 댓글 정렬/투표/BEST 댓글 + 수정 기능

---

## 4. 신청 페이지 (Event Forms)

- [x] 폼 레이아웃 2컬럼 그리드 (Foundation medium-3/medium-9 grid)
- [x] 기사제보 페이지 파일 첨부 필드 (event4 전용, 10MB 제한)
- [ ] 자동등록방지(CAPTCHA) 누락 (원본: Google reCAPTCHA)
- [x] 개인정보 동의 문구 원본 일치

---

## 5. 정보 페이지 (Info Pages)

- [x] 히어로 영역 높이/제목 크기 원본 일치 (250px, 45px, 반응형)
- [x] 찾아오시는길 지도 연동 (Daum roughmap 정상 동작)

---

## 6. 배너/팝업

- [x] 팝업 모바일 노출 (중앙 모달 스타일, 오늘 하루 보지 않기 지원)
- [x] 윙배너(wing banner) 구현 (position:fixed, wing_left/wing_right, 닫기 버튼)
- [x] 팝업 "오늘 하루 보지 않기" 쿠키 기능 (base.html에 구현 완료)

---

## 7. 모바일 뷰

- [x] 모바일 기사 상세의 댓글 UI (PC와 동일 템플릿 사용)
- [x] 모바일 게시판 댓글 UI (PC와 동일 템플릿 사용)
- [x] 모바일 설문조사 상세 스타일 (반응형 CSS 적용 완료)

---

## 8. 관리자 (Admin) — 원본 대비 차이점

### 회원목록
- [x] 관리등급 시스템 (admin/editor/reporter — settings_authority 페이지)
- [x] 회원 기타등급 관리 (EtcLevel 모델 + etc_level_list 페이지)
- [x] 회원등급(일반/시민기자/기자/데스크) Member 모델에 level 필드 추가
- [x] 회원 수정내역(로그) 모달 (MemberLog 모델 + API + 모달)
- [x] 탈퇴아이디 보기 기능 (비활성 회원 탭)
- [x] 휴면회원 목록 (is_dormant 탭)

### 댓글설정
- [x] 기본설정/기사댓글/게시판댓글 3개 탭으로 세분화 (설문조사댓글은 미사용)
- [x] BEST 댓글 설정 (기준수, 노출수)
- [x] 작성자 이름/IP/아이디 숨김 처리 설정
- [x] 관리자 표기 이름 변경 설정
- [ ] 프로필 이미지 업로드 설정 누락
- [ ] 비회원 CAPTCHA 설정 누락

### 기사설정
- [x] 섹션 설정 페이지에서 드래그앤드롭 순서 변경 기능 (Sortable.js)
- [x] 2차섹션 관리 (settings_sections 페이지 — 추가/수정/삭제)
- [x] 연재 관리 (settings_serial 페이지 — 추가/삭제)
- [x] 권한설정 (settings_authority 페이지)

### 승인관리
- [x] 미승인기사/예약기사 탭 분리 (전체/미승인/예약 3탭)
- [x] 기사 등급 토글 버튼 (일반/중요/헤드라인 AJAX)
- [x] 일괄 승인/반려 기능 (체크박스 + 모달)

### 통계
- [x] 기자별 통계 월별 필터 + 인쇄 기능
- [x] 기자별 통계 엑셀(CSV) 다운로드
- [x] 기사 랭킹 페이지 섹션/기간 필터 + 엑셀(CSV) 다운로드

### 기사 작성
- [x] 사진/영상/파일 업로드 Dropzone.js 드래그앤드롭 (클릭하면 본문 삽입)
- [x] 임시보관함(자동저장) 기능 (ArticleDraft 모델, 60초 자동저장, 이어쓰기)
- [ ] 포토DB 검색/즐겨찾기 기능 누락
- [x] 기자 선택 팝업 (모달 — AdminUser 목록에서 선택)
- [x] 본문 크기 토글 (데스크탑/모바일 미리보기 전환)

---

## 9. 기사 등록 화면 개선 (에디터 도구 원본 일치)

> 현재 CKEditor 5 Classic 기본 빌드 사용 중. 원본 사이트(NPC CMS)의 글쓰기 도구와 동일하게 맞춰야 함.

### CKEditor 빌드 전환
- [x] CKEditor 5 CDN Classic → importmap 기반 모듈 방식 전환 (v43.3.1, 플러그인 개별 import)

### 에디터 툴바 확장
- [x] 글자 크기 조절 (fontSize — 9pt~36pt 드롭다운)
- [x] 글자 색상 (fontColor — 컬러피커)
- [x] 글자 배경색 (fontBackgroundColor — 하이라이트)
- [x] 텍스트 정렬 (alignment — 좌/중/우/양쪽 정렬)
- [ ] 줄간격/문단 간격 조절 (lineHeight — CKEditor 5 미지원, 별도 플러그인 필요)
- [x] 수평선 삽입 (horizontalLine)
- [x] 특수문자 삽입 (specialCharacters)
- [x] 서식 제거 (removeFormat)
- [x] 찾기 및 바꾸기 (findAndReplace)
- [x] HTML 소스 편집 모드 (sourceEditing)
- [x] YouTube/동영상 임베드 (mediaEmbed)
- [x] 이미지 캡션/정렬/리사이즈 (imageResize, imageStyle — 25%/50%/75%/원본 + 좌/우/중앙)
- [ ] 전체화면 편집 모드 (fullscreen — CKEditor 5 미지원, 커스텀 구현 필요)

### 기사 작성 폼 필드 보강
- [x] 리드문(요약문) 입력 필드 (summary — 부제목 아래 별도 요약문 입력란)
- [x] 연재(SerialCode) 선택 드롭다운 (기사 옵션 사이드바에 추가, serial_code_id 필드)
- [x] 출처(source) 입력 필드 (기사 옵션 사이드바에 추가)
- [ ] SNS 자동발행 옵션 체크박스 (페이스북/트위터 — UI만 구현, 실제 발행은 미구현)

---

## 10. 이미지 Cloudinary 전환

> 이미지 파일(기사 본문/썸네일/배너/팝업/프로필)은 Cloudinary를 통해 업로드/서빙.

- [ ] Cloudinary SDK 연동 (cloudinary python SDK 설치, 환경변수 설정: CLOUD_NAME, API_KEY, API_SECRET)
- [ ] 기사 본문 이미지 업로드 → Cloudinary (admin upload_image 라우트 변경)
- [ ] 기사 대표 이미지(thumbnail) 업로드 → Cloudinary
- [ ] Dropzone 이미지 업로드 → Cloudinary (업로드 후 Cloudinary URL 반환)
- [ ] 배너/팝업 이미지 업로드 → Cloudinary
- [ ] 회원 프로필 이미지 업로드 → Cloudinary
- [ ] 댓글 작성자 프로필 이미지 → Cloudinary URL 참조
- [ ] 기존 로컬 이미지(`static/uploads/`) → Cloudinary 마이그레이션 스크립트 작성
- [ ] 모든 템플릿에서 로컬 이미지 경로를 Cloudinary URL로 교체

---

## 11. 첨부파일 Google Drive 전환

> 이미지가 아닌 첨부파일(문서, PDF, HWP 등)은 Google Drive를 통해 업로드/서빙.

- [ ] Google Drive API 연동 (google-api-python-client SDK 설치, 서비스 계정 키 설정)
- [ ] 공유 폴더 설정 (업로드 대상 폴더 ID 환경변수)
- [ ] 기사제보 첨부파일(.doc/.hwp/.pdf 등) 업로드 → Google Drive
- [ ] Dropzone 비이미지 파일 업로드 → Google Drive (업로드 후 공유 링크 반환)
- [ ] 첨부파일 다운로드 링크를 Google Drive 공유 URL로 변경
- [ ] 기존 로컬 첨부파일 → Google Drive 마이그레이션 스크립트 작성

---

## 완료된 항목

- [x] 메인(홈) 페이지 원본 복제
- [x] 기사 목록 페이지 원본 복제 (3가지 뷰 타입)
- [x] 기사 상세 페이지 원본 복제
- [x] 관련기사 추가 기능 (팝업 방식)
- [x] 관리자 CMS 전체 (55개 라우트, 36개 템플릿)
- [x] 원본 CSS/폰트/로고 다운로드
- [x] 댓글 기능 (기본 입력/표시)
- [x] 게시판 (공개) 목록/상세/글쓰기
- [x] 배너/광고 노출
- [x] 팝업 노출 (데스크탑)
- [x] 설문조사 (공개) 투표 + 결과
- [x] 신청 페이지 (구독/제보/저작권)
- [x] SNS 공유 (페이스북/트위터/URL복사/이메일)
- [x] 정보 페이지 (인사말, 약관 등)
- [x] 탭형 많이 본 뉴스
- [x] 사이드 네비게이션
- [x] sticky 스크롤 헤더
- [x] OG 메타태그
- [x] 회원가입 3단계 (유형선택 → 약관동의 → 정보입력)
- [x] 회원 로그인/로그아웃/마이페이지
- [x] 모바일 뷰 (UA 감지 + 전용 레이아웃)
- [x] 편집 레이아웃 (드래그앤드롭 블록 편집기)

