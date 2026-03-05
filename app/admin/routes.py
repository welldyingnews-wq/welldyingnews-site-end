import json
import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (render_template, request, redirect, url_for, flash,
                   jsonify, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app import limiter
from app.admin import admin_bp
from app.models import (db, AdminUser, Section, SubSection, Article, ArticleRelation,
                        ArticleDraft, SiteSetting, ArticleComment, Board, BoardPost,
                        BoardReply, EventRequest, Banner, Popup, Poll, PollOption,
                        SerialCode, Department, MemberDivision, EtcLevel, LayoutBlock,
                        Member, MemberLog, DailyStat, PageView, VisitorLog, Photo,
                        Schedule, Newsletter, AiDraft)
from app.services.ai_draft import (
    STATUS_PENDING, STATUS_PUBLISHED, STATUS_REJECTED, STALE_STATUSES,
)


ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif', 'tiff', 'avif'}
ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'ogg', 'mov'}
ALLOWED_EXT = ALLOWED_IMAGE_EXT | ALLOWED_VIDEO_EXT | {'pdf', 'doc', 'docx', 'hwp', 'hwpx', 'zip'}


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        user_id = request.form.get('user_id', '')
        user_pw = request.form.get('user_pw', '')
        user = AdminUser.query.filter_by(user_id=user_id).first()
        if user and check_password_hash(user.password_hash, user_pw):
            login_user(user)
            return redirect(url_for('admin.dashboard'))
        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'error')

    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@admin_required
def dashboard():
    total_articles = Article.query.filter_by(is_deleted=False).count()
    unapproved = Article.query.filter_by(is_deleted=False, recognition='C').count()
    embargo_count = Article.query.filter(
        Article.is_deleted == False,  # noqa: E712
        Article.embargo_date != None,  # noqa: E711
        Article.embargo_date > datetime.now()
    ).count()
    deleted_count = Article.query.filter_by(is_deleted=True).count()
    restored_count = 0  # 복원 기사 (별도 추적 없으므로 0)

    comment_count = ArticleComment.query.count()
    post_count = BoardPost.query.count()
    post_reply_count = BoardReply.query.count()
    member_count = Member.query.count()
    dormant_count = AdminUser.query.filter_by(is_dormant=True).count()

    # 미승인 기사
    unapproved_articles = Article.query.filter_by(
        is_deleted=False, recognition='C'
    ).order_by(Article.created_at.desc()).limit(10).all()

    # 예약 기사
    embargo_articles = Article.query.filter(
        Article.is_deleted == False,
        Article.embargo_date != None,
        Article.embargo_date > datetime.now()
    ).order_by(Article.created_at.desc()).limit(10).all()

    # 최근 등록 기사 (노출시간 기준)
    recent_articles = Article.query.filter_by(is_deleted=False).order_by(
        db.func.coalesce(Article.embargo_date, Article.created_at).desc()
    ).limit(10).all()

    # 일자별 PV/UV 데이터 (최근 31일) - DailyStat 테이블 기반
    today = datetime.now().date()
    pv_labels = []
    pv_data = []
    visitor_data = []
    date_list = [today - timedelta(days=i) for i in range(30, -1, -1)]
    stats_map = {}
    for s in DailyStat.query.filter(DailyStat.date >= date_list[0]).all():
        stats_map[s.date] = s
    for d in date_list:
        pv_labels.append(d.strftime('%m.%d'))
        s = stats_map.get(d)
        pv_data.append(s.page_views if s else 0)
        visitor_data.append(s.unique_visitors if s else 0)

    # 페이지별 PV (최근 7일 실제 집계)
    seven_days_ago = today - timedelta(days=7)
    top_articles_pv = db.session.query(
        PageView.article_id,
        db.func.sum(PageView.view_count).label('total_pv'),
        db.func.sum(PageView.unique_count).label('total_uv')
    ).filter(
        PageView.date >= seven_days_ago
    ).group_by(PageView.article_id).order_by(
        db.func.sum(PageView.view_count).desc()
    ).limit(7).all()
    pv_article_ids = [row.article_id for row in top_articles_pv]
    pv_articles_map = {a.id: a for a in Article.query.filter(Article.id.in_(pv_article_ids)).all()} if pv_article_ids else {}
    top_pv_articles = []
    for row in top_articles_pv:
        art = pv_articles_map.get(row.article_id)
        if art:
            top_pv_articles.append({
                'article': art,
                'pv': row.total_pv,
                'avg': row.total_pv // 7
            })

    # 신규/재방문자 (최근 7일)
    new_visitors_7d = 0
    return_visitors_7d = 0
    for d in date_list[-7:]:
        day_ips = db.session.query(VisitorLog.ip_address).filter(
            VisitorLog.date == d, VisitorLog.article_id == None  # noqa: E711
        ).all()
        for (ip,) in day_ips:
            prev = VisitorLog.query.filter(
                VisitorLog.ip_address == ip,
                VisitorLog.date < d,
                VisitorLog.article_id == None  # noqa: E711
            ).first()
            if prev:
                return_visitors_7d += 1
            else:
                new_visitors_7d += 1

    # 디바이스별 통계 (최근 7일)
    device_stats = db.session.query(
        VisitorLog.user_agent, db.func.count(VisitorLog.id)
    ).filter(
        VisitorLog.date >= seven_days_ago,
        VisitorLog.article_id == None  # noqa: E711
    ).group_by(VisitorLog.user_agent).all()
    device_map = {d: c for d, c in device_stats}

    # 유입경로별 통계 (최근 7일)
    referrer_stats = db.session.query(
        VisitorLog.referrer_source, db.func.count(VisitorLog.id)
    ).filter(
        VisitorLog.date >= seven_days_ago,
        VisitorLog.article_id == None  # noqa: E711
    ).group_by(VisitorLog.referrer_source).all()
    referrer_map = {r: c for r, c in referrer_stats}

    # 유입경로 x 디바이스 교차분석 (최근 7일)
    cross_stats = db.session.query(
        VisitorLog.referrer_source, VisitorLog.user_agent, db.func.count(VisitorLog.id)
    ).filter(
        VisitorLog.date >= seven_days_ago,
        VisitorLog.article_id == None  # noqa: E711
    ).group_by(VisitorLog.referrer_source, VisitorLog.user_agent).all()
    cross_map = {}
    for ref, dev, cnt in cross_stats:
        if ref not in cross_map:
            cross_map[ref] = {}
        cross_map[ref][dev] = cnt

    # 구독/제보/저작권 신청 수
    subscribe_count = EventRequest.query.filter_by(event_code='event5', is_processed=False).count()
    report_count = EventRequest.query.filter_by(event_code='event4', is_processed=False).count()
    copyright_count = EventRequest.query.filter_by(event_code='event3', is_processed=False).count()

    # 최근 댓글
    recent_comments = ArticleComment.query.order_by(
        ArticleComment.created_at.desc()
    ).limit(5).all()

    # 최근 게시판 댓글
    recent_replies = BoardReply.query.order_by(
        BoardReply.created_at.desc()
    ).limit(5).all()

    # 최근 신청
    recent_requests = EventRequest.query.filter_by(
        is_processed=False
    ).order_by(EventRequest.created_at.desc()).limit(5).all()

    # 현재 편집 설정 상태 (대시보드 빠른 편집 미리보기)
    hero_preview = []
    for i in range(1, 5):
        setting = SiteSetting.query.filter_by(key=f'hero_slot_{i}').first()
        if setting and setting.value and setting.value.strip().isdigit():
            art = db.session.get(Article, int(setting.value))
            if art:
                hero_preview.append(art)

    featured_preview = []
    featured_setting = SiteSetting.query.filter_by(key='featured_article_ids').first()
    if featured_setting and featured_setting.value:
        for aid in featured_setting.value.split(',')[:4]:
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art:
                    featured_preview.append(art)

    popular_preview = []
    popular_setting = SiteSetting.query.filter_by(key='popular_article_ids').first()
    if popular_setting and popular_setting.value:
        for aid in popular_setting.value.split(',')[:3]:
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art:
                    popular_preview.append(art)

    return render_template('admin/dashboard.html',
                           total_articles=total_articles,
                           unapproved=unapproved,
                           embargo_count=embargo_count,
                           deleted_count=deleted_count,
                           restored_count=restored_count,
                           comment_count=comment_count,
                           post_count=post_count,
                           post_reply_count=post_reply_count,
                           member_count=member_count,
                           dormant_count=dormant_count,
                           unapproved_articles=unapproved_articles,
                           embargo_articles=embargo_articles,
                           recent_articles=recent_articles,
                           pv_labels=pv_labels,
                           pv_data=pv_data,
                           visitor_data=visitor_data,
                           top_pv_articles=top_pv_articles,
                           new_visitors_7d=new_visitors_7d,
                           return_visitors_7d=return_visitors_7d,
                           device_map=device_map,
                           subscribe_count=subscribe_count,
                           report_count=report_count,
                           copyright_count=copyright_count,
                           recent_comments=recent_comments,
                           recent_replies=recent_replies,
                           recent_requests=recent_requests,
                           hero_preview=hero_preview,
                           featured_preview=featured_preview,
                           popular_preview=popular_preview,
                           referrer_map=referrer_map,
                           cross_map=cross_map)


@admin_bp.route('/article/new', methods=['GET', 'POST'])
@admin_required
def article_new():
    if request.method == 'POST':
        return _save_article(None)

    sections = Section.query.order_by(Section.sort_order).all()
    serial_codes = SerialCode.query.filter_by(is_active=True).all()
    draft_id = request.args.get('draft_id', 0, type=int)
    return render_template('admin/article_form.html', article=None, sections=sections,
                           serial_codes=serial_codes, draft_id=draft_id)


@admin_bp.route('/article/<int:article_id>/edit', methods=['GET', 'POST'])
@admin_required
def article_edit(article_id):
    article = Article.query.get_or_404(article_id)

    if request.method == 'POST':
        return _save_article(article)

    sections = Section.query.order_by(Section.sort_order).all()
    serial_codes = SerialCode.query.filter_by(is_active=True).all()
    related_articles = ArticleRelation.query.filter_by(
        article_id=article.id
    ).order_by(ArticleRelation.sort_order).all()
    return render_template('admin/article_form.html', article=article,
                           sections=sections, serial_codes=serial_codes,
                           related_articles=related_articles)


def _save_article(article):
    is_new = article is None
    if is_new:
        article = Article()

    article.title = request.form.get('title', '').strip()
    if not article.title:
        flash('제목을 입력하세요.', 'error')
        sections = Section.query.order_by(Section.sort_order).all()
        return render_template('admin/article_form.html', article=article, sections=sections)

    article.subtitle = request.form.get('subtitle', '')
    article.content = request.form.get('content', '')
    article.summary = request.form.get('summary', '')
    article.keyword = request.form.get('keyword', '')
    article.author_name = request.form.get('author_name', '웰다잉뉴스')
    article.author_email = request.form.get('author_email', 'welldyingnews@naver.com')
    article.author_title = request.form.get('author_title', '')
    article.author_affiliation = request.form.get('author_affiliation', '')
    article.level = request.form.get('level', 'B')
    article.recognition = request.form.get('recognition', 'E')
    article.article_type = request.form.get('article_type', 'B')
    article.source = request.form.get('source', '')
    article.photo_caption = request.form.get('photo_caption', '')

    serial_code_id = request.form.get('serial_code_id')
    article.serial_code_id = int(serial_code_id) if serial_code_id else None

    section_id = request.form.get('section_id')
    subsection_id = request.form.get('subsection_id')
    article.section_id = int(section_id) if section_id else None
    article.subsection_id = int(subsection_id) if subsection_id else None

    embargo_date = request.form.get('embargo_date', '').strip()
    embargo_time = request.form.get('embargo_time', '').strip()
    if embargo_date:
        dt_str = f"{embargo_date} {embargo_time}" if embargo_time else f"{embargo_date} 00:00"
        try:
            article.embargo_date = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
        except ValueError:
            article.embargo_date = None
    else:
        article.embargo_date = None

    # 썸네일 업로드
    thumbnail = request.files.get('thumbnail')
    if thumbnail and thumbnail.filename:
        from app.utils.cloud_storage import upload_file
        filename = f"{uuid.uuid4().hex}_{secure_filename(thumbnail.filename)}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        thumbnail.save(filepath)
        url = upload_file(filepath, folder='welldying/thumbnails')
        if not url:
            flash('썸네일 업로드에 실패했습니다.', 'error')
        else:
            article.thumbnail_path = url

    # 필진 프로필 사진
    if request.form.get('delete_author_photo') == '1':
        article.author_photo = ''
    author_photo = request.files.get('author_photo')
    if author_photo and author_photo.filename:
        from app.utils.cloud_storage import upload_file as upload_author
        ap_filename = f"{uuid.uuid4().hex}_{secure_filename(author_photo.filename)}"
        ap_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], ap_filename)
        author_photo.save(ap_filepath)
        ap_url = upload_author(ap_filepath, folder='welldying/authors')
        if ap_url:
            article.author_photo = ap_url
    # 프로필 사진 크롭 위치
    photo_pos = request.form.get('author_photo_pos', '').strip()
    if photo_pos:
        article.author_photo_pos = photo_pos

    # [Bug 4 fix] 동일 datetime 객체를 사용하여 created_at/updated_at 비교 시 오차 방지
    now = datetime.now()
    article.updated_at = now
    if is_new:
        article.created_at = now
        db.session.add(article)

    # [Bug 1 fix] 엠바고 날짜가 설정되면 created_at을 엠바고 날짜로 갱신 (is_new 이후에 덮어쓰기)
    # → 기사가 날짜순으로 재정렬되도록 보장
    if article.embargo_date:
        article.created_at = article.embargo_date

    db.session.flush()  # article.id 확보

    # 관련기사 저장
    ArticleRelation.query.filter_by(article_id=article.id).delete()
    related_ids = request.form.getlist('related_ids[]')
    for i, rid in enumerate(related_ids):
        try:
            rid = int(rid)
        except (ValueError, TypeError):
            continue
        if rid != article.id:
            db.session.add(ArticleRelation(
                article_id=article.id,
                related_article_id=rid,
                sort_order=i
            ))

    # 추가 섹션 저장 (다중 섹션 게재)
    extra_section_ids = request.form.getlist('extra_section_ids')
    article.extra_sections.clear()
    for sid in extra_section_ids:
        try:
            sec = db.session.get(Section, int(sid))
            if sec:
                article.extra_sections.append(sec)
        except (ValueError, TypeError):
            continue

    # 추가 2차 섹션 저장
    extra_subsection_ids = request.form.getlist('extra_subsection_ids')
    article.extra_subsections.clear()
    for sid in extra_subsection_ids:
        try:
            sub = db.session.get(SubSection, int(sid))
            if sub:
                article.extra_subsections.append(sub)
        except (ValueError, TypeError):
            continue

    db.session.commit()
    flash('기사가 저장되었습니다.', 'success')
    # [Feature 3] 저장 후 기사 목록으로 이동
    return redirect(url_for('admin.article_list'))


