"""
기사 초안을 /tmp/welldying_drafts/에 JSON 파일로 저장 (DB 직접 저장 없음)
race condition 방지: 각 파일은 collect_id 기반 고유 파일명 사용
"""
import json
import sys
import os
import argparse


DRAFTS_DIR = '/tmp/welldying_drafts'


def write_draft(data: dict) -> str | None:
    """초안 데이터를 JSON 파일로 저장. 성공 시 파일 경로 반환."""
    os.makedirs(DRAFTS_DIR, exist_ok=True)

    collect_id = data.get('collect_id', 'unknown')
    fpath = os.path.join(DRAFTS_DIR, f'draft_{collect_id}.json')

    # 이미 처리된 파일은 스킵
    if os.path.exists(fpath):
        print(f'SKIP (이미 존재): draft_{collect_id}.json')
        return None

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'WRITTEN: draft_{collect_id}.json - {data.get("title", "")[:50]}')
    return fpath


def main():
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
        written = 0
        for item in data:
            if write_draft(item):
                written += 1
        print(f'총 {written}/{len(data)}건 저장')
    else:
        write_draft(data)


if __name__ == '__main__':
    main()
