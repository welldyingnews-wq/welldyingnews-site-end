from datetime import datetime, timedelta

import re

from flask import render_template, request, abort, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

import json
from app.models import (db, Section, SubSection, Article, ArticleRelation, ArticleComment,
                        CommentVote, SiteSetting, Board, BoardPost, BoardReply,
                        BoardReplyVote, Banner,
                        EventRequest, Popup, Poll, PollOption, Member,
                        DailyStat, PageView, VisitorLog)
from app.public import public_bp


@public_bp.route('/v2')
def index_v2():
    return render_template('public/index_v2.html')



def _get_published_query():
    """승인된 + 삭제되지 않은 + 노출시간 지난 기사만 조회"""
    now = datetime.now()
    return Article.query.filter(
        Article.is_deleted == False,  # noqa: E712
        Article.recognition == 'E',
        db.or_(Article.embargo_date == None, Article.embargo_date <= now)  # noqa: E711
    )


@public_bp.context_processor
def inject_sections():
    sections = Section.query.order_by(Section.sort_order).all()
    boards = Board.query.filter_by(is_active=True).order_by(Board.sort_order).all()
    # 최근 기사 업데이트 시간
    latest = Article.query.filter_by(is_deleted=False, recognition='E').order_by(
        Article.updated_at.desc()
    ).first()
    if latest and latest.updated_at:
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        t = latest.updated_at
        updated_time = f"{t.strftime('%Y-%m-%d %H:%M')} ({weekdays[t.weekday()]})"
    else:
        t = datetime.now()
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        updated_time = f"{t.strftime('%Y-%m-%d %H:%M')} ({weekdays[t.weekday()]})"
    # 활성 배너 (position별 그룹)
    now = datetime.now()
    active_banners = Banner.query.filter(
        Banner.is_active == True,  # noqa: E712
        db.or_(Banner.start_date == None, Banner.start_date <= now),  # noqa: E711
        db.or_(Banner.end_date == None, Banner.end_date >= now)  # noqa: E711
    ).order_by(Banner.sort_order).all()
    banners_by_pos = {}
    for b in active_banners:
        banners_by_pos.setdefault(b.position, []).append(b)
    # 활성 팝업
    active_popups = Popup.query.filter(
        Popup.is_active == True,  # noqa: E712
        db.or_(Popup.start_date == None, Popup.start_date <= now),  # noqa: E711
        db.or_(Popup.end_date == None, Popup.end_date >= now)  # noqa: E711
    ).all()
    # 모바일 감지
    is_mobile = False
    if request.cookies.get('view_pc') != 'y':
        ua = request.headers.get('User-Agent', '')
        if re.search(r'Mobile|Android|iPhone|iPod|Opera Mini|IEMobile', ua, re.I):
            is_mobile = True
    # 로그인 회원 정보
    current_member = None
    member_id = session.get('member_id')
    if member_id:
        current_member = Member.query.get(member_id)
    return {'nav_sections': sections, 'nav_boards': boards, 'updated_time': updated_time,
            'banners': banners_by_pos, 'popups': active_popups, 'is_mobile': is_mobile,
            'current_member': current_member}


def _detect_device():
    """User-Agent에서 디바이스 유형 감지"""
    ua = request.headers.get('User-Agent', '')
    if re.search(r'iPad|Tablet|PlayBook|Silk', ua, re.I):
        return 'tablet'
    if re.search(r'Mobile|Android|iPhone|iPod|Opera Mini|IEMobile', ua, re.I):
        return 'mobile'
    return 'pc'


@public_bp.before_request
def track_visitor():
    """사이트 방문자(UV) 추적 — IP 기반 일별 중복 제거"""
    if request.path.startswith('/static'):
        return
    today = datetime.now().date()
    ip = request.remote_addr or '0.0.0.0'
    # 이미 오늘 기록된 방문자인지 확인
    exists = VisitorLog.query.filter_by(
        ip_address=ip, date=today, article_id=None
    ).first()
    if not exists:
        device = _detect_device()
        log = VisitorLog(ip_address=ip, date=today, article_id=None, user_agent=device)
        db.session.add(log)
        # DailyStat UV 증가
        stat = DailyStat.query.filter_by(date=today).first()
        if not stat:
            stat = DailyStat(date=today, page_views=0, unique_visitors=0, article_views=0)
            db.session.add(stat)
            db.session.flush()
        stat.unique_visitors += 1
        db.session.commit()


