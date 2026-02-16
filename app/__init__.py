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

    # DB 테이블 생성
    with app.app_context():
        db.create_all()

    return app
