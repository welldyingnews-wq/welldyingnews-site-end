"""
국립연명의료관리기관(lst.go.kr) 실시간 통계 크롤링
- 사전연명의료의향서 등록 (advance_directive)
- 연명의료계획서 (care_plan)
- 연명의료중단결정 (lst_decision)
"""
import re
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

LST_MAIN_URL = 'https://www.lst.go.kr/main/main.do'
TIMEOUT = 15


def fetch_lst_stats():
    """메인 페이지에서 3종 누적 수치를 크롤링하여 dict로 반환.

    Returns:
        dict | None: {
            'advance_directive': int,
            'care_plan': int,
            'lst_decision': int,
            'as_of': str,  # e.g. '2026.03.07 17:00'
        }
    """
    try:
        resp = requests.get(LST_MAIN_URL, timeout=TIMEOUT, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; WelldyingNews/1.0)',
        })
        resp.raise_for_status()
        html = resp.text

        # <strong class="map-strong">3,264,141</strong> 패턴 추출
        numbers = re.findall(r'<strong\s+class="map-strong">\s*([\d,]+)\s*</strong>', html)
        if len(numbers) < 3:
            logger.error(f'LST 크롤링: map-strong 태그 {len(numbers)}개만 발견 (3개 필요)')
            return None

        # 기준 시간 추출
        as_of_match = re.search(r'<p\s+class="map_txt">\s*\(([^)]+)\s*기준\)', html)
        as_of = as_of_match.group(1).strip() if as_of_match else datetime.now().strftime('%Y.%m.%d %H:%M')

        return {
            'advance_directive': int(numbers[0].replace(',', '')),
            'care_plan': int(numbers[1].replace(',', '')),
            'lst_decision': int(numbers[2].replace(',', '')),
            'as_of': as_of,
        }
    except Exception as e:
        logger.error(f'LST 크롤링 실패: {e}')
        return None


def update_lst_stats(app=None):
    """DB의 WelldyingStat 테이블을 최신 값으로 갱신.

    Args:
        app: Flask app instance (없으면 current_app 사용)
    Returns:
        bool: 성공 여부
    """
    data = fetch_lst_stats()
    if not data:
        return False

    from app import db
    from app.models import WelldyingStat

    try:
        if app:
            ctx = app.app_context()
            ctx.push()

        updated = 0
        for key in ('advance_directive', 'care_plan', 'lst_decision'):
            stat = WelldyingStat.query.filter_by(indicator_key=key).first()
            if stat and data[key]:
                old_val = stat.value
                stat.value = data[key]
                stat.as_of_date = data['as_of']
                stat.updated_at = datetime.now()
                updated += 1
                logger.info(f'LST 갱신: {key} {old_val:,.0f} → {data[key]:,}')

        if updated:
            db.session.commit()
            logger.info(f'LST 통계 {updated}건 갱신 완료 (기준: {data["as_of"]})')

        if app:
            ctx.pop()

        return True
    except Exception as e:
        logger.error(f'LST DB 갱신 실패: {e}')
        db.session.rollback()
        return False
