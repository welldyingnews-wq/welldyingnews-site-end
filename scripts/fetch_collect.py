"""Supabase collect 테이블에서 기사 가져오기 + 원문 스크래핑

Usage:
    python scripts/fetch_collect.py              # 전체 수집
    python scripts/fetch_collect.py --limit 5    # 5건만 테스트
    python scripts/fetch_collect.py --kr-only    # 한국 기사만 (Google News URL 문제 우회)
    python scripts/fetch_collect.py --skip-scrape # 스크래핑 건너뛰기 (메타만 저장)
"""
import argparse
import json
import os
import re
import sys
import time

import requests
import trafilatura
from dotenv import load_dotenv
from supabase import create_client

# 프로젝트 루트의 .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

COLLECTED_DIR = os.path.join(os.path.dirname(__file__), 'collected')
FAILED_LOG = os.path.join(os.path.dirname(__file__), 'collected_failed.json')
SCRAPE_DELAY = 2  # 초


# ── Google News URL 디코딩 ──

def _decode_google_news_url(source_url):
    """googlenewsdecoder 라이브러리로 디코딩 시도"""
    try:
        from googlenewsdecoder import new_decoderv1
        result = new_decoderv1(source_url, interval=1)
        if result.get('status') and result.get('decoded_url'):
            return result['decoded_url']
    except Exception:
        pass
    return None


