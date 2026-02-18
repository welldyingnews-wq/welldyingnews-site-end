from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_user'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100))
    department = db.Column(db.String(50), default='')
    level = db.Column(db.String(20), default='admin')  # admin, editor, reporter
    is_active = db.Column(db.Boolean, default=True)
    is_dormant = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Member(db.Model):
    """일반 회원"""
    __tablename__ = 'member'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), default='')
    phone = db.Column(db.String(20), default='')
    level = db.Column(db.String(20), default='일반')  # 일반/시민기자/기자/데스크
    profile_image = db.Column(db.String(500), default='')  # 프로필 이미지 경로/URL
    is_active = db.Column(db.Boolean, default=True)
    is_dormant = db.Column(db.Boolean, default=False)  # 휴면회원
    created_at = db.Column(db.DateTime, default=datetime.now)


class Department(db.Model):
    __tablename__ = 'department'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class MemberDivision(db.Model):
    """필자표시관리 (기자 표시 구분)"""
    __tablename__ = 'member_division'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class EtcLevel(db.Model):
    """기타등급관리"""
    __tablename__ = 'etc_level'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), default='')
    sort_order = db.Column(db.Integer, default=0)


class Section(db.Model):
    __tablename__ = 'section'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    subsections = db.relationship('SubSection', backref='section', lazy='dynamic', order_by='SubSection.sort_order')


class SubSection(db.Model):
    __tablename__ = 'sub_section'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class SerialCode(db.Model):
    """연재설정"""
    __tablename__ = 'serial_code'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class DailyStat(db.Model):
    """사이트 일별 통계"""
    __tablename__ = 'daily_stat'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True, index=True)
    page_views = db.Column(db.Integer, default=0)       # 전체 PV (모든 페이지 조회)
    unique_visitors = db.Column(db.Integer, default=0)   # UV (IP 기반 고유 방문자)
    article_views = db.Column(db.Integer, default=0)     # 기사 PV (기사 상세 조회)


class PageView(db.Model):
    """기사별 일별 조회 기록"""
    __tablename__ = 'page_view'
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    view_count = db.Column(db.Integer, default=0)        # 해당일 총 PV
    unique_count = db.Column(db.Integer, default=0)      # 해당일 UV

    __table_args__ = (
        db.UniqueConstraint('article_id', 'date', name='uq_pageview_article_date'),
    )


class VisitorLog(db.Model):
    """방문자 로그 (UV 중복 체크용)"""
    __tablename__ = 'visitor_log'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), nullable=False)
    session_key = db.Column(db.String(64), default='')
    user_agent = db.Column(db.String(20), default='pc')   # pc, mobile, tablet
    date = db.Column(db.Date, nullable=False, index=True)
    article_id = db.Column(db.Integer, nullable=True)    # NULL이면 사이트 방문, 값 있으면 기사 조회
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        db.Index('ix_visitor_ip_date', 'ip_address', 'date'),
        db.Index('ix_visitor_article_ip_date', 'article_id', 'ip_address', 'date'),
    )


class ArticleDraft(db.Model):
    """임시보관함 (자동저장)"""
    __tablename__ = 'article_draft'
    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=False)
    article_id = db.Column(db.Integer, nullable=True)  # 기존 기사 수정 시
    title = db.Column(db.String(500), default='')
    content = db.Column(db.Text, default='')
    data_json = db.Column(db.Text, default='{}')  # 기타 필드 JSON
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class MemberLog(db.Model):
    """회원 수정내역 로그"""
    __tablename__ = 'member_log'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # create, update, activate, deactivate, delete
    detail = db.Column(db.Text, default='')
    admin_name = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)


# 기사-추가섹션 다대다 중간 테이블
article_extra_section = db.Table('article_extra_section',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('section_id', db.Integer, db.ForeignKey('section.id'), primary_key=True)
)