@admin_bp.route('/articles')
@admin_required
def article_list():
    from datetime import timedelta

    page = request.args.get('page', 1, type=int)
    per_page = 20
    show_deleted = request.args.get('deleted', '0') == '1'

    # 검색 파라미터
    sc_section_code = request.args.get('sc_section_code', '')
    sc_area = request.args.get('sc_area', 'A')
    sc_level = request.args.get('sc_level', '')
    sc_article_type = request.args.get('sc_article_type', '')
    sc_user_name = request.args.get('sc_user_name', '').strip()
    sc_word = request.args.get('sc_word', '').strip()
    sc_word2 = request.args.get('sc_word2', '').strip()
    sc_andor = request.args.get('sc_andor', 'OR')
    sc_sdate = request.args.get('sc_sdate', '')
    sc_edate = request.args.get('sc_edate', '')
    sc_order_by = request.args.get('sc_order_by', 'E')

    # 하위 호환 (이전 q 파라미터 지원)
    q = request.args.get('q', '').strip()
    section_id = request.args.get('section_id', '')
    recognition = request.args.get('recognition', '')

    query = Article.query
    if show_deleted:
        query = query.filter_by(is_deleted=True)
    else:
        query = query.filter_by(is_deleted=False)

    # 섹션 필터
    if sc_section_code:
        try:
            query = query.filter_by(section_id=int(sc_section_code))
        except (ValueError, TypeError):
            sec = Section.query.filter_by(code=sc_section_code).first()
            if sec:
                query = query.filter_by(section_id=sec.id)
    elif section_id:
        try:
            query = query.filter_by(section_id=int(section_id))
        except (ValueError, TypeError):
            pass

    # 등급 필터
    if sc_level:
        query = query.filter_by(level=sc_level)
    # 형태 필터
    if sc_article_type:
        query = query.filter_by(article_type=sc_article_type)
    # 승인상태
    if recognition:
        query = query.filter_by(recognition=recognition)
    # 기자명
    if sc_user_name:
        query = query.filter(Article.author_name.contains(sc_user_name))

    # 검색어
    def _word_filter(word, area):
        if area == 'T':
            return db.or_(Article.title.contains(word), Article.subtitle.contains(word))
        elif area == 'B':
            return Article.content.contains(word)
        else:
            return db.or_(Article.title.contains(word), Article.content.contains(word))

    if sc_word:
        if sc_word2:
            f1 = _word_filter(sc_word, sc_area)
            f2 = _word_filter(sc_word2, sc_area)
            if sc_andor == 'AND':
                query = query.filter(f1).filter(f2)
            else:
                query = query.filter(db.or_(f1, f2))
        else:
            query = query.filter(_word_filter(sc_word, sc_area))
    elif q:
        query = query.filter(db.or_(Article.title.contains(q), Article.content.contains(q)))

    # 날짜 범위
    if sc_sdate:
        try:
            query = query.filter(Article.created_at >= datetime.strptime(sc_sdate, '%Y-%m-%d'))
        except ValueError:
            pass
    if sc_edate:
        try:
            query = query.filter(Article.created_at < datetime.strptime(sc_edate, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass

    # 정렬
    if sc_order_by == 'C':
        query = query.order_by(Article.view_count.desc())
    else:
        query = query.order_by(Article.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    sections = Section.query.order_by(Section.sort_order).all()
    return render_template('admin/article_list.html',
                           articles=pagination.items,
                           pagination=pagination,
                           sections=sections,
                           q=q,
                           section_id=section_id,
                           recognition=recognition,
                           show_deleted=show_deleted,
                           sc_section_code=sc_section_code,
                           sc_area=sc_area,
                           sc_level=sc_level,
                           sc_article_type=sc_article_type,
                           sc_user_name=sc_user_name,
                           sc_word=sc_word,
                           sc_word2=sc_word2,
                           sc_andor=sc_andor,
                           sc_sdate=sc_sdate,
                           sc_edate=sc_edate,
                           sc_order_by=sc_order_by)


@admin_bp.route('/article/<int:article_id>/delete', methods=['POST'])
@admin_required
def article_delete(article_id):
    article = Article.query.get_or_404(article_id)
    article.is_deleted = True
    db.session.commit()
    flash('기사가 휴지통으로 이동되었습니다.', 'success')
    return redirect(url_for('admin.article_list'))


@admin_bp.route('/article/<int:article_id>/restore', methods=['POST'])
@admin_required
def article_restore(article_id):
    article = Article.query.get_or_404(article_id)
    article.is_deleted = False
    db.session.commit()
    flash('기사가 복원되었습니다.', 'success')
    return redirect(url_for('admin.article_list', deleted='1'))


@admin_bp.route('/article/<int:article_id>/toggle_level', methods=['POST'])
@admin_required
def article_toggle_level(article_id):
    """기사 등급 토글 (일반 ↔ 헤드라인/중요)"""
    article = Article.query.get_or_404(article_id)
    target = request.form.get('level', 'T')
    if article.level == target:
        article.level = 'B'  # 이미 해당 등급이면 일반으로
    else:
        article.level = target
    db.session.commit()
    return jsonify({'ok': True, 'level': article.level})


@admin_bp.route('/api/subsections/<int:section_id>')
@admin_required
def api_subsections(section_id):
    subs = SubSection.query.filter_by(section_id=section_id).order_by(SubSection.sort_order).all()
    return jsonify([{'id': s.id, 'code': s.code, 'name': s.name} for s in subs])


@admin_bp.route('/api/reporters')
@admin_required
def api_reporters():
    """기자 목록 API (기자 선택 팝업)"""
    users = AdminUser.query.filter_by(is_active=True).order_by(AdminUser.name).all()
    return jsonify([{'user_id': u.user_id, 'name': u.name, 'email': u.email or '', 'level': u.level} for u in users])


@admin_bp.route('/api/search-articles')
@admin_required
def api_search_articles():
    """관련기사 검색 API"""
    q = request.args.get('q', '').strip()
    exclude = request.args.get('exclude', 0, type=int)
    if not q or len(q) < 1:
        return jsonify([])
    query = Article.query.filter(
        Article.is_deleted == False,  # noqa: E712
        Article.title.contains(q)
    )
    if exclude:
        query = query.filter(Article.id != exclude)
    articles = query.order_by(Article.created_at.desc()).limit(10).all()
    return jsonify([{
        'id': a.id,
        'title': a.title,
        'created_at': a.created_at.strftime('%Y.%m.%d')
    } for a in articles])


@admin_bp.route('/find-related')
@admin_required
def find_related():
    """관련기사 검색 팝업"""
    article_id = request.args.get('article_id', 0, type=int)
    page = request.args.get('page', 1, type=int)
    sc_section_code = request.args.get('sc_section_code', '')
    sc_word = request.args.get('sc_word', '').strip()

    query = Article.query.filter_by(is_deleted=False)
    if article_id:
        query = query.filter(Article.id != article_id)
    if sc_section_code:
        query = query.filter_by(section_id=int(sc_section_code))
    if sc_word:
        query = query.filter(Article.title.contains(sc_word))

    pagination = query.order_by(Article.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    sections = Section.query.order_by(Section.sort_order).all()

    # 기존 관련기사 (initial load)
    initial_related = []
    selected_ids = set()
    if article_id:
        initial_related = ArticleRelation.query.filter_by(
            article_id=article_id
        ).order_by(ArticleRelation.sort_order).all()
        selected_ids = {r.related_article_id for r in initial_related}

    return render_template('admin/find_related.html',
                           article_id=article_id,
                           articles=pagination.items,
                           pagination=pagination,
                           sections=sections,
                           selected_ids=selected_ids,
                           initial_related=initial_related)


@admin_bp.route('/api/upload-image', methods=['POST'])
@admin_required
def upload_image():
    """CKEditor 이미지 업로드 API + 포토DB 저장"""
    from app.utils.cloud_storage import upload_file

    upload = request.files.get('upload')
    if not upload or not upload.filename:
        return jsonify({'error': {'message': '파일이 없습니다.'}}), 400

    original_name = secure_filename(upload.filename) or 'upload'
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    content_type = upload.content_type or ''

    if ext and ext not in ALLOWED_EXT:
        return jsonify({'error': {'message': f'허용되지 않는 파일 형식입니다: .{ext}'}}), 400

    filename = f"{uuid.uuid4().hex}.{ext}" if ext else f"{uuid.uuid4().hex}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    upload.save(filepath)

    is_image = ext in ALLOWED_IMAGE_EXT or content_type.startswith('image/')
    is_video = ext in ALLOWED_VIDEO_EXT or content_type.startswith('video/')

    current_app.logger.info(f'[upload] 파일: {original_name}, ext={ext}, content_type={content_type}, is_image={is_image}, is_video={is_video}')

    # 파일 업로드
    current_app.logger.info(f'[upload] 업로드 시도: {original_name}')
    resource_type = 'image' if is_image else ('video' if is_video else 'raw')
    file_size = os.path.getsize(filepath)
    url = upload_file(filepath, folder='welldying/articles', resource_type=resource_type)
    if not url:
        current_app.logger.error(f'[upload] 업로드 실패: {original_name}')
        return jsonify({'error': {'message': '파일 업로드에 실패했습니다.'}}), 500
    current_app.logger.info(f'[upload] 업로드 성공: {url}')

    # 이미지 파일이면 포토DB에 저장
    if is_image:
        photo = Photo(
            filename=filename, original_name=original_name,
            file_path=filepath, file_url=url,
            file_size=file_size,
            uploaded_by=current_user.name if current_user else ''
        )
        db.session.add(photo)
        db.session.commit()
        current_app.logger.info(f'[upload] 포토DB 저장 완료: id={photo.id}')

    current_app.logger.info(f'[upload] 응답: url={url}, is_image={is_image}, is_video={is_video}, filename={original_name}')
    return jsonify({'url': url, 'is_image': is_image, 'is_video': is_video, 'filename': original_name})


# ── 포토DB ──

@admin_bp.route('/api/photos')
@admin_required
def api_photos():
    """포토DB 목록/검색 API"""
    q = request.args.get('q', '').strip()
    fav = request.args.get('favorite', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Photo.query
    if q:
        query = query.filter(Photo.original_name.contains(q))
    if fav == '1':
        query = query.filter_by(is_favorite=True)
    query = query.order_by(Photo.created_at.desc())
    total = query.count()
    photos = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'photos': [{
            'id': p.id, 'filename': p.filename, 'original_name': p.original_name,
            'url': p.file_url, 'file_size': p.file_size,
            'is_favorite': p.is_favorite, 'uploaded_by': p.uploaded_by,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M')
        } for p in photos],
        'total': total, 'page': page, 'per_page': per_page
    })


@admin_bp.route('/api/photos/<int:photo_id>/favorite', methods=['POST'])
@admin_required
def api_photo_favorite(photo_id):
    """포토DB 즐겨찾기 토글"""
    photo = Photo.query.get_or_404(photo_id)
    photo.is_favorite = not photo.is_favorite
    db.session.commit()
    return jsonify({'ok': True, 'is_favorite': photo.is_favorite})


# ── 임시보관함 ──

@admin_bp.route('/drafts')
@admin_required
def draft_list():
    drafts = ArticleDraft.query.filter_by(admin_user_id=current_user.id).order_by(
        ArticleDraft.updated_at.desc()
    ).all()
    return render_template('admin/draft_list.html', drafts=drafts)


@admin_bp.route('/draft/save', methods=['POST'])
@admin_required
def draft_save():
    """자동저장 AJAX"""
    data = request.get_json(silent=True) or {}
    draft_id = data.get('draft_id')
    article_id = data.get('article_id')

    if draft_id:
        draft = ArticleDraft.query.filter_by(id=draft_id, admin_user_id=current_user.id).first()
    else:
        # 같은 기사의 기존 임시저장 찾기
        draft = None
        if article_id:
            draft = ArticleDraft.query.filter_by(
                admin_user_id=current_user.id, article_id=article_id
            ).first()
        if not draft:
            draft = ArticleDraft(admin_user_id=current_user.id, article_id=article_id)
            db.session.add(draft)

    draft.title = data.get('title', '')
    draft.content = data.get('content', '')
    draft.data_json = json.dumps({
        'section_id': data.get('section_id', ''),
        'author_name': data.get('author_name', ''),
        'author_email': data.get('author_email', ''),
        'level': data.get('level', 'B'),
    })
    draft.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'ok': True, 'draft_id': draft.id})


@admin_bp.route('/draft/<int:draft_id>/load')
@admin_required
def draft_load(draft_id):
    draft = ArticleDraft.query.get_or_404(draft_id)
    return jsonify({
        'id': draft.id,
        'title': draft.title,
        'content': draft.content,
        'data': json.loads(draft.data_json or '{}'),
        'updated_at': draft.updated_at.strftime('%Y-%m-%d %H:%M:%S')
    })


@admin_bp.route('/draft/<int:draft_id>/delete', methods=['POST'])
@admin_required
def draft_delete(draft_id):
    draft = ArticleDraft.query.get_or_404(draft_id)
    db.session.delete(draft)
    db.session.commit()
    flash('임시보관글이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.draft_list'))


