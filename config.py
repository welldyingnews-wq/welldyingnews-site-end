import os
import secrets
import warnings

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY or SECRET_KEY == 'your-secret-key-here':
        SECRET_KEY = secrets.token_hex(32)
        warnings.warn(
            'SECRET_KEY가 설정되지 않았거나 기본값입니다. '
            '프로덕션에서는 반드시 강력한 SECRET_KEY를 .env에 설정하세요.',
            stacklevel=2
        )
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "welldying.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload (영상 포함)
    SITE_URL = os.environ.get('SITE_URL', 'https://www.welldyingnews.com')

    # Cloudinary (이미지+파일 업로드) — 환경변수 설정 시 자동 활성화
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')

    # AI 기사 자동화
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    GOOGLE_CSE_KEY = os.environ.get('GOOGLE_CSE_KEY', '')
    GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID', '')
    NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
    NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
    AI_FLASH_MODEL = 'gemini-2.5-flash'
    # NOTE: 비용 절약을 위해 flash와 동일하게 설정됨. 품질 필요시 'gemini-2.5-pro'로 변경
    AI_PRO_MODEL = 'gemini-2.5-flash'
