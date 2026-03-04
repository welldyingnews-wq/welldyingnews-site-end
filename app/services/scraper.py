"""URL 스크래핑 + 검색 API 연동"""
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

TIMEOUT = 10


def scrape_article_content(url):
    """trafilatura로 URL에서 기사 본문 추출

    Returns:
        dict: {success: True, text: '...', title: '...'} 또는 {success: False, reason: '...'}
    """
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {'success': False, 'reason': '페이지 다운로드 실패'}
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
        if not text or len(text.strip()) < 50:
            return {'success': False, 'reason': '본문 추출 실패 (내용 부족)'}
        # 제목도 추출 시도
        metadata = trafilatura.extract_metadata(downloaded)
        title = metadata.title if metadata else ''
        return {'success': True, 'text': text, 'title': title}
    except Exception as e:
        logger.error(f'스크래핑 오류 ({url}): {e}')
        return {'success': False, 'reason': str(e)}


def search_naver(query, display=5):
    """Naver 검색 API로 관련 기사 검색

    Returns:
        list[dict]: [{title, link, description}, ...]
    """
    client_id = current_app.config.get('NAVER_CLIENT_ID', '')
    client_secret = current_app.config.get('NAVER_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        return []
    try:
        resp = requests.get(
            'https://openapi.naver.com/v1/search/news.json',
            params={'query': query, 'display': display, 'sort': 'sim'},
            headers={
                'X-Naver-Client-Id': client_id,
                'X-Naver-Client-Secret': client_secret,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])
        return [{'title': i['title'], 'link': i['link'], 'description': i['description']} for i in items]
    except Exception as e:
        logger.error(f'Naver 검색 오류: {e}')
        return []


def search_google_cse(query, num=5):
    """Google Custom Search API로 관련 기사 검색

    Returns:
        list[dict]: [{title, link, snippet}, ...]
    """
    api_key = current_app.config.get('GOOGLE_CSE_KEY', '')
    cse_id = current_app.config.get('GOOGLE_CSE_ID', '')
    if not api_key or not cse_id:
        return []
    try:
        resp = requests.get(
            'https://www.googleapis.com/customsearch/v1',
            params={'key': api_key, 'cx': cse_id, 'q': query, 'num': num},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])
        return [{'title': i['title'], 'link': i['link'], 'snippet': i.get('snippet', '')} for i in items]
    except Exception as e:
        logger.error(f'Google CSE 검색 오류: {e}')
        return []
