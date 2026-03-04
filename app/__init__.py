import json
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template
from flask_login import LoginManager

from app.models import db, AdminUser, AiDraft
from config import Config

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── 세션 보안 설정 ──
    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
    if not app.debug:
        app.config.setdefault('SESSION_COOKIE_SECURE', True)

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

    # ── 보안 헤더 (nginx에서 설정, 로컬 개발용 폴백) ──
    @app.after_request
    def set_security_headers(response):
        if app.debug:
            response.headers.setdefault('X-Content-Type-Options', 'nosniff')
            response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
            response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        return response

    # ── 에러 핸들러 ──
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        app.logger.error(f'500 error: {e}')
        return render_template('errors/500.html'), 500

    # ── 프로덕션 로깅 ──
    if not app.debug:
        log_dir = os.path.join(os.path.dirname(app.root_path), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)

    # ── 정적 파일 캐시 버스팅 ──
    @app.context_processor
    def static_cache_buster():
        def static_v(filename):
            fpath = os.path.join(app.static_folder, filename)
            try:
                mtime = int(os.path.getmtime(fpath))
            except OSError:
                mtime = 0
            return f'/static/{filename}?v={mtime}'
        return dict(static_v=static_v)

    # Blueprint 등록
    from app.admin import admin_bp
    from app.public import public_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(public_bp)

    # 기사 ID 리다이렉트 맵 (누락 idxno → 대체 기사로 301 리다이렉트)
    app.config['ARTICLE_ID_REDIRECT_MAP'] = {
        189: 1734,   # 조력사망 관련 → 브리태니커 조력사망 정리
    }

    # DB 테이블 생성 + 마이그레이션
    with app.app_context():
        db.create_all()
        _run_migrations()

        # 서버 시작 시 중단된 AI 작업 복구 (bulk update)
        from app.services.ai_draft import STALE_STATUSES, STATUS_PENDING
        AiDraft.query.filter(
            AiDraft.status.in_(STALE_STATUSES)
        ).update({AiDraft.status: STATUS_PENDING}, synchronize_session=False)
        db.session.commit()

    # 백그라운드 워커 (GEMINI_API_KEY가 있을 때만)
    if app.config.get('GEMINI_API_KEY'):
        from app.services.background_queue import init_background_worker
        init_background_worker(app)

    return app


