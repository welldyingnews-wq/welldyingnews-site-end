"""
AI 초안을 SQLite DB에 직접 저장 (Flask/SQLAlchemy 우회)
mounted filesystem의 disk I/O 문제를 /tmp 복사 방식으로 해결
"""
import json
import sqlite3
import sys
import os
import shutil
from datetime import datetime

DB_SRC = '/sessions/awesome-focused-goldberg/mnt/welldying-news/welldying.db'
DB_TMP = '/tmp/welldying_draft_work.db'
LOCK_FILE = '/tmp/welldying_db_lock'


def acquire_lock():
    """간단한 파일 기반 락"""
    import time
    for _ in range(60):  # 최대 60초 대기
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(1)
    return False


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except:
        pass


def save_draft(data: dict) -> int | None:
    """초안 1건 저장. 성공 시 id 반환, 중복이면 None"""
    if not acquire_lock():
        print("ERROR: DB 락 획득 실패 (60초 초과)")
        return None

    try:
        # 최신 DB 가져오기
        shutil.copy2(DB_SRC, DB_TMP)

        conn = sqlite3.connect(DB_TMP)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        url = data.get('link', '')

        # 중복 확인
        if url:
            cur.execute('SELECT id FROM ai_draft WHERE original_url = ?', (url,))
            if cur.fetchone():
                conn.close()
                print(f'SKIP (중복): {url[:80]}')
                return None

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
        new_id = cur.lastrowid
        conn.commit()
        conn.close()

        # 원본 DB에 복사 (저장)
        shutil.copy2(DB_TMP, DB_SRC)
        print(f'SAVED: AiDraft #{new_id} - {data.get("title", "")[:50]}')
        return new_id

    except Exception as e:
        print(f'ERROR: {e}')
        return None
    finally:
        release_lock()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=str, help='JSON 파일 경로')
    parser.add_argument('--json', type=str, help='JSON 문자열')
    args = parser.parse_args()

    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    elif args.json:
        data = json.loads(args.json)
    else:
        data = json.load(sys.stdin)

    if isinstance(data, list):
        saved = 0
        for item in data:
            if save_draft(item):
                saved += 1
        print(f'총 {saved}/{len(data)}건 저장')
    else:
        save_draft(data)


if __name__ == '__main__':
    main()
