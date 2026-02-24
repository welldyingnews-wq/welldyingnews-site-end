"""
로컬 이미지를 Cloudinary로 일괄 마이그레이션하는 스크립트.

1. app/static/uploads/ 내 모든 파일을 Cloudinary에 업로드
2. DB의 thumbnail_path, content, banner.image_path, popup.image_path 내
   /static/uploads/... 경로를 Cloudinary URL로 교체
3. 로컬 파일은 삭제하지 않음 (백업 유지)

사용법:
    source .venv/bin/activate
    python scripts/migrate_to_cloudinary.py
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import cloudinary
import cloudinary.uploader

from app import create_app
from app.models import db, Article, Banner, Popup, Member

# Cloudinary 설정
cloudinary.config(
    cloud_name=os.environ['CLOUDINARY_CLOUD_NAME'],
    api_key=os.environ['CLOUDINARY_API_KEY'],
    api_secret=os.environ['CLOUDINARY_API_SECRET'],
    secure=True,
)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'app', 'static', 'uploads')


def upload_to_cloudinary(local_path, folder='welldying/uploads'):
    """로컬 파일을 Cloudinary에 업로드하고 secure_url 반환"""
    ext = local_path.rsplit('.', 1)[-1].lower()
    if ext in ('mp4', 'webm', 'mov', 'avi'):
        resource_type = 'video'
    elif ext in ('pdf', 'doc', 'docx', 'hwp', 'zip'):
        resource_type = 'raw'
    else:
        resource_type = 'image'

    result = cloudinary.uploader.upload(
        local_path, folder=folder, resource_type=resource_type
    )
    return result.get('secure_url')


def migrate_files():
    """로컬 파일을 Cloudinary에 업로드하고 URL 매핑 생성"""
    url_map = {}  # {'/static/uploads/filename': 'https://res.cloudinary.com/...'}

    files = [f for f in os.listdir(UPLOAD_DIR)
             if os.path.isfile(os.path.join(UPLOAD_DIR, f)) and not f.startswith('.')]
    total = len(files)
    print(f'총 {total}개 파일 업로드 시작...\n')

    success = 0
    failed = 0
    for i, fname in enumerate(files, 1):
        local_path = os.path.join(UPLOAD_DIR, fname)
        local_url = f'/static/uploads/{fname}'

        try:
            cloud_url = upload_to_cloudinary(local_path)
            url_map[local_url] = cloud_url
            success += 1
            if i % 50 == 0 or i == total:
                print(f'  [{i}/{total}] 업로드 완료 ({success} 성공, {failed} 실패)')
        except Exception as e:
            failed += 1
            print(f'  [{i}/{total}] 실패: {fname} — {e}')
            # 실패한 파일은 로컬 URL 유지
            url_map[local_url] = local_url

        # API 속도 제한 방지
        if i % 100 == 0:
            time.sleep(1)

    print(f'\n업로드 완료: {success} 성공, {failed} 실패')
    return url_map


def update_database(url_map):
    """DB 내 로컬 경로를 Cloudinary URL로 교체"""
    print('\n=== DB 업데이트 시작 ===')

    # 1. Article.thumbnail_path
    articles = Article.query.filter(
        Article.thumbnail_path.like('%/static/uploads/%')
    ).all()
    count = 0
    for art in articles:
        old = art.thumbnail_path
        if old in url_map and url_map[old] != old:
            art.thumbnail_path = url_map[old]
            count += 1
    print(f'thumbnail_path 업데이트: {count}개')

    # 2. Article.content 내 이미지 URL
    articles = Article.query.filter(
        Article.content.contains('/static/uploads/')
    ).all()
    count = 0
    for art in articles:
        new_content = art.content
        changed = False
        for local_url, cloud_url in url_map.items():
            if local_url == cloud_url:
                continue
            if local_url in new_content:
                new_content = new_content.replace(local_url, cloud_url)
                changed = True
        if changed:
            art.content = new_content
            count += 1
    print(f'content 내 이미지 업데이트: {count}개 기사')

    # 3. Banner.image_path
    banners = Banner.query.filter(
        Banner.image_path.like('%/static/uploads/%')
    ).all()
    count = 0
    for b in banners:
        if b.image_path in url_map and url_map[b.image_path] != b.image_path:
            b.image_path = url_map[b.image_path]
            count += 1
    print(f'배너 업데이트: {count}개')

    # 4. Popup.image_path
    popups = Popup.query.filter(
        Popup.image_path.like('%/static/uploads/%')
    ).all()
    count = 0
    for p in popups:
        if p.image_path in url_map and url_map[p.image_path] != p.image_path:
            p.image_path = url_map[p.image_path]
            count += 1
    print(f'팝업 업데이트: {count}개')

    # 5. Member.profile_image
    members = Member.query.filter(
        Member.profile_image.like('%/static/uploads/%')
    ).all()
    count = 0
    for m in members:
        if m.profile_image in url_map and url_map[m.profile_image] != m.profile_image:
            m.profile_image = url_map[m.profile_image]
            count += 1
    print(f'회원 프로필 업데이트: {count}개')

    db.session.commit()
    print('\nDB 업데이트 완료!')


def main():
    app = create_app()
    with app.app_context():
        print('=' * 50)
        print(' Cloudinary 마이그레이션 시작')
        print('=' * 50)

        # 1단계: 파일 업로드
        url_map = migrate_files()

        # URL 매핑 백업 저장
        import json
        map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'url_map.json')
        with open(map_path, 'w') as f:
            json.dump(url_map, f, indent=2)
        print(f'\nURL 매핑 저장: {map_path}')

        # 2단계: DB 업데이트
        update_database(url_map)

        print('\n' + '=' * 50)
        print(' 마이그레이션 완료!')
        print(' 로컬 파일은 삭제되지 않았습니다 (백업)')
        print('=' * 50)


if __name__ == '__main__':
    main()