# ── 승인관리 ──

@admin_bp.route('/articles/approval')
@admin_required
def approval():
    from datetime import timedelta

    page = request.args.get('page', 1, type=int)
    tab = request.args.get('tab', 'all')  # all, unapproved, embargo
    per_page = request.args.get('sc_list_per_page', 20, type=int)

    # 필터 파라미터
    section_id = request.args.get('sc_section_code', '')
    subsection_id = request.args.get('sc_sub_section_code', '')
    sc_level = request.args.get('sc_level', '')
    sc_article_type = request.args.get('sc_article_type', '')
    sc_area = request.args.get('sc_area', 'A')
    sc_word = request.args.get('sc_word', '').strip()
    sc_date = request.args.get('sc_date', '')
    sc_sdate = request.args.get('sc_sdate', '')
    sc_edate = request.args.get('sc_edate', '')

    query = Article.query.filter_by(is_deleted=False)

    # 탭 필터
    if tab == 'unapproved':
        query = query.filter_by(recognition='C')
    elif tab == 'embargo':
        query = query.filter(Article.embargo_date != None, Article.embargo_date > datetime.now())

    # 섹션
    if section_id:
        query = query.filter_by(section_id=int(section_id))
    if subsection_id:
        query = query.filter_by(subsection_id=int(subsection_id))
    # 등급
    if sc_level:
        query = query.filter_by(level=sc_level)
    # 형태
    if sc_article_type:
        query = query.filter_by(article_type=sc_article_type)
    # 검색어
    if sc_word:
        if sc_area == 'T':
            query = query.filter(db.or_(Article.title.contains(sc_word), Article.subtitle.contains(sc_word)))
        elif sc_area == 'B':
            query = query.filter(Article.content.contains(sc_word))
        elif sc_area == 'W':
            query = query.filter(Article.author_name.contains(sc_word))
        else:
            query = query.filter(db.or_(
                Article.title.contains(sc_word),
                Article.content.contains(sc_word),
                Article.author_name.contains(sc_word)
            ))
    # 날짜 필터
    if sc_date and sc_date != 'S':
        days = int(sc_date)
        if days > 0:
            start = datetime.now().replace(hour=0, minute=0, second=0)
            query = query.filter(Article.created_at >= start - timedelta(days=days - 1))
        elif days < 0:
            yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0)
            query = query.filter(Article.created_at >= yesterday, Article.created_at < yesterday + timedelta(days=1))
    elif sc_date == 'S' and sc_sdate:
        try:
            sd = datetime.strptime(sc_sdate, '%Y-%m-%d')
            query = query.filter(Article.created_at >= sd)
        except ValueError:
            pass
        if sc_edate:
            try:
                ed = datetime.strptime(sc_edate, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Article.created_at < ed)
            except ValueError:
                pass

    pagination = query.order_by(Article.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    sections = Section.query.order_by(Section.sort_order).all()

    return render_template('admin/approval.html',
                           articles=pagination.items, pagination=pagination,
                           sections=sections, tab=tab, per_page=per_page,
                           sc_section_code=section_id, sc_sub_section_code=subsection_id,
                           sc_level=sc_level, sc_article_type=sc_article_type,
                           sc_area=sc_area, sc_word=sc_word, sc_date=sc_date,
                           sc_sdate=sc_sdate, sc_edate=sc_edate)


@admin_bp.route('/article/<int:article_id>/approve', methods=['POST'])
@admin_required
def article_approve(article_id):
    article = Article.query.get_or_404(article_id)
    action = request.form.get('action', 'E')
    article.recognition = action
    db.session.commit()
    label = '승인' if action == 'E' else '반려'
    flash(f'기사가 {label}되었습니다.', 'success')
    return redirect(request.referrer or url_for('admin.approval'))


@admin_bp.route('/articles/batch-approve', methods=['POST'])
@admin_required
def batch_approve():
    ids = request.form.getlist('chkbox[]')
    action = request.form.get('action', 'E')
    level = request.form.get('level', '')
    count = 0
    for aid in ids:
        try:
            article = db.session.get(Article, int(aid))
        except (ValueError, TypeError):
            continue
        if article:
            article.recognition = action
            if level and level != 'RE':
                article.level = level
            count += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('처리 중 오류가 발생했습니다.', 'error')
        return redirect(request.referrer or url_for('admin.approval'))
    flash(f'{count}건의 기사가 처리되었습니다.', 'success')
    return redirect(request.referrer or url_for('admin.approval'))


@admin_bp.route('/article/<int:article_id>/set-level', methods=['POST'])
@admin_required
def article_set_level(article_id):
    article = Article.query.get_or_404(article_id)
    article.level = request.form.get('level', 'B')
    db.session.commit()
    return jsonify({'ok': True})


# ── 회원 관리 ──

@admin_bp.route('/members')
@admin_required
def member_list():
    tab = request.args.get('tab', 'all')  # all, inactive, dormant
    stype = request.args.get('stype', '')
    sword = request.args.get('sword', '').strip()
    user_state = request.args.get('user_state', '')

    query = Member.query

    # 탭 필터
    if tab == 'inactive':
        query = query.filter_by(is_active=False)
    elif tab == 'dormant':
        query = query.filter_by(is_dormant=True)

    if sword:
        if stype == 'I':
            query = query.filter(Member.user_id.contains(sword))
        elif stype == 'N':
            query = query.filter(Member.name.contains(sword))
        elif stype == 'E':
            query = query.filter(Member.email.contains(sword))
        else:
            query = query.filter(db.or_(
                Member.user_id.contains(sword),
                Member.name.contains(sword),
                Member.email.contains(sword)
            ))
    if user_state == 'A':
        query = query.filter_by(is_active=True)
    elif user_state == 'D':
        query = query.filter_by(is_active=False)

    members = query.order_by(Member.created_at.desc()).all()

    # 탭 카운트
    all_count = Member.query.count()
    inactive_count = Member.query.filter_by(is_active=False).count()
    dormant_count = Member.query.filter_by(is_dormant=True).count()

    return render_template('admin/member_list.html', members=members,
                           stype=stype, sword=sword, tab=tab,
                           user_state=user_state, member_count=len(members),
                           all_count=all_count, inactive_count=inactive_count,
                           dormant_count=dormant_count)


@admin_bp.route('/member/new', methods=['GET', 'POST'])
@admin_required
def member_new():
    if request.method == 'POST':
        return _save_member(None)
    return render_template('admin/member_form.html', member=None)


@admin_bp.route('/member/<int:member_id>/edit', methods=['GET', 'POST'])
@admin_required
def member_edit(member_id):
    member = Member.query.get_or_404(member_id)
    if request.method == 'POST':
        return _save_member(member)
    return render_template('admin/member_form.html', member=member)


def _save_member(member):
    is_new = member is None
    if is_new:
        member = Member()

    member.user_id = request.form.get('user_id', '').strip()
    if not member.user_id:
        flash('아이디를 입력하세요.', 'error')
        return render_template('admin/member_form.html', member=member)

    if is_new:
        existing = Member.query.filter_by(user_id=member.user_id).first()
        if existing:
            flash('이미 존재하는 아이디입니다.', 'error')
            return render_template('admin/member_form.html', member=member)

    member.name = request.form.get('name', '').strip()
    member.email = request.form.get('email', '')
    member.phone = request.form.get('phone', '')
    member.level = request.form.get('level', '일반')

    password = request.form.get('password', '').strip()
    if password:
        member.password_hash = generate_password_hash(password)
    elif is_new:
        flash('비밀번호를 입력하세요.', 'error')
        return render_template('admin/member_form.html', member=member)

    if is_new:
        db.session.add(member)

    db.session.commit()

    # 수정내역 로그
    log = MemberLog(
        member_id=member.id,
        action='create' if is_new else 'update',
        detail=f'이름:{member.name}, 등급:{member.level}, 이메일:{member.email}',
        admin_name=current_user.name
    )
    db.session.add(log)
    db.session.commit()

    flash('회원 정보가 저장되었습니다.', 'success')
    return redirect(url_for('admin.member_list'))


@admin_bp.route('/member/<int:member_id>/delete', methods=['POST'])
@admin_required
def member_delete(member_id):
    member = Member.query.get_or_404(member_id)
    log = MemberLog(member_id=member.id, action='delete',
                    detail=f'아이디:{member.user_id}, 이름:{member.name}',
                    admin_name=current_user.name)
    db.session.add(log)
    db.session.delete(member)
    db.session.commit()
    flash('회원이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.member_list'))


@admin_bp.route('/member/<int:member_id>/toggle-active', methods=['POST'])
@admin_required
def member_toggle_active(member_id):
    member = Member.query.get_or_404(member_id)
    member.is_active = not member.is_active
    db.session.commit()
    log = MemberLog(member_id=member.id,
                    action='activate' if member.is_active else 'deactivate',
                    detail='', admin_name=current_user.name)
    db.session.add(log)
    db.session.commit()
    flash(f'회원 "{member.user_id}" 상태가 {"활성" if member.is_active else "비활성"}으로 변경되었습니다.', 'success')
    return redirect(url_for('admin.member_list'))


@admin_bp.route('/member/<int:member_id>/logs')
@admin_required
def member_logs(member_id):
    """회원 수정내역 조회 API"""
    logs = MemberLog.query.filter_by(member_id=member_id).order_by(
        MemberLog.created_at.desc()
    ).limit(50).all()
    return jsonify([{
        'action': l.action,
        'detail': l.detail,
        'admin_name': l.admin_name,
        'created_at': l.created_at.strftime('%Y-%m-%d %H:%M')
    } for l in logs])


# ── 통계 ──

@admin_bp.route('/stats/authors')
@admin_required
def stats_authors():
    from datetime import timedelta
    import calendar

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    sc_date = request.args.get('sc_date', 'M1')
    order_by = request.args.get('order_by', 'total')

    today = datetime.now()

    # 월별 프리셋
    if sc_date == 'M1':  # 이번 달
        sd = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        ed = today.replace(day=last_day)
    elif sc_date == 'M-1':  # 지난 달
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        sd = last_month.replace(day=1)
        ed = last_month
    elif sc_date == 'M-2':  # 2달 전
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        two_months = last_month.replace(day=1) - timedelta(days=1)
        sd = two_months.replace(day=1)
        ed = two_months
    elif sc_date == 'S' and start_date:  # 상세검색
        try:
            sd = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            sd = today.replace(day=1)
        try:
            ed = datetime.strptime(end_date, '%Y-%m-%d') if end_date else today
        except ValueError:
            ed = today
    else:
        sd = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        ed = today.replace(day=last_day)

    start_str = sd.strftime('%Y-%m-%d')
    end_str = ed.strftime('%Y-%m-%d')

    stats = db.session.query(
        Article.author_name,
        db.func.count(Article.id).label('article_count'),
        db.func.count(db.case((Article.recognition == 'E', 1))).label('approved_count'),
        db.func.count(db.case((Article.level == 'T', 1))).label('headline_count'),
        db.func.count(db.case((Article.level == 'I', 1))).label('important_count'),
        db.func.count(db.case((Article.level == 'B', 1))).label('normal_count'),
        db.func.sum(Article.view_count).label('total_views')
    ).filter(
        Article.is_deleted == False,
        Article.created_at >= sd,
        Article.created_at < ed + timedelta(days=1)
    ).group_by(Article.author_name)

    # 정렬
    if order_by == 'total_pv':
        stats = stats.order_by(db.func.sum(Article.view_count).desc())
    elif order_by == 'total_recognition_e':
        stats = stats.order_by(db.func.count(db.case((Article.recognition == 'E', 1))).desc())
    else:
        stats = stats.order_by(db.func.count(Article.id).desc())

    results = stats.all()

    # 요약 통계
    total_articles = sum(r.article_count for r in results)
    total_views = sum((r.total_views or 0) for r in results)
    total_comments = db.session.query(db.func.count(ArticleComment.id)).filter(
        ArticleComment.created_at >= sd,
        ArticleComment.created_at < ed + timedelta(days=1)
    ).scalar() or 0

    # 월 라벨
    months = []
    for i in range(-2, 1):
        m = today.month + i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append({'label': f'{m}월', 'key': f'M{i}' if i != 0 else 'M1'})

    return render_template('admin/stats_authors.html',
                           stats=results, sc_date=sc_date,
                           start_date=start_str, end_date=end_str,
                           order_by=order_by, months=months,
                           total_articles=total_articles,
                           total_views=total_views,
                           total_comments=total_comments)


