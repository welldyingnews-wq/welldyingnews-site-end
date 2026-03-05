from datetime import datetime, timedelta

import re

from flask import render_template, request, abort, redirect, url_for, flash, session, jsonify, send_from_directory, current_app
from werkzeug.security import generate_password_hash, check_password_hash

import json
from app.models import (db, Section, SubSection, Article, ArticleRelation, ArticleComment,
                        CommentVote, SiteSetting, Board, BoardPost, BoardReply,
                        BoardReplyVote, Banner, article_extra_subsection,
                        EventRequest, Popup, Poll, PollOption, Member,
                        DailyStat, PageView, VisitorLog,
                        NewsletterSubscriber, Newsletter, Schedule, Resource,
                        AdminUser)
from app import limiter
from app.public import public_bp
from flask_login import current_user



@public_bp.route('/naver545517745dfc7af9299e6ea019861bf4.html')
def naver_verify():
    return send_from_directory(current_app.static_folder, 'naver545517745dfc7af9299e6ea019861bf4.html')


@public_bp.route('/favicon.ico')
def favicon_ico():
    return send_from_directory(current_app.static_folder, 'images/favicon.ico', mimetype='image/x-icon')


@public_bp.route('/robots.txt')
def robots_txt():
    content = """User-agent: *
Allow: /
Disallow: /admin/

Sitemap: https://www.welldyingnews.com/sitemap.xml
"""
    return current_app.response_class(content, mimetype='text/plain')


@public_bp.route('/sitemap.xml')
def sitemap_xml():
    from flask import make_response
    now = datetime.now()
    articles = Article.query.filter(
        Article.is_deleted == False,  # noqa: E712
        Article.recognition == 'E',
        db.or_(Article.embargo_date == None, Article.embargo_date <= now)  # noqa: E711
    ).order_by(Article.updated_at.desc()).limit(5000).all()
    sections = Section.query.order_by(Section.sort_order).all()

    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # 메인 페이지
    xml.append('  <url>')
    xml.append('    <loc>https://www.welldyingnews.com/</loc>')
    xml.append('    <changefreq>hourly</changefreq>')
    xml.append('    <priority>1.0</priority>')
    xml.append('  </url>')

    # 섹션 목록 페이지
    for section in sections:
        xml.append('  <url>')
        xml.append(f'    <loc>https://www.welldyingnews.com/news/articleList.html?sc_section_code={section.code}&amp;view_type=sm</loc>')
        xml.append('    <changefreq>daily</changefreq>')
        xml.append('    <priority>0.8</priority>')
        xml.append('  </url>')

    # 기사 상세 페이지
    for article in articles:
        lastmod = article.updated_at.strftime('%Y-%m-%d') if article.updated_at else article.created_at.strftime('%Y-%m-%d')
        xml.append('  <url>')
        xml.append(f'    <loc>https://www.welldyingnews.com/news/articleView.html?idxno={article.id}</loc>')
        xml.append(f'    <lastmod>{lastmod}</lastmod>')
        xml.append('    <changefreq>monthly</changefreq>')
        xml.append('    <priority>0.6</priority>')
        xml.append('  </url>')

    xml.append('</urlset>')

    response = make_response('\n'.join(xml))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    return response