def _run_migrations():
    """기존 DB에 새 컬럼이 없으면 추가 (ALTER TABLE)"""
    import sqlite3
    db_path = db.engine.url.database
    if not db_path or not os.path.exists(db_path):
        return
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # article 테이블 컬럼 확인
        cursor.execute('PRAGMA table_info(article)')
        columns = {row[1] for row in cursor.fetchall()}

        migrations = [
            ('photo_caption', 'ALTER TABLE article ADD COLUMN photo_caption TEXT DEFAULT ""'),
            ('author_photo', 'ALTER TABLE article ADD COLUMN author_photo VARCHAR(500) DEFAULT ""'),
            ('author_title', 'ALTER TABLE article ADD COLUMN author_title VARCHAR(100) DEFAULT ""'),
            ('author_affiliation', 'ALTER TABLE article ADD COLUMN author_affiliation VARCHAR(100) DEFAULT ""'),
            ('author_photo_pos', 'ALTER TABLE article ADD COLUMN author_photo_pos VARCHAR(20) DEFAULT "center center"'),
        ]
        for col, sql in migrations:
            if col not in columns:
                cursor.execute(sql)

        # 새 테이블 자동 생성 (newsletter_subscriber, schedule, resource)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        if 'newsletter_subscriber' not in tables:
            cursor.execute('''CREATE TABLE newsletter_subscriber (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(200) UNIQUE NOT NULL,
                name VARCHAR(50) DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
        if 'schedule' not in tables:
            cursor.execute('''CREATE TABLE schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(500) NOT NULL,
                description TEXT DEFAULT '',
                event_date DATETIME NOT NULL,
                end_date DATETIME,
                location VARCHAR(200) DEFAULT '',
                category VARCHAR(50) DEFAULT '',
                link_url VARCHAR(500) DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
        if 'resource' not in tables:
            cursor.execute('''CREATE TABLE resource (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(500) NOT NULL,
                description TEXT DEFAULT '',
                file_path VARCHAR(500) DEFAULT '',
                file_url VARCHAR(500) DEFAULT '',
                file_size INTEGER DEFAULT 0,
                file_type VARCHAR(50) DEFAULT '',
                category VARCHAR(50) DEFAULT '',
                author_name VARCHAR(50) DEFAULT '',
                download_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
        if 'newsletter' not in tables:
            cursor.execute('''CREATE TABLE newsletter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                volume_number INTEGER NOT NULL UNIQUE,
                title VARCHAR(500) NOT NULL,
                slug VARCHAR(200) UNIQUE NOT NULL,
                publish_date DATE,
                status VARCHAR(10) DEFAULT 'draft',
                briefing_title VARCHAR(500) DEFAULT '',
                briefing_image VARCHAR(500) DEFAULT '',
                briefing_content TEXT DEFAULT '',
                briefing_article_id INTEGER REFERENCES article(id),
                briefing_visible BOOLEAN DEFAULT 1,
                sections_data TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

        # 테이블별 컬럼 추가 (공통 헬퍼)
        def _add_cols(table, col_sql_pairs):
            if table not in tables:
                return
            cursor.execute(f'PRAGMA table_info({table})')
            cols = {row[1] for row in cursor.fetchall()}
            for col, sql in col_sql_pairs:
                if col not in cols:
                    cursor.execute(sql)

        _add_cols('newsletter', [
            ('view_count', 'ALTER TABLE newsletter ADD COLUMN view_count INTEGER DEFAULT 0'),
        ])
        _add_cols('schedule', [
            ('content', 'ALTER TABLE schedule ADD COLUMN content TEXT DEFAULT ""'),
            ('image_url', 'ALTER TABLE schedule ADD COLUMN image_url VARCHAR(500) DEFAULT ""'),
        ])
        _add_cols('banner', [
            ('mobile_image_path', 'ALTER TABLE banner ADD COLUMN mobile_image_path VARCHAR(500) DEFAULT ""'),
        ])
        _add_cols('admin_user', [
            ('photo', 'ALTER TABLE admin_user ADD COLUMN photo VARCHAR(500) DEFAULT ""'),
            ('photo_pos', 'ALTER TABLE admin_user ADD COLUMN photo_pos VARCHAR(20) DEFAULT "center center"'),
        ])
        _add_cols('visitor_log', [
            ('referrer_source', 'ALTER TABLE visitor_log ADD COLUMN referrer_source VARCHAR(20) DEFAULT "direct"'),
        ])

        # ai_draft 테이블
        if 'ai_draft' not in tables:
            cursor.execute('''CREATE TABLE ai_draft (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_news_ids TEXT DEFAULT '',
                source_data TEXT DEFAULT '',
                original_url VARCHAR(1000) DEFAULT '',
                related_urls TEXT DEFAULT '',
                curation_result TEXT DEFAULT '',
                scraped_data TEXT DEFAULT '',
                fact_package TEXT DEFAULT '',
                article_result TEXT DEFAULT '',
                validation_result TEXT DEFAULT '',
                title VARCHAR(500) DEFAULT '',
                subtitle TEXT DEFAULT '',
                content TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                keywords VARCHAR(500) DEFAULT '',
                author_name VARCHAR(50) DEFAULT '웰다잉뉴스',
                source_text VARCHAR(200) DEFAULT '',
                grade VARCHAR(5) DEFAULT '',
                article_type VARCHAR(20) DEFAULT '',
                suggested_section_id INTEGER,
                suggested_subsection_id INTEGER,
                status VARCHAR(20) DEFAULT 'pending',
                skip_reason VARCHAR(500) DEFAULT '',
                validation_score INTEGER DEFAULT 0,
                article_id INTEGER REFERENCES article(id),
                created_by INTEGER REFERENCES admin_user(id),
                ai_models_used VARCHAR(200) DEFAULT '',
                total_tokens_used INTEGER DEFAULT 0,
                generation_time_sec REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                published_at DATETIME
            )''')

        conn.commit()
    except sqlite3.Error as e:
        logging.getLogger(__name__).warning(f'Migration error (non-fatal): {e}')
    finally:
        if conn:
            conn.close()