def _search_title_for_url(title, title_ko):
    """제목으로 네이버/구글 검색하여 실제 기사 URL 찾기 (API 키 없이)"""
    query = title_ko if title_ko else title
    if not query:
        return None

    # Naver 검색 API 사용 (환경변수에 키가 있을 때)
    naver_id = os.getenv('NAVER_CLIENT_ID', '')
    naver_secret = os.getenv('NAVER_CLIENT_SECRET', '')
    if naver_id and naver_secret:
        try:
            resp = requests.get(
                'https://openapi.naver.com/v1/search/news.json',
                params={'query': query[:50], 'display': 1, 'sort': 'sim'},
                headers={
                    'X-Naver-Client-Id': naver_id,
                    'X-Naver-Client-Secret': naver_secret,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                if items:
                    return items[0]['link']
        except Exception:
            pass

    return None


def resolve_url(link, title='', title_ko=''):
    """Google News URL을 실제 기사 URL로 해석

    전략:
    1. Google News URL이 아니면 그대로 반환
    2. googlenewsdecoder 라이브러리 시도
    3. requests.get follow redirect 시도
    4. 제목 기반 검색 (Naver API)
    """
    if 'news.google.com' not in link:
        return link

    # 1) 라이브러리 디코딩
    decoded = _decode_google_news_url(link)
    if decoded and 'news.google.com' not in decoded:
        return decoded

    # 2) HTTP redirect 따라가기 (consent 쿠키 포함)
    try:
        session = requests.Session()
        session.cookies.set('CONSENT', 'YES+', domain='.google.com')
        resp = session.get(link, allow_redirects=True, timeout=15,
                           headers={
                               'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                             'AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
                           })
        if 'news.google.com' not in resp.url:
            return resp.url
    except Exception:
        pass

    # 3) 제목 기반 검색
    found = _search_title_for_url(title, title_ko)
    if found:
        return found

    return link  # 모든 시도 실패 → 원본 반환


def scrape_article(url):
    """trafilatura로 기사 본문 스크래핑"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {'success': False, 'reason': '페이지 다운로드 실패'}

        text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
        if not text or len(text.strip()) < 50:
            return {'success': False, 'reason': '본문 추출 실패 (내용 부족)'}

        metadata = trafilatura.extract_metadata(downloaded)
        title = metadata.title if metadata else ''
        return {'success': True, 'text': text, 'title': title}
    except Exception as e:
        return {'success': False, 'reason': str(e)[:200]}


def get_existing_files():
    """이미 수집된 collect_id 목록 반환"""
    existing = set()
    if not os.path.isdir(COLLECTED_DIR):
        return existing
    for fname in os.listdir(COLLECTED_DIR):
        if fname.endswith('.json'):
            parts = fname.replace('.json', '').split('_')
            if len(parts) >= 2:
                try:
                    existing.add(int(parts[1]))
                except ValueError:
                    pass
    return existing


def fetch_all_from_supabase(country_filter=None):
    """Supabase collect 테이블에서 전체 기사 조회 (페이지네이션)"""
    sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    all_data = []
    page_size = 1000
    offset = 0
    while True:
        query = sb.table('collect').select('*') \
            .order('collected_at', desc=True)
        if country_filter:
            query = query.eq('country', country_filter)
        resp = query.range(offset, offset + page_size - 1).execute()
        if not resp.data:
            break
        all_data.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return all_data


def main():
    parser = argparse.ArgumentParser(description='Supabase collect → 로컬 JSON + 스크래핑')
    parser.add_argument('--limit', type=int, default=0, help='처리할 최대 건수 (0=전체)')
    parser.add_argument('--kr-only', action='store_true', help='한국 기사만 수집')
    parser.add_argument('--global-only', action='store_true', help='해외 기사만 수집')
    parser.add_argument('--skip-scrape', action='store_true', help='스크래핑 건너뛰기')
    args = parser.parse_args()

    os.makedirs(COLLECTED_DIR, exist_ok=True)

    # 1. 이미 처리된 건 확인
    existing = get_existing_files()
    print(f'기존 수집 파일: {len(existing)}건')

    # 2. Supabase에서 가져오기
    country = None
    if args.kr_only:
        country = 'KR'
    elif args.global_only:
        country = 'Global'

    label = f' (country={country})' if country else ''
    print(f'Supabase collect 테이블 조회 중{label}...')
    articles = fetch_all_from_supabase(country)
    print(f'총 {len(articles)}건 조회됨')

    # 3. 미처리 건 필터링
    to_process = [a for a in articles if a['id'] not in existing]
    if args.limit > 0:
        to_process = to_process[:args.limit]
    print(f'처리 대상: {len(to_process)}건 (스킵: {len(articles) - len(to_process)}건)')

    if not to_process:
        print('처리할 기사가 없습니다.')
        return

    # 4. 스크래핑 + 저장
    failed = []
    success_count = 0
    scrape_fail_count = 0

    for idx, article in enumerate(to_process):
        collect_id = article['id']
        seq = idx + 1 + len(existing)
        filename = f'{seq:03d}_{collect_id}.json'
        filepath = os.path.join(COLLECTED_DIR, filename)

        link = article.get('link', '')
        title = article.get('title', '')
        title_ko = article.get('title_ko') or title
        print(f'[{idx + 1}/{len(to_process)}] {title_ko[:50]}...', end=' ', flush=True)

        # 스크래핑
        scraped = {'success': False, 'reason': '스크래핑 건너뜀'}
        real_url = link

        if not args.skip_scrape and link:
            # URL 해석 (Google News → 실제 URL)
            real_url = resolve_url(link, title, title_ko)
            is_google = ('news.google.com' in real_url)

            if is_google:
                # Google News URL 해석 실패 → 메타만 저장
                scraped = {'success': False, 'reason': 'Google News URL 해석 실패'}
                print(f'GNEWS_FAIL')
                scrape_fail_count += 1
                failed.append({
                    'collect_id': collect_id,
                    'link': link,
                    'real_url': real_url,
                    'reason': 'Google News URL 해석 실패',
                })
            else:
                scraped = scrape_article(real_url)
                if scraped['success']:
                    print(f'OK ({len(scraped["text"])}자)')
                    success_count += 1
                else:
                    print(f'FAIL ({scraped["reason"][:40]})')
                    scrape_fail_count += 1
                    failed.append({
                        'collect_id': collect_id,
                        'link': link,
                        'real_url': real_url,
                        'reason': scraped['reason'],
                    })

            time.sleep(SCRAPE_DELAY)
        else:
            print('SKIP')

        # JSON 저장 (스크래핑 실패해도 메타 데이터는 저장)
        output = {
            'collect_id': collect_id,
            'news_id': article.get('news_id'),
            'title': title,
            'title_ko': title_ko,
            'link': link,
            'real_url': real_url,
            'country': article.get('country', ''),
            'published_at': article.get('published_at', ''),
            'description': article.get('description', ''),
            'source': article.get('source', ''),
            'scraped': scraped,
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    # 5. 실패 기록
    if failed:
        with open(FAILED_LOG, 'w', encoding='utf-8') as f:
            json.dump(failed, f, ensure_ascii=False, indent=2)

    # 6. 결과 요약
    print(f'\n{"=" * 50}')
    print(f'완료: {len(to_process)}건 처리')
    print(f'  스크래핑 성공: {success_count}건')
    print(f'  스크래핑 실패: {scrape_fail_count}건')
    print(f'  파일 저장 위치: {COLLECTED_DIR}')
    if failed:
        print(f'  실패 로그: {FAILED_LOG}')


if __name__ == '__main__':
    main()