@admin_bp.route('/stats/ranking')
@admin_required
def stats_ranking():
    from datetime import timedelta

    opt_section = request.args.get('opt_section', '')
    opt_limit = request.args.get('opt_limit', 50, type=int)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    sc_date = request.args.get('sc_date', '30')

    today = datetime.now()

    # 날짜 프리셋
    if sc_date and sc_date != 'S':
        days = int(sc_date) if sc_date not in ('', 'S') else 30
        if days > 0:
            sd = today - timedelta(days=days - 1)
            ed = today
        elif days < 0:
            sd = ed = today - timedelta(days=1)
        else:
            sd = ed = today
    elif start_date:
        try:
            sd = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            sd = today
        try:
            ed = datetime.strptime(end_date, '%Y-%m-%d') if end_date else today
        except ValueError:
            ed = today
    else:
        sd = today - timedelta(days=29)
        ed = today

    start_str = sd.strftime('%Y-%m-%d')
    end_str = ed.strftime('%Y-%m-%d')

    query = Article.query.filter(
        Article.is_deleted == False,
        Article.created_at >= sd,
        Article.created_at < ed + timedelta(days=1)
    )
    if opt_section:
        query = query.filter_by(section_id=int(opt_section))

    articles = query.order_by(Article.view_count.desc()).limit(opt_limit).all()
    sections = Section.query.order_by(Section.sort_order).all()

    return render_template('admin/stats_ranking.html',
                           articles=articles, sections=sections,
                           opt_section=opt_section, opt_limit=opt_limit,
                           start_date=start_str, end_date=end_str,
                           sc_date=sc_date)


# ── 1면 헤드 편집 ──

@admin_bp.route('/hero-config', methods=['GET', 'POST'])
@admin_required
def hero_config():
    if request.method == 'POST':
        for i in range(1, 5):
            key = f'hero_slot_{i}'
            val = request.form.get(key, '').strip()
            setting = SiteSetting.query.filter_by(key=key).first()
            if not setting:
                setting = SiteSetting(key=key)
                db.session.add(setting)
            setting.value = val
        db.session.commit()
        flash('1면 헤드 구성이 저장되었습니다.', 'success')
        return redirect(url_for('admin.hero_config'))

    settings = {}
    preview = {}
    for i in range(1, 5):
        key = f'hero_slot_{i}'
        s = SiteSetting.query.filter_by(key=key).first()
        val = s.value if s else ''
        settings[key] = val
        if val and val.strip().isdigit():
            art = db.session.get(Article, int(val))
            preview[key] = art  # None이면 못 찾은 것
    recent_articles = Article.query.filter_by(is_deleted=False, recognition='E').order_by(
        db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(30).all()
    return render_template('admin/hero_config.html', settings=settings, preview=preview, recent_articles=recent_articles)


# ── 많이 본 뉴스 관리 ──

@admin_bp.route('/popular-config', methods=['GET', 'POST'])
@admin_required
def popular_config():
    if request.method == 'POST':
        # 오늘 탭
        ids = request.form.get('popular_ids', '').strip()
        setting = SiteSetting.query.filter_by(key='popular_article_ids').first()
        if not setting:
            setting = SiteSetting(key='popular_article_ids')
            db.session.add(setting)
        setting.value = ids

        # 주간 탭
        weekly_ids = request.form.get('popular_weekly_ids', '').strip()
        weekly_setting = SiteSetting.query.filter_by(key='popular_weekly_article_ids').first()
        if not weekly_setting:
            weekly_setting = SiteSetting(key='popular_weekly_article_ids')
            db.session.add(weekly_setting)
        weekly_setting.value = weekly_ids

        db.session.commit()
        flash('많이 본 뉴스 설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.popular_config'))

    setting = SiteSetting.query.filter_by(key='popular_article_ids').first()
    ids_str = setting.value if setting else ''
    selected_articles = []
    if ids_str:
        for aid in ids_str.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art:
                    selected_articles.append(art)

    weekly_setting = SiteSetting.query.filter_by(key='popular_weekly_article_ids').first()
    weekly_ids_str = weekly_setting.value if weekly_setting else ''
    weekly_selected_articles = []
    if weekly_ids_str:
        for aid in weekly_ids_str.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art:
                    weekly_selected_articles.append(art)

    recent_articles = Article.query.filter_by(is_deleted=False, recognition='E').order_by(
        db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(30).all()
    return render_template('admin/popular_config.html',
                           ids_str=ids_str, selected_articles=selected_articles,
                           weekly_ids_str=weekly_ids_str, weekly_selected_articles=weekly_selected_articles,
                           recent_articles=recent_articles)


@admin_bp.route('/featured-config', methods=['GET', 'POST'])
@admin_required
def featured_config():
    """주요 기사 편집"""
    if request.method == 'POST':
        ids = request.form.get('featured_ids', '').strip()
        setting = SiteSetting.query.filter_by(key='featured_article_ids').first()
        if not setting:
            setting = SiteSetting(key='featured_article_ids')
            db.session.add(setting)
        setting.value = ids
        db.session.commit()
        flash('주요 기사 설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.featured_config'))

    setting = SiteSetting.query.filter_by(key='featured_article_ids').first()
    ids_str = setting.value if setting else ''
    selected_articles = []
    if ids_str:
        for aid in ids_str.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art:
                    selected_articles.append(art)

    recent_articles = Article.query.filter_by(is_deleted=False, recognition='E').order_by(
        db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(30).all()
    return render_template('admin/featured_config.html',
                           ids_str=ids_str, selected_articles=selected_articles, recent_articles=recent_articles)


@admin_bp.route('/settings/quotes', methods=['GET', 'POST'])
@admin_required
def settings_quotes():
    """명언 관리"""
    if request.method == 'POST':
        quotes_text = request.form.get('quotes', '').strip()
        setting = SiteSetting.query.filter_by(key='header_quotes').first()
        if not setting:
            setting = SiteSetting(key='header_quotes')
            db.session.add(setting)
        setting.value = quotes_text
        db.session.commit()
        flash('명언이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings_quotes'))

    setting = SiteSetting.query.filter_by(key='header_quotes').first()
    quotes_text = setting.value if setting else ''
    return render_template('admin/quotes_config.html', quotes_text=quotes_text)


# ── 환경설정 ──

@admin_bp.route('/settings/general', methods=['GET', 'POST'])
@admin_required
def settings_general():
    if request.method == 'POST':
        keys = ['site_name', 'site_tagline', 'publisher', 'editor_name',
                'company_name', 'address', 'address2', 'email', 'tel', 'fax',
                'registration_no', 'registration_date', 'publication_date',
                'zipcode', 'p_person', 'p_tel', 'p_email',
                'y_person', 'y_tel', 'y_email',
                'copy_person', 'copy_tel', 'copy_email',
                'ga4_measurement_id']
        for key in keys:
            setting = SiteSetting.query.filter_by(key=key).first()
            if not setting:
                setting = SiteSetting(key=key)
                db.session.add(setting)
            setting.value = request.form.get(key, '')
        db.session.commit()
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings_general'))

    settings = {s.key: s for s in SiteSetting.query.all()}
    return render_template('admin/settings_general.html', settings=settings)


@admin_bp.route('/settings/sections')
@admin_required
def settings_sections():
    sections = Section.query.order_by(Section.sort_order).all()
    return render_template('admin/settings_sections.html', sections=sections)


@admin_bp.route('/settings/section/add', methods=['POST'])
@admin_required
def section_add():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    if not code or not name:
        flash('코드와 이름을 입력하세요.', 'error')
        return redirect(url_for('admin.settings_sections'))
    if Section.query.filter_by(code=code).first():
        flash('이미 존재하는 코드입니다.', 'error')
        return redirect(url_for('admin.settings_sections'))
    max_order = db.session.query(db.func.max(Section.sort_order)).scalar() or 0
    db.session.add(Section(code=code, name=name, sort_order=max_order + 1))
    db.session.commit()
    flash('섹션이 추가되었습니다.', 'success')
    return redirect(url_for('admin.settings_sections'))


@admin_bp.route('/settings/section/<int:section_id>/edit', methods=['POST'])
@admin_required
def section_edit(section_id):
    sec = Section.query.get_or_404(section_id)
    sec.name = request.form.get('name', sec.name).strip()
    db.session.commit()
    if request.form.get('ajax'):
        return jsonify(success=True)
    flash('섹션이 수정되었습니다.', 'success')
    return redirect(url_for('admin.settings_sections'))


@admin_bp.route('/settings/section/<int:section_id>/delete', methods=['POST'])
@admin_required
def section_delete(section_id):
    sec = Section.query.get_or_404(section_id)
    SubSection.query.filter_by(section_id=sec.id).delete()
    db.session.delete(sec)
    db.session.commit()
    flash('섹션이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.settings_sections'))


@admin_bp.route('/settings/subsection/add', methods=['POST'])
@admin_required
def subsection_add():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    section_id = request.form.get('section_id', type=int)
    if not code or not name or not section_id:
        flash('모든 필드를 입력하세요.', 'error')
        return redirect(url_for('admin.settings_sections'))
    if SubSection.query.filter_by(code=code).first():
        flash('이미 존재하는 코드입니다.', 'error')
        return redirect(url_for('admin.settings_sections'))
    max_order = db.session.query(db.func.max(SubSection.sort_order)).filter_by(section_id=section_id).scalar() or 0
    db.session.add(SubSection(code=code, name=name, section_id=section_id, sort_order=max_order + 1))
    db.session.commit()
    flash('2차 섹션이 추가되었습니다.', 'success')
    return redirect(url_for('admin.settings_sections'))


@admin_bp.route('/settings/subsection/<int:sub_id>/edit', methods=['POST'])
@admin_required
def subsection_edit(sub_id):
    sub = SubSection.query.get_or_404(sub_id)
    sub.name = request.form.get('name', sub.name).strip()
    db.session.commit()
    if request.form.get('ajax'):
        return jsonify(success=True)
    flash('2차 섹션이 수정되었습니다.', 'success')
    return redirect(url_for('admin.settings_sections'))


@admin_bp.route('/settings/subsection/<int:sub_id>/delete', methods=['POST'])
@admin_required
def subsection_delete(sub_id):
    sub = SubSection.query.get_or_404(sub_id)
    db.session.delete(sub)
    db.session.commit()
    flash('2차 섹션이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.settings_sections'))


@admin_bp.route('/settings/sections/reorder', methods=['POST'])
@admin_required
def sections_reorder():
    """드래그앤드롭 순서 변경 AJAX"""
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    target = data.get('target', 'section')  # section or subsection
    Model = Section if target == 'section' else SubSection
    for idx, item_id in enumerate(ids):
        item = db.session.get(Model, int(item_id))
        if item:
            item.sort_order = idx
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.route('/stats/authors/csv')
@admin_required
def stats_authors_csv():
    """기자별 통계 CSV 다운로드"""
    import csv
    import io
    from datetime import timedelta
    import calendar
    from flask import Response

    sc_date = request.args.get('sc_date', 'M1')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    order_by = request.args.get('order_by', 'total')
    today = datetime.now()

    if sc_date == 'M1':
        sd = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        ed = today.replace(day=last_day)
    elif sc_date == 'M-1':
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        sd = last_month.replace(day=1)
        ed = last_month
    elif sc_date == 'M-2':
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        two_months = last_month.replace(day=1) - timedelta(days=1)
        sd = two_months.replace(day=1)
        ed = two_months
    elif sc_date == 'S' and start_date:
        try:
            sd = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            sd = today.replace(day=1)
        try:
            ed = datetime.strptime(end_date, '%Y-%m-%d') if end_date else today
        except ValueError:
            ed = today
    else:
        sd = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        ed = today.replace(day=last_day)

    stats = db.session.query(
        Article.author_name,
        db.func.count(Article.id).label('article_count'),
        db.func.count(db.case((Article.recognition == 'E', 1))).label('approved_count'),
        db.func.count(db.case((Article.level == 'T', 1))).label('headline_count'),
        db.func.count(db.case((Article.level == 'I', 1))).label('important_count'),
        db.func.count(db.case((Article.level == 'B', 1))).label('normal_count'),
        db.func.sum(Article.view_count).label('total_views')
    ).filter(
        Article.is_deleted == False,
        Article.created_at >= sd,
        Article.created_at < ed + timedelta(days=1)
    ).group_by(Article.author_name)

    if order_by == 'total_pv':
        stats = stats.order_by(db.func.sum(Article.view_count).desc())
    elif order_by == 'total_recognition_e':
        stats = stats.order_by(db.func.count(db.case((Article.recognition == 'E', 1))).desc())
    else:
        stats = stats.order_by(db.func.count(Article.id).desc())

    results = stats.all()

    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel
    writer = csv.writer(output)
    writer.writerow(['순위', '기자명', '기사수', '승인', '헤드라인', '중요', '일반', '기사뷰'])
    for i, row in enumerate(results, 1):
        writer.writerow([i, row.author_name, row.article_count, row.approved_count,
                         row.headline_count, row.important_count, row.normal_count,
                         row.total_views or 0])

    filename = f'기자별통계_{sd.strftime("%Y%m%d")}_{ed.strftime("%Y%m%d")}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename*=UTF-8\'\'{filename}'}
    )


