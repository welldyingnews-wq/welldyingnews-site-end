"""DB 초기화 및 시드 데이터 삽입"""
import os

from werkzeug.security import generate_password_hash

from app import create_app
from app.models import db, AdminUser, Section, SubSection, SiteSetting

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()

    # 관리자 계정 (.env에서 읽음)
    admin = AdminUser(
        user_id=os.environ.get('ADMIN_USER_ID', 'admin'),
        password_hash=generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin')),
        name=os.environ.get('ADMIN_NAME', '관리자'),
        email=os.environ.get('ADMIN_EMAIL', ''),
    )
    db.session.add(admin)

    # 1차 섹션
    sections_data = [
        ('S1N1', '뉴스', 1),
        ('S1N2', '오피니언', 2),
        ('S1N3', '웰다잉TV', 3),
        ('S1N4', '자료실', 4),
        ('S1N5', '주요 일정', 5),
        ('S1N6', '뉴스레터', 6),
    ]
    sections = {}
    for code, name, order in sections_data:
        s = Section(code=code, name=name, sort_order=order)
        db.session.add(s)
        sections[code] = s

    db.session.flush()

    # 2차 섹션
    news_subs = [
        ('S2N1', '정책ㆍ사회', 1),
        ('S2N2', '문화ㆍ생활', 2),
        ('S2N4', '교육ㆍ행사', 3),
        ('S2N17', '도서·출판', 4),
        ('S2N12', '호스피스', 5),
        ('S2N11', '연명의료결정', 6),
        ('S2N7', '장례ㆍ장사', 7),
        ('S2N16', '돌봄·요양', 8),
        ('S2N9', '유언ㆍ기부', 9),
        ('S2N10', '애도ㆍ추모', 10),
        ('S2N21', '조력사망·안락사', 11),
        ('S2N13', '자살 예방', 12),
        ('S2N15', '고독사ㆍ무연고', 13),
        ('S2N20', '반려동물', 14),
        ('S2N5', '사건ㆍ사고', 15),
        ('S2N18', '인사이트', 16),
    ]
    for code, name, order in news_subs:
        db.session.add(SubSection(code=code, name=name, section_id=sections['S1N1'].id, sort_order=order))

    opinion_subs = [
        ('S2N22', '칼럼', 1),
        ('S2N23', '기고', 2),
    ]
    for code, name, order in opinion_subs:
        db.session.add(SubSection(code=code, name=name, section_id=sections['S1N2'].id, sort_order=order))

    # 사이트 설정
    settings = [
        ('site_name', '웰다잉뉴스', '사이트명'),
        ('site_tagline', '삶과 죽음의 존엄성을 전하는 웰다잉뉴스', '태그라인'),
        ('publisher', '김동하', '발행인'),
        ('editor_name', '김동하', '편집인'),
        ('company_name', '웰다잉미디어', '법인명'),
        ('address', '서울특별시 송파구 송파대로 345', '주소'),
        ('email', os.environ.get('ADMIN_EMAIL', ''), '이메일'),
        ('tel', '', '전화번호'),
        ('registration_no', '', '등록번호'),
        ('registration_date', '', '등록일'),
    ]
    for key, value, desc in settings:
        db.session.add(SiteSetting(key=key, value=value, description=desc))

    db.session.commit()
    print('DB 초기화 완료: 관리자 계정, 섹션, 2차 섹션, 사이트 설정 생성됨')
