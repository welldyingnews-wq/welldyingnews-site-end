"""
원본 welldyingnews.com 기사를 배치로 마이그레이션하는 스크립트.

사용법:
    # 1735부터 1까지 역순 마이그레이션
    python scripts/batch_migrate.py

    # 특정 범위만
    python scripts/batch_migrate.py --start 100 --end 1

    # dry-run (DB 저장/업로드 없이 확인만)
    python scripts/batch_migrate.py --dry-run
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from io import BytesIO

import requests as http_requests
from bs4 import BeautifulSoup
from PIL import Image

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
ORIGIN_URL = 'https://www.welldyingnews.com/news/articleView.html?idxno={}'

# PythonAnywhere 설정
PA_USERNAME = 'comekjh'
PA_TOKEN = 'a630d9e0e9eac3def6118f3ec3541efda6e789a6'
PA_HEADERS = {'Authorization': f'Token {PA_TOKEN}'}
PA_BASE_PATH = '/home/comekjh/welldyingnews'

# DB 경로
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'welldying.db')

# 마이그레이션 로그 (원본 idxno → 로컬 article.id 매핑)
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrate_log.json')

# 섹션 매핑
SECTION_MAP = {'S1N1': 1, 'S1N2': 2, 'S1N3': 3, 'S1N4': 4, 'S1N5': 5, 'S1N6': 6}
SUBSECTION_MAP = {
    'S2N1': 1, 'S2N2': 2, 'S2N4': 3, 'S2N17': 4, 'S2N12': 5, 'S2N11': 6,
    'S2N7': 7, 'S2N16': 8, 'S2N9': 9, 'S2N10': 10, 'S2N21': 11, 'S2N13': 12,
    'S2N15': 13, 'S2N20': 14, 'S2N5': 15, 'S2N18': 16, 'S2N22': 17, 'S2N23': 18,
}

BATCH_SIZE = 10
SLEEP_SECONDS = 1


def load_log():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f:
            return json.load(f)
    return {'migrated': {}, 'skipped': [], 'errors': []}


def save_log(log):
    with open(LOG_PATH, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def fetch_article(idxno):
    """원본 기사 HTML을 가져온다. 없으면 None 반환."""
    url = ORIGIN_URL.format(idxno)
    try:
        resp = http_requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except http_requests.RequestException as e:
        print(f'      요청 에러: {e}')
        return None


def parse_article(html):
    """HTML에서 기사 데이터를 추출한다."""
    soup = BeautifulSoup(html, 'html.parser')

    h1 = soup.select_one('h1.heading, H1.heading')
    title = h1.get_text(strip=True) if h1 else ''
    if not title:
        return None  # 제목 없으면 유효하지 않은 페이지

    h2 = soup.select_one('h2.subheading, H2.subheading')
    subtitle = h2.get_text(strip=True) if h2 else ''

    body_article = soup.select_one('#article-view-content-div')
    body_html = body_article.decode_contents().strip() if body_article else ''
    if not body_html:
        return None

    meta = {}

    # 섹션/서브섹션
    header = soup.select_one('.article-view-header')
    if header:
        for a in header.select('a[href*="sc_section_code"]'):
            m = re.search(r'sc_section_code=(\w+)', a.get('href', ''))
            if m:
                meta['section_code'] = m.group(1)
                break
        for a in header.select('a[href*="sc_sub_section_code"]'):
            m = re.search(r'sc_sub_section_code=(\w+)', a.get('href', ''))
            if m:
                meta['subsection_code'] = m.group(1)
                break
    if 'section_code' not in meta:
        meta['section_code'] = 'S1N1'

    # 기자명
    for li in soup.select('.infomation li'):
        if li.select_one('.icon-user-o, .icon-user'):
            icon = li.select_one('i')
            if icon:
                icon.extract()
            meta['author_name'] = li.get_text(strip=True)
            break
    if 'author_name' not in meta:
        meta['author_name'] = '웰다잉뉴스'

    # 이메일
    email_tag = soup.select_one('.article-writer .email, .writer .email, .writer-txt .email, article.writer .email')
    meta['author_email'] = email_tag.get_text(strip=True) if email_tag else 'welldyingnews@naver.com'

    # 날짜
    date_tag = soup.select_one('meta[property="article:published_time"]')
    if date_tag:
        try:
            meta['created_at'] = datetime.fromisoformat(date_tag.get('content', '')).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            meta['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        meta['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return {
        'title': title,
        'subtitle': subtitle,
        'body_html': body_html,
        'meta': meta,
    }


def download_images(body_html):
    """본문 이미지를 다운로드하고 src를 로컬 경로로 치환한다."""
    soup = BeautifulSoup(body_html, 'html.parser')
    image_files = []

    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src or src.startswith('data:') or 'welldyingnews.com' not in src:
            continue
        try:
            resp = http_requests.get(src, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            pil_img = Image.open(BytesIO(resp.content))
            if pil_img.mode in ('RGBA', 'LA', 'P'):
                bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                if pil_img.mode == 'P':
                    pil_img = pil_img.convert('RGBA')
                bg.paste(pil_img, mask=pil_img.split()[-1] if 'A' in pil_img.mode else None)
                pil_img = bg
            filename = f'{uuid.uuid4().hex}.jpg'
            filepath = f'/tmp/{filename}'
            pil_img.save(filepath, 'JPEG', quality=90)
            local_url = f'/static/uploads/{filename}'
            img['src'] = local_url
            image_files.append({'filename': filename, 'filepath': filepath})
        except Exception as e:
            print(f'      이미지 다운로드 실패: {src[:60]}... ({e})')

    return str(soup), image_files


def insert_to_db(data, image_files):
    """welldying.db에 기사를 INSERT한다."""
    meta = data['meta']
    section_id = SECTION_MAP.get(meta.get('section_code', 'S1N1'), 1)
    subsection_id = SUBSECTION_MAP.get(meta.get('subsection_code', ''))
    thumbnail_path = f'/static/uploads/{image_files[0]["filename"]}' if image_files else ''
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''INSERT INTO article
        (title, subtitle, content, summary, section_id, subsection_id,
         author_name, author_email, source, level, recognition, article_type,
         thumbnail_path, photo_caption, keyword, view_count,
         created_at, updated_at, embargo_date, is_deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['title'], data['subtitle'], data['body_html'], '',
         section_id, subsection_id,
         meta.get('author_name', '웰다잉뉴스'),
         meta.get('author_email', 'welldyingnews@naver.com'),
         '', 'B', 'E', 'B',
         thumbnail_path, '', '', 0,
         meta['created_at'], now, None, 0))
    article_id = cur.lastrowid
    conn.commit()
    conn.close()
    return article_id


def upload_images_to_pa(image_files):
    """PythonAnywhere에 이미지 파일을 업로드한다."""
    for img in image_files:
        remote_path = f'{PA_BASE_PATH}/app/static/uploads/{img["filename"]}'
        url = f'https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/files/path{remote_path}'
        with open(img['filepath'], 'rb') as f:
            r = http_requests.post(url, headers=PA_HEADERS, files={'content': f})
        if r.status_code not in (200, 201):
            print(f'      이미지 업로드 실패: {img["filename"]} ({r.status_code})')


def upload_db_to_pa():
    """welldying.db를 PythonAnywhere에 업로드한다."""
    url = f'https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/files/path{PA_BASE_PATH}/welldying.db'
    with open(DB_PATH, 'rb') as f:
        r = http_requests.post(url, headers=PA_HEADERS, files={'content': f})
    return r.status_code in (200, 201)


def reload_webapp():
    """PythonAnywhere 웹앱을 리로드한다."""
    url = f'https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/webapps/comekjh.pythonanywhere.com/reload/'
    r = http_requests.post(url, headers=PA_HEADERS)
    return r.status_code == 200


def migrate_one(idxno, log, dry_run=False):
    """기사 1건을 마이그레이션한다. 성공 시 article_id, 스킵 시 None 반환."""
    str_idxno = str(idxno)

    # 이미 마이그레이션된 기사 건너뜀
    if str_idxno in log['migrated']:
        return 'already'

    # HTML 가져오기
    html = fetch_article(idxno)
    if html is None:
        return 'not_found'

    # 파싱
    data = parse_article(html)
    if data is None:
        return 'parse_fail'

    # 이미지 다운로드 + src 치환
    processed_body, image_files = download_images(data['body_html'])
    data['body_html'] = processed_body

    if dry_run:
        print(f'      [DRY] 제목: {data["title"][:40]}, 이미지: {len(image_files)}개')
        return 'dry'

    # DB INSERT
    article_id = insert_to_db(data, image_files)

    # 이미지 PythonAnywhere 업로드
    if image_files:
        upload_images_to_pa(image_files)

    # 임시 파일 정리
    for img in image_files:
        try:
            os.remove(img['filepath'])
        except OSError:
            pass

    return article_id


def main():
    parser = argparse.ArgumentParser(description='배치 기사 마이그레이션')
    parser.add_argument('--start', type=int, default=1735, help='시작 기사 번호 (내림차순)')
    parser.add_argument('--end', type=int, default=1, help='끝 기사 번호')
    parser.add_argument('--dry-run', action='store_true', help='DB 저장/업로드 없이 확인만')
    args = parser.parse_args()

    log = load_log()
    total_range = list(range(args.start, args.end - 1, -1))
    total_count = len(total_range)

    print(f'{"="*60}')
    print(f'배치 마이그레이션: {args.start} → {args.end} ({total_count}건)')
    print(f'이미 완료: {len(log["migrated"])}건, 스킵(404): {len(log["skipped"])}건')
    print(f'배치: {BATCH_SIZE}개씩 / {SLEEP_SECONDS}초 대기')
    if args.dry_run:
        print(f'모드: DRY-RUN')
    print(f'{"="*60}\n')

    success_count = 0
    skip_count = 0
    error_count = 0
    batch_count = 0

    for i, idxno in enumerate(total_range):
        progress = f'[{i+1}/{total_count}]'

        result = migrate_one(idxno, log, dry_run=args.dry_run)

        if result == 'already':
            print(f'  {progress} #{idxno} → 이미 완료 (id={log["migrated"][str(idxno)]})')
            continue
        elif result == 'not_found':
            print(f'  {progress} #{idxno} → 404 (없음)')
            if idxno not in log['skipped']:
                log['skipped'].append(idxno)
            skip_count += 1
        elif result == 'parse_fail':
            url = ORIGIN_URL.format(idxno)
            print(f'  {progress} #{idxno} → 파싱 실패 ({url})')
            if idxno not in [e if isinstance(e, int) else e['idxno'] for e in log['errors']]:
                log['errors'].append({'idxno': idxno, 'url': url})
            error_count += 1
        elif result == 'dry':
            pass
        else:
            # 성공 (article_id 반환)
            article_id = result
            log['migrated'][str(idxno)] = article_id
            print(f'  {progress} #{idxno} → id={article_id} ✓')
            success_count += 1

        batch_count += 1

        # 5개마다 로그 저장 + DB 업로드 + 3초 대기
        if batch_count >= BATCH_SIZE:
            batch_count = 0
            if not args.dry_run:
                save_log(log)
                # DB 업로드 (5개마다)
                if success_count > 0:
                    print(f'\n  --- DB 업로드 중... ', end='', flush=True)
                    if upload_db_to_pa():
                        print('OK ---')
                    else:
                        print('FAIL ---')
            print(f'  --- {SLEEP_SECONDS}초 대기 ---\n')
            time.sleep(SLEEP_SECONDS)

    # 마지막 배치 처리
    if not args.dry_run and batch_count > 0:
        save_log(log)
        if success_count > 0:
            print(f'\n  --- 최종 DB 업로드 중... ', end='', flush=True)
            if upload_db_to_pa():
                print('OK ---')
            else:
                print('FAIL ---')

    # 웹앱 리로드
    if not args.dry_run and success_count > 0:
        print(f'\n  --- 웹앱 리로드... ', end='', flush=True)
        if reload_webapp():
            print('OK ---')
        else:
            print('FAIL ---')

    # 결과 요약
    print(f'\n{"="*60}')
    print(f'완료! 성공: {success_count}, 스킵(404): {skip_count}, 에러: {error_count}')
    print(f'누적 마이그레이션: {len(log["migrated"])}건')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