@admin_bp.route('/stats/ranking/csv')
@admin_required
def stats_ranking_csv():
    """기사 랭킹 CSV 다운로드"""
    import csv
    import io
    from datetime import timedelta
    from flask import Response

    opt_section = request.args.get('opt_section', '')
    opt_limit = request.args.get('opt_limit', 50, type=int)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    sc_date = request.args.get('sc_date', '30')
    today = datetime.now()

    if sc_date and sc_date != 'S':
        days = int(sc_date) if sc_date not in ('', 'S') else 30
        if days > 0:
            sd = today - timedelta(days=days - 1)
            ed = today
        elif days < 0:
            sd = ed = today - timedelta(days=1)
        else:
            sd = ed = today
    elif start_date:
        try:
            sd = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            sd = today
        try:
            ed = datetime.strptime(end_date, '%Y-%m-%d') if end_date else today
        except ValueError:
            ed = today
    else:
        sd = today - timedelta(days=29)
        ed = today

    query = Article.query.filter(
        Article.is_deleted == False,
        Article.created_at >= sd,
        Article.created_at < ed + timedelta(days=1)
    )
    if opt_section:
        query = query.filter_by(section_id=int(opt_section))

    articles = query.order_by(Article.view_count.desc()).limit(opt_limit).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['순위', '기사제목', '기자명', '기사노출일', '조회수'])
    for i, a in enumerate(articles, 1):
        writer.writerow([i, a.title, a.author_name, a.created_at.strftime('%Y-%m-%d'), a.view_count])

    filename = f'기사랭킹_{sd.strftime("%Y%m%d")}_{ed.strftime("%Y%m%d")}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename*=UTF-8\'\'{filename}'}
    )


# ── 기사댓글 ──

@admin_bp.route('/article-comments')
@admin_required
def article_comments():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    query = ArticleComment.query
    if q:
        query = query.filter(ArticleComment.content.contains(q))
    pagination = query.order_by(ArticleComment.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/article_comments.html', comments=pagination.items, pagination=pagination, q=q)


@admin_bp.route('/article-comment/<int:comment_id>/toggle', methods=['POST'])
@admin_required
def article_comment_toggle(comment_id):
    c = ArticleComment.query.get_or_404(comment_id)
    c.is_hidden = not c.is_hidden
    db.session.commit()
    flash('댓글 상태가 변경되었습니다.', 'success')
    return redirect(url_for('admin.article_comments'))


@admin_bp.route('/article-comment/<int:comment_id>/delete', methods=['POST'])
@admin_required
def article_comment_delete(comment_id):
    c = ArticleComment.query.get_or_404(comment_id)
    db.session.delete(c)
    db.session.commit()
    flash('댓글이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.article_comments'))


# ── 기사구조 ──

@admin_bp.route('/article-structure')
@admin_required
def article_structure():
    sections = Section.query.order_by(Section.sort_order).all()
    structure = []
    for sec in sections:
        subs = []
        for sub in sec.subsections:
            count = Article.query.filter_by(subsection_id=sub.id, is_deleted=False).count()
            subs.append({'id': sub.id, 'name': sub.name, 'code': sub.code, 'count': count})
        sec_count = Article.query.filter_by(section_id=sec.id, is_deleted=False).count()
        structure.append({'id': sec.id, 'name': sec.name, 'code': sec.code, 'count': sec_count, 'subs': subs})
    return render_template('admin/article_structure.html', structure=structure)


# ── 편집 ──

# 레이아웃별 사용 가능한 블록 타입 정의
LAYOUT_BLOCK_DEFS = {
    'MAIN': [
        {'type': 'headline', 'label': '헤드라인', 'icon': 'bi-newspaper', 'defaults': {'count': 3}},
        {'type': 'latest_grid', 'label': '최신기사 그리드', 'icon': 'bi-grid-3x2', 'defaults': {'count': 8}},
        {'type': 'opinion_sidebar', 'label': '오피니언 (사이드바)', 'icon': 'bi-chat-quote', 'defaults': {'count': 4, 'section_code': 'S1N2'}},
        {'type': 'popular_sidebar', 'label': '많이 본 뉴스 (사이드바)', 'icon': 'bi-bar-chart', 'defaults': {'count': 5}},
        {'type': 'section_articles', 'label': '섹션별 기사', 'icon': 'bi-columns-gap', 'defaults': {'count': 4, 'columns': 3}},
        {'type': 'banner', 'label': '배너 영역', 'icon': 'bi-megaphone', 'defaults': {'position': 'main_bottom'}},
    ],
    'MOBILE': [
        {'type': 'headline', 'label': '헤드라인', 'icon': 'bi-newspaper', 'defaults': {'count': 3}},
        {'type': 'latest_list', 'label': '최신기사 리스트', 'icon': 'bi-list-ul', 'defaults': {'count': 10}},
        {'type': 'popular', 'label': '많이 본 뉴스', 'icon': 'bi-bar-chart', 'defaults': {'count': 5}},
        {'type': 'section_articles', 'label': '섹션별 기사', 'icon': 'bi-columns-gap', 'defaults': {'count': 3}},
        {'type': 'banner', 'label': '배너 영역', 'icon': 'bi-megaphone', 'defaults': {'position': 'mobile'}},
    ],
    'PCVIEW': [
        {'type': 'related_articles', 'label': '관련기사', 'icon': 'bi-link-45deg', 'defaults': {'count': 5}},
        {'type': 'article_nav', 'label': '이전/다음 기사', 'icon': 'bi-arrow-left-right', 'defaults': {}},
        {'type': 'comment', 'label': '댓글', 'icon': 'bi-chat-dots', 'defaults': {}},
        {'type': 'opinion_sidebar', 'label': '오피니언 (사이드바)', 'icon': 'bi-chat-quote', 'defaults': {'count': 4}},
        {'type': 'popular_sidebar', 'label': '많이 본 뉴스 (사이드바)', 'icon': 'bi-bar-chart', 'defaults': {'count': 5}},
        {'type': 'banner', 'label': '배너 영역', 'icon': 'bi-megaphone', 'defaults': {'position': 'view_bottom'}},
    ],
    'PCLIST': [
        {'type': 'article_list', 'label': '기사 목록', 'icon': 'bi-list-ul', 'defaults': {'per_page': 20}},
        {'type': 'opinion_sidebar', 'label': '오피니언 (사이드바)', 'icon': 'bi-chat-quote', 'defaults': {'count': 4}},
        {'type': 'popular_sidebar', 'label': '많이 본 뉴스 (사이드바)', 'icon': 'bi-bar-chart', 'defaults': {'count': 5}},
        {'type': 'banner', 'label': '배너 영역', 'icon': 'bi-megaphone', 'defaults': {'position': 'list_bottom'}},
    ],
    'LETTER': [
        {'type': 'headline', 'label': '주요 기사', 'icon': 'bi-newspaper', 'defaults': {'count': 3}},
        {'type': 'latest_list', 'label': '최신 기사', 'icon': 'bi-list-ul', 'defaults': {'count': 10}},
        {'type': 'opinion', 'label': '오피니언', 'icon': 'bi-chat-quote', 'defaults': {'count': 3}},
    ],
}


def _edit_layout(layout_type, layout_name):
    import json
    blocks = LayoutBlock.query.filter_by(layout_type=layout_type).order_by(LayoutBlock.sort_order).all()
    block_defs = LAYOUT_BLOCK_DEFS.get(layout_type, [])
    # 현재 사용 중인 블록 타입 목록
    used_types = [b.block_type for b in blocks]
    # 추가 가능한 블록 (아직 사용하지 않는 것)
    available = [d for d in block_defs if d['type'] not in used_types]
    # 블록에 아이콘 정보 매핑
    icon_map = {d['type']: d['icon'] for d in block_defs}
    blocks_data = []
    for b in blocks:
        blocks_data.append({
            'id': b.id,
            'block_type': b.block_type,
            'block_label': b.block_label,
            'settings': json.loads(b.settings or '{}'),
            'sort_order': b.sort_order,
            'is_active': b.is_active,
            'icon': icon_map.get(b.block_type, 'bi-box'),
        })
    return render_template('admin/edit_layout.html',
                           layout_type=layout_type,
                           layout_name=layout_name,
                           blocks=blocks_data,
                           available=available,
                           blocks_json=json.dumps(blocks_data, ensure_ascii=False))


@admin_bp.route('/edit/main')
@admin_required
def edit_layout_main():
    return _edit_layout('MAIN', '메인')


@admin_bp.route('/edit/mobile')
@admin_required
def edit_layout_mobile():
    return _edit_layout('MOBILE', '모바일메인')


@admin_bp.route('/edit/article-view')
@admin_required
def edit_layout_article_view():
    return _edit_layout('PCVIEW', '기사뷰')


@admin_bp.route('/edit/article-list')
@admin_required
def edit_layout_article_list():
    return _edit_layout('PCLIST', '기사리스트')


@admin_bp.route('/edit/newsletter')
@admin_required
def edit_layout_newsletter():
    return _edit_layout('LETTER', '뉴스레터')


@admin_bp.route('/edit/save', methods=['POST'])
@admin_required
def edit_layout_save():
    """레이아웃 블록 순서/활성 상태/설정 저장 (AJAX)"""
    import json
    data = request.get_json()
    layout_type = data.get('layout_type', '')
    blocks = data.get('blocks', [])

    for i, bdata in enumerate(blocks):
        block_id = bdata.get('id')
        if block_id:
            block = db.session.get(LayoutBlock, block_id)
            if block and block.layout_type == layout_type:
                block.sort_order = i + 1
                block.is_active = bdata.get('is_active', True)
                block.settings = json.dumps(bdata.get('settings', {}), ensure_ascii=False)

    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/edit/block/add', methods=['POST'])
@admin_required
def edit_layout_block_add():
    """블록 추가 (AJAX)"""
    import json
    data = request.get_json()
    layout_type = data.get('layout_type', '')
    block_type = data.get('block_type', '')
    block_defs = LAYOUT_BLOCK_DEFS.get(layout_type, [])
    defn = next((d for d in block_defs if d['type'] == block_type), None)
    if not defn:
        return jsonify({'success': False, 'error': 'Invalid block type'}), 400

    max_order = db.session.query(db.func.max(LayoutBlock.sort_order)).filter_by(
        layout_type=layout_type).scalar() or 0

    block = LayoutBlock(
        layout_type=layout_type,
        block_type=block_type,
        block_label=defn['label'],
        settings=json.dumps(defn['defaults'], ensure_ascii=False),
        sort_order=max_order + 1,
        is_active=True
    )
    db.session.add(block)
    db.session.commit()

    return jsonify({
        'success': True,
        'block': {
            'id': block.id,
            'block_type': block.block_type,
            'block_label': block.block_label,
            'settings': defn['defaults'],
            'sort_order': block.sort_order,
            'is_active': True,
            'icon': defn['icon'],
        }
    })


@admin_bp.route('/edit/block/delete', methods=['POST'])
@admin_required
def edit_layout_block_delete():
    """블록 삭제 (AJAX)"""
    data = request.get_json()
    block_id = data.get('id')
    block = db.session.get(LayoutBlock, block_id)
    if block:
        db.session.delete(block)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Block not found'}), 404


# ── 회원 - 휴면/등급/필자/부서 ──

@admin_bp.route('/members/dormant')
@admin_required
def dormant_list():
    members = AdminUser.query.filter_by(is_dormant=True).order_by(AdminUser.created_at.desc()).all()
    return render_template('admin/dormant_list.html', members=members)


@admin_bp.route('/member/<int:member_id>/toggle-dormant', methods=['POST'])
@admin_required
def member_toggle_dormant(member_id):
    m = AdminUser.query.get_or_404(member_id)
    m.is_dormant = not m.is_dormant
    db.session.commit()
    flash('회원 상태가 변경되었습니다.', 'success')
    return redirect(request.referrer or url_for('admin.member_list'))


@admin_bp.route('/etc-levels')
@admin_required
def etc_level_list():
    levels = EtcLevel.query.order_by(EtcLevel.sort_order).all()
    return render_template('admin/etc_level_list.html', levels=levels)


@admin_bp.route('/etc-level/add', methods=['POST'])
@admin_required
def etc_level_add():
    name = request.form.get('name', '').strip()
    if name:
        max_order = db.session.query(db.func.max(EtcLevel.sort_order)).scalar() or 0
        db.session.add(EtcLevel(name=name, sort_order=max_order + 1))
        db.session.commit()
        flash('등급이 추가되었습니다.', 'success')
    return redirect(url_for('admin.etc_level_list'))


@admin_bp.route('/etc-level/<int:level_id>/delete', methods=['POST'])
@admin_required
def etc_level_delete(level_id):
    db.session.delete(EtcLevel.query.get_or_404(level_id))
    db.session.commit()
    flash('등급이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.etc_level_list'))


@admin_bp.route('/divisions')
@admin_required
def division_list():
    divisions = MemberDivision.query.order_by(MemberDivision.sort_order).all()
    return render_template('admin/division_list.html', divisions=divisions)


@admin_bp.route('/division/add', methods=['POST'])
@admin_required
def division_add():
    name = request.form.get('name', '').strip()
    if name:
        max_order = db.session.query(db.func.max(MemberDivision.sort_order)).scalar() or 0
        db.session.add(MemberDivision(name=name, sort_order=max_order + 1))
        db.session.commit()
        flash('필자표시가 추가되었습니다.', 'success')
    return redirect(url_for('admin.division_list'))


@admin_bp.route('/division/<int:div_id>/delete', methods=['POST'])
@admin_required
def division_delete(div_id):
    db.session.delete(MemberDivision.query.get_or_404(div_id))
    db.session.commit()
    flash('필자표시가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.division_list'))


@admin_bp.route('/departments')
@admin_required
def department_list():
    departments = Department.query.order_by(Department.sort_order).all()
    return render_template('admin/department_list.html', departments=departments)


@admin_bp.route('/department/add', methods=['POST'])
@admin_required
def department_add():
    name = request.form.get('name', '').strip()
    if name:
        max_order = db.session.query(db.func.max(Department.sort_order)).scalar() or 0
        db.session.add(Department(name=name, sort_order=max_order + 1))
        db.session.commit()
        flash('부서가 추가되었습니다.', 'success')
    return redirect(url_for('admin.department_list'))


