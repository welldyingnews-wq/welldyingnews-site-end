import os
import time

os.environ.setdefault('TZ', 'Asia/Seoul')
time.tzset()

from app import create_app

application = create_app()
