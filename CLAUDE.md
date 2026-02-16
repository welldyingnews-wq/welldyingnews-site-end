# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**welldying-news** — 웰다잉뉴스(welldyingnews.com) 관리자 CMS + 서비스 사이트를 Flask + SQLite로 구현한 프로젝트.

## Development Environment

- **Python:** 3.12.4
- **Virtual environment:** `.venv/`

```bash
# 가상환경 활성화
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# DB 초기화 (섹션/관리자 시드 데이터 포함)
python init_db.py

# 서버 실행 (포트 5001)
python run.py
```

## Key URLs

- 서비스 사이트: http://localhost:5001/
- 관리자 CMS: http://localhost:5001/admin/login
- 관리자 계정: `welldyingnews` / `rkatkgo1`

## Architecture

Flask Blueprint 구조로 관리자(admin)와 서비스(public)가 분리됨.

```
app/
├── __init__.py          # Flask 앱 팩토리 (create_app)
├── models.py            # SQLAlchemy 모델 (AdminUser, Section, SubSection, Article)
├── admin/               # 관리자 CMS Blueprint (/admin 프리픽스)
│   ├── routes.py        # 로그인, 대시보드, 기사 CRUD, 이미지 업로드 API
│   └── templates/admin/ # 관리자 Jinja2 템플릿
├── public/              # 서비스 사이트 Blueprint (/ 루트)
│   ├── routes.py        # 메인, 기사목록, 기사상세
│   └── templates/public/# 서비스 Jinja2 템플릿
└── static/
    ├── css/             # admin.css, public.css
    └── uploads/         # 이미지 업로드 디렉토리
```

## Data Model

- **Section**: 1차 섹션 (뉴스, 오피니언, 웰다잉TV 등), code 필드로 식별 (S1N1, S1N2...)
- **SubSection**: 2차 섹션 (정책ㆍ사회, 호스피스 등), section_id FK, code 필드 (S2N1, S2N2...)
- **Article**: 기사. level(B/I/T=일반/중요/헤드라인), recognition(C/E/R=미승인/승인/반려), is_deleted(소프트 삭제)
- 서비스 사이트에는 `recognition='E'` (승인) + `is_deleted=False` + 엠바고 해제된 기사만 노출

## Tech Stack

- Flask 3.1, Flask-SQLAlchemy, Flask-Login
- SQLite (welldying.db)
- CKEditor 5 CDN (기사 본문 에디터)
- Bootstrap 5 (관리자 UI)
- Zurb Foundation 6 + ND Soft CMS 스킨 (서비스 사이트 — 원본과 동일한 CSS)
- jQuery 3.7.1 + Slick Carousel 1.8.1 (서비스 사이트)
- 브랜드 색상: `#5e1985`

## TODO

미구현 기능 목록은 `TODO.md` 참고. 원본 사이트 대비 공개 사이트 미구현 항목(댓글, 게시판, 배너/팝업 노출, 설문, 신청 페이지 등)이 정리되어 있음.

## 원본 사이트 복제 작업 (서비스 사이트)

### 원본 사이트 접근

- **서비스 URL**: https://www.welldyingnews.com/ (또는 https://cms.welldyingnews.com/)
- **관리자 URL**: https://cms.welldyingnews.com/user/login.html
- **CDN URL**: https://cdn.welldyingnews.com/ (이미지, CSS 등)
- 원본 사이트는 ND Soft CMS 기반, Foundation 6 프레임워크 사용

### 원본 CSS/폰트 다운로드 현황

`app/static/css/orig/`에 원본 사이트의 CSS 12개 파일 다운로드 완료:
- foundation.min.css, custom.foundation.min.css, style.min.css, media.min.css
- plugin.style.min.css, webfonts.min.css, autobox.style.min.css, menubar.css
- templates.style.min.css, design.style.css, font.style.css, slick.css

`app/static/fonts/`에 fontello 아이콘 폰트 다운로드 완료:
- fontello.woff2, fontello.woff
- webfonts.min.css 내부 경로를 `/static/fonts/`로 수정됨

`app/static/images/`에 로고 이미지 다운로드 완료:
- logo.png (상단), footer-logo.png (하단), print-logo.png (인쇄용)

### 서비스 사이트 템플릿 구현 현황

| 페이지 | 파일 | 원본 복제 완료 |
|--------|------|:---:|
| 기본 레이아웃 | `public/base.html` | O |
| 메인 (홈) | `public/index.html` | O |
| 기사 목록 | `public/article_list.html` | O |
| 기사 상세 | `public/article_view.html` | O |

### 원본 사이트의 핵심 CSS 클래스/구조

- **레이아웃**: `#user-wrap.min-width-1240 > #user-wrapper > #user-header + #user-container + #user-footer.type-31`
- **헤더**: `#header-wrapper.vertical.full.left > #nav-header + #user-nav`
- **메뉴**: `#user-menu.user-menu > li.secline` (서브메뉴 hover 드롭다운)
- **메인 스킨**: skin-3(히어로), skin-11(오피니언), skin-12(그리드), skin-15(랭킹)
- **기사목록**: `#user-section > .grid-wrap (table-layout) > .grid.body + .grid.side`
- **기사상세**: `#article-view > .wrapper > .article-view-header + .article-view-content (table-layout)`
- **공통 사이드바**: `aside.grid.side > .sticky` (오피니언 + 많이 본 뉴스)
- **페이지네이션**: `ul.pagination > li.pagination-start/current.user-bg/pagination-end`
- **footer**: `#user-footer.type-31 > .user-nav + .user-logo + .user-address`
- 글자 크기: `.size-15`, `.size-22` 등 유틸리티 클래스 (autobox.style.min.css)
- 줄 수 제한: `.line-3x2`, `.line-6x2` 등 (autobox.style.min.css)

### 원본 사이트 구조 분석 방법

원본 HTML을 가져와 분석할 때:
```bash
# 홈페이지
curl -s https://cms.welldyingnews.com/ > /tmp/orig_homepage.html

# 기사 목록 (요약형)
curl -s "https://cms.welldyingnews.com/news/articleList.html?sc_section_code=S1N1&view_type=sm" > /tmp/orig_article_list.html

# 기사 상세
curl -s "https://cms.welldyingnews.com/news/articleView.html?idxno=1714" > /tmp/orig_article_view.html

# CSS 다운로드 예시
curl -s "https://cdn.welldyingnews.com/css/foundation.min.css" > app/static/css/orig/foundation.min.css
```