@public_bp.route('/rss')
@public_bp.route('/rss.xml')
def rss_feed():
    """RSS 2.0 피드 — 네이버 뉴스 제휴용"""
    from flask import make_response
    import html as html_lib
    from email.utils import format_datetime
    from datetime import timezone, timedelta

    sc_section_code = request.args.get('sc_section_code', '')
    site_url = current_app.config.get('SITE_URL', 'https://www.welldyingnews.com')

    now = datetime.now()
    query = Article.query.filter(
        Article.is_deleted == False,  # noqa: E712
        Article.recognition == 'E',
        db.or_(Article.embargo_date == None, Article.embargo_date <= now)  # noqa: E711
    )

    section = None
    if sc_section_code:
        section = Section.query.filter_by(code=sc_section_code).first()
        if section:
            query = query.filter(Article.section_id == section.id)

    articles = query.order_by(
        db.func.coalesce(Article.embargo_date, Article.created_at).desc()
    ).limit(50).all()

    channel_title = '웰다잉뉴스'
    if section:
        channel_title += f' - {section.name}'

    kst = timezone(timedelta(hours=9))

    def to_rfc2822(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=kst)
        return format_datetime(dt)

    def strip_html(text):
        if not text:
            return ''
        cleaned = re.sub(r'<[^>]+>', '', text)
        return html_lib.unescape(cleaned).strip()

    rss_self_url = f'{site_url}/rss'
    if sc_section_code:
        rss_self_url += f'?sc_section_code={sc_section_code}'

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'  <title>{channel_title}</title>',
        f'  <link>{site_url}</link>',
        '  <description>호스피스, 사전연명의료의향서, 연명의료결정, 조력사망, 장례, 애도, 고독사, 돌봄 등 생애말기 전 주제를 취재하여 존엄한 마무리를 준비할 수 있도록 돕는 미디어</description>',
        '  <language>ko</language>',
        f'  <atom:link href="{rss_self_url}" rel="self" type="application/rss+xml" />',
    ]

    if articles:
        pub_date = articles[0].embargo_date or articles[0].created_at
        xml_parts.append(f'  <lastBuildDate>{to_rfc2822(pub_date)}</lastBuildDate>')

    for article in articles:
        pub_date = article.embargo_date or article.created_at
        article_url = f'{site_url}/news/articleView.html?idxno={article.id}'
        description = strip_html(article.summary_text)

        category_parts = []
        if article.section:
            category_parts.append(article.section.name)
        if article.subsection:
            category_parts.append(article.subsection.name)
        category_name = ' > '.join(category_parts)

        xml_parts.append('  <item>')
        xml_parts.append(f'    <title><![CDATA[{article.title}]]></title>')
        xml_parts.append(f'    <link>{article_url}</link>')
        xml_parts.append(f'    <description><![CDATA[{description}]]></description>')
        xml_parts.append(f'    <pubDate>{to_rfc2822(pub_date)}</pubDate>')
        xml_parts.append(f'    <guid isPermaLink="true">{article_url}</guid>')
        if article.author_name:
            author_email = article.author_email or 'welldyingnews@naver.com'
            xml_parts.append(f'    <author>{author_email} ({article.author_name})</author>')
        if category_name:
            xml_parts.append(f'    <category><![CDATA[{category_name}]]></category>')
        xml_parts.append('  </item>')

    xml_parts.append('</channel>')
    xml_parts.append('</rss>')

    response = make_response('\n'.join(xml_parts))
    response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=600'
    return response


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
        current_member = db.session.get(Member, member_id)
    # 헤더 명언
    quotes_setting = SiteSetting.query.filter_by(key='header_quotes').first()
    header_quotes = []
    if quotes_setting and quotes_setting.value:
        header_quotes = [q.strip() for q in quotes_setting.value.split('\n') if q.strip()]
    if not header_quotes:
        header_quotes = [
            '잘 보낸 하루가 편안한 잠을 주듯이<br>잘 쓰인 일생은 평안한 죽음을 준다.',
            '사람은 어떻게 죽느냐가 문제가 아니라<br>어떻게 사느냐가 문제다.',
            '항상 죽을 각오를 하고 있는<br>사람만이 참으로 자유로운 인간이다.',
            '죽음은 마지막 성장의 기회다.',
            '인생은 입구에서 볼 때만 멀고 아늑하다.<br>인생은 출구에서 볼 때는 오히려 너무 짧다.',
            '삶을 깊이 이해하면 할수록<br>죽음으로 인한 슬픔은 그만큼 줄어들 것입니다.',
            '죽음을 알려고 하지 말고<br>내가 어디에서 왔는지를 알아야 한다.',
        ]
    ga4_setting = SiteSetting.query.filter_by(key='ga4_measurement_id').first()
    ga4_id = ga4_setting.value.strip() if ga4_setting and ga4_setting.value else ''

    # 푸터 서브섹션 (뉴스 섹션 하위 16개)
    news_section = Section.query.filter_by(code='S1N1').first()
    if news_section:
        footer_subsections = SubSection.query.filter_by(section_id=news_section.id).order_by(SubSection.sort_order).all()
    else:
        footer_subsections = SubSection.query.order_by(SubSection.sort_order).limit(16).all()

    site_url = current_app.config.get('SITE_URL', 'https://www.welldyingnews.com')

    return {'nav_sections': sections, 'nav_boards': boards, 'updated_time': updated_time,
            'banners': banners_by_pos, 'popups': active_popups, 'is_mobile': is_mobile,
            'current_member': current_member, 'header_quotes': header_quotes,
            'ga4_id': ga4_id, 'footer_subsections': footer_subsections,
            'site_url': site_url}


