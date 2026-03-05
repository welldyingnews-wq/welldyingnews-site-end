"""
/tmp/welldying_drafts/ 폴더의 모든 JSON 파일을 읽어 DB에 일괄 저장
race condition 없이 단일 프로세스로 순차 임포트
"""
import json
import sqlite3
import sys
import os
import shutil
import glob
from datetime import datetime

DB_SRC = '/sessions/awesome-focused-goldberg/mnt/welldying-news/welldying.db'
DB_BASE = '/tmp/clean_base.db'
DRAFTS_DIR = '/tmp/welldying_drafts'


def import_all():
    # 최신 DB 복사
    shutil.copy2(DB_SRC, '/tmp/import_work.db')
    conn = sqlite3.connect('/tmp/import_work.db')
    cur = conn.cursor()

    # 이미 저장된 URL 목록
    cur.execute('SELECT original_url FROM ai_draft')
    saved_urls = set(row[0] for row in cur.fetchall())
    print(f'이미 저장된 초안: {len(saved_urls)}건')

    # JSON 파일 목록
    draft_files = sorted(glob.glob(os.path.join(DRAFTS_DIR, '*.json')))
    print(f'임포트할 파일: {len(draft_files)}개')

    saved = 0
    skipped = 0
    errors = 0

    for fpath in draft_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            url = data.get('link', '')
            if url in saved_urls:
                skipped += 1
                continue

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cur.execute('''
                INSERT INTO ai_draft (
                    source_news_ids, source_data, original_url,
                    title, subtitle, content, summary, keywords,
                    author_name, source_text, grade, article_type,
                    suggested_section_id, suggested_subsection_id,
                    status, ai_models_used, validation_score,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                json.dumps([data.get('collect_id', '')]),
                json.dumps(data.get('source_data', {}), ensure_ascii=False),
                url,
                data.get('title', ''),
                data.get('subtitle', ''),
                data.get('content', ''),
                data.get('summary', ''),
                data.get('keywords', ''),
                data.get('author_name', '웰다잉뉴스'),
                data.get('source_text', ''),
                data.get('grade', 'A2'),
                data.get('article_type', '스트레이트'),
                data.get('section_id'),
                data.get('subsection_id'),
                'completed',
                'claude-cowork',
                80,
                now,
                now,
            ))
            saved_urls.add(url)
            saved += 1
            print(f'SAVED: {data.get("title", "")[:50]}')

        except Exception as e:
            errors += 1
            print(f'ERROR {fpath}: {e}')

    conn.commit()
    cur.execute('SELECT count(*) FROM ai_draft')
    total = cur.fetchone()[0]
    conn.close()

    # 원본 DB에 복사
    shutil.copy2('/tmp/import_work.db', DB_SRC)
    print(f'\n=== 임포트 완료 ===')
    print(f'저장: {saved}건 | 중복스킵: {skipped}건 | 에러: {errors}건')
    print(f'총 DB 초안: {total}건')


if __name__ == '__main__':
    import_all()