@admin_bp.route('/department/<int:dept_id>/delete', methods=['POST'])
@admin_required
def department_delete(dept_id):
    db.session.delete(Department.query.get_or_404(dept_id))
    db.session.commit()
    flash('부서가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.department_list'))


# ── 게시판 ──

@admin_bp.route('/boards')
@admin_required
def board_list():
    boards = Board.query.order_by(Board.sort_order).all()
    return render_template('admin/board_list.html', boards=boards)


@admin_bp.route('/board/add', methods=['POST'])
@admin_required
def board_add():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    if code and name:
        if not Board.query.filter_by(code=code).first():
            max_order = db.session.query(db.func.max(Board.sort_order)).scalar() or 0
            db.session.add(Board(code=code, name=name, sort_order=max_order + 1))
            db.session.commit()
            flash('게시판이 추가되었습니다.', 'success')
        else:
            flash('이미 존재하는 코드입니다.', 'error')
    return redirect(url_for('admin.board_list'))


@admin_bp.route('/board/<int:board_id>/edit', methods=['POST'])
@admin_required
def board_edit(board_id):
    b = Board.query.get_or_404(board_id)
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = request.form.get('is_active') == '1'
    sort_order = request.form.get('sort_order', 0, type=int)
    if name:
        b.name = name
        b.description = description
        b.is_active = is_active
        b.sort_order = sort_order
        db.session.commit()
        flash('게시판이 수정되었습니다.', 'success')
    return redirect(url_for('admin.board_list'))


@admin_bp.route('/board/<int:board_id>/delete', methods=['POST'])
@admin_required
def board_delete(board_id):
    b = Board.query.get_or_404(board_id)
    BoardPost.query.filter_by(board_id=b.id).delete()
    db.session.delete(b)
    db.session.commit()
    flash('게시판이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.board_list'))


@admin_bp.route('/bbs/posts')
@admin_required
def bbs_post_list():
    page = request.args.get('page', 1, type=int)
    board_id = request.args.get('board_id', '', type=str)
    q = request.args.get('q', '').strip()
    query = BoardPost.query
    if board_id:
        query = query.filter_by(board_id=int(board_id))
    if q:
        query = query.filter(BoardPost.title.contains(q))
    pagination = query.order_by(BoardPost.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    boards = Board.query.order_by(Board.sort_order).all()
    return render_template('admin/bbs_post_list.html', posts=pagination.items, pagination=pagination, boards=boards, board_id=board_id, q=q)


@admin_bp.route('/bbs/post/<int:post_id>/toggle', methods=['POST'])
@admin_required
def bbs_post_toggle(post_id):
    p = BoardPost.query.get_or_404(post_id)
    p.is_hidden = not p.is_hidden
    db.session.commit()
    flash('게시물 상태가 변경되었습니다.', 'success')
    return redirect(url_for('admin.bbs_post_list'))


@admin_bp.route('/bbs/post/<int:post_id>/delete', methods=['POST'])
@admin_required
def bbs_post_delete(post_id):
    p = BoardPost.query.get_or_404(post_id)
    BoardReply.query.filter_by(post_id=p.id).delete()
    db.session.delete(p)
    db.session.commit()
    flash('게시물이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.bbs_post_list'))


@admin_bp.route('/bbs/replies')
@admin_required
def bbs_reply_list():
    page = request.args.get('page', 1, type=int)
    pagination = BoardReply.query.order_by(BoardReply.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/bbs_reply_list.html', replies=pagination.items, pagination=pagination)


@admin_bp.route('/bbs/reply/<int:reply_id>/delete', methods=['POST'])
@admin_required
def bbs_reply_delete(reply_id):
    r = BoardReply.query.get_or_404(reply_id)
    db.session.delete(r)
    db.session.commit()
    flash('댓글이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.bbs_reply_list'))


@admin_bp.route('/event-requests')
@admin_required
def event_request_list():
    page = request.args.get('page', 1, type=int)
    event_code = request.args.get('event_code', '')
    query = EventRequest.query
    if event_code:
        query = query.filter_by(event_code=event_code)
    pagination = query.order_by(EventRequest.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    # extra_data JSON 파싱
    extras = {}
    for r in pagination.items:
        if r.extra_data and r.extra_data.startswith('{'):
            try:
                extras[r.id] = json.loads(r.extra_data)
            except Exception:
                extras[r.id] = {}
    return render_template('admin/event_request_list.html', requests=pagination.items, pagination=pagination, event_code=event_code, extras=extras)


@admin_bp.route('/event-request/<int:req_id>/toggle', methods=['POST'])
@admin_required
def event_request_toggle(req_id):
    r = EventRequest.query.get_or_404(req_id)
    r.is_processed = not r.is_processed
    db.session.commit()
    flash('처리 상태가 변경되었습니다.', 'success')
    return redirect(url_for('admin.event_request_list'))


# ── 광고 ──

@admin_bp.route('/banners')
@admin_required
def banner_list():
    banners = Banner.query.order_by(Banner.sort_order).all()
    return render_template('admin/banner_list.html', banners=banners)


@admin_bp.route('/banner/new', methods=['GET', 'POST'])
@admin_required
def banner_new():
    if request.method == 'POST':
        return _save_banner(None)
    return render_template('admin/banner_form.html', banner=None)


@admin_bp.route('/banner/<int:banner_id>/edit', methods=['GET', 'POST'])
@admin_required
def banner_edit(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    if request.method == 'POST':
        return _save_banner(banner)
    return render_template('admin/banner_form.html', banner=banner)


def _save_banner(banner):
    is_new = banner is None
    if is_new:
        banner = Banner()
    banner.name = request.form.get('name', '').strip()
    banner.link_url = request.form.get('link_url', '')
    banner.position = request.form.get('position', '')
    banner.is_active = request.form.get('is_active') == '1'

    # 시작일/종료일
    start_str = request.form.get('start_date', '').strip()
    end_str = request.form.get('end_date', '').strip()
    banner.start_date = datetime.strptime(start_str, '%Y-%m-%dT%H:%M') if start_str else None
    banner.end_date = datetime.strptime(end_str, '%Y-%m-%dT%H:%M') if end_str else None

    # 정렬순서
    sort_val = request.form.get('sort_order', '0').strip()
    banner.sort_order = int(sort_val) if sort_val.isdigit() else 0

    image = request.files.get('image')
    if image and image.filename:
        from app.utils.cloud_storage import upload_file
        filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        image.save(filepath)
        url = upload_file(filepath, folder='welldying/banners')
        if not url:
            flash('배너 이미지 업로드에 실패했습니다.', 'error')
            return redirect(request.referrer or url_for('admin.banner_list'))
        banner.image_path = url

    # 모바일 이미지 삭제 체크박스
    if request.form.get('delete_mobile_image') == '1':
        banner.mobile_image_path = ''

    # 모바일 이미지 업로드
    mobile_image = request.files.get('mobile_image')
    if mobile_image and mobile_image.filename:
        from app.utils.cloud_storage import upload_file as upload_mob
        mob_filename = f"{uuid.uuid4().hex}_{secure_filename(mobile_image.filename)}"
        mob_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], mob_filename)
        mobile_image.save(mob_filepath)
        mob_url = upload_mob(mob_filepath, folder='welldying/banners')
        if mob_url:
            banner.mobile_image_path = mob_url

    if is_new:
        db.session.add(banner)
    db.session.commit()
    flash('배너가 저장되었습니다.', 'success')
    return redirect(url_for('admin.banner_list'))


@admin_bp.route('/banner/<int:banner_id>/toggle', methods=['POST'])
@admin_required
def banner_toggle(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    banner.is_active = not banner.is_active
    db.session.commit()
    return redirect(url_for('admin.banner_list'))


@admin_bp.route('/banner/<int:banner_id>/delete', methods=['POST'])
@admin_required
def banner_delete(banner_id):
    db.session.delete(Banner.query.get_or_404(banner_id))
    db.session.commit()
    flash('배너가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.banner_list'))


@admin_bp.route('/popups')
@admin_required
def popup_list():
    popups = Popup.query.order_by(Popup.created_at.desc()).all()
    return render_template('admin/popup_list.html', popups=popups)


@admin_bp.route('/popup/new', methods=['GET', 'POST'])
@admin_required
def popup_new():
    if request.method == 'POST':
        return _save_popup(None)
    return render_template('admin/popup_form.html', popup=None)


@admin_bp.route('/popup/<int:popup_id>/edit', methods=['GET', 'POST'])
@admin_required
def popup_edit(popup_id):
    popup = Popup.query.get_or_404(popup_id)
    if request.method == 'POST':
        return _save_popup(popup)
    return render_template('admin/popup_form.html', popup=popup)


def _save_popup(popup):
    is_new = popup is None
    if is_new:
        popup = Popup()
    popup.name = request.form.get('name', '').strip()
    popup.content = request.form.get('content', '')
    popup.link_url = request.form.get('link_url', '')
    popup.width = request.form.get('width', 500, type=int)
    popup.height = request.form.get('height', 400, type=int)
    popup.is_active = request.form.get('is_active') == '1'
    popup.pos_x = request.form.get('pos_x', 100, type=int)
    popup.pos_y = request.form.get('pos_y', 100, type=int)
    sd = request.form.get('start_date', '').strip()
    ed = request.form.get('end_date', '').strip()
    popup.start_date = datetime.strptime(sd, '%Y-%m-%dT%H:%M') if sd else None
    popup.end_date = datetime.strptime(ed, '%Y-%m-%dT%H:%M') if ed else None
    image = request.files.get('image')
    if image and image.filename:
        from app.utils.cloud_storage import upload_file
        filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        image.save(filepath)
        url = upload_file(filepath, folder='welldying/popups')
        if not url:
            flash('팝업 이미지 업로드에 실패했습니다.', 'error')
            return redirect(request.referrer or url_for('admin.popup_list'))
        popup.image_path = url
    if is_new:
        db.session.add(popup)
    db.session.commit()
    flash('팝업이 저장되었습니다.', 'success')
    return redirect(url_for('admin.popup_list'))


@admin_bp.route('/popup/<int:popup_id>/delete', methods=['POST'])
@admin_required
def popup_delete(popup_id):
    p = Popup.query.get_or_404(popup_id)
    db.session.delete(p)
    db.session.commit()
    flash('팝업이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.popup_list'))


# ── 플러그인 - 설문조사 ──

@admin_bp.route('/polls')
@admin_required
def poll_list():
    polls = Poll.query.order_by(Poll.created_at.desc()).all()
    return render_template('admin/poll_list.html', polls=polls)


@admin_bp.route('/poll/new', methods=['GET', 'POST'])
@admin_required
def poll_new():
    if request.method == 'POST':
        return _save_poll(None)
    return render_template('admin/poll_form.html', poll=None)


@admin_bp.route('/poll/<int:poll_id>/edit', methods=['GET', 'POST'])
@admin_required
def poll_edit(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if request.method == 'POST':
        return _save_poll(poll)
    return render_template('admin/poll_form.html', poll=poll)


def _save_poll(poll):
    is_new = poll is None
    if is_new:
        poll = Poll()
    poll.title = request.form.get('title', '').strip()
    poll.is_active = request.form.get('is_active') == '1'
    poll.is_multiple = request.form.get('is_multiple') == '1'
    if is_new:
        db.session.add(poll)
        db.session.flush()
    # 선택지 처리
    options = request.form.getlist('options')
    if is_new:
        for i, text in enumerate(options):
            if text.strip():
                db.session.add(PollOption(poll_id=poll.id, text=text.strip(), sort_order=i))
    db.session.commit()
    flash('설문이 저장되었습니다.', 'success')
    return redirect(url_for('admin.poll_list'))


@admin_bp.route('/poll/<int:poll_id>/delete', methods=['POST'])
@admin_required
def poll_delete(poll_id):
    p = Poll.query.get_or_404(poll_id)
    PollOption.query.filter_by(poll_id=p.id).delete()
    db.session.delete(p)
    db.session.commit()
    flash('설문이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.poll_list'))


# ── 통계 - 기사출처 ──

@admin_bp.route('/stats/source')
@admin_required
def stats_source():
    stats = db.session.query(
        Article.source,
        db.func.count(Article.id).label('article_count')
    ).filter(Article.is_deleted == False, Article.source != '').group_by(
        Article.source
    ).order_by(db.func.count(Article.id).desc()).all()
    return render_template('admin/stats_source.html', stats=stats)


# ── 환경설정 - 메타태그/연재/권한 ──

@admin_bp.route('/settings/meta', methods=['GET', 'POST'])
@admin_required
def settings_meta():
    if request.method == 'POST':
        keys = ['meta_title', 'meta_description', 'meta_keywords', 'meta_og_image']
        for key in keys:
            setting = SiteSetting.query.filter_by(key=key).first()
            if not setting:
                setting = SiteSetting(key=key)
                db.session.add(setting)
            setting.value = request.form.get(key, '')
        db.session.commit()
        flash('메타태그 설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings_meta'))
    settings = {s.key: s for s in SiteSetting.query.all()}
    return render_template('admin/settings_meta.html', settings=settings)


@admin_bp.route('/settings/serial')
@admin_required
def settings_serial():
    serials = SerialCode.query.order_by(SerialCode.created_at.desc()).all()
    return render_template('admin/settings_serial.html', serials=serials)


