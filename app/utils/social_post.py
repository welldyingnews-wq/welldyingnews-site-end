"""SNS 자동 포스팅 유틸리티 — 기사 승인 시 X(트위터)에 자동 게시"""

import os
import logging
import requests
from requests_oauthlib import OAuth1

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get('SITE_URL', 'https://www.welldyingnews.com')


def post_to_x(article):
    """기사를 X(트위터)에 포스팅. 성공 시 tweet_id, 실패 시 None 반환."""
    api_key = os.environ.get('X_API_KEY')
    api_secret = os.environ.get('X_API_SECRET')
    access_token = os.environ.get('X_ACCESS_TOKEN')
    access_secret = os.environ.get('X_ACCESS_SECRET')

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning('X API 키가 설정되지 않음 — 포스팅 건너뜀')
        return None

    # 트윗 텍스트 구성: SNS 커스텀 텍스트 또는 제목 + URL + 해시태그
    url = f'{SITE_URL}/news/articleView.html?idxno={article.id}'
    title = article.sns_text if article.sns_text else article.title

    # 해시태그 (keyword에서 추출, 최대 3개)
    hashtags = ''
    if article.keyword:
        tags = [f'#{t.strip().replace(" ", "")}' for t in article.keyword.split(',') if t.strip()]
        if tags:
            hashtags = ' ' + ' '.join(tags[:3])

    # X 최대 280자 (URL은 23자로 카운트)
    max_title_len = 280 - 23 - 2 - len(hashtags)  # URL(23) + 줄바꿈(2) + 해시태그
    if len(title) > max_title_len:
        title = title[:max_title_len - 1] + '…'

    text = f'{title}\n{url}{hashtags}'

    auth = OAuth1(api_key, api_secret, access_token, access_secret)

    try:
        resp = requests.post(
            'https://api.twitter.com/2/tweets',
            json={'text': text},
            auth=auth,
            timeout=15
        )
        if resp.status_code == 201:
            tweet_id = resp.json().get('data', {}).get('id')
            logger.info(f'X 포스팅 성공: article={article.id}, tweet={tweet_id}')
            return tweet_id
        else:
            logger.error(f'X 포스팅 실패: {resp.status_code} {resp.text}')
            return None
    except Exception as e:
        logger.error(f'X 포스팅 에러: {e}')
        return None