@public_bp.route('/')
def index():
    query = _get_published_query()

    # 헤드라인/중요 기사 (상단 skin-3 영역: 1 large + 2 small)
    headline_articles = query.filter(
        Article.level.in_(['T', 'I'])
    ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(3).all()

    # 부족하면 최신 기사로 채움
    if len(headline_articles) < 3:
        existing_ids = [a.id for a in headline_articles]
        extra = query.filter(
            ~Article.id.in_(existing_ids) if existing_ids else True
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(3 - len(headline_articles)).all()
        headline_articles.extend(extra)

    # 최신 기사 (skin-12 그리드: 8개)
    latest_articles = query.order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(8).all()

    # 많이 본 뉴스 (사이드바 랭킹: 5개)
    popular_articles = query.order_by(Article.view_count.desc()).limit(5).all()

    # 섹션별 최신 기사 (하단 3열 카테고리 섹션들)
    section_articles = {}
    key_subsections = SubSection.query.join(Section).filter(
        Section.code == 'S1N1'
    ).order_by(SubSection.sort_order).all()

    for sub in key_subsections[:16]:
        articles = query.filter(
            Article.subsection_id == sub.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()
        if articles:
            section_articles[sub] = articles

    # 오피니언 (사이드바: 4개)
    opinion_section = Section.query.filter_by(code='S1N2').first()
    opinion_articles = []
    if opinion_section:
        opinion_articles = query.filter(
            Article.section_id == opinion_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()

    # 설문조사 (활성 상태)
    active_poll = Poll.query.filter_by(is_active=True).order_by(Poll.created_at.desc()).first()

    return render_template('public/index.html',
                           headline_articles=headline_articles,
                           latest_articles=latest_articles,
                           popular_articles=popular_articles,
                           section_articles=section_articles,
                           opinion_articles=opinion_articles,
                           active_poll=active_poll)


def _get_sidebar_data():
    """사이드바 공통 데이터: 오피니언 + 많이 본 뉴스 (오늘/주간)"""
    query = _get_published_query()
    opinion_section = Section.query.filter_by(code='S1N2').first()
    sidebar_opinion = []
    if opinion_section:
        sidebar_opinion = query.filter(
            Article.section_id == opinion_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()
    # 많이 본 뉴스: 오늘
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    popular_today = _get_published_query().filter(
        Article.created_at >= today_start
    ).order_by(Article.view_count.desc()).limit(5).all()
    # 많이 본 뉴스: 주간
    week_start = today_start - timedelta(days=7)
    popular_week = _get_published_query().filter(
        Article.created_at >= week_start
    ).order_by(Article.view_count.desc()).limit(5).all()
    # 오늘 데이터가 부족하면 전체로 채움
    sidebar_popular = popular_today if len(popular_today) >= 3 else popular_week
    return sidebar_opinion, sidebar_popular, popular_today, popular_week


@public_bp.route('/news/articleList.html')
def article_list():
    page = request.args.get('page', 1, type=int)
    sc_section_code = request.args.get('sc_section_code', '')
    sc_sub_section_code = request.args.get('sc_sub_section_code', '')
    sc_area = request.args.get('sc_area', 'A')
    sc_word = request.args.get('sc_word', '').strip()
    view_type = request.args.get('view_type', '')

    query = _get_published_query()

    section = None
    subsection = None

    if sc_sub_section_code:
        subsection = SubSection.query.filter_by(code=sc_sub_section_code).first()
        if subsection:
            query = query.filter(Article.subsection_id == subsection.id)
            section = subsection.section
    elif sc_section_code:
        section = Section.query.filter_by(code=sc_section_code).first()
        if section:
            from app.models import article_extra_section
            query = query.filter(db.or_(
                Article.section_id == section.id,
                Article.id.in_(
                    db.session.query(article_extra_section.c.article_id).filter(
                        article_extra_section.c.section_id == section.id
                    )
                )
            ))

    if sc_word:
        if sc_area == 'T':
            query = query.filter(Article.title.contains(sc_word))
        elif sc_area == 'C':
            query = query.filter(Article.content.contains(sc_word))
        elif sc_area == 'N':
            query = query.filter(Article.author_name.contains(sc_word))
        else:  # A = 제목+내용
            query = query.filter(
                db.or_(Article.title.contains(sc_word), Article.content.contains(sc_word))
            )

    pagination = query.order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    sidebar_opinion, sidebar_popular, popular_today, popular_week = _get_sidebar_data()

    return render_template('public/article_list.html',
                           articles=pagination.items,
                           pagination=pagination,
                           section=section,
                           subsection=subsection,
                           sc_section_code=sc_section_code,
                           sc_sub_section_code=sc_sub_section_code,
                           sc_area=sc_area,
                           sc_word=sc_word,
                           view_type=view_type,
                           sidebar_opinion=sidebar_opinion,
                           sidebar_popular=sidebar_popular,
                           popular_today=popular_today,
                           popular_week=popular_week)


@public_bp.route('/news/articleView.html')
def article_view():
    idxno = request.args.get('idxno', 0, type=int)
    if not idxno:
        abort(404)

    article = Article.query.get_or_404(idxno)
    if article.is_deleted or article.recognition != 'E':
        abort(404)

    # 조회수 — IP 기반 일별 중복 제거
    today = datetime.now().date()
    ip = request.remote_addr or '0.0.0.0'
    already_viewed = VisitorLog.query.filter_by(
        ip_address=ip, date=today, article_id=article.id
    ).first()
    if not already_viewed:
        # VisitorLog 기록
        device = _detect_device()
        db.session.add(VisitorLog(ip_address=ip, date=today, article_id=article.id, user_agent=device))
        # Article 누적 조회수
        article.view_count += 1
        # PageView 일별 집계
        pv = PageView.query.filter_by(article_id=article.id, date=today).first()
        if not pv:
            pv = PageView(article_id=article.id, date=today, view_count=0, unique_count=0)
            db.session.add(pv)
            db.session.flush()
        pv.view_count += 1
        pv.unique_count += 1
        # DailyStat 기사PV 증가
        stat = DailyStat.query.filter_by(date=today).first()
        if not stat:
            stat = DailyStat(date=today, page_views=0, unique_visitors=0, article_views=0)
            db.session.add(stat)
            db.session.flush()
        stat.article_views += 1
        stat.page_views += 1
        db.session.commit()
    else:
        # 중복 방문이라도 PV(총 조회) 카운트는 증가
        pv = PageView.query.filter_by(article_id=article.id, date=today).first()
        if not pv:
            pv = PageView(article_id=article.id, date=today, view_count=0, unique_count=0)
            db.session.add(pv)
            db.session.flush()
        pv.view_count += 1
        stat = DailyStat.query.filter_by(date=today).first()
        if stat:
            stat.page_views += 1
            stat.article_views += 1
        db.session.commit()

    # 관련 기사: 수동 설정 우선, 없으면 같은 2차섹션 자동
    relations = ArticleRelation.query.filter_by(
        article_id=article.id
    ).order_by(ArticleRelation.sort_order).all()
    if relations:
        related = [r.related_article for r in relations if r.related_article and not r.related_article.is_deleted]
    else:
        related = []
        if article.subsection_id:
            related = _get_published_query().filter(
                Article.subsection_id == article.subsection_id,
                Article.id != article.id
            ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(5).all()

    # 이전/다음 기사
    prev_article = _get_published_query().filter(
        Article.id < article.id
    ).order_by(Article.id.desc()).first()
    next_article = _get_published_query().filter(
        Article.id > article.id
    ).order_by(Article.id.asc()).first()

    sidebar_opinion, sidebar_popular, popular_today, popular_week = _get_sidebar_data()

    # 댓글
    comment_use = _get_setting('comment_use', 'Y')
    comment_max_length = int(_get_setting('comment_max_length', '500') or 500)
    comment_sort = request.args.get('csort', 'newest')  # newest / oldest
    comments = []
    best_comments = []
    comment_count = 0
    if comment_use != 'N':
        # 전체 댓글 수 (대댓글 포함)
        comment_count = article.comments.filter_by(is_hidden=False).count()
        # 최상위 댓글만 (parent_id IS NULL)
        q = article.comments.filter_by(is_hidden=False, parent_id=None)
        if comment_sort == 'oldest':
            q = q.order_by(ArticleComment.created_at.asc())
        else:
            q = q.order_by(ArticleComment.created_at.desc())
        comments = q.all()
        # BEST 댓글: 추천 3개 이상, 최대 3개
        best_comments = article.comments.filter(
            ArticleComment.is_hidden == False,
            ArticleComment.like_count >= 3,
            ArticleComment.parent_id == None
        ).order_by(ArticleComment.like_count.desc()).limit(3).all()

    return render_template('public/article_view.html',
                           article=article,
                           related_articles=related,
                           prev_article=prev_article,
                           next_article=next_article,
                           sidebar_opinion=sidebar_opinion,
                           sidebar_popular=sidebar_popular,
                           popular_today=popular_today,
                           popular_week=popular_week,
                           comments=comments,
                           best_comments=best_comments,
                           comment_count=comment_count,
                           comment_use=comment_use,
                           comment_max_length=comment_max_length,
                           comment_sort=comment_sort)


def _get_setting(key, default=''):
    s = SiteSetting.query.filter_by(key=key).first()
    return s.value if s and s.value else default


@public_bp.route('/news/comment/write', methods=['POST'])
def comment_write():
    article_id = request.form.get('article_id', 0, type=int)
    parent_id = request.form.get('parent_id', 0, type=int) or None
    author_name = request.form.get('author_name', '').strip()
    password = request.form.get('password', '').strip()
    content = request.form.get('content', '').strip()

    if not article_id or not content:
        abort(400)

    article = Article.query.get_or_404(article_id)

    # 댓글 사용 여부 확인
    if _get_setting('comment_use', 'Y') == 'N':
        abort(403)

    # 글자수 제한
    max_length = int(_get_setting('comment_max_length', '500') or 500)
    if len(content) > max_length:
        content = content[:max_length]

    # 금칙어 체크
    block_words = _get_setting('comment_block_words', '')
    if block_words:
        for word in block_words.split(','):
            word = word.strip()
            if word and word in content:
                flash('금칙어가 포함되어 있습니다.', 'error')
                return redirect(url_for('public.article_view', idxno=article_id) + '#comment')

    # 로그인 회원이면 회원 정보 사용
    member_id = session.get('member_id')
    if member_id:
        member = Member.query.get(member_id)
        if member:
            author_name = member.name

    comment = ArticleComment(
        article_id=article_id,
        parent_id=parent_id,
        member_id=member_id if member_id else None,
        author_name=author_name or '익명',
        content=content,
        password=generate_password_hash(password) if password else '',
        ip_address=request.remote_addr or ''
    )
    db.session.add(comment)
    db.session.commit()

    return redirect(url_for('public.article_view', idxno=article_id) + '#comment')


@public_bp.route('/news/comment/delete', methods=['POST'])
def comment_delete():
    comment_id = request.form.get('comment_id', 0, type=int)
    password = request.form.get('password', '').strip()
    article_id = request.form.get('article_id', 0, type=int)

    comment = ArticleComment.query.get_or_404(comment_id)

    # 로그인 회원 본인 댓글이면 비밀번호 없이 삭제
    member_id = session.get('member_id')
    can_delete = False
    if comment.member_id and comment.member_id == member_id:
        can_delete = True
    elif comment.password and check_password_hash(comment.password, password):
        can_delete = True

    if not can_delete:
        flash('비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('public.article_view', idxno=article_id) + '#comment')

    # 대댓글도 함께 삭제
    ArticleComment.query.filter_by(parent_id=comment.id).delete()
    CommentVote.query.filter_by(comment_id=comment.id).delete()
    db.session.delete(comment)
    db.session.commit()

    return redirect(url_for('public.article_view', idxno=article_id) + '#comment')


@public_bp.route('/news/comment/vote', methods=['POST'])
def comment_vote():
    """댓글 추천/비추천"""
    from flask import jsonify
    comment_id = request.form.get('comment_id', 0, type=int)
    vote_type = request.form.get('vote_type', '')  # like / dislike

    if not comment_id or vote_type not in ('like', 'dislike'):
        return jsonify({'error': 'invalid'}), 400

    comment = ArticleComment.query.get_or_404(comment_id)
    ip = request.remote_addr or ''
    member_id = session.get('member_id')

    # 중복 투표 확인 (IP 또는 회원 기준)
    existing = CommentVote.query.filter_by(comment_id=comment_id, ip_address=ip).first()
    if not existing and member_id:
        existing = CommentVote.query.filter_by(comment_id=comment_id, member_id=member_id).first()
    if existing:
        return jsonify({'error': 'already_voted', 'like': comment.like_count, 'dislike': comment.dislike_count})

    vote = CommentVote(
        comment_id=comment_id,
        ip_address=ip,
        member_id=member_id,
        vote_type=vote_type
    )
    db.session.add(vote)

    if vote_type == 'like':
        comment.like_count = (comment.like_count or 0) + 1
    else:
        comment.dislike_count = (comment.dislike_count or 0) + 1

    db.session.commit()
    return jsonify({'like': comment.like_count, 'dislike': comment.dislike_count})


@public_bp.route('/news/comment/edit', methods=['POST'])
def comment_edit():
    """댓글 수정"""
    comment_id = request.form.get('comment_id', 0, type=int)
    password = request.form.get('password', '').strip()
    content = request.form.get('content', '').strip()
    article_id = request.form.get('article_id', 0, type=int)

    if not content:
        flash('댓글 내용을 입력하세요.', 'error')
        return redirect(url_for('public.article_view', idxno=article_id) + '#comment')

    comment = ArticleComment.query.get_or_404(comment_id)

    # 권한 확인
    member_id = session.get('member_id')
    can_edit = False
    if comment.member_id and comment.member_id == member_id:
        can_edit = True
    elif comment.password and check_password_hash(comment.password, password):
        can_edit = True

    if not can_edit:
        flash('비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('public.article_view', idxno=article_id) + '#comment')

    # 글자수 제한
    max_length = int(_get_setting('comment_max_length', '500') or 500)
    comment.content = content[:max_length]
    db.session.commit()

    return redirect(url_for('public.article_view', idxno=article_id) + '#comment')


@public_bp.route('/banner/click/<int:banner_id>')
def banner_click(banner_id):
    """배너 클릭 추적 후 링크로 리다이렉트"""
    banner = Banner.query.get_or_404(banner_id)
    banner.click_count += 1
    db.session.commit()
    return redirect(banner.link_url or '/')


# ===== 정보 페이지 (Company/Info) =====

COM_PAGES = {
    'com-1':       {'title': '인사말',             'group': '매체소개',    'content': 'com/company.html'},
    'com-2':       {'title': '찾아오시는길',       'group': '매체소개',    'content': 'com/map.html'},
    'service':     {'title': '이용약관',           'group': '약관 및 정책', 'content': 'com/service.html'},
    'privacy':     {'title': '개인정보처리방침',   'group': '약관 및 정책', 'content': 'com/privacy.html'},
    'youthpolicy': {'title': '청소년보호정책',     'group': '약관 및 정책', 'content': 'com/youthpolicy.html'},
    'copyright':   {'title': '저작권보호정책',     'group': '약관 및 정책', 'content': 'com/copyright.html'},
    'emailno':     {'title': '이메일무단수집거부', 'group': '약관 및 정책', 'content': 'com/emailno.html'},
    'ad':          {'title': '광고문의',           'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event1'},
    'jb':          {'title': '기사제보',           'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event4'},
    'kd':          {'title': '구독신청',           'group': '고객센터',    'content': 'com/event_kd.html',   'event_code': 'event5'},
    'copy':        {'title': '저작권문의',         'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event3'},
    'bp':          {'title': '불편신고',           'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event6'},
    'tg':          {'title': '독자투고',           'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event7'},
    'jh':          {'title': '제휴문의',           'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event2'},
}

COM_NAV = [
    {'group': '매체소개', 'links': [
        {'code': 'com-1', 'title': '인사말'},
        {'code': 'com-2', 'title': '찾아오시는길'},
    ]},
    {'group': '약관 및 정책', 'links': [
        {'code': 'service', 'title': '이용약관'},
        {'code': 'privacy', 'title': '개인정보처리방침'},
        {'code': 'youthpolicy', 'title': '청소년보호정책'},
        {'code': 'copyright', 'title': '저작권보호정책'},
        {'code': 'emailno', 'title': '이메일무단수집거부'},
    ]},
    {'group': '고객센터', 'links': [
        {'code': 'jb', 'title': '기사제보'},
        {'code': 'kd', 'title': '구독신청'},
        {'code': 'ad', 'title': '광고문의'},
        {'code': 'bp', 'title': '불편신고'},
        {'code': 'tg', 'title': '독자투고'},
        {'code': 'jh', 'title': '제휴문의'},
        {'code': 'copy', 'title': '저작권문의'},
    ]},
]


@public_bp.route('/com/<page_code>.html')
def com_page(page_code):
    """정보 페이지 (인사말, 이용약관, 개인정보처리방침 등)"""
    page = COM_PAGES.get(page_code)
    if not page:
        abort(404)
    recaptcha_site_key = ''
    if 'event_code' in page:
        s = SiteSetting.query.filter_by(key='recaptcha_site_key').first()
        recaptcha_site_key = s.value if s and s.value else ''
    return render_template('public/com_page.html',
                           page=page, page_code=page_code, com_nav=COM_NAV,
                           recaptcha_site_key=recaptcha_site_key)


@public_bp.route('/com/event/submit', methods=['POST'])
def event_submit():
    """신청 폼 제출 처리"""
    page_code = request.form.get('page_code', '')
    page = COM_PAGES.get(page_code)
    if not page or 'event_code' not in page:
        abort(400)

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('tel', '').strip()
    subject = request.form.get('subject', '').strip()
    content = request.form.get('maintext', '').strip() or request.form.get('othertext', '').strip()

    # 필수 검증
    if not name or not email or not phone:
        flash('이름, 이메일, 연락처는 필수 입력 항목입니다.', 'error')
        return redirect(url_for('public.com_page', page_code=page_code), code=303)

    # reCAPTCHA 검증
    recaptcha_secret = _get_setting('recaptcha_secret_key', '')
    if recaptcha_secret:
        import urllib.request, urllib.parse
        recaptcha_response = request.form.get('g-recaptcha-response', '')
        if not recaptcha_response:
            flash('자동등록방지(CAPTCHA)를 확인해주세요.', 'error')
            return redirect(url_for('public.com_page', page_code=page_code), code=303)
        try:
            verify_data = urllib.parse.urlencode({
                'secret': recaptcha_secret, 'response': recaptcha_response
            }).encode()
            verify_req = urllib.request.Request('https://www.google.com/recaptcha/api/siteverify',
                                                data=verify_data, method='POST')
            verify_resp = urllib.request.urlopen(verify_req, timeout=5)
            result = json.loads(verify_resp.read().decode())
            if not result.get('success'):
                flash('자동등록방지 인증에 실패했습니다. 다시 시도해주세요.', 'error')
                return redirect(url_for('public.com_page', page_code=page_code), code=303)
        except Exception:
            pass  # 검증 실패 시 통과 허용 (네트워크 오류 등)

    req = EventRequest(
        event_code=page['event_code'],
        name=name,
        email=email,
        phone=phone,
        subject=subject,
        content=content,
        ip_address=request.remote_addr,
    )

    # 기사제보 파일 첨부 (Google Drive 지원)
    if page['event_code'] == 'event4':
        import os
        from werkzeug.utils import secure_filename
        file = request.files.get('attachment')
        if file and file.filename:
            fname = secure_filename(file.filename)
            upload_dir = os.path.join('app', 'static', 'uploads', 'event')
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, f'{int(datetime.now().timestamp())}_{fname}')
            file.save(filepath)
            from app.utils.cloud_storage import upload_file
            url = upload_file(filepath, folder='welldying/attachments', resource_type='raw')
            if not url:
                flash('파일 업로드에 실패했습니다.', 'error')
                return redirect(request.referrer or '/')
            req.extra_data = json.dumps({'attachment': url, 'filename': fname}, ensure_ascii=False)

    # 구독신청 추가 필드
    if page['event_code'] == 'event5':
        extra = {
            'reqname': request.form.get('reqname', ''),
            'reqemail': request.form.get('reqemail', ''),
            'reqnum': request.form.get('reqnum', ''),
            'reqtel': request.form.get('reqtel', ''),
            'reqaddr': request.form.get('reqaddr', ''),
            'reqmoney': request.form.get('reqmoney', ''),
        }
        req.extra_data = json.dumps(extra, ensure_ascii=False)

    db.session.add(req)
    db.session.commit()

    flash('신청이 완료되었습니다. 감사합니다.', 'success')
    return redirect(url_for('public.com_page', page_code=page_code), code=303)


# ===== 게시판 (BBS) =====

@public_bp.route('/bbs/list.html')
def bbs_list():
    table = request.args.get('table', '')
    page = request.args.get('page', 1, type=int)
    sc_area = request.args.get('sc_area', 'T')
    sc_word = request.args.get('sc_word', '').strip()

    board = Board.query.filter_by(code=table, is_active=True).first()
    if not board:
        # table 파라미터 없으면 첫 번째 활성 게시판
        board = Board.query.filter_by(is_active=True).order_by(Board.sort_order).first()
        if not board:
            abort(404)

    query = BoardPost.query.filter_by(board_id=board.id, is_hidden=False)

    if sc_word:
        if sc_area == 'T':
            query = query.filter(BoardPost.title.contains(sc_word))
        elif sc_area == 'C':
            query = query.filter(BoardPost.content.contains(sc_word))
        elif sc_area == 'A':
            query = query.filter(
                db.or_(BoardPost.title.contains(sc_word), BoardPost.content.contains(sc_word))
            )
        elif sc_area == 'N':
            query = query.filter(BoardPost.author_name.contains(sc_word))

    pagination = query.order_by(BoardPost.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    # 전체 글 수 기반 번호 계산용
    total = pagination.total

    return render_template('public/bbs_list.html',
                           board=board,
                           posts=pagination.items,
                           pagination=pagination,
                           total=total,
                           sc_area=sc_area,
                           sc_word=sc_word)


@public_bp.route('/bbs/view.html')
def bbs_view():
    idxno = request.args.get('idxno', 0, type=int)
    if not idxno:
        abort(404)

    post = BoardPost.query.get_or_404(idxno)
    if post.is_hidden:
        abort(404)

    # 비밀글 접근 확인
    if post.is_secret and not session.get(f'bbs_secret_{post.id}'):
        return render_template('public/bbs_secret.html', post=post, board=post.board)

    # 조회수 증가
    post.view_count += 1
    db.session.commit()

    # 댓글 정렬
    reply_sort = request.args.get('reply_sort', 'newest')
    if reply_sort == 'oldest':
        order = BoardReply.created_at.asc()
    else:
        order = BoardReply.created_at.desc()

    # 상위 댓글만 (parent_id IS NULL)
    replies = post.replies.filter_by(is_hidden=False, parent_id=None).order_by(order).all()

    # BEST 댓글 (좋아요 3개 이상, 상위 3개)
    best_replies = post.replies.filter(
        BoardReply.is_hidden == False,
        BoardReply.parent_id == None,
        BoardReply.like_count >= 3
    ).order_by(BoardReply.like_count.desc()).limit(3).all()

    reply_count = post.replies.filter_by(is_hidden=False).count()

    # 이전/다음 글
    prev_post = BoardPost.query.filter(
        BoardPost.board_id == post.board_id,
        BoardPost.is_hidden == False,  # noqa: E712
        BoardPost.id < post.id
    ).order_by(BoardPost.id.desc()).first()
    next_post = BoardPost.query.filter(
        BoardPost.board_id == post.board_id,
        BoardPost.is_hidden == False,  # noqa: E712
        BoardPost.id > post.id
    ).order_by(BoardPost.id.asc()).first()

    # 로그인 회원 정보
    member = None
    member_id = session.get('member_id')
    if member_id:
        member = Member.query.get(member_id)

    return render_template('public/bbs_view.html',
                           board=post.board,
                           post=post,
                           replies=replies,
                           best_replies=best_replies,
                           reply_count=reply_count,
                           reply_sort=reply_sort,
                           member=member,
                           prev_post=prev_post,
                           next_post=next_post)


@public_bp.route('/bbs/writeForm.html')
def bbs_write_form():
    table = request.args.get('table', '')
    board = Board.query.filter_by(code=table, is_active=True).first()
    if not board:
        abort(404)
    # 답글 모드
    reply_to = request.args.get('reply_to', 0, type=int)
    parent_post = BoardPost.query.get(reply_to) if reply_to else None
    return render_template('public/bbs_write.html', board=board, parent_post=parent_post)


@public_bp.route('/bbs/write', methods=['POST'])
def bbs_write():
    table = request.form.get('table', '')
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    author_name = request.form.get('author_name', '').strip()
    password = request.form.get('password', '').strip()

    board = Board.query.filter_by(code=table, is_active=True).first()
    if not board:
        abort(404)

    if not title or not content:
        flash('제목과 내용을 입력해주세요.', 'error')
        return redirect(url_for('public.bbs_write_form', table=table))

    is_secret = request.form.get('is_secret') == '1'
    parent_post_id = request.form.get('parent_post_id', 0, type=int) or None

    # 로그인 회원이면 member_id 연동
    member_id = session.get('member_id')
    current_member = Member.query.get(member_id) if member_id else None

    post = BoardPost(
        board_id=board.id,
        parent_post_id=parent_post_id,
        title=title,
        content=content,
        author_name=current_member.name if current_member else (author_name or '익명'),
        password='' if current_member else (generate_password_hash(password) if password else ''),
        member_id=current_member.id if current_member else None,
        is_secret=is_secret
    )
    db.session.add(post)
    db.session.commit()

    return redirect(url_for('public.bbs_view', idxno=post.id))


@public_bp.route('/bbs/delete', methods=['POST'])
def bbs_delete():
    post_id = request.form.get('post_id', 0, type=int)
    password = request.form.get('password', '').strip()

    post = BoardPost.query.get_or_404(post_id)
    table = post.board.code

    # 로그인 회원 본인이면 비밀번호 불필요
    member_id = session.get('member_id')
    is_owner = post.member_id and member_id and post.member_id == member_id
    if not is_owner:
        if not post.password or not check_password_hash(post.password, password):
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return redirect(url_for('public.bbs_view', idxno=post_id))

    # 댓글도 함께 삭제
    BoardReply.query.filter_by(post_id=post.id).delete()
    db.session.delete(post)
    db.session.commit()

    return redirect(url_for('public.bbs_list', table=table))


@public_bp.route('/bbs/secret/verify', methods=['POST'])
def bbs_secret_verify():
    """비밀글 비밀번호 확인"""
    post_id = request.form.get('post_id', 0, type=int)
    password = request.form.get('password', '').strip()

    post = BoardPost.query.get_or_404(post_id)

    if not post.password or not check_password_hash(post.password, password):
        flash('비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('public.bbs_view', idxno=post_id))

    session[f'bbs_secret_{post_id}'] = True
    return redirect(url_for('public.bbs_view', idxno=post_id))


@public_bp.route('/bbs/edit/verify', methods=['POST'])
def bbs_edit_verify():
    """글 수정 비밀번호 확인 → 수정 폼으로 이동"""
    post_id = request.form.get('post_id', 0, type=int)
    password = request.form.get('password', '').strip()

    post = BoardPost.query.get_or_404(post_id)

    # 로그인 회원 본인이면 비밀번호 불필요
    member_id = session.get('member_id')
    is_owner = post.member_id and member_id and post.member_id == member_id
    if not is_owner:
        if not post.password or not check_password_hash(post.password, password):
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return redirect(url_for('public.bbs_view', idxno=post_id))

    # 비밀번호 확인 완료 → 세션에 수정 허가 저장
    session[f'bbs_edit_{post_id}'] = True
    return redirect(url_for('public.bbs_edit_form', post_id=post_id))


@public_bp.route('/bbs/editForm.html')
def bbs_edit_form():
    post_id = request.args.get('post_id', 0, type=int)
    post = BoardPost.query.get_or_404(post_id)

    if not session.get(f'bbs_edit_{post_id}'):
        flash('수정 권한이 없습니다.', 'error')
        return redirect(url_for('public.bbs_view', idxno=post_id))

    return render_template('public/bbs_write.html', board=post.board, edit_post=post)


@public_bp.route('/bbs/edit/<int:post_id>', methods=['POST'])
def bbs_edit(post_id):
    post = BoardPost.query.get_or_404(post_id)

    if not session.pop(f'bbs_edit_{post_id}', None):
        flash('수정 권한이 없습니다.', 'error')
        return redirect(url_for('public.bbs_view', idxno=post_id))

    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()

    if not title or not content:
        flash('제목과 내용을 입력해주세요.', 'error')
        session[f'bbs_edit_{post_id}'] = True
        return redirect(url_for('public.bbs_edit_form', post_id=post_id))

    post.title = title
    post.content = content
    db.session.commit()

    flash('글이 수정되었습니다.', 'success')
    return redirect(url_for('public.bbs_view', idxno=post_id))


@public_bp.route('/bbs/reply/write', methods=['POST'])
def bbs_reply_write():
    post_id = request.form.get('post_id', 0, type=int)
    parent_id = request.form.get('parent_id', 0, type=int) or None
    author_name = request.form.get('author_name', '').strip()
    password = request.form.get('password', '').strip()
    content = request.form.get('content', '').strip()

    post = BoardPost.query.get_or_404(post_id)

    if not content:
        flash('댓글 내용을 입력해주세요.', 'error')
        return redirect(url_for('public.bbs_view', idxno=post_id) + '#replies')

    # 로그인 회원
    member_id = session.get('member_id')
    member = Member.query.get(member_id) if member_id else None

    reply = BoardReply(
        post_id=post_id,
        parent_id=parent_id,
        author_name=member.name if member else (author_name or '익명'),
        password=generate_password_hash(password) if password and not member else '',
        content=content,
        ip_address=request.remote_addr,
        member_id=member.id if member else None
    )
    db.session.add(reply)
    db.session.commit()

    return redirect(url_for('public.bbs_view', idxno=post_id) + '#replies')


@public_bp.route('/bbs/reply/delete', methods=['POST'])
def bbs_reply_delete():
    reply_id = request.form.get('reply_id', 0, type=int)
    password = request.form.get('password', '').strip()
    post_id = request.form.get('post_id', 0, type=int)

    reply = BoardReply.query.get_or_404(reply_id)

    # 회원 본인 삭제
    member_id = session.get('member_id')
    if reply.member_id and member_id and reply.member_id == member_id:
        pass  # OK
    elif reply.password and check_password_hash(reply.password, password):
        pass  # OK
    else:
        flash('비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('public.bbs_view', idxno=post_id) + '#replies')

    # 자식 댓글 + 투표 삭제
    for child in reply.children.all():
        BoardReplyVote.query.filter_by(reply_id=child.id).delete()
        db.session.delete(child)
    BoardReplyVote.query.filter_by(reply_id=reply.id).delete()
    db.session.delete(reply)
    db.session.commit()

    return redirect(url_for('public.bbs_view', idxno=post_id) + '#replies')


@public_bp.route('/bbs/reply/vote', methods=['POST'])
def bbs_reply_vote():
    from flask import jsonify
    reply_id = request.form.get('reply_id', 0, type=int)
    vote_type = request.form.get('vote_type', '')
    if vote_type not in ('like', 'dislike'):
        return jsonify({'error': 'invalid'}), 400

    reply = BoardReply.query.get_or_404(reply_id)
    ip = request.remote_addr
    member_id = session.get('member_id')

    existing = BoardReplyVote.query.filter_by(reply_id=reply_id, vote_type=vote_type)
    if member_id:
        existing = existing.filter_by(member_id=member_id)
    else:
        existing = existing.filter_by(ip_address=ip)
    if existing.first():
        return jsonify({'error': 'already_voted', 'like': reply.like_count, 'dislike': reply.dislike_count})

    vote = BoardReplyVote(reply_id=reply_id, ip_address=ip,
                          member_id=member_id, vote_type=vote_type)
    db.session.add(vote)
    if vote_type == 'like':
        reply.like_count = (reply.like_count or 0) + 1
    else:
        reply.dislike_count = (reply.dislike_count or 0) + 1
    db.session.commit()
    return jsonify({'like': reply.like_count, 'dislike': reply.dislike_count})


@public_bp.route('/bbs/reply/edit', methods=['POST'])
def bbs_reply_edit():
    from flask import jsonify
    reply_id = request.form.get('reply_id', 0, type=int)
    content = request.form.get('content', '').strip()
    password = request.form.get('password', '').strip()

    reply = BoardReply.query.get_or_404(reply_id)

    # 권한 확인
    member_id = session.get('member_id')
    if reply.member_id and member_id and reply.member_id == member_id:
        pass  # OK
    elif reply.password and check_password_hash(reply.password, password):
        pass  # OK
    else:
        return jsonify({'error': '비밀번호가 일치하지 않습니다.'}), 403

    if not content:
        return jsonify({'error': '내용을 입력하세요.'}), 400

    reply.content = content
    db.session.commit()
    return jsonify({'ok': True, 'content': content})


# ─── 설문조사 ───────────────────────────────────────────────

@public_bp.route('/poll/pollView.html')
def poll_view():
    from datetime import datetime
    poll_id = request.args.get('id', 0, type=int)
    if poll_id:
        poll = Poll.query.get_or_404(poll_id)
    else:
        poll = Poll.query.filter_by(is_active=True).order_by(Poll.created_at.desc()).first()
    if not poll:
        abort(404)
    options = poll.options.order_by(PollOption.sort_order).all()
    total_votes = sum(o.vote_count for o in options)
    voted = request.cookies.get(f'poll_voted_{poll.id}')
    show_result = request.args.get('result', 0, type=int)
    return render_template('public/poll.html',
                           poll=poll, options=options,
                           total_votes=total_votes,
                           voted=voted or show_result,
                           now=datetime.now())


@public_bp.route('/poll/vote', methods=['POST'])
def poll_vote():
    poll_id = request.form.get('poll_id', 0, type=int)
    poll = Poll.query.get_or_404(poll_id)

    if request.cookies.get(f'poll_voted_{poll.id}'):
        flash('이미 투표하셨습니다.', 'error')
        resp = redirect(url_for('public.poll_view', id=poll.id))
        return resp

    if poll.is_multiple:
        option_ids = request.form.getlist('option_id', type=int)
    else:
        oid = request.form.get('option_id', 0, type=int)
        option_ids = [oid] if oid else []

    for oid in option_ids:
        opt = PollOption.query.get(oid)
        if opt and opt.poll_id == poll.id:
            opt.vote_count += 1

    db.session.commit()

    resp = redirect(url_for('public.poll_view', id=poll.id))
    resp.set_cookie(f'poll_voted_{poll.id}', 'y', max_age=60*60*24*365)
    return resp


# ─── 회원가입/로그인 ──────────────────────────────────────────

@public_bp.route('/member/')
def member_index():
    """회원가입 1단계: 회원 유형 선택"""
    return render_template('public/member_index.html')


@public_bp.route('/member/memberAgree.html', methods=['GET', 'POST'])
def member_agree():
    """회원가입 2단계: 이용약관 동의"""
    if request.method == 'POST':
        check1 = request.form.get('check1')
        check2 = request.form.get('check2')
        if check1 != 'Y' or check2 != 'Y':
            flash('필수 약관에 동의해주세요.', 'error')
            return redirect(url_for('public.member_agree', kind='member'))
        session['member_agree'] = True
        return redirect(url_for('public.member_register'))
    return render_template('public/member_agree.html')


@public_bp.route('/member/register.html', methods=['GET', 'POST'])
def member_register():
    """회원가입 3단계: 회원정보 입력"""
    if not session.get('member_agree'):
        return redirect(url_for('public.member_index'))

    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '').strip()
        password2 = request.form.get('password2', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()

        if not user_id or not password or not name:
            flash('아이디, 비밀번호, 이름은 필수입니다.', 'error')
            return redirect(url_for('public.member_register'))
        if password != password2:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return redirect(url_for('public.member_register'))
        if len(user_id) < 4:
            flash('아이디는 4자 이상이어야 합니다.', 'error')
            return redirect(url_for('public.member_register'))
        if Member.query.filter_by(user_id=user_id).first():
            flash('이미 사용 중인 아이디입니다.', 'error')
            return redirect(url_for('public.member_register'))

        member = Member(
            user_id=user_id,
            password_hash=generate_password_hash(password),
            name=name,
            email=email,
            phone=phone,
        )
        db.session.add(member)
        db.session.commit()
        session.pop('member_agree', None)

        flash('회원가입이 완료되었습니다. 로그인해주세요.', 'success')
        return redirect(url_for('public.member_login'))

    return render_template('public/member_register.html')


@public_bp.route('/member/login.html', methods=['GET', 'POST'])
def member_login():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '').strip()

        member = Member.query.filter_by(user_id=user_id).first()
        if not member or not check_password_hash(member.password_hash, password):
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'error')
            return redirect(url_for('public.member_login'))
        if not member.is_active:
            flash('비활성화된 계정입니다.', 'error')
            return redirect(url_for('public.member_login'))

        session['member_id'] = member.id
        flash(f'{member.name}님, 환영합니다!', 'success')
        next_url = request.args.get('next', url_for('public.index'))
        return redirect(next_url)

    return render_template('public/member_login.html')


@public_bp.route('/member/logout')
def member_logout():
    session.pop('member_id', None)
    return redirect(url_for('public.index'))


@public_bp.route('/member/mypage.html')
def member_mypage():
    if not session.get('member_id'):
        return redirect(url_for('public.member_login'))
    member = Member.query.get_or_404(session['member_id'])
    return render_template('public/member_mypage.html', member=member)


@public_bp.route('/member/mypage/update', methods=['POST'])
def member_update():
    if not session.get('member_id'):
        return redirect(url_for('public.member_login'))
    member = Member.query.get_or_404(session['member_id'])

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    new_password = request.form.get('new_password', '').strip()

    if name:
        member.name = name
    member.email = email
    member.phone = phone

    if new_password:
        member.password_hash = generate_password_hash(new_password)

    # 프로필 이미지 업로드 (Cloudinary 지원)
    profile_file = request.files.get('profile_image')
    if profile_file and profile_file.filename:
        import os, uuid
        from werkzeug.utils import secure_filename as sf
        ext = profile_file.filename.rsplit('.', 1)[-1].lower()
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            fname = f"profile_{uuid.uuid4().hex}.{ext}"
            upload_dir = os.path.join('app', 'static', 'uploads', 'profile')
            os.makedirs(upload_dir, exist_ok=True)
            local_path = os.path.join(upload_dir, fname)
            profile_file.save(local_path)
            from app.utils.cloud_storage import upload_file
            url = upload_file(local_path, folder='welldying/profiles')
            if not url:
                flash('프로필 이미지 업로드에 실패했습니다.', 'error')
                return redirect(url_for('public.member_mypage'))
            member.profile_image = url

    db.session.commit()
    flash('회원정보가 수정되었습니다.', 'success')
    return redirect(url_for('public.member_mypage'))
