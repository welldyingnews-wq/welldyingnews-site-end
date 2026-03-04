"""
원본 welldyingnews.com 기사를 리모트 서버에 POST 방식으로 마이그레이션하는 스크립트.

사용법:
    # 로컬 DB에 저장 (기본)
    python scripts/migrate_article.py --idxno 1735

    # 리모트 서버에 POST
    python scripts/migrate_article.py --idxno 1735 --remote https://www.welldyingnews.com

    # 확인만 (DB 저장 없음)
    python scripts/migrate_article.py --idxno 1735 --dry-run
"""
import argparse
import os
import re
import sys
import uuid
from datetime import datetime

import requests as http_requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ORIGIN_URL = 'https://www.welldyingnews.com/news/articleView.html?idxno={}'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

# 섹션 코드 → ID 매핑 (로컬/리모트 DB 동일 구조)
SECTION_CODE_TO_ID = {
    'S1N1': 1, 'S1N2': 2, 'S1N3': 3, 'S1N4': 4, 'S1N5': 5, 'S1N6': 6,
}
SUBSECTION_CODE_TO_ID = {
    'S2N1': 1, 'S2N2': 2, 'S2N4': 3, 'S2N17': 4, 'S2N12': 5, 'S2N11': 6,
    'S2N7': 7, 'S2N16': 8, 'S2N9': 9, 'S2N10': 10, 'S2N21': 11, 'S2N13': 12,
    'S2N15': 13, 'S2N20': 14, 'S2N5': 15, 'S2N18': 16, 'S2N22': 17, 'S2N23': 18,
}


def fetch_article_html(idxno):
    """원본 기사 HTML을 가져온다."""
    url = ORIGIN_URL.format(idxno)
    resp = http_requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_article(html):
    """HTML에서 기사 데이터를 추출한다."""
    soup = BeautifulSoup(html, 'html.parser')

    # 제목
    h1 = soup.select_one('h1.heading, H1.heading')
    title = h1.get_text(strip=True) if h1 else ''

    # 부제목
    h2 = soup.select_one('h2.subheading, H2.subheading')
    subtitle = h2.get_text(strip=True) if h2 else ''

    # 본문 HTML
    body_article = soup.select_one('#article-view-content-div')
    body_html = body_article.decode_contents().strip() if body_article else ''

    # 메타데이터
    meta = {}

    # 섹션/서브섹션 코드 (article-view-header 내 breadcrumb에서만 검색)
    header = soup.select_one('.article-view-header')
    if header:
        for a in header.select('a[href*="sc_section_code"]'):
            href = a.get('href', '')
            m = re.search(r'sc_section_code=(\w+)', href)
            if m:
                meta['section_code'] = m.group(1)
                break
        for a in header.select('a[href*="sc_sub_section_code"]'):
            href = a.get('href', '')
            m = re.search(r'sc_sub_section_code=(\w+)', href)
            if m:
                meta['subsection_code'] = m.group(1)
                break

    # fallback: meta 태그에서 섹션명으로 매핑
    if 'section_code' not in meta:
        meta['section_code'] = 'S1N1'

    # 기자명 (아이콘 텍스트 제거 후 추출)
    info_list = soup.select('.infomation li')
    for li in info_list:
        if li.select_one('.icon-user-o, .icon-user'):
            icon = li.select_one('i')
            if icon:
                icon.extract()
            meta['author_name'] = li.get_text(strip=True)
            break
    if 'author_name' not in meta:
        meta['author_name'] = '웰다잉뉴스'

    # 기자 이메일
    email_tag = soup.select_one('.article-writer .email, .writer .email')
    if email_tag:
        meta['author_email'] = email_tag.get_text(strip=True)
    else:
        writer_block = soup.select_one('.writer-txt .email, article.writer .email')
        if writer_block:
            meta['author_email'] = writer_block.get_text(strip=True)
        else:
            meta['author_email'] = 'welldyingnews@naver.com'

    # 날짜
    date_tag = soup.select_one('meta[property="article:published_time"]')
    if date_tag:
        dt_str = date_tag.get('content', '')
        try:
            meta['created_at'] = datetime.fromisoformat(dt_str)
        except ValueError:
            meta['created_at'] = datetime.now()
    else:
        meta['created_at'] = datetime.now()

    return title, subtitle, body_html, meta


def download_image_as_jpg(url, upload_dir):
    """이미지를 다운로드하여 JPG로 저장하고 로컬 경로를 반환한다."""
    resp = http_requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    img = Image.open(BytesIO(resp.content))

    # RGBA → RGB 변환 (PNG 투명 배경 처리)
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
        img = background

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(upload_dir, filename)
    img.save(filepath, 'JPEG', quality=90)

    file_size = os.path.getsize(filepath)
    print(f"  [IMG] {url}")
    print(f"        → {filepath} ({file_size:,} bytes, {img.size[0]}x{img.size[1]})")

    return filename, filepath, img.size[0], img.size[1]


