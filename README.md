# welldying-news

웰다잉뉴스(welldyingnews.com) 클론 CMS — Flask + SQLite

## 서버 실행

```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.sample .env
# .env 파일을 열어 값을 수정하세요
```

### .env 설정 항목

| 변수 | 설명 | 예시 |
|------|------|------|
| `SECRET_KEY` | Flask 세션 암호화 키 (필수) | 랜덤 문자열 |
| `ADMIN_USER_ID` | 초기 관리자 아이디 | `admin` |
| `ADMIN_PASSWORD` | 초기 관리자 비밀번호 | `my-secure-pw` |
| `ADMIN_NAME` | 관리자 표시 이름 | `관리자` |
| `ADMIN_EMAIL` | 관리자 이메일 | `admin@example.com` |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary Cloud Name | `dk9ptebu2` |
| `CLOUDINARY_API_KEY` | Cloudinary API Key | `373745398985613` |
| `CLOUDINARY_API_SECRET` | Cloudinary API Secret | `ADYF4O7b...` |
| `RECAPTCHA_SITE_KEY` | reCAPTCHA v2 사이트 키 | `6LeIxAcTAAAAAJcZ...` |
| `RECAPTCHA_SECRET_KEY` | reCAPTCHA v2 시크릿 키 | `6LeIxAcTAAAAAGG-...` |

```bash
# 4. DB 초기화 (최초 1회)
python init_db.py

# 5. 서버 실행 (포트 5001, 디버그 모드)
python run.py
```

실행 후 브라우저에서 `http://localhost:5001` 접속.
관리자 페이지는 `http://localhost:5001/admin`.

### 관리자 비밀번호 재설정

DB 초기화 없이 관리자 비밀번호만 변경할 수 있습니다.

```bash
python reset_admin_pw.py <새비밀번호> [관리자ID]

# 예시
python reset_admin_pw.py mypassword123
python reset_admin_pw.py mypassword123 admin
```

## Vultr 배포 (프로덕션)

- 서버: Vultr VPS (158.247.196.251)
- 프로젝트 경로: `/home/deploy/welldying-news`
- 프로세스: gunicorn + nginx (systemd: `welldying.service`)
- SSL: Let's Encrypt (certbot 자동갱신)
- DB 백업: 매일 한국시간 새벽 3시 자동 (`backups/` 디렉토리, 30일 보관)

```bash
# 서비스 재시작
ssh root@158.247.196.251 "systemctl restart welldying"

# 로그 확인
ssh root@158.247.196.251 "tail -50 /home/deploy/welldying-news/logs/error.log"
```

## 서버 종료

터미널에서 `Ctrl + C`를 누르면 서버가 종료됩니다.

---

## 외부 서비스 키 발급 가이드

아래 서비스는 모두 **선택사항**입니다. Cloudinary 미설정 시 로컬 저장소(`app/static/uploads/`)를 사용합니다. Cloudinary 설정 시 모든 파일이 Cloudinary로 업로드되며, 실패 시 로컬 폴백 없이 에러가 발생합니다.

### Cloudinary (이미지+파일 업로드)

1. https://cloudinary.com 에서 무료 계정 생성
2. 로그인 후 **Dashboard** 진입
3. **Product Environment Credentials** 섹션에서 아래 3개 값 확인:
   - `Cloud Name` → `CLOUDINARY_CLOUD_NAME`
   - `API Key` → `CLOUDINARY_API_KEY`
   - `API Secret` → `CLOUDINARY_API_SECRET`
4. pip 의존성 설치:
   ```bash
   pip install cloudinary
   ```

### Google reCAPTCHA v2 (자동등록방지)

1. https://www.google.com/recaptcha/admin 접속 (Google 계정 로그인)
2. **+** 버튼으로 새 사이트 등록:
   - **라벨**: 사이트 이름 (예: `welldying-news`)
   - **reCAPTCHA 유형**: **reCAPTCHA v2 > "로봇이 아닙니다" 체크박스** 선택
   - **도메인**: `localhost`, 운영 도메인 추가
3. 등록 완료 후 표시되는 키 확인:
   - `사이트 키` → `RECAPTCHA_SITE_KEY`
   - `비밀 키` → `RECAPTCHA_SECRET_KEY`
4. 또는 관리자 페이지 **댓글설정 > 비회원 CAPTCHA 설정**에서도 입력 가능
