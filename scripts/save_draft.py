"""Claude Code가 작성한 초안을 AiDraft DB에 저장

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
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import db, AiDraft


def is_duplicate(url):
    """이미 같은 URL로 AiDraft가 존재하는지 확인"""
    if not url:
        return False
    return AiDraft.query.filter_by(original_url=url).first() is not None


def save_draft(data):
    """초안 데이터를 AiDraft 레코드로 저장

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

    Returns:
        int: 생성된 AiDraft ID
    """
    url = data.get('link', '')

    # 중복 확인
    if is_duplicate(url):
        print(f'SKIP: 이미 존재하는 URL - {url[:80]}')
        return None

    draft = AiDraft(
        source_news_ids=json.dumps([data.get('collect_id', '')]),
        source_data=json.dumps(data.get('source_data', {}), ensure_ascii=False),
        original_url=url,
        title=data.get('title', ''),
        subtitle=data.get('subtitle', ''),
        content=data.get('content', ''),
        summary=data.get('summary', ''),
        keywords=data.get('keywords', ''),
        author_name=data.get('author_name', '웰다잉뉴스'),
        source_text=data.get('source_text', ''),
        grade=data.get('grade', 'A2'),
        article_type=data.get('article_type', '스트레이트'),
        suggested_section_id=data.get('section_id'),
        suggested_subsection_id=data.get('subsection_id'),
        status='completed',
        ai_models_used='claude-code',
        validation_score=80,
    )
    db.session.add(draft)
    db.session.commit()
    return draft.id


def main():
    parser = argparse.ArgumentParser(description='초안 → AiDraft DB 저장')
    parser.add_argument('--json', type=str, help='JSON 문자열로 초안 데이터 전달')
    parser.add_argument('--file', type=str, help='JSON 파일 경로')
    parser.add_argument('--check-url', type=str, help='URL 중복 확인만')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        # 중복 확인 모드
        if args.check_url:
            dup = is_duplicate(args.check_url)
            print(f'{"DUPLICATE" if dup else "NEW"}: {args.check_url[:80]}')
            sys.exit(0 if not dup else 1)

        # 데이터 로드
        if args.json:
            data = json.loads(args.json)
        elif args.file:
            with open(args.file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # stdin에서 읽기
            data = json.load(sys.stdin)

        # 단일 또는 배치
        if isinstance(data, list):
            saved = 0
            for item in data:
                draft_id = save_draft(item)
                if draft_id:
                    print(f'SAVED: AiDraft #{draft_id} - {item.get("title", "")[:50]}')
                    saved += 1
            print(f'\n총 {saved}/{len(data)}건 저장 완료')
        else:
            draft_id = save_draft(data)
            if draft_id:
                print(f'SAVED: AiDraft #{draft_id} - {data.get("title", "")[:50]}')


if __name__ == '__main__':
    main()
