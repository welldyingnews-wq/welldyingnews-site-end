"""관리자 비밀번호 재설정 스크립트"""
import sys

from werkzeug.security import generate_password_hash

from app import create_app
from app.models import db, AdminUser

if len(sys.argv) < 2:
    print('사용법: python reset_admin_pw.py <새비밀번호> [관리자ID]')
    print('예시:   python reset_admin_pw.py mypassword123')
    print('예시:   python reset_admin_pw.py mypassword123 admin')
    sys.exit(1)

new_password = sys.argv[1]
user_id = sys.argv[2] if len(sys.argv) >= 3 else 'admin'

app = create_app()
with app.app_context():
    admin = AdminUser.query.filter_by(user_id=user_id).first()
    if not admin:
        print(f'관리자 계정 "{user_id}"를 찾을 수 없습니다.')
        sys.exit(1)

    admin.password_hash = generate_password_hash(new_password)
    db.session.commit()
    print(f'관리자 "{user_id}" 비밀번호가 변경되었습니다.')