def _detect_device():
    """User-Agent에서 디바이스 유형 감지"""
    ua = request.headers.get('User-Agent', '')
    if re.search(r'iPad|Tablet|PlayBook|Silk', ua, re.I):
        return 'tablet'
    if re.search(r'Mobile|Android|iPhone|iPod|Opera Mini|IEMobile', ua, re.I):
        return 'mobile'
    return 'pc'


def _classify_referrer(referrer_url):
    """Referer 헤더에서 유입경로 분류"""
    if not referrer_url:
        return 'direct'
    ref = referrer_url.lower()
    if 'naver.com' in ref or 'naver.me' in ref:
        return 'naver'
    if 'google.' in ref or 'googleapis.com' in ref:
        return 'google'
    if 'daum.net' in ref or 'daum.co.kr' in ref:
        return 'daum'
    if 'facebook.com' in ref or 'fb.com' in ref or 'fbcdn.net' in ref:
        return 'facebook'
    if 'kakao' in ref:
        return 'kakao'
    if request.host and request.host in ref:
        return 'direct'
    return 'other'


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
        referrer = _classify_referrer(request.referrer)
        log = VisitorLog(ip_address=ip, date=today, article_id=None,
                         user_agent=device, referrer_source=referrer)
        db.session.add(log)
        # DailyStat UV 증가
        stat = DailyStat.query.filter_by(date=today).first()
        if not stat:
            stat = DailyStat(date=today, page_views=0, unique_visitors=0, article_views=0)
            db.session.add(stat)
            db.session.flush()
        stat.unique_visitors += 1
        db.session.commit()


@public_bp.route('/main1/')
def index_main1():
    return redirect(url_for('public.index'), code=301)


@public_bp.route('/v1/')
def index_v1():
    return redirect(url_for('public.index'), code=301)


