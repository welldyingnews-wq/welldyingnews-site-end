import os, time
os.environ.setdefault('TZ', 'Asia/Seoul')
time.tzset()

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
