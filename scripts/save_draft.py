"""Claude Cowork가 작성한 초안을 서버 AI Draft API로 저장

Usage:
    # JSON 문자열로 전달
    python scripts/save_draft.py --json '{"collect_id":619, "title":"제목", ...}'

    # JSON 파일로 전달
    python scripts/save_draft.py --file scripts/draft_output.json

    # 중복 확인 (original_url 기준)
    python scripts/save_draft.py --check-url "https://example.com/article"
"""
import argparse
import json
import os
import re
import sys

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')

API_URL = os.environ.get(
    'AI_DRAFT_API_URL',
    'https://www.welldyingnews.com/admin/api/ai-draft',
)
API_KEY = os.environ.get('AI_DRAFT_API_KEY', '')

# .env 파일에서 키 로드 (환경변수 미설정 시)
ENV_VARS = {}
if not API_KEY:
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    ENV_VARS[k.strip()] = v.strip().strip("'\"")
        API_KEY = ENV_VARS.get('AI_DRAFT_API_KEY', '')


def upload_chart_to_cloudinary(filepath):
    """차트 이미지를 Cloudinary에 업로드하고 URL 반환"""
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME') or ENV_VARS.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY') or ENV_VARS.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET') or ENV_VARS.get('CLOUDINARY_API_SECRET')

    if not (cloud_name and api_key and api_secret):
        print(f'  WARN: Cloudinary 미설정, 차트 업로드 스킵: {filepath}')
        return None

    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=cloud_name, api_key=api_key,
        api_secret=api_secret, secure=True,
    )
    result = cloudinary.uploader.upload(filepath, folder='welldying/charts', resource_type='image')
    url = result.get('secure_url')
    print(f'  차트 업로드: {os.path.basename(filepath)} -> {url}')
    return url


def process_chart_images(data, json_file_dir=None):
    """content 내 로컬 차트 이미지를 Cloudinary에 업로드하고 URL로 교체

    차트 파일 탐색 순서:
    1. /tmp/chart_{id}.png
    2. JSON 파일이 있던 디렉토리
    3. scripts/collected/
    """
    content = data.get('content', '')
    if not content:
        return data

    # <img src="chart_608.png" ...> 패턴 찾기
    img_pattern = re.compile(r'(<img[^>]+src=")([^"]*chart_[^"]+\.png)("[^>]*>)')
    matches = img_pattern.findall(content)
    if not matches:
        return data

    search_dirs = ['/tmp']
    if json_file_dir:
        search_dirs.append(json_file_dir)
    search_dirs.append(os.path.join(PROJECT_ROOT, 'scripts', 'collected'))

    for prefix, filename, suffix in matches:
        basename = os.path.basename(filename)

        # 파일 찾기
        found_path = None
        for d in search_dirs:
            candidate = os.path.join(d, basename)
            if os.path.exists(candidate):
                found_path = candidate
                break

        if not found_path:
            print(f'  WARN: 차트 파일 못 찾음: {basename}')
            continue

        cloud_url = upload_chart_to_cloudinary(found_path)
        if cloud_url:
            content = content.replace(f'{prefix}{filename}{suffix}',
                                      f'{prefix}{cloud_url}{suffix}')

    data['content'] = content
    return data


def save_draft(data, json_file_dir=None):
    """초안 데이터를 서버 API로 전송

    Args:
        data: dict with keys:
            - collect_id (int): Supabase collect ID
            - source_data (dict, optional): 원본 수집 데이터
            - link (str): 원문 URL
            - title (str): 기사 제목
            - subtitle (str): 부제/리드문
            - content (str): 본문 HTML
            - summary (str): 요약 200자
            - keywords (str): 키워드 (쉼표 구분)
            - section_id (int): 섹션 ID
            - subsection_id (int): 서브섹션 ID
            - grade (str): A1/A2/B
            - article_type (str): 스트레이트/해설/단신
            - author_name (str, optional): 기자명 (기본: 웰다잉뉴스)
            - source_text (str, optional): 출처 표시
        json_file_dir: JSON 파일이 있던 디렉토리 (차트 파일 탐색용)

    Returns:
        int: 생성된 AiDraft ID, 실패 시 None
    """
    if not API_KEY:
        print('ERROR: AI_DRAFT_API_KEY가 설정되지 않았습니다 (.env 또는 환경변수)')
        return None

    # 차트 이미지 업로드 처리
    data = process_chart_images(data, json_file_dir)

    resp = requests.post(
        API_URL,
        json=data,
        headers={'Authorization': f'Bearer {API_KEY}'},
        timeout=30,
    )

    if resp.status_code == 201:
        result = resp.json()
        return result.get('id')
    elif resp.status_code == 409:
        result = resp.json()
        print(f'SKIP: 이미 존재하는 URL (기존 ID: {result.get("existing_id")})')
        return None
    else:
        print(f'ERROR [{resp.status_code}]: {resp.text}')
        return None


def main():
    parser = argparse.ArgumentParser(description='초안 → 서버 AiDraft API 저장')
    parser.add_argument('--json', type=str, help='JSON 문자열로 초안 데이터 전달')
    parser.add_argument('--file', type=str, help='JSON 파일 경로')
    parser.add_argument('--check-url', type=str, help='URL 중복 확인만')
    args = parser.parse_args()

    # 중복 확인 모드 (서버에 POST해서 409 여부로 판단)
    if args.check_url:
        resp = requests.post(
            API_URL,
            json={'link': args.check_url, 'title': '__check__'},
            headers={'Authorization': f'Bearer {API_KEY}'},
            timeout=10,
        )
        if resp.status_code == 409:
            print(f'DUPLICATE: {args.check_url[:80]}')
            sys.exit(1)
        else:
            print(f'NEW: {args.check_url[:80]}')
            sys.exit(0)

    # 데이터 로드
    json_file_dir = None
    if args.json:
        data = json.loads(args.json)
    elif args.file:
        json_file_dir = os.path.dirname(os.path.abspath(args.file))
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        # stdin에서 읽기
        data = json.load(sys.stdin)

    # 단일 또는 배치
    if isinstance(data, list):
        saved = 0
        for item in data:
            draft_id = save_draft(item, json_file_dir)
            if draft_id:
                print(f'SAVED: AiDraft #{draft_id} - {item.get("title", "")[:50]}')
                saved += 1
        print(f'\n총 {saved}/{len(data)}건 저장 완료')
    else:
        draft_id = save_draft(data, json_file_dir)
        if draft_id:
            print(f'SAVED: AiDraft #{draft_id} - {data.get("title", "")[:50]}')


if __name__ == '__main__':
    main()