def process_body_images(body_html, upload_dir):
    """본문 HTML 내 이미지를 다운로드하고 임시 저장한다. src 치환은 모드별로 다르게 처리."""
    soup = BeautifulSoup(body_html, 'html.parser')
    images_info = []

    for img_tag in soup.find_all('img'):
        src = img_tag.get('src', '')
        if not src or src.startswith('data:'):
            continue
        if 'welldyingnews.com' not in src:
            continue

        filename, filepath, w, h = download_image_as_jpg(src, upload_dir)
        images_info.append({
            'original_url': src,
            'local_path': filepath,
            'filename': filename,
            'local_url': f'/static/uploads/{filename}',
            'width': w,
            'height': h,
            'img_tag': img_tag,  # BeautifulSoup 태그 참조
        })

    return soup, images_info


# ─── 리모트 POST 방식 ─────────────────────────────────

def remote_login(session, base_url, user_id, password):
    """관리자 로그인 후 세션 쿠키를 획득한다."""
    login_url = f'{base_url}/admin/login'
    resp = session.post(login_url, data={
        'user_id': user_id,
        'user_pw': password,
    }, allow_redirects=False)

    # 로그인 성공 시 302 redirect
    if resp.status_code in (302, 303):
        print("    로그인 성공!")
        return True

    print(f"    로그인 실패 (status={resp.status_code})")
    return False


def remote_upload_image(session, base_url, filepath, filename):
    """리모트 서버에 이미지를 업로드하고 URL을 반환한다."""
    upload_url = f'{base_url}/admin/api/upload-image'
    with open(filepath, 'rb') as f:
        resp = session.post(upload_url, files={
            'upload': (filename, f, 'image/jpeg')
        })

    if resp.status_code == 200:
        data = resp.json()
        url = data.get('url', '')
        print(f"    업로드 성공: {filename} → {url}")
        return url
    else:
        print(f"    업로드 실패: {filename} (status={resp.status_code})")
        return None


def remote_create_article(session, base_url, form_data):
    """리모트 서버에 기사를 POST로 생성한다."""
    create_url = f'{base_url}/admin/article/new'
    resp = session.post(create_url, data=form_data, allow_redirects=False)

    # 성공 시 302 redirect to article list
    if resp.status_code in (302, 303):
        print("    기사 생성 성공!")
        return True

    print(f"    기사 생성 실패 (status={resp.status_code})")
    if resp.status_code == 200:
        # 에러 메시지가 포함된 HTML일 수 있음
        soup = BeautifulSoup(resp.text, 'html.parser')
        flash_msgs = soup.select('.alert, .flash-message')
        for msg in flash_msgs:
            print(f"    에러: {msg.get_text(strip=True)}")
    return False


# ─── 로컬 DB 방식 ─────────────────────────────────────

def local_save(title, subtitle, body_html, meta, images, photo_caption):
    """로컬 DB에 직접 저장한다."""
    from app.models import db, Article, Section, SubSection
    from app import create_app

    app = create_app()
    with app.app_context():
        section_code = meta.get('section_code', 'S1N1')
        subsection_code = meta.get('subsection_code')
        section = Section.query.filter_by(code=section_code).first()
        subsection = SubSection.query.filter_by(code=subsection_code).first() if subsection_code else None

        thumbnail_path = images[0]['local_url'] if images else ''

        article = Article(
            title=title,
            subtitle=subtitle,
            content=body_html,
            section_id=section.id if section else None,
            subsection_id=subsection.id if subsection else None,
            author_name=meta.get('author_name', '웰다잉뉴스'),
            author_email=meta.get('author_email', 'welldyingnews@naver.com'),
            level='B',
            recognition='E',
            article_type='B',
            thumbnail_path=thumbnail_path,
            photo_caption=photo_caption,
            created_at=meta.get('created_at', datetime.now()),
            updated_at=datetime.now(),
        )
        db.session.add(article)
        db.session.commit()

        print(f"    저장 완료! article.id = {article.id}")
        print(f"    확인: http://localhost:5001/news/articleView.html?idxno={article.id}")
        return article.id


# ─── 메인 ─────────────────────────────────────────────

