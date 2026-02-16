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
- Bootstrap 5 (관리자 UI), 커스텀 CSS (서비스)
- 브랜드 색상: `#5e1985`