@admin_bp.route('/settings/serial/add', methods=['POST'])
@admin_required
def serial_add():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    if code and name:
        if not SerialCode.query.filter_by(code=code).first():
            db.session.add(SerialCode(code=code, name=name))
            db.session.commit()
            flash('연재가 추가되었습니다.', 'success')
        else:
            flash('이미 존재하는 코드입니다.', 'error')
    return redirect(url_for('admin.settings_serial'))


@admin_bp.route('/settings/serial/<int:serial_id>/delete', methods=['POST'])
@admin_required
def serial_delete(serial_id):
    db.session.delete(SerialCode.query.get_or_404(serial_id))
    db.session.commit()
    flash('연재가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.settings_serial'))


@admin_bp.route('/settings/authority')
@admin_required
def settings_authority():
    members = AdminUser.query.order_by(AdminUser.created_at.desc()).all()
    return render_template('admin/settings_authority.html', members=members)


@admin_bp.route('/settings/authority/<int:member_id>/update', methods=['POST'])
@admin_required
def authority_update(member_id):
    m = AdminUser.query.get_or_404(member_id)
    m.level = request.form.get('level', 'reporter')
    db.session.commit()
    flash('권한이 변경되었습니다.', 'success')
    return redirect(url_for('admin.settings_authority'))


# ── 댓글설정 ──

@admin_bp.route('/settings/comment', methods=['GET', 'POST'])
@admin_required
def settings_comment():
    if request.method == 'POST':
        keys = ['comment_use', 'comment_login_required', 'comment_approval_required',
                'comment_max_length', 'comment_block_words',
                'comment_best_threshold', 'comment_best_count',
                'comment_show_name', 'comment_show_ip', 'comment_show_id',
                'comment_admin_name',
                'comment_profile_image', 'comment_captcha_use',
                'recaptcha_site_key', 'recaptcha_secret_key',
                'bbs_comment_use', 'bbs_comment_login_required']
        for key in keys:
            setting = SiteSetting.query.filter_by(key=key).first()
            if not setting:
                setting = SiteSetting(key=key)
                db.session.add(setting)
            setting.value = request.form.get(key, '')
        db.session.commit()
        flash('댓글 설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings_comment'))
    settings = {s.key: s for s in SiteSetting.query.all()}
    return render_template('admin/settings_comment.html', settings=settings)


# ── 주요일정 ──

@admin_bp.route('/schedules')
@admin_required
def schedule_list():
    schedules = Schedule.query.order_by(Schedule.event_date.desc()).all()
    return render_template('admin/schedule_list.html', schedules=schedules)


@admin_bp.route('/schedule/new', methods=['GET', 'POST'])
@admin_required
def schedule_new():
    if request.method == 'POST':
        return _save_schedule(None)
    return render_template('admin/schedule_form.html', schedule=None)


@admin_bp.route('/schedule/<int:schedule_id>/edit', methods=['GET', 'POST'])
@admin_required
def schedule_edit(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if request.method == 'POST':
        return _save_schedule(schedule)
    return render_template('admin/schedule_form.html', schedule=schedule)


@admin_bp.route('/schedule/<int:schedule_id>/category', methods=['POST'])
@admin_required
def schedule_update_category(schedule_id):
    """인라인 카테고리 수정 API"""
    schedule = Schedule.query.get_or_404(schedule_id)
    data = request.get_json(silent=True) or {}
    schedule.category = (data.get('category') or '').strip()
    db.session.commit()
    return jsonify({'ok': True, 'category': schedule.category})


@admin_bp.route('/schedule/<int:schedule_id>/date', methods=['POST'])
@admin_required
def schedule_update_date(schedule_id):
    """인라인 일시 수정 API"""
    schedule = Schedule.query.get_or_404(schedule_id)
    data = request.get_json(silent=True) or {}
    event_date_str = (data.get('event_date') or '').strip()
    end_date_str = (data.get('end_date') or '').strip()
    if event_date_str:
        fmt = '%Y-%m-%dT%H:%M' if 'T' in event_date_str else '%Y-%m-%d'
        schedule.event_date = datetime.strptime(event_date_str, fmt)
    if end_date_str:
        fmt = '%Y-%m-%dT%H:%M' if 'T' in end_date_str else '%Y-%m-%d'
        schedule.end_date = datetime.strptime(end_date_str, fmt)
    elif 'end_date' in data:
        schedule.end_date = None
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.route('/schedule/<int:schedule_id>/delete', methods=['POST'])
@admin_required
def schedule_delete(schedule_id):
    db.session.delete(Schedule.query.get_or_404(schedule_id))
    db.session.commit()
    flash('일정이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.schedule_list'))


def _save_schedule(schedule):
    is_new = schedule is None
    if is_new:
        schedule = Schedule()

    schedule.title = request.form.get('title', '').strip()
    schedule.description = request.form.get('description', '').strip()
    schedule.content = request.form.get('content', '').strip()
    schedule.location = request.form.get('location', '').strip()
    schedule.category = request.form.get('category', '').strip()
    schedule.link_url = request.form.get('link_url', '').strip()
    schedule.image_url = request.form.get('image_url', '').strip()
    schedule.is_active = request.form.get('is_active') == '1'

    event_date_str = request.form.get('event_date', '').strip()
    end_date_str = request.form.get('end_date', '').strip()
    if event_date_str:
        schedule.event_date = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M')
    end_date = None
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M')
    schedule.end_date = end_date

    if is_new:
        db.session.add(schedule)
    db.session.commit()
    flash('일정이 저장되었습니다.', 'success')
    return redirect(url_for('admin.schedule_list'))


# ── 메뉴얼 ──

@admin_bp.route('/manual')
@admin_required
def manual():
    return render_template('admin/manual.html')


# ── 뉴스레터 ──

@admin_bp.route('/newsletters')
@admin_required
def newsletter_list():
    newsletters = Newsletter.query.order_by(Newsletter.volume_number.desc()).all()
    return render_template('admin/newsletter_list.html', newsletters=newsletters)


@admin_bp.route('/newsletter/new', methods=['GET', 'POST'])
@admin_required
def newsletter_new():
    if request.method == 'POST':
        return _save_newsletter(None)
    max_vol = db.session.query(db.func.max(Newsletter.volume_number)).scalar() or 0
    next_vol = max_vol + 1
    return render_template('admin/newsletter_form.html', newsletter=None, next_vol=next_vol)


@admin_bp.route('/newsletter/<int:newsletter_id>/edit', methods=['GET', 'POST'])
@admin_required
def newsletter_edit(newsletter_id):
    nl = Newsletter.query.get_or_404(newsletter_id)
    if request.method == 'POST':
        return _save_newsletter(nl)
    return render_template('admin/newsletter_form.html', newsletter=nl, next_vol=nl.volume_number)


@admin_bp.route('/newsletter/<int:newsletter_id>/delete', methods=['POST'])
@admin_required
def newsletter_delete(newsletter_id):
    db.session.delete(Newsletter.query.get_or_404(newsletter_id))
    db.session.commit()
    flash('뉴스레터가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.newsletter_list'))


@admin_bp.route('/newsletter/<int:newsletter_id>/duplicate', methods=['POST'])
@admin_required
def newsletter_duplicate(newsletter_id):
    source = Newsletter.query.get_or_404(newsletter_id)
    max_vol = db.session.query(db.func.max(Newsletter.volume_number)).scalar() or 0
    new_vol = max_vol + 1
    new_nl = Newsletter(
        volume_number=new_vol,
        title=f'웰다잉뉴스 Weekly #{new_vol}',
        slug=f'weekly-{new_vol}',
        status='draft',
        briefing_title=source.briefing_title,
        briefing_image=source.briefing_image,
        briefing_content=source.briefing_content,
        briefing_article_id=source.briefing_article_id,
        briefing_visible=source.briefing_visible,
        sections_data=source.sections_data,
    )
    db.session.add(new_nl)
    db.session.commit()
    flash(f'#{source.volume_number} 뉴스레터가 #{new_vol}로 복제되었습니다.', 'success')
    return redirect(url_for('admin.newsletter_edit', newsletter_id=new_nl.id))


@admin_bp.route('/api/newsletter-article/<int:article_id>')
@admin_required
def api_newsletter_article(article_id):
    art = db.session.get(Article, article_id)
    if not art:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'id': art.id,
        'title': art.title,
        'summary': art.summary_text,
        'thumbnail': art.thumb_url,
        'author_name': art.author_name or '',
        'section_name': art.section.name if art.section else '',
        'created_at': (art.embargo_date or art.created_at).strftime('%Y.%m.%d') if (art.embargo_date or art.created_at) else '',
    })


def _parse_nl_section_items(prefix):
    """뉴스레터 focus/opinion 반복 아이템 파싱"""
    items = []
    types = request.form.getlist(f'{prefix}_item_type[]')
    article_ids = request.form.getlist(f'{prefix}_item_article_id[]')
    titles = request.form.getlist(f'{prefix}_item_title[]')
    summaries = request.form.getlist(f'{prefix}_item_summary[]')
    images = request.form.getlist(f'{prefix}_item_image[]')
    links = request.form.getlist(f'{prefix}_item_link[]')

    for i in range(len(types)):
        item_type = types[i].strip() if i < len(types) else 'custom'
        if item_type == 'article':
            aid = article_ids[i].strip() if i < len(article_ids) else ''
            if aid and aid.isdigit():
                items.append({'type': 'article', 'article_id': int(aid)})
        else:
            title = titles[i].strip() if i < len(titles) else ''
            if title:
                items.append({
                    'type': 'custom',
                    'title': title,
                    'summary': summaries[i].strip() if i < len(summaries) else '',
                    'image': images[i].strip() if i < len(images) else '',
                    'link': links[i].strip() if i < len(links) else '',
                })
    return items


def _save_newsletter(newsletter):
    is_new = newsletter is None
    if is_new:
        newsletter = Newsletter()

    newsletter.volume_number = int(request.form.get('volume_number', 1))
    newsletter.title = request.form.get('title', '').strip()
    newsletter.slug = request.form.get('slug', '').strip() or f"weekly-{newsletter.volume_number}"
    pub_date_str = request.form.get('publish_date', '').strip()
    newsletter.publish_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date() if pub_date_str else None
    newsletter.status = request.form.get('status', 'draft')

    # 브리핑 섹션
    newsletter.briefing_visible = request.form.get('briefing_visible') == '1'
    newsletter.briefing_title = request.form.get('briefing_title', '').strip()
    newsletter.briefing_image = request.form.get('briefing_image', '').strip()
    newsletter.briefing_content = request.form.get('briefing_content', '').strip()
    briefing_aid = request.form.get('briefing_article_id', '').strip()
    newsletter.briefing_article_id = int(briefing_aid) if briefing_aid and briefing_aid.isdigit() else None

    # sections JSON 조립
    sections = {}

    sections['focus'] = {
        'visible': request.form.get('focus_visible') == '1',
        'title': request.form.get('focus_title', '주간 포커스').strip(),
        'items': _parse_nl_section_items('focus'),
    }

    sections['opinion'] = {
        'visible': request.form.get('opinion_visible') == '1',
        'title': request.form.get('opinion_title', '주간 오피니언').strip(),
        'items': _parse_nl_section_items('opinion'),
    }

    sections['book'] = {
        'visible': request.form.get('book_visible') == '1',
        'title': request.form.get('book_section_title', '주간 추천 도서').strip(),
        'book_title': request.form.get('book_title', '').strip(),
        'author': request.form.get('book_author', '').strip(),
        'image': request.form.get('book_image', '').strip(),
        'description': request.form.get('book_description', '').strip(),
        'link': request.form.get('book_link', '').strip(),
    }

    video_items = []
    video_urls = request.form.getlist('video_url[]')
    video_titles = request.form.getlist('video_title[]')
    video_descs = request.form.getlist('video_desc[]')
    for i in range(len(video_urls)):
        url = video_urls[i].strip() if i < len(video_urls) else ''
        if url:
            video_items.append({
                'youtube_url': url,
                'title': video_titles[i].strip() if i < len(video_titles) else '',
                'description': video_descs[i].strip() if i < len(video_descs) else '',
            })
    sections['videos'] = {
        'visible': request.form.get('videos_visible') == '1',
        'title': request.form.get('videos_title', '주간 화제의 영상').strip(),
        'items': video_items,
    }

    sections['quote'] = {
        'visible': request.form.get('quote_visible') == '1',
        'title': request.form.get('quote_title', '이 주의 글귀').strip(),
        'text': request.form.get('quote_text', '').strip(),
        'author': request.form.get('quote_author', '').strip(),
    }

    ads = []
    for i in range(1, 5):
        ads.append({
            'position': i,
            'visible': request.form.get(f'ad_{i}_visible') == '1',
            'image': request.form.get(f'ad_{i}_image', '').strip(),
            'link': request.form.get(f'ad_{i}_link', '').strip(),
        })
    sections['ads'] = ads

    newsletter.sections = sections

    if is_new:
        db.session.add(newsletter)
    newsletter.updated_at = datetime.now()
    db.session.commit()
    flash('뉴스레터가 저장되었습니다.', 'success')
    return redirect(url_for('admin.newsletter_edit', newsletter_id=newsletter.id))


# ── 기자(관리자 사용자) 관리 ──────────────────────────────

@admin_bp.route('/reporters')
@admin_required
def reporter_list():
    users = AdminUser.query.order_by(AdminUser.name).all()
    return render_template('admin/reporter_list.html', users=users)


@admin_bp.route('/reporter/new', methods=['GET', 'POST'])
@admin_required
def reporter_new():
    if request.method == 'POST':
        return _save_reporter(None)
    return render_template('admin/reporter_form.html', user=None)


