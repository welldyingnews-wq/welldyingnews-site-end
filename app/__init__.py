import os

from flask import Flask
from flask_login import LoginManager

from app.models import db, AdminUser
from config import Config

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 업로드 폴더 생성
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # DB 초기화
    db.init_app(app)

    # 로그인 매니저
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AdminUser, int(user_id))

    # Blueprint 등록
    from app.admin import admin_bp
    from app.public import public_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(public_bp)

    # DB 테이블 생성 + 마이그레이션
    with app.app_context():
        db.create_all()
        _run_migrations()

    return app


def _run_migrations():
    """기존 DB에 새 컬럼이 없으면 추가 (ALTER TABLE)"""
    import sqlite3
    db_path = db.engine.url.database
    if not db_path or not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # article 테이블 컬럼 확인
    cursor.execute('PRAGMA table_info(article)')
    columns = {row[1] for row in cursor.fetchall()}

    migrations = [
        ('photo_caption', 'ALTER TABLE article ADD COLUMN photo_caption TEXT DEFAULT ""'),
    ]
    for col, sql in migrations:
        if col not in columns:
            cursor.execute(sql)

    conn.commit()
    conn.close()
