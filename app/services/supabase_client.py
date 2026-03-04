"""Supabase 연동 — 크롤링 시스템이 수집한 기사 조회"""
import logging

from flask import current_app

logger = logging.getLogger(__name__)

_client = None


def get_supabase():
    """Lazy 싱글턴 Supabase 클라이언트"""
    global _client
    if _client is None:
        from supabase import create_client
        url = current_app.config['SUPABASE_URL']
        key = current_app.config['SUPABASE_KEY']
        if not url or not key:
            raise RuntimeError('SUPABASE_URL / SUPABASE_KEY 환경변수가 설정되지 않았습니다.')
        _client = create_client(url, key)
    return _client


def _fetch_from_table(table, date_col, start_date, end_date, country=None):
    """Supabase 테이블에서 날짜/국가 필터로 기사 조회"""
    try:
        sb = get_supabase()
        q = sb.table(table).select('*') \
            .gte(date_col, start_date) \
            .lte(date_col, end_date + 'T23:59:59') \
            .order(date_col, desc=True)
        if country:
            q = q.eq('country', country)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f'Supabase {table} 조회 오류: {e}')
        return []


def fetch_news_articles(start_date, end_date, country=None):
    """news 테이블에서 수집된 기사 조회"""
    return _fetch_from_table('news', 'published_at', start_date, end_date, country)


def fetch_collected_articles(start_date, end_date, country=None):
    """collect 테이블에서 큐레이션된 기사 조회"""
    return _fetch_from_table('collect', 'collected_at', start_date, end_date, country)