@admin_bp.route('/reporter/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def reporter_edit(user_id):
    user = AdminUser.query.get_or_404(user_id)
    if request.method == 'POST':
        return _save_reporter(user)
    return render_template('admin/reporter_form.html', user=user)


@admin_bp.route('/reporter/<int:user_id>/delete', methods=['POST'])
@admin_required
def reporter_delete(user_id):
    user = AdminUser.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('자기 자신은 삭제할 수 없습니다.', 'error')
        return redirect(url_for('admin.reporter_list'))
    db.session.delete(user)
    db.session.commit()
    flash(f'{user.name} 기자가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.reporter_list'))


def _save_reporter(user):
    is_new = user is None
    if is_new:
        user = AdminUser()

    login_id = request.form.get('user_id', '').strip()
    password = request.form.get('password', '').strip()
    name = request.form.get('name', '').strip()

    if not login_id or not name:
        flash('아이디와 이름은 필수입니다.', 'error')
        return redirect(request.referrer or url_for('admin.reporter_list'))

    if is_new:
        if not password:
            flash('비밀번호는 필수입니다.', 'error')
            return redirect(request.referrer or url_for('admin.reporter_list'))
        existing = AdminUser.query.filter_by(user_id=login_id).first()
        if existing:
            flash('이미 사용 중인 아이디입니다.', 'error')
            return redirect(request.referrer or url_for('admin.reporter_list'))
        user.user_id = login_id

    if password:
        user.password_hash = generate_password_hash(password)

    user.name = name
    user.email = request.form.get('email', '').strip()
    user.department = request.form.get('department', '').strip()
    user.level = request.form.get('level', 'reporter')
    user.is_active = request.form.get('is_active') == '1'

    # 프로필 사진
    if request.form.get('delete_photo') == '1':
        user.photo = ''
    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        from app.utils.cloud_storage import upload_file as upload_photo
        p_filename = f"{uuid.uuid4().hex}_{secure_filename(photo_file.filename)}"
        p_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], p_filename)
        photo_file.save(p_filepath)
        p_url = upload_photo(p_filepath, folder='welldying/authors')
        if p_url:
            user.photo = p_url
    # 크롭 위치
    photo_pos = request.form.get('photo_pos', '').strip()
    if photo_pos:
        user.photo_pos = photo_pos

    if is_new:
        db.session.add(user)
    db.session.commit()
    flash(f'{user.name} 기자가 {"등록" if is_new else "수정"}되었습니다.', 'success')
    return redirect(url_for('admin.reporter_list'))


# ===== 정보페이지 관리 =====

COM_PAGES_ADMIN = [
    {'code': 'com-1',       'title': '인사말(매체소개)',    'group': '매체소개',    'template': 'com/company.html'},
    {'code': 'com-2',       'title': '찾아오시는길',        'group': '매체소개',    'template': 'com/map.html'},
    {'code': 'service',     'title': '이용약관',            'group': '약관 및 정책', 'template': 'com/service.html'},
    {'code': 'privacy',     'title': '개인정보처리방침',    'group': '약관 및 정책', 'template': 'com/privacy.html'},
    {'code': 'youthpolicy', 'title': '청소년보호정책',      'group': '약관 및 정책', 'template': 'com/youthpolicy.html'},
    {'code': 'copyright',   'title': '저작권보호정책',      'group': '약관 및 정책', 'template': 'com/copyright.html'},
    {'code': 'emailno',     'title': '이메일무단수집거부',  'group': '약관 및 정책', 'template': 'com/emailno.html'},
]


@admin_bp.route('/com-pages')
@admin_required
def com_page_list():
    """정보페이지 목록"""
    pages = []
    for p in COM_PAGES_ADMIN:
        setting = SiteSetting.query.filter_by(key=f'com_page_{p["code"]}').first()
        pages.append({
            'code': p['code'],
            'title': p['title'],
            'group': p['group'],
            'has_db_content': bool(setting and setting.value),
        })
    return render_template('admin/com_page_list.html', pages=pages)


@admin_bp.route('/com-pages/<page_code>/edit', methods=['GET', 'POST'])
@admin_required
def com_page_edit(page_code):
    """정보페이지 편집"""
    page_info = next((p for p in COM_PAGES_ADMIN if p['code'] == page_code), None)
    if not page_info:
        flash('존재하지 않는 페이지입니다.', 'error')
        return redirect(url_for('admin.com_page_list'))

    db_key = f'com_page_{page_code}'

    if request.method == 'POST':
        content = request.form.get('content', '')
        setting = SiteSetting.query.filter_by(key=db_key).first()
        if not setting:
            setting = SiteSetting(key=db_key, description=page_info['title'])
            db.session.add(setting)
        setting.value = content
        db.session.commit()
        flash(f'"{page_info["title"]}" 페이지가 저장되었습니다.', 'success')
        return redirect(url_for('admin.com_page_list'))

    # GET: DB 내용 또는 템플릿 파일 내용 로드
    setting = SiteSetting.query.filter_by(key=db_key).first()
    if setting and setting.value:
        content = setting.value
    else:
        # 템플릿 파일에서 기본 내용 로드
        template_path = os.path.join(
            current_app.root_path, 'public', 'templates', 'public', page_info['template']
        )
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            content = ''

    return render_template('admin/com_page_edit.html',
                           page_info=page_info, page_code=page_code, content=content)


@admin_bp.route('/com-pages/<page_code>/reset', methods=['POST'])
@admin_required
def com_page_reset(page_code):
    """정보페이지 초기화 (DB 내용 삭제, 템플릿 파일로 복원)"""
    page_info = next((p for p in COM_PAGES_ADMIN if p['code'] == page_code), None)
    if not page_info:
        flash('존재하지 않는 페이지입니다.', 'error')
        return redirect(url_for('admin.com_page_list'))

    setting = SiteSetting.query.filter_by(key=f'com_page_{page_code}').first()
    if setting:
        db.session.delete(setting)
        db.session.commit()
    flash(f'"{page_info["title"]}" 페이지가 기본값으로 초기화되었습니다.', 'success')
    return redirect(url_for('admin.com_page_list'))


# ── AI 큐레이션 & 초안 ──

@admin_bp.route('/curation')
@admin_required
def curation():
    """AI 큐레이션 페이지"""
    return render_template('admin/curation.html')


@admin_bp.route('/api/curation/articles')
@admin_required
def api_curation_articles():
    """Supabase에서 수집 기사 조회 (AJAX)"""
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    country = request.args.get('country', '')
    source_table = request.args.get('source', 'news')  # news 또는 collect

    if not start_date or not end_date:
        return jsonify({'error': '날짜를 선택하세요.'}), 400

    try:
        from app.services.supabase_client import fetch_news_articles, fetch_collected_articles
        if source_table == 'collect':
            articles = fetch_collected_articles(start_date, end_date, country or None)
        else:
            articles = fetch_news_articles(start_date, end_date, country or None)
        return jsonify({'articles': articles, 'count': len(articles)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/curation/classify', methods=['POST'])
@admin_required
def curation_classify():
    """Step 1: 선택된 기사를 AiDraft로 생성 후 Haiku 분류 트리거"""
    data = request.get_json()
    articles = data.get('articles', [])
    if not articles:
        return jsonify({'error': '기사를 선택하세요.'}), 400

    draft_ids = []
    for a in articles:
        draft = AiDraft(
            source_news_ids=json.dumps([a.get('id', '')]),
            source_data=json.dumps(a, ensure_ascii=False),
            original_url=a.get('link', ''),
            title=a.get('title_ko') or a.get('title', ''),
            status=STATUS_PENDING,
            created_by=current_user.id,
        )
        db.session.add(draft)
        db.session.flush()
        draft_ids.append(draft.id)
    db.session.commit()

    from app.services.background_queue import enqueue_task
    enqueue_task('classify', draft_ids)

    return jsonify({'message': f'{len(draft_ids)}건 분류 시작', 'draft_ids': draft_ids})


@admin_bp.route('/curation/generate', methods=['POST'])
@admin_required
def curation_generate():
    """Step 0~4: 선택된 초안의 생성 파이프라인 트리거"""
    data = request.get_json()
    draft_ids = data.get('draft_ids', [])
    if not draft_ids:
        return jsonify({'error': '초안을 선택하세요.'}), 400

    # 상태 확인 — 분류 완료되고 사용가능한 건만 (단일 쿼리)
    valid_ids = [r.id for r in db.session.query(AiDraft.id).filter(
        AiDraft.id.in_(draft_ids),
        AiDraft.status == STATUS_PENDING,
        AiDraft.grade != '',
    ).all()]
    if not valid_ids:
        return jsonify({'error': '생성 가능한 초안이 없습니다.'}), 400

    from app.services.background_queue import enqueue_task
    enqueue_task('generate', valid_ids)

    return jsonify({'message': f'{len(valid_ids)}건 생성 시작', 'draft_ids': valid_ids})


@admin_bp.route('/ai-drafts')
@admin_required
def ai_draft_list():
    """AI 초안 목록"""
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    query = AiDraft.query.order_by(AiDraft.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)

    pagination = query.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/ai_draft_list.html',
                           drafts=pagination.items, pagination=pagination,
                           status_filter=status_filter)


@admin_bp.route('/ai-draft/<int:draft_id>')
@admin_required
def ai_draft_edit(draft_id):
    """AI 초안 편집 페이지"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        flash('초안을 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin.ai_draft_list'))

    sections = Section.query.order_by(Section.sort_order).all()

    # JSON 데이터 파싱
    article_result = {}
    fact_package = {}
    validation = {}
    related_urls = []
    try:
        if draft.article_result:
            article_result = json.loads(draft.article_result)
        if draft.fact_package:
            fact_package = json.loads(draft.fact_package)
        if draft.validation_result:
            validation = json.loads(draft.validation_result)
        if draft.related_urls:
            related_urls = json.loads(draft.related_urls)
    except (json.JSONDecodeError, TypeError):
        pass

    return render_template('admin/ai_draft_edit.html',
                           draft=draft, sections=sections,
                           article_result=article_result,
                           fact_package=fact_package,
                           validation=validation,
                           related_urls=related_urls)


@admin_bp.route('/ai-draft/<int:draft_id>/update', methods=['POST'])
@admin_required
def ai_draft_update(draft_id):
    """AI 초안 수정 저장"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        flash('초안을 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin.ai_draft_list'))

    draft.title = request.form.get('title', '').strip()
    draft.subtitle = request.form.get('subtitle', '')
    draft.content = request.form.get('content', '')
    draft.summary = request.form.get('summary', '')
    draft.keywords = request.form.get('keywords', '')
    draft.author_name = request.form.get('author_name', '웰다잉뉴스')
    draft.source_text = request.form.get('source_text', '')
    draft.suggested_section_id = request.form.get('section_id', type=int)
    draft.suggested_subsection_id = request.form.get('subsection_id', type=int)
    db.session.commit()

    flash('초안이 저장되었습니다.', 'success')
    return redirect(url_for('admin.ai_draft_edit', draft_id=draft_id))


@admin_bp.route('/ai-draft/<int:draft_id>/publish', methods=['POST'])
@admin_required
def ai_draft_publish(draft_id):
    """AI 초안 → 기사로 발행"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        flash('초안을 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin.ai_draft_list'))

    article = Article(
        title=draft.title,
        subtitle=draft.subtitle,
        content=draft.content,
        summary=draft.summary,
        keyword=draft.keywords,
        author_name=draft.author_name,
        source=draft.source_text,
        section_id=draft.suggested_section_id,
        subsection_id=draft.suggested_subsection_id,
        recognition='C',  # 미승인 상태로 발행
        level='B',
    )
    db.session.add(article)
    db.session.flush()

    draft.article_id = article.id
    draft.status = STATUS_PUBLISHED
    draft.published_at = datetime.now()
    db.session.commit()

    flash(f'기사가 발행되었습니다. (기사 ID: {article.id}, 미승인 상태)', 'success')
    return redirect(url_for('admin.article_edit', article_id=article.id))


@admin_bp.route('/ai-draft/<int:draft_id>/reject', methods=['POST'])
@admin_required
def ai_draft_reject(draft_id):
    """AI 초안 반려"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        flash('초안을 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin.ai_draft_list'))

    draft.status = STATUS_REJECTED
    db.session.commit()
    flash('초안이 반려되었습니다.', 'success')
    return redirect(url_for('admin.ai_draft_list'))


@admin_bp.route('/ai-draft/<int:draft_id>/delete', methods=['POST'])
@admin_required
def ai_draft_delete(draft_id):
    """AI 초안 삭제"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        flash('초안을 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin.ai_draft_list'))

    db.session.delete(draft)
    db.session.commit()
    flash('초안이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.ai_draft_list'))


@admin_bp.route('/api/ai-drafts/progress')
@admin_required
def api_ai_draft_progress():
    """큐 진행상황 + 최근 초안 상태 (폴링용)"""
    from app.services.background_queue import get_queue_status
    queue_status = get_queue_status()

    # 최근 초안 상태 (가벼운 컬럼만 조회)
    recent = db.session.query(
        AiDraft.id, AiDraft.title, AiDraft.status, AiDraft.grade, AiDraft.skip_reason
    ).filter(
        AiDraft.status.in_(STALE_STATUSES + [STATUS_PENDING])
    ).order_by(AiDraft.created_at.desc()).limit(50).all()

    drafts_info = [{
        'id': d.id,
        'title': d.title or '',
        'status': d.status,
        'grade': d.grade,
        'skip_reason': d.skip_reason,
    } for d in recent]

    return jsonify({
        'queue': queue_status,
        'drafts': drafts_info,
    })
