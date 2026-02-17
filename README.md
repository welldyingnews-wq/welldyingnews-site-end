# welldying-news

웰다잉뉴스(welldyingnews.com) 클론 CMS — Flask + SQLite

## 서버 실행

```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 서버 실행 (포트 5001, 디버그 모드)
python run.py
```

실행 후 브라우저에서 `http://localhost:5001` 접속.
관리자 페이지는 `http://localhost:5001/admin`.

## 서버 종료

터미널에서 `Ctrl + C`를 누르면 서버가 종료됩니다.
