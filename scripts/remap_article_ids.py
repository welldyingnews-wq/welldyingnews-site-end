"""
기사 ID를 원본 사이트의 idxno와 일치시키는 스크립트.

마이그레이션 시 AUTO INCREMENT로 부여된 ID를 원본 idxno로 재매핑하여
URL 영속성을 보장한다.

사용법:
    # 로컬 DB (기본)
    python scripts/remap_article_ids.py

    # 특정 DB 파일 지정
    python scripts/remap_article_ids.py --db /path/to/welldying.db

    # dry-run (변경 없이 확인만)
    python scripts/remap_article_ids.py --dry-run
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_PATH = os.path.join(SCRIPT_DIR, 'migrate_log.json')
DEFAULT_DB = os.path.join(PROJECT_DIR, 'welldying.db')

# article.id를 FK로 참조하는 테이블 목록
FK_TABLES = [
    ('page_view', 'article_id'),
    ('visitor_log', 'article_id'),
    ('article_draft', 'article_id'),
    ('article_extra_section', 'article_id'),
    ('article_extra_subsection', 'article_id'),
    ('article_relation', 'article_id'),
    ('article_relation', 'related_article_id'),
    ('article_comment', 'article_id'),
    ('newsletter', 'briefing_article_id'),
    ('ai_draft', 'article_id'),
]

# 임시 ID 오프셋 (충돌 방지용)
TEMP_OFFSET = 1_000_000


def load_migration_log():
    with open(LOG_PATH, 'r') as f:
        log = json.load(f)
    return log['migrated']  # {orig_idxno_str: current_new_id}


def build_id_mapping(conn, migrated):
    """전체 기사의 ID 매핑을 생성한다.
    - 마이그레이션된 기사: current_id → original_idxno
    - 수동 생성 기사: current_id → 1736+ (원본 최대 idxno 이후)
    """
    cur = conn.cursor()
    cur.execute('SELECT id FROM article ORDER BY id')
    all_ids = [row[0] for row in cur.fetchall()]

    # 역매핑: current_id → orig_idxno
    current_to_orig = {v: int(k) for k, v in migrated.items()}

    migrated_ids = set(current_to_orig.keys())
    manual_ids = [aid for aid in all_ids if aid not in migrated_ids]

    max_orig_idxno = max(int(k) for k in migrated.keys())
    next_id = max_orig_idxno + 1  # 1736~

    mapping = {}  # old_id → new_id

    # 마이그레이션 기사: current_id → original_idxno
    for current_id, orig_idxno in current_to_orig.items():
        mapping[current_id] = orig_idxno

    # 수동 생성 기사: 충돌 없는 ID 할당
    orig_idxnos = set(int(k) for k in migrated.keys())
    for manual_id in sorted(manual_ids):
        # 이미 원본 idxno와 겹치지 않으면 그대로 유지
        if manual_id not in orig_idxnos and manual_id not in current_to_orig:
            # 다른 매핑의 target과도 겹치지 않는지 확인
            if manual_id not in mapping.values():
                mapping[manual_id] = manual_id
                continue
        # 겹치면 새 ID 할당
        while next_id in orig_idxnos or next_id in mapping.values():
            next_id += 1
        mapping[manual_id] = next_id
        next_id += 1

    return mapping, manual_ids


def remap_ids(conn, mapping, dry_run=False):
    """2단계 리매핑: 임시 ID → 최종 ID"""
    cur = conn.cursor()

    # FK 체크 비활성화
    cur.execute('PRAGMA foreign_keys = OFF')

    total = len(mapping)
    changed = sum(1 for old, new in mapping.items() if old != new)
    unchanged = total - changed

    print(f'\n전체 기사: {total}건')
    print(f'  ID 변경: {changed}건')
    print(f'  ID 유지: {unchanged}건')

    if dry_run:
        print('\n[DRY-RUN] 변경 사항 미리보기:')
        samples = [(old, new) for old, new in sorted(mapping.items()) if old != new]
        for old, new in samples[:20]:
            cur.execute('SELECT title FROM article WHERE id = ?', (old,))
            row = cur.fetchone()
            title = row[0][:40] if row else '(없음)'
            print(f'  id={old:>5} → {new:>5}  {title}')
        if len(samples) > 20:
            print(f'  ... 외 {len(samples)-20}건')
        return

    # === Pass 1: 모든 변경 대상을 임시 ID로 이동 (충돌 방지) ===
    print('\n[Pass 1] 임시 ID로 이동...')
    changes = {old: new for old, new in mapping.items() if old != new}

    for old_id, new_id in changes.items():
        temp_id = old_id + TEMP_OFFSET
        cur.execute('UPDATE article SET id = ? WHERE id = ?', (temp_id, old_id))
        for tbl, col in FK_TABLES:
            try:
                cur.execute(f'UPDATE {tbl} SET {col} = ? WHERE {col} = ?', (temp_id, old_id))
            except sqlite3.OperationalError:
                pass  # 테이블이 없으면 무시

    print(f'  {len(changes)}건 → 임시 ID 이동 완료')

    # === Pass 2: 임시 ID를 최종 ID로 이동 ===
    print('[Pass 2] 최종 ID로 이동...')
    for old_id, new_id in changes.items():
        temp_id = old_id + TEMP_OFFSET
        cur.execute('UPDATE article SET id = ? WHERE id = ?', (new_id, temp_id))
        for tbl, col in FK_TABLES:
            try:
                cur.execute(f'UPDATE {tbl} SET {col} = ? WHERE {col} = ?', (new_id, temp_id))
            except sqlite3.OperationalError:
                pass

    print(f'  {len(changes)}건 → 최종 ID 이동 완료')

    # auto increment 시퀀스 업데이트 (AUTOINCREMENT 사용 시에만 존재)
    max_id = max(mapping.values())
    try:
        cur.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'article'", (max_id,))
    except sqlite3.OperationalError:
        pass  # sqlite_sequence 테이블 없으면 무시

    conn.commit()

    # FK 체크 재활성화
    cur.execute('PRAGMA foreign_keys = ON')

    print(f'\n  auto_increment 시퀀스: {max_id}')


def verify(conn, migrated):
    """리매핑 결과를 검증한다."""
    cur = conn.cursor()
    errors = 0

    print('\n[검증] 리매핑 결과 확인...')

    # 랜덤 샘플 5건 확인
    import random
    samples = random.sample(list(migrated.items()), min(5, len(migrated)))

    for orig_idxno_str, old_new_id in samples:
        orig_idxno = int(orig_idxno_str)
        cur.execute('SELECT id, title FROM article WHERE id = ?', (orig_idxno,))
        row = cur.fetchone()
        if row:
            print(f'  OK: idxno={orig_idxno} → id={row[0]}, "{row[1][:40]}"')
        else:
            print(f'  ERROR: idxno={orig_idxno} → 기사 없음!')
            errors += 1

    # 전체 매핑 검증
    cur.execute('SELECT COUNT(*) FROM article')
    total = cur.fetchone()[0]
    print(f'\n  전체 기사 수: {total}건')

    # 중복 ID 체크
    cur.execute('SELECT id, COUNT(*) as cnt FROM article GROUP BY id HAVING cnt > 1')
    dups = cur.fetchall()
    if dups:
        print(f'  ERROR: 중복 ID 발견! {dups}')
        errors += 1
    else:
        print(f'  중복 ID: 없음')

    # FK 무결성 체크
    cur.execute('PRAGMA foreign_key_check')
    fk_errors = cur.fetchall()
    if fk_errors:
        print(f'  WARNING: FK 무결성 오류 {len(fk_errors)}건')
        for e in fk_errors[:5]:
            print(f'    {e}')
    else:
        print(f'  FK 무결성: 정상')

    if errors == 0:
        print('\n  리매핑 검증 통과!')
    else:
        print(f'\n  ERROR: {errors}건의 오류 발견')

    return errors


def main():
    parser = argparse.ArgumentParser(description='기사 ID를 원본 idxno로 재매핑')
    parser.add_argument('--db', type=str, default=DEFAULT_DB, help='DB 파일 경로')
    parser.add_argument('--dry-run', action='store_true', help='변경 없이 확인만')
    args = parser.parse_args()

    db_path = args.db
    if not os.path.exists(db_path):
        print(f'ERROR: DB 파일 없음: {db_path}')
        sys.exit(1)

    if not os.path.exists(LOG_PATH):
        print(f'ERROR: 마이그레이션 로그 없음: {LOG_PATH}')
        sys.exit(1)

    print('=' * 60)
    print('기사 ID 재매핑 (원본 idxno 복원)')
    print('=' * 60)
    print(f'DB: {db_path}')
    print(f'로그: {LOG_PATH}')

    # 마이그레이션 로그 로드
    migrated = load_migration_log()
    print(f'마이그레이션 기사: {len(migrated)}건')

    # 백업
    if not args.dry_run:
        backup_path = db_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy2(db_path, backup_path)
        print(f'백업: {backup_path}')

    # DB 연결
    conn = sqlite3.connect(db_path)

    # 매핑 생성
    mapping, manual_ids = build_id_mapping(conn, migrated)

    print(f'\n수동 생성 기사: {len(manual_ids)}건')
    for mid in manual_ids[:5]:
        new_id = mapping[mid]
        status = f'→ {new_id}' if mid != new_id else '(유지)'
        print(f'  id={mid} {status}')

    # 리매핑 실행
    remap_ids(conn, mapping, dry_run=args.dry_run)

    # 검증
    if not args.dry_run:
        verify(conn, migrated)

    conn.close()

    print('\n' + '=' * 60)
    if args.dry_run:
        print('DRY-RUN 완료. 실제 변경하려면 --dry-run 없이 실행하세요.')
    else:
        print('재매핑 완료!')
    print('=' * 60)


if __name__ == '__main__':
    main()