def _build_index_context(hero_slots=4):
    """메인 페이지 공통 데이터 조회. hero_slots: 1면 헤드 기사 수"""
    query = _get_published_query()

    # 1면 헤드 기사
    headline_articles = []
    for i in range(1, hero_slots + 1):
        setting = SiteSetting.query.filter_by(key=f'hero_slot_{i}').first()
        if setting and setting.value and setting.value.strip().isdigit():
            art = query.filter(Article.id == int(setting.value)).first()
            if art:
                headline_articles.append(art)
    if len(headline_articles) < hero_slots:
        existing_ids = [a.id for a in headline_articles]
        auto = query.filter(
            Article.level.in_(['T', 'I']),
            ~Article.id.in_(existing_ids) if existing_ids else True
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(hero_slots - len(headline_articles)).all()
        headline_articles.extend(auto)
    if len(headline_articles) < hero_slots:
        existing_ids = [a.id for a in headline_articles]
        extra = query.filter(
            ~Article.id.in_(existing_ids) if existing_ids else True
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(hero_slots - len(headline_articles)).all()
        headline_articles.extend(extra)

    # 주요 기사 (8개) — 수동 설정 우선, 부족하면 최신 기사로 채움
    featured_setting = SiteSetting.query.filter_by(key='featured_article_ids').first()
    manual_featured = []
    if featured_setting and featured_setting.value:
        for aid in featured_setting.value.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = query.filter(Article.id == int(aid)).first()
                if art:
                    manual_featured.append(art)
    if manual_featured:
        latest_articles = manual_featured[:8]
        if len(latest_articles) < 8:
            existing_ids = [a.id for a in latest_articles]
            fill = query.filter(
                ~Article.id.in_(existing_ids)
            ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(8 - len(latest_articles)).all()
            latest_articles.extend(fill)
    else:
        latest_articles = query.order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(8).all()

    # 많이 본 뉴스 — 수동 설정 우선, 없으면 자동
    popular_setting = SiteSetting.query.filter_by(key='popular_article_ids').first()
    manual_popular = []
    if popular_setting and popular_setting.value:
        for aid in popular_setting.value.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art and not art.is_deleted and art.recognition == 'E':
                    manual_popular.append(art)

    weekly_setting = SiteSetting.query.filter_by(key='popular_weekly_article_ids').first()
    manual_weekly = []
    if weekly_setting and weekly_setting.value:
        for aid in weekly_setting.value.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art and not art.is_deleted and art.recognition == 'E':
                    manual_weekly.append(art)

    if manual_popular:
        popular_today = manual_popular[:5]
    else:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        popular_today = query.filter(
            Article.created_at >= today_start
        ).order_by(Article.view_count.desc()).limit(5).all()

    if manual_weekly:
        popular_week = manual_weekly[:5]
    else:
        popular_week = query.order_by(Article.view_count.desc()).limit(5).all()

    # 섹션별 최신 기사
    section_articles = {}
    key_subsections = SubSection.query.join(Section).filter(
        Section.code == 'S1N1'
    ).order_by(SubSection.sort_order).all()
    for sub in key_subsections[:16]:
        articles = query.filter(
            db.or_(
                Article.subsection_id == sub.id,
                Article.id.in_(
                    db.session.query(article_extra_subsection.c.article_id).filter(
                        article_extra_subsection.c.subsection_id == sub.id
                    )
                )
            )
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()
        if articles:
            section_articles[sub] = articles

    opinion_section = Section.query.filter_by(code='S1N2').first()
    opinion_articles = []
    if opinion_section:
        opinion_articles = query.filter(
            Article.section_id == opinion_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()

    library_section = Section.query.filter_by(code='S1N4').first()
    library_articles = []
    if library_section:
        library_articles = query.filter(
            Article.section_id == library_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(5).all()

    schedules = Schedule.query.filter_by(is_active=True).order_by(
        Schedule.event_date.desc()
    ).limit(5).all()

    active_poll = Poll.query.filter_by(is_active=True).order_by(Poll.created_at.desc()).first()

    book_subsection = SubSection.query.filter_by(code='S2N17').first()
    book_articles = []
    if book_subsection:
        book_articles = query.filter(
            Article.subsection_id == book_subsection.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(10).all()

    tv_section = Section.query.filter_by(code='S1N3').first()
    tv_articles = []
    if tv_section:
        tv_articles = query.filter(
            Article.section_id == tv_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(8).all()

    popular_articles = popular_today if popular_today else popular_week

    return dict(
        headline_articles=headline_articles,
        latest_articles=latest_articles,
        popular_today=popular_today,
        popular_week=popular_week,
        popular_articles=popular_articles,
        section_articles=section_articles,
        opinion_articles=opinion_articles,
        library_articles=library_articles,
        schedules=schedules,
        active_poll=active_poll,
        book_articles=book_articles,
        tv_articles=tv_articles,
    )


def _build_bottom_section_articles():
    """하단 섹션별 기사 (뉴스 카테고리의 서브섹션별 최신 4개씩)"""
    from collections import OrderedDict
    query = _get_published_query()
    bottom = OrderedDict()
    news_section = Section.query.filter_by(code='S1N1').first()
    if news_section:
        for sub in SubSection.query.filter_by(section_id=news_section.id).order_by(SubSection.sort_order).all():
            arts = query.filter(
                Article.subsection_id == sub.id
            ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()
            if arts:
                bottom[sub] = arts
    return bottom


@public_bp.route('/')
def index():
    ctx = _build_index_context(hero_slots=4)
    ctx['bottom_section_articles'] = _build_bottom_section_articles()
    return render_template('public/index.html', **ctx)


@public_bp.route('/v2/')
def index_v2():
    ctx = _build_index_context(hero_slots=3)
    return render_template('public/index_v2.html', **ctx)


def _get_sidebar_data():
    """사이드바 공통 데이터: 오피니언 + 많이 본 뉴스 (오늘/주간)"""
    query = _get_published_query()
    opinion_section = Section.query.filter_by(code='S1N2').first()
    sidebar_opinion = []
    if opinion_section:
        sidebar_opinion = query.filter(
            Article.section_id == opinion_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()

    # 대시보드에서 수동 선택한 기사 우선
    popular_setting = SiteSetting.query.filter_by(key='popular_article_ids').first()
    manual_popular = []
    if popular_setting and popular_setting.value:
        for aid in popular_setting.value.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art and not art.is_deleted and art.recognition == 'E':
                    manual_popular.append(art)

    weekly_setting = SiteSetting.query.filter_by(key='popular_weekly_article_ids').first()
    manual_weekly = []
    if weekly_setting and weekly_setting.value:
        for aid in weekly_setting.value.split(','):
            aid = aid.strip()
            if aid.isdigit():
                art = db.session.get(Article, int(aid))
                if art and not art.is_deleted and art.recognition == 'E':
                    manual_weekly.append(art)

    if manual_popular:
        popular_today = manual_popular[:5]
    else:
        # 많이 본 뉴스: 오늘
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        popular_today = _get_published_query().filter(
            Article.created_at >= today_start
        ).order_by(Article.view_count.desc()).limit(5).all()

    if manual_weekly:
        popular_week = manual_weekly[:5]
    else:
        # 많이 본 뉴스: 주간
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
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
    default_view = '' if sc_section_code == 'S1N4' else 'sm'
    view_type = request.args.get('view_type', default_view)

    query = _get_published_query()

    section = None
    subsection = None

    if sc_sub_section_code:
        subsection = SubSection.query.filter_by(code=sc_sub_section_code).first()
        if subsection:
            from app.models import article_extra_subsection
            query = query.filter(db.or_(
                Article.subsection_id == subsection.id,
                Article.id.in_(
                    db.session.query(article_extra_subsection.c.article_id).filter(
                        article_extra_subsection.c.subsection_id == subsection.id
                    )
                )
            ))
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

    # 검색어가 있으면 일정도 함께 검색
    schedule_results = []
    if sc_word:
        schedule_results = Schedule.query.filter(
            Schedule.is_active == True,
            Schedule.title.contains(sc_word)
        ).order_by(Schedule.event_date.desc()).limit(5).all()

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
                           popular_week=popular_week,
                           schedule_results=schedule_results)


@public_bp.route('/news/articleView.html')
def article_view():
    idxno = request.args.get('idxno', 0, type=int)
    if not idxno:
        abort(404)

    # ── 301 리다이렉트: 원본 CMS 기사 ID → 새 DB ID ──
    # DB 우선 조회: 새 DB에 해당 ID 기사가 있으면 바로 표시 (내부 링크 정상 작동)
    # DB에 없을 때만 마이그레이션 매핑으로 301 리다이렉트
    article = db.session.get(Article, idxno)
    if article is None or article.is_deleted or article.recognition != 'E':
        redirect_map = current_app.config.get('ARTICLE_ID_REDIRECT_MAP', {})
        new_id = redirect_map.get(idxno)
        if new_id is not None and new_id != idxno:
            return redirect(
                url_for('public.article_view', idxno=new_id),
                code=301
            )
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
        referrer = _classify_referrer(request.referrer)
        db.session.add(VisitorLog(ip_address=ip, date=today, article_id=article.id,
                                  user_agent=device, referrer_source=referrer))
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

    # 이전/다음 기사 (게시 시간 기준)
    prev_article = _get_published_query().filter(
        Article.created_at < article.created_at
    ).order_by(Article.created_at.desc()).first()
    next_article = _get_published_query().filter(
        Article.created_at > article.created_at
    ).order_by(Article.created_at.asc()).first()

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

    # 사이드바: 주요일정, 자료실
    schedules = Schedule.query.filter_by(is_active=True).order_by(
        Schedule.event_date.desc()
    ).limit(5).all()

    library_section = Section.query.filter_by(code='S1N4').first()
    library_articles = []
    if library_section:
        library_articles = _get_published_query().filter(
            Article.section_id == library_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(4).all()

    # 하단 콘텐츠: Books, 웰다잉TV, 섹션별 기사
    query = _get_published_query()
    book_subsection = SubSection.query.filter_by(code='S2N17').first()
    book_articles = []
    if book_subsection:
        book_articles = query.filter(
            Article.subsection_id == book_subsection.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(10).all()

    tv_section = Section.query.filter_by(code='S1N3').first()
    tv_articles = []
    if tv_section:
        tv_articles = query.filter(
            Article.section_id == tv_section.id
        ).order_by(db.func.coalesce(Article.embargo_date, Article.created_at).desc()).limit(5).all()

    bottom_section_articles = _build_bottom_section_articles()

    # 기자 프로필 사진: AdminUser에서 조회
    reporter = None
    if article.author_name:
        reporter = AdminUser.query.filter_by(name=article.author_name, is_active=True).first()

    # 디자인 선택: v2=기존 v2, clean=Atlantic 스타일 클린 디자인
    template = 'public/article_view.html'
    design = request.args.get('design', '')
    if design == 'v2':
        template = 'public/article_view_v2.html'
    elif design == 'clean':
        template = 'public/article_view_clean.html'

    return render_template(template,
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
                           comment_sort=comment_sort,
                           book_articles=book_articles,
                           tv_articles=tv_articles,
                           bottom_section_articles=bottom_section_articles,
                           schedules=schedules,
                           library_articles=library_articles,
                           reporter=reporter)


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
        member = db.session.get(Member, member_id)
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
    'copy':        {'title': '저작권문의',         'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event3'},
    'jh':          {'title': '제휴문의',           'group': '고객센터',    'content': 'com/event_form.html', 'event_code': 'event2'},
}

COM_NAV = [
    {'group': '매체소개', 'group_en': 'ABOUT', 'links': [
        {'code': 'com-1', 'title': '인사말'},
        {'code': 'com-2', 'title': '찾아오시는길'},
    ]},
    {'group': '약관 및 정책', 'group_en': 'POLICY', 'links': [
        {'code': 'service', 'title': '이용약관'},
        {'code': 'privacy', 'title': '개인정보처리방침'},
        {'code': 'youthpolicy', 'title': '청소년보호정책'},
        {'code': 'copyright', 'title': '저작권보호정책'},
        {'code': 'emailno', 'title': '이메일무단수집거부'},
    ]},
    {'group': '고객센터', 'group_en': 'SUPPORT', 'links': [
        {'code': 'jb', 'title': '기사제보'},
        {'code': 'ad', 'title': '광고문의'},
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
    # DB에 저장된 내용이 있으면 우선 사용 (폼 페이지 제외)
    db_content = None
    if 'event_code' not in page:
        setting = SiteSetting.query.filter_by(key=f'com_page_{page_code}').first()
        if setting and setting.value:
            db_content = setting.value
    return render_template('public/com_page.html',
                           page=page, page_code=page_code, com_nav=COM_NAV,
                           recaptcha_site_key=recaptcha_site_key,
                           db_content=db_content)


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

    sidebar_opinion, sidebar_popular, popular_today, popular_week = _get_sidebar_data()

    return render_template('public/bbs_list.html',
                           board=board,
                           posts=pagination.items,
                           pagination=pagination,
                           total=total,
                           sc_area=sc_area,
                           sc_word=sc_word,
                           sidebar_opinion=sidebar_opinion,
                           popular_today=popular_today,
                           popular_week=popular_week)


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
        member = db.session.get(Member, member_id)

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
    parent_post = db.session.get(BoardPost, reply_to) if reply_to else None
    return render_template('public/bbs_write.html', board=board, parent_post=parent_post)


@public_bp.route('/bbs/upload', methods=['POST'])
def bbs_upload():
    """게시판 이미지/파일 업로드 API (로그인 필요)"""
    import uuid, os
    from werkzeug.utils import secure_filename
    from app.utils.cloud_storage import upload_file

    # 인증 확인: 관리자 또는 회원 로그인 필요
    if not current_user.is_authenticated and not session.get('member_id'):
        return jsonify({'error': '로그인이 필요합니다.'}), 401

    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': '파일이 없습니다.'}), 400

    original = secure_filename(f.filename) or ''
    if not original or '.' not in original:
        return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400
    ext = original.rsplit('.', 1)[-1].lower()
    allowed = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'doc', 'docx', 'hwp', 'hwpx', 'zip', 'txt'}
    if ext not in allowed:
        return jsonify({'error': f'허용되지 않는 파일 형식: .{ext}'}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    f.save(filepath)

    is_image = ext in {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    resource_type = 'image' if is_image else 'raw'
    url = upload_file(filepath, folder='welldying/bbs', resource_type=resource_type)
    if not url:
        url = f'/static/uploads/{filename}'

    return jsonify({'url': url, 'filename': original, 'is_image': is_image})


@public_bp.route('/bbs/write', methods=['POST'])
def bbs_write():
    import bleach
    ALLOWED_TAGS = ['p', 'br', 'b', 'i', 'u', 'strong', 'em', 'a', 'img',
                    'ul', 'ol', 'li', 'blockquote', 'h2', 'h3', 'h4',
                    'span', 'div', 'table', 'thead', 'tbody', 'tr', 'td', 'th']
    ALLOWED_ATTRS = {'a': ['href', 'title', 'target'], 'img': ['src', 'alt', 'width', 'height'],
                     'span': ['style'], 'td': ['colspan', 'rowspan'], 'th': ['colspan', 'rowspan']}

    table = request.form.get('table', '')
    title = request.form.get('title', '').strip()
    content = bleach.clean(request.form.get('content', '').strip(),
                           tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
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
    current_member = db.session.get(Member, member_id) if member_id else None

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
    member = db.session.get(Member, member_id) if member_id else None

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
        opt = db.session.get(PollOption, oid)
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
@limiter.limit("5 per minute", methods=["POST"])
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
        next_url = request.args.get('next', '')
        # Open Redirect 방지: 상대경로만 허용
        if not next_url or not next_url.startswith('/') or next_url.startswith('//'):
            next_url = url_for('public.index')
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


# ===== 뉴스레터 =====

@public_bp.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    from flask import jsonify
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()

    if not email or '@' not in email:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': '올바른 이메일을 입력해주세요.'}), 400
        flash('올바른 이메일을 입력해주세요.', 'error')
        return redirect(request.referrer or url_for('public.index'))

    existing = NewsletterSubscriber.query.filter_by(email=email).first()
    if existing:
        if existing.is_active:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': '이미 구독 중인 이메일입니다.'})
            flash('이미 구독 중인 이메일입니다.', 'info')
        else:
            existing.is_active = True
            existing.name = name or existing.name
            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': '뉴스레터 구독이 재활성화되었습니다.'})
            flash('뉴스레터 구독이 재활성화되었습니다.', 'success')
    else:
        sub = NewsletterSubscriber(email=email, name=name)
        db.session.add(sub)
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': '뉴스레터 구독이 완료되었습니다.'})
        flash('뉴스레터 구독이 완료되었습니다.', 'success')

    return redirect(request.referrer or url_for('public.index'))


@public_bp.route('/newsletter/unsubscribe', methods=['GET', 'POST'])
def newsletter_unsubscribe():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if email:
            sub = NewsletterSubscriber.query.filter_by(email=email).first()
            if sub:
                sub.is_active = False
                db.session.commit()
                flash('뉴스레터 구독이 해지되었습니다.', 'success')
            else:
                flash('등록되지 않은 이메일입니다.', 'error')
    return render_template('public/newsletter_unsubscribe.html')


# ===== 뉴스레터 웹 보기 =====

@public_bp.route('/newsletter/archive')
def newsletter_archive():
    page = request.args.get('page', 1, type=int)
    pagination = Newsletter.query.filter_by(status='published').order_by(
        Newsletter.volume_number.desc()
    ).paginate(page=page, per_page=12, error_out=False)
    sidebar_opinion, sidebar_popular, popular_today, popular_week = _get_sidebar_data()
    return render_template('public/newsletter_archive.html',
                           newsletters=pagination.items, pagination=pagination,
                           sidebar_opinion=sidebar_opinion, popular_today=popular_today,
                           popular_week=popular_week)


@public_bp.route('/newsletter/<slug>')
def newsletter_view(slug):
    nl = Newsletter.query.filter_by(slug=slug, status='published').first_or_404()
    nl.view_count = (nl.view_count or 0) + 1
    db.session.commit()
    sections = nl.sections

    def _resolve_items(items):
        resolved = []
        for item in (items or []):
            if item.get('type') == 'article' and item.get('article_id'):
                art = db.session.get(Article, item['article_id'])
                if art:
                    resolved.append({
                        'type': 'article',
                        'title': art.title,
                        'summary': art.summary_text,
                        'image': art.thumb_url,
                        'link': f'/news/articleView.html?idxno={art.id}',
                        'author': art.author_name or '',
                    })
            elif item.get('type') == 'custom':
                resolved.append(item)
        return resolved

    focus_items = _resolve_items(sections.get('focus', {}).get('items', []))
    opinion_items = _resolve_items(sections.get('opinion', {}).get('items', []))

    video_items = []
    for v in sections.get('videos', {}).get('items', []):
        yt_match = re.search(r'(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{11})', v.get('youtube_url', ''))
        thumb = f"https://img.youtube.com/vi/{yt_match.group(1)}/hqdefault.jpg" if yt_match else ''
        video_items.append({**v, 'thumbnail': thumb, 'video_id': yt_match.group(1) if yt_match else ''})

    # 지난 뉴스레터 (현재 제외, 최근 4개)
    recent_newsletters = Newsletter.query.filter(
        Newsletter.status == 'published', Newsletter.id != nl.id
    ).order_by(Newsletter.volume_number.desc()).limit(4).all()

    # 모바일 감지
    ua = request.headers.get('User-Agent', '')
    mobile = bool(re.search(r'Mobile|Android|iPhone|iPod|Opera Mini|IEMobile', ua, re.I))
    if request.cookies.get('view_pc') == 'y':
        mobile = False

    template = 'public/newsletter_view.html' if mobile else 'public/newsletter_view_magazine.html'
    return render_template(template,
                           newsletter=nl, sections=sections,
                           focus_items=focus_items, opinion_items=opinion_items,
                           video_items=video_items,
                           recent_newsletters=recent_newsletters)


# ===== 주요일정 =====

@public_bp.route('/schedule/list.html')
def schedule_list():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    view = request.args.get('view', 'list')  # list / calendar

    query = Schedule.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)

    pagination = query.order_by(Schedule.event_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    categories = db.session.query(Schedule.category).filter(
        Schedule.is_active == True, Schedule.category != ''
    ).distinct().all()
    categories = [c[0] for c in categories]

    # 캘린더 뷰용: 현재 월의 일정
    import calendar as cal_module
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1)
    else:
        last_day = datetime(year, month + 1, 1)

    month_schedules = Schedule.query.filter(
        Schedule.is_active == True,
        Schedule.event_date >= first_day,
        Schedule.event_date < last_day
    ).order_by(Schedule.event_date).all()

    cal_data = cal_module.monthcalendar(year, month)

    return render_template('public/schedule_list.html',
                           schedules=pagination.items,
                           pagination=pagination,
                           category=category,
                           categories=categories,
                           view=view,
                           year=year, month=month,
                           cal_data=cal_data,
                           month_schedules=month_schedules)


@public_bp.route('/api/schedules')
def api_schedules():
    """React 캘린더용 일정 API"""
    import calendar as cal_module

    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)

    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1)
    else:
        last_day = datetime(year, month + 1, 1)

    # 해당 월의 일정
    month_schedules = Schedule.query.filter(
        Schedule.is_active == True,
        Schedule.event_date >= first_day,
        Schedule.event_date < last_day
    ).order_by(Schedule.event_date).all()

    # 오늘 이후 예정 일정 (최대 15건)
    now = datetime.now()
    upcoming = Schedule.query.filter(
        Schedule.is_active == True,
        Schedule.event_date >= now
    ).order_by(Schedule.event_date).limit(15).all()

    # 최신순 전체 일정 (사이드바용)
    recent = Schedule.query.filter(
        Schedule.is_active == True
    ).order_by(Schedule.event_date.desc()).all()

    def serialize(s):
        return {
            'id': s.id,
            'title': s.title,
            'description': s.description or '',
            'content': s.content or '',
            'event_date': s.event_date.isoformat() if s.event_date else '',
            'end_date': s.end_date.isoformat() if s.end_date else None,
            'location': s.location or '',
            'category': s.category or '',
            'link_url': s.link_url or '',
            'image_url': s.image_url or '',
            'is_active': s.is_active,
        }

    return jsonify({
        'schedules': [serialize(s) for s in month_schedules],
        'upcoming': [serialize(s) for s in upcoming],
        'recent': [serialize(s) for s in recent],
    })


@public_bp.route('/api/schedules/search')
def api_schedules_search():
    """일정 제목 검색 API"""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'results': []})

    results = Schedule.query.filter(
        Schedule.is_active == True,
        Schedule.title.contains(q)
    ).order_by(Schedule.event_date.desc()).limit(20).all()

    def serialize(s):
        return {
            'id': s.id,
            'title': s.title,
            'description': s.description or '',
            'content': s.content or '',
            'event_date': s.event_date.isoformat() if s.event_date else '',
            'end_date': s.end_date.isoformat() if s.end_date else None,
            'location': s.location or '',
            'category': s.category or '',
            'link_url': s.link_url or '',
            'image_url': s.image_url or '',
            'is_active': s.is_active,
        }

    return jsonify({'results': [serialize(s) for s in results]})


@public_bp.route('/schedule/view/<int:schedule_id>')
def schedule_view(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if not schedule.is_active:
        abort(404)
    return render_template('public/schedule_view.html', schedule=schedule)
