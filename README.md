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

```bash
# 4. DB 초기화 (최초 1회)
python init_db.py

# 5. 서버 실행 (포트 5001, 디버그 모드)
python run.py
```

실행 후 브라우저에서 `http://localhost:5001` 접속.
관리자 페이지는 `http://localhost:5001/admin`.

## 서버 종료

터미널에서 `Ctrl + C`를 누르면 서버가 종료됩니다.