class Article(db.Model):
    __tablename__ = 'article'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    subtitle = db.Column(db.Text, default='')
    content = db.Column(db.Text, default='')
    summary = db.Column(db.Text, default='')
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'))
    subsection_id = db.Column(db.Integer, db.ForeignKey('sub_section.id'))
    author_name = db.Column(db.String(50), default='웰다잉뉴스')
    author_email = db.Column(db.String(100), default='welldyingnews@naver.com')
    source = db.Column(db.String(100), default='')  # 기사출처
    level = db.Column(db.String(1), default='B')  # B=일반, I=중요, T=헤드라인
    recognition = db.Column(db.String(1), default='E')  # C=미승인, E=승인, R=반려
    article_type = db.Column(db.String(1), default='B')  # B=일반, P=카드뉴스, G=갤러리, V=동영상
    thumbnail_path = db.Column(db.String(500), default='')
    serial_code_id = db.Column(db.Integer, db.ForeignKey('serial_code.id'), nullable=True)
    keyword = db.Column(db.String(500), default='')
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    embargo_date = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    section = db.relationship('Section', backref='articles', foreign_keys=[section_id])
    subsection = db.relationship('SubSection', backref='articles')
    serial_code = db.relationship('SerialCode', backref='articles')
    extra_sections = db.relationship('Section', secondary=article_extra_section,
                                     backref=db.backref('extra_articles', lazy='dynamic'))
    article_relations = db.relationship('ArticleRelation', foreign_keys='ArticleRelation.article_id',
                                        backref='article', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def summary_text(self):
        if self.summary:
            return self.summary
        import re
        text = re.sub(r'<[^>]+>', '', self.content or '')
        return text[:200]

    @property
    def thumb_url(self):
        """썸네일 URL 반환: thumbnail_path가 유효한 파일이면 사용, 아니면 본문 첫 이미지 추출"""
        if self.thumbnail_path and '/' in self.thumbnail_path:
            return '/static/' + self.thumbnail_path
        import re
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', self.content or '')
        if match:
            return match.group(1)
        return ''


class ArticleRelation(db.Model):
    """관련기사 매핑"""
    __tablename__ = 'article_relation'
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    related_article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    related_article = db.relationship('Article', foreign_keys=[related_article_id])


class ArticleComment(db.Model):
    """기사댓글"""
    __tablename__ = 'article_comment'
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('article_comment.id'), nullable=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=True)
    author_name = db.Column(db.String(50), default='')
    content = db.Column(db.Text, nullable=False)
    password = db.Column(db.String(200), default='')
    ip_address = db.Column(db.String(50), default='')
    like_count = db.Column(db.Integer, default=0)
    dislike_count = db.Column(db.Integer, default=0)
    is_hidden = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    article = db.relationship('Article', backref=db.backref('comments', lazy='dynamic'))
    member = db.relationship('Member', backref='comments')
    replies = db.relationship('ArticleComment', backref=db.backref('parent', remote_side='ArticleComment.id'),
                              lazy='dynamic', order_by='ArticleComment.created_at.asc()')


class CommentVote(db.Model):
    """댓글 추천/비추천"""
    __tablename__ = 'comment_vote'
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('article_comment.id'), nullable=False)
    ip_address = db.Column(db.String(50), default='')
    member_id = db.Column(db.Integer, nullable=True)
    vote_type = db.Column(db.String(10), nullable=False)  # like / dislike
    created_at = db.Column(db.DateTime, default=datetime.now)


class Board(db.Model):
    """게시판"""
    __tablename__ = 'board'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)


class BoardPost(db.Model):
    """게시물"""
    __tablename__ = 'board_post'
    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'), nullable=False)
    parent_post_id = db.Column(db.Integer, db.ForeignKey('board_post.id'), nullable=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, default='')
    author_name = db.Column(db.String(50), default='')
    password = db.Column(db.String(200), default='')
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=True)
    view_count = db.Column(db.Integer, default=0)
    is_hidden = db.Column(db.Boolean, default=False)
    is_secret = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    board = db.relationship('Board', backref=db.backref('posts', lazy='dynamic'))
    parent_post = db.relationship('BoardPost', remote_side='BoardPost.id', backref='child_posts')
    member = db.relationship('Member', backref='board_posts')


