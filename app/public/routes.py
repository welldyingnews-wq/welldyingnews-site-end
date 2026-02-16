from datetime import datetime, timedelta

from flask import render_template, request, abort, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from app.models import db, Section, SubSection, Article, ArticleRelation, ArticleComment, SiteSetting
from app.public import public_bp


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
    return {'nav_sections': sections, 'updated_time': updated_time}


@public_bp.route('/')
def index():
    query = _get_published_query()

    # 헤드라인/중요 기사 (상단 skin-3 영역: 1 large + 2 small)
    headline_articles = query.filter(
        Article.level.in_(['T', 'I'])
    ).order_by(Article.created_at.desc()).limit(3).all()

    # 부족하면 최신 기사로 채움
    if len(headline_articles) < 3:
        existing_ids = [a.id for a in headline_articles]
        extra = query.filter(
            ~Article.id.in_(existing_ids) if existing_ids else True
        ).order_by(Article.created_at.desc()).limit(3 - len(headline_articles)).all()
        headline_articles.extend(extra)

    # 최신 기사 (skin-12 그리드: 8개)
    latest_articles = query.order_by(Article.created_at.desc()).limit(8).all()

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
        ).order_by(Article.created_at.desc()).limit(4).all()
        if articles:
            section_articles[sub] = articles

    # 오피니언 (사이드바: 4개)
    opinion_section = Section.query.filter_by(code='S1N2').first()
    opinion_articles = []
    if opinion_section:
        opinion_articles = query.filter(
            Article.section_id == opinion_section.id
        ).order_by(Article.created_at.desc()).limit(4).all()

    return render_template('public/index.html',
                           headline_articles=headline_articles,
                           latest_articles=latest_articles,
                           popular_articles=popular_articles,
                           section_articles=section_articles,
                           opinion_articles=opinion_articles)


def _get_sidebar_data():
    """사이드바 공통 데이터: 오피니언 + 많이 본 뉴스"""
    query = _get_published_query()
    opinion_section = Section.query.filter_by(code='S1N2').first()
    sidebar_opinion = []
    if opinion_section:
        sidebar_opinion = query.filter(
            Article.section_id == opinion_section.id
        ).order_by(Article.created_at.desc()).limit(4).all()
    sidebar_popular = query.order_by(Article.view_count.desc()).limit(5).all()
    return sidebar_opinion, sidebar_popular


@public_bp.route('/news/articleList.html')
def article_list():
    page = request.args.get('page', 1, type=int)
    sc_section_code = request.args.get('sc_section_code', '')
    sc_sub_section_code = request.args.get('sc_sub_section_code', '')
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
            query = query.filter(Article.section_id == section.id)

    if sc_word:
        query = query.filter(
            db.or_(Article.title.contains(sc_word), Article.content.contains(sc_word))
        )

    pagination = query.order_by(Article.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    sidebar_opinion, sidebar_popular = _get_sidebar_data()

    return render_template('public/article_list.html',
                           articles=pagination.items,
                           pagination=pagination,
                           section=section,
                           subsection=subsection,
                           sc_section_code=sc_section_code,
                           sc_sub_section_code=sc_sub_section_code,
                           sc_word=sc_word,
                           view_type=view_type,
                           sidebar_opinion=sidebar_opinion,
                           sidebar_popular=sidebar_popular)


@public_bp.route('/news/articleView.html')
def article_view():
    idxno = request.args.get('idxno', 0, type=int)
    if not idxno:
        abort(404)

    article = Article.query.get_or_404(idxno)
    if article.is_deleted or article.recognition != 'E':
        abort(404)

    # 조회수 증가
    article.view_count += 1
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
            ).order_by(Article.created_at.desc()).limit(5).all()

    # 이전/다음 기사
    prev_article = _get_published_query().filter(
        Article.id < article.id
    ).order_by(Article.id.desc()).first()
    next_article = _get_published_query().filter(
        Article.id > article.id
    ).order_by(Article.id.asc()).first()

    sidebar_opinion, sidebar_popular = _get_sidebar_data()

    # 댓글
    comment_use = _get_setting('comment_use', 'Y')
    comment_max_length = int(_get_setting('comment_max_length', '500') or 500)
    comments = []
    comment_count = 0
    if comment_use != 'N':
        comments = article.comments.filter_by(is_hidden=False).order_by(
            ArticleComment.created_at.desc()
        ).all()
        comment_count = len(comments)

    return render_template('public/article_view.html',
                           article=article,
                           related_articles=related,
                           prev_article=prev_article,
                           next_article=next_article,
                           sidebar_opinion=sidebar_opinion,
                           sidebar_popular=sidebar_popular,
                           comments=comments,
                           comment_count=comment_count,
                           comment_use=comment_use,
                           comment_max_length=comment_max_length)


def _get_setting(key, default=''):
    s = SiteSetting.query.filter_by(key=key).first()
    return s.value if s and s.value else default


@public_bp.route('/news/comment/write', methods=['POST'])
def comment_write():
    article_id = request.form.get('article_id', 0, type=int)
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

    comment = ArticleComment(
        article_id=article_id,
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

    if not comment.password or not check_password_hash(comment.password, password):
        flash('비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('public.article_view', idxno=article_id) + '#comment')

    db.session.delete(comment)
    db.session.commit()

    return redirect(url_for('public.article_view', idxno=article_id) + '#comment')