def migrate_article(idxno, remote_url=None, admin_id=None, admin_pw=None, dry_run=False):
    """기사 1건을 마이그레이션한다."""
    print(f"\n{'='*60}")
    print(f"기사 마이그레이션: idxno={idxno}")
    print(f"모드: {'DRY-RUN' if dry_run else ('리모트 POST → ' + remote_url if remote_url else '로컬 DB')}")
    print(f"{'='*60}")

    # 1. 원본 HTML 가져오기
    print("\n[1] 원본 HTML 가져오기...")
    html = fetch_article_html(idxno)
    print(f"    HTML 크기: {len(html):,} bytes")

    # 2. 파싱
    print("\n[2] 기사 데이터 파싱...")
    title, subtitle, body_html, meta = parse_article(html)
    print(f"    제목: {title}")
    print(f"    부제: {subtitle or '(없음)'}")
    print(f"    섹션: {meta.get('section_code', '?')} > {meta.get('subsection_code', '?')}")
    print(f"    기자: {meta.get('author_name', '?')}")
    print(f"    날짜: {meta.get('created_at', '?')}")

    # 3. 이미지 다운로드 (임시 디렉토리)
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix='migrate_')
    print(f"\n[3] 이미지 다운로드... (임시: {tmp_dir})")
    body_soup, images = process_body_images(body_html, tmp_dir)
    if not images:
        print("    이미지 없음")

    # 캡션 추출
    figcaption = body_soup.find('figcaption')
    photo_caption = figcaption.get_text(strip=True) if figcaption else ''

    if dry_run:
        # dry-run: src를 로컬 경로로 치환해서 미리보기
        for info in images:
            info['img_tag']['src'] = info['local_url']
        print(f"\n[DRY RUN] 저장 건너뜀")
        print(f"\n본문 미리보기 (처음 500자):")
        print(str(body_soup)[:500])
        return None

    if remote_url:
        # ─── 리모트 POST 방식 ───
        print(f"\n[4] 리모트 서버 로그인... ({remote_url})")
        session = http_requests.Session()
        if not remote_login(session, remote_url, admin_id, admin_pw):
            print("    중단: 로그인 실패")
            return None

        # 이미지 업로드 → 리모트 URL 획득 → 본문 src 치환
        print("\n[5] 이미지 리모트 업로드...")
        thumbnail_url = ''
        for info in images:
            uploaded_url = remote_upload_image(session, remote_url, info['local_path'], info['filename'])
            if uploaded_url:
                info['img_tag']['src'] = uploaded_url
                if not thumbnail_url:
                    thumbnail_url = uploaded_url
            else:
                # 업로드 실패 시 원본 URL 유지
                info['img_tag']['src'] = info['original_url']

        processed_body = str(body_soup)

        # 섹션 ID 매핑
        section_id = SECTION_CODE_TO_ID.get(meta.get('section_code', 'S1N1'), 1)
        subsection_id = SUBSECTION_CODE_TO_ID.get(meta.get('subsection_code', ''), '')

        # 기사 POST
        print("\n[6] 기사 POST...")
        form_data = {
            'title': title,
            'subtitle': subtitle,
            'content': processed_body,
            'author_name': meta.get('author_name', '웰다잉뉴스'),
            'author_email': meta.get('author_email', 'welldyingnews@naver.com'),
            'section_id': section_id,
            'subsection_id': subsection_id,
            'level': 'B',
            'recognition': 'E',
            'article_type': 'B',
            'photo_caption': photo_caption,
        }
        success = remote_create_article(session, remote_url, form_data)
        if success:
            print(f"    확인: {remote_url}/news/articleView.html")
        return success

    else:
        # ─── 로컬 DB 방식 ───
        # 본문 이미지 src를 로컬 경로로 치환
        for info in images:
            info['img_tag']['src'] = info['local_url']
        processed_body = str(body_soup)

        # 로컬 uploads 디렉토리로 이미지 복사
        from app import create_app
        app = create_app()
        with app.app_context():
            upload_dir = app.config.get('UPLOAD_FOLDER',
                                         os.path.join(app.static_folder, 'uploads'))
            os.makedirs(upload_dir, exist_ok=True)
            import shutil
            for info in images:
                dest = os.path.join(upload_dir, info['filename'])
                shutil.copy2(info['local_path'], dest)

        print("\n[4] 로컬 DB 저장...")
        return local_save(title, subtitle, processed_body, meta, images, photo_caption)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='원본 기사 마이그레이션')
    parser.add_argument('--idxno', type=int, required=True, help='원본 기사 번호')
    parser.add_argument('--remote', type=str, default=None,
                        help='리모트 서버 URL (예: https://www.welldyingnews.com)')
    parser.add_argument('--admin-id', type=str, default=None, help='관리자 ID')
    parser.add_argument('--admin-pw', type=str, default=None, help='관리자 비밀번호')
    parser.add_argument('--dry-run', action='store_true', help='DB 저장 없이 확인만')
    args = parser.parse_args()

    # 리모트 모드일 때 관리자 계정 필요
    if args.remote:
        admin_id = args.admin_id
        admin_pw = args.admin_pw
        if not admin_id or not admin_pw:
            # .env에서 읽기 시도
            from dotenv import load_dotenv
            load_dotenv()
            admin_id = admin_id or os.environ.get('ADMIN_USER_ID', '')
            admin_pw = admin_pw or os.environ.get('ADMIN_PASSWORD', '')
        if not admin_id or not admin_pw:
            print("에러: --admin-id, --admin-pw 또는 .env의 ADMIN_USER_ID/ADMIN_PASSWORD 필요")
            sys.exit(1)
        migrate_article(args.idxno, remote_url=args.remote,
                        admin_id=admin_id, admin_pw=admin_pw, dry_run=args.dry_run)
    else:
        migrate_article(args.idxno, dry_run=args.dry_run)