class BoardReply(db.Model):
    """게시판 댓글"""
    __tablename__ = 'board_reply'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('board_post.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('board_reply.id'), nullable=True)
    author_name = db.Column(db.String(50), default='')
    password = db.Column(db.String(200), default='')
    content = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(50), default='')
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=True)
    like_count = db.Column(db.Integer, default=0)
    dislike_count = db.Column(db.Integer, default=0)
    is_hidden = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    post = db.relationship('BoardPost', backref=db.backref('replies', lazy='dynamic'))
    member = db.relationship('Member', backref='board_replies')
    children = db.relationship('BoardReply', backref=db.backref('parent', remote_side='BoardReply.id'),
                               lazy='dynamic', order_by='BoardReply.created_at.asc()')


class BoardReplyVote(db.Model):
    """게시판 댓글 추천/비추천"""
    __tablename__ = 'board_reply_vote'
    id = db.Column(db.Integer, primary_key=True)
    reply_id = db.Column(db.Integer, db.ForeignKey('board_reply.id'), nullable=False)
    ip_address = db.Column(db.String(50), default='')
    member_id = db.Column(db.Integer, nullable=True)
    vote_type = db.Column(db.String(10), nullable=False)  # like / dislike
    created_at = db.Column(db.DateTime, default=datetime.now)


class EventRequest(db.Model):
    """신청글 (구독신청, 기사제보, 저작권문의 등)"""
    __tablename__ = 'event_request'
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(20), nullable=False)  # event2~event7
    name = db.Column(db.String(50), default='')
    email = db.Column(db.String(100), default='')
    phone = db.Column(db.String(20), default='')
    subject = db.Column(db.String(200), default='')
    content = db.Column(db.Text, default='')
    # 구독신청 전용 필드
    extra_data = db.Column(db.Text, default='')  # JSON (reqname, reqemail, reqnum, reqtel, reqaddr, reqmoney)
    ip_address = db.Column(db.String(50), default='')
    is_processed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Banner(db.Model):
    """배너 광고"""
    __tablename__ = 'banner'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image_path = db.Column(db.String(500), default='')
    link_url = db.Column(db.String(500), default='')
    position = db.Column(db.String(50), default='')  # header, sidebar, footer 등
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    click_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Popup(db.Model):
    """팝업 광고"""
    __tablename__ = 'popup'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, default='')
    image_path = db.Column(db.String(500), default='')
    link_url = db.Column(db.String(500), default='')
    width = db.Column(db.Integer, default=500)
    height = db.Column(db.Integer, default=400)
    pos_x = db.Column(db.Integer, default=100)
    pos_y = db.Column(db.Integer, default=100)
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Poll(db.Model):
    """설문조사"""
    __tablename__ = 'poll'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_multiple = db.Column(db.Boolean, default=False)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class PollOption(db.Model):
    """설문 선택지"""
    __tablename__ = 'poll_option'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    vote_count = db.Column(db.Integer, default=0)
    sort_order = db.Column(db.Integer, default=0)
    poll = db.relationship('Poll', backref=db.backref('options', lazy='dynamic', order_by='PollOption.sort_order'))


class SiteSetting(db.Model):
    __tablename__ = 'site_setting'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
    description = db.Column(db.String(200), default='')


class LayoutBlock(db.Model):
    """편집 레이아웃 블록"""
    __tablename__ = 'layout_block'
    id = db.Column(db.Integer, primary_key=True)
    layout_type = db.Column(db.String(20), nullable=False)  # MAIN, MOBILE, PCVIEW, PCLIST, LETTER
    block_type = db.Column(db.String(50), nullable=False)  # headline, latest_grid, etc.
    block_label = db.Column(db.String(100), default='')
    settings = db.Column(db.Text, default='{}')  # JSON: section_code, count, skin 등
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


class Photo(db.Model):
    """포토DB (업로드된 이미지 관리)"""
    __tablename__ = 'photo'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200), default='')
    file_path = db.Column(db.String(500), nullable=False)
    file_url = db.Column(db.String(500), default='')
    file_size = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer, default=0)
    height = db.Column(db.Integer, default=0)
    is_favorite = db.Column(db.Boolean, default=False)
    uploaded_by = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
