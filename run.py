import os, time
os.environ.setdefault('TZ', 'Asia/Seoul')
time.tzset()

from app import create_app

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=debug, port=port)
