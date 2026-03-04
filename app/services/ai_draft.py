"""AI 기사 초안 파이프라인 (Google Gemini)

Step 1: Flash 배치 분류
Step 0: 원문 스크래핑 + 관련기사 검색
Step 2: Pro 자료 패키지 생성
Step 3: Pro 기사 작성
Step 4a: Flash 기계적 검증
Step 4b: Pro 할루시네이션 대조 검증
"""
import html
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import current_app

from app.models import db, AiDraft
from app.services.scraper import scrape_article_content, search_naver, search_google_cse

logger = logging.getLogger(__name__)

# ── 상태 상수 ──
STATUS_PENDING = 'pending'
STATUS_CURATING = 'curating'
STATUS_SCRAPING = 'scraping'
STATUS_GENERATING = 'generating'
STATUS_VALIDATING = 'validating'
STATUS_COMPLETED = 'completed'
STATUS_SKIPPED = 'skipped'
STATUS_PUBLISHED = 'published'
STATUS_REJECTED = 'rejected'

# 서버 시작 시 복구 대상 상태
STALE_STATUSES = [STATUS_CURATING, STATUS_SCRAPING, STATUS_GENERATING, STATUS_VALIDATING]

_ai_client = None

# API 호출 간 딜레이 (초) — Gemini 무료 티어 rate limit 대응
API_CALL_DELAY = 5
MAX_RETRIES = 3


def _get_client():
    """Gemini 클라이언트 싱글턴"""
    global _ai_client
    if _ai_client is None:
        from google import genai
        _ai_client = genai.Client(api_key=current_app.config['GEMINI_API_KEY'])
    return _ai_client


def _extract_retry_delay(error_str):
    """Gemini 429 에러에서 retryDelay 파싱 (예: 'Please retry in 34.5s')"""
    match = re.search(r'retry in (\d+(?:\.\d+)?)s', error_str)
    if match:
        return float(match.group(1)) + 2  # 여유 2초 추가
    return None


def _call_ai(model_key, system_prompt, user_prompt, max_tokens=4096):
    """Gemini API 호출 래퍼 (재시도 + 딜레이 포함)

    Returns:
        tuple: (text, usage_dict)
    """
    from google.genai import types

    client = _get_client()
    model = current_app.config[model_key]

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                # 이전 에러에서 retry delay 파싱, 없으면 지수 백오프
                retry_delay = _extract_retry_delay(str(last_error))
                wait = retry_delay or (API_CALL_DELAY * (2 ** (attempt + 1)))
                logger.info(f'API 재시도 {attempt + 1}/{MAX_RETRIES} ({wait:.0f}초 대기)')
                time.sleep(wait)

            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                    response_mime_type='application/json',
                ),
            )
            text = response.text or ''
            meta = response.usage_metadata
            usage = {
                'input_tokens': meta.prompt_token_count if meta else 0,
                'output_tokens': meta.candidates_token_count if meta else 0,
                'model': model,
            }

            # 다음 호출까지 딜레이
            time.sleep(API_CALL_DELAY)
            return text, usage

        except Exception as e:
            last_error = e
            error_str = str(e)
            # 503/429 = 재시도 가능, 그 외는 즉시 실패
            if '503' in error_str or '429' in error_str or 'UNAVAILABLE' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                logger.warning(f'API 제한 (attempt {attempt + 1}): {error_str[:150]}')
                continue
            raise  # 다른 에러는 즉시 raise

    raise last_error  # 재시도 모두 실패


def _parse_json_response(text):
    """AI 응답에서 JSON 추출 (response_mime_type=json이면 보통 깨끗하게 옴)"""
    if not text or not text.strip():
        logger.warning('JSON 파싱 실패: 빈 응답')
        return None

    # BOM 제거 + strip
    text = text.strip().lstrip('\ufeff')

    # Gemini가 간혹 ```json 코드블록으로 감쌀 수 있음
    if text.startswith('```'):
        lines = text.split('\n')
        lines = lines[1:]  # ```json 제거
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()

    # 1차: 직접 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2차: 코드블록이 중간에 있을 때 — ```json ... ``` 추출
    code_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', text)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3차: {...} 또는 [...] 범위 추출
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    # 4차: 잘린 JSON 배열 복구 (max_output_tokens 초과 시)
    if text.startswith('['):
        # 마지막 완전한 객체 끝(})까지 잘라서 배열 닫기
        last_brace = text.rfind('}')
        if last_brace > 0:
            try:
                return json.loads(text[:last_brace + 1] + ']')
            except json.JSONDecodeError:
                pass

    logger.warning('JSON 파싱 실패 (len=%d): %s', len(text), text[:300])
    return None


def _strip_html(text):
    """HTML 태그 제거 + 엔티티 디코딩"""
    return html.unescape(re.sub(r'<[^>]+>', '', text or '')).strip()


def _track_usage(draft, usage):
    """토큰 사용량 + 모델명 추적"""
    draft.total_tokens_used += usage['input_tokens'] + usage['output_tokens']
    models = set(filter(None, draft.ai_models_used.split(','))) if draft.ai_models_used else set()
    models.add(usage['model'])
    draft.ai_models_used = ','.join(sorted(models))


def _safe_json_loads(text):
    """JSON 파싱 with fallback to empty dict"""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


# ── Step 1: Haiku 배치 분류 ──

CLASSIFY_SYSTEM = """당신은 뉴스 기사 큐레이터입니다. 기사를 분류하고 활용 가능 여부를 판단합니다.

## 큐레이션 기준

### 사용 가능 (usable=true)
- 보도자료, 공공기관 발표, 해외 소식, 학술/세미나 소식, 통계/보고서

### 사용 불가 (usable=false)
- '단독' 표시 기사, 칼럼/사설/기고, 심층 탐사보도, 단독 인터뷰, 유료 콘텐츠

## 등급 분류
- A1: 해설/분석 기사로 작성 가능 (심층적 주제, 다각적 분석 가능)
- A2: 스트레이트 기사로 작성 가능 (사실 전달 중심)
- B: 단신으로 작성 가능 (단순 소식)

응답은 반드시 JSON 배열로 출력하세요."""

CLASSIFY_USER = """다음 기사들을 분류해주세요. 각 기사에 대해 JSON으로 응답하세요.

기사 목록:
{articles_text}

응답 형식 (JSON 배열):
[
  {{
    "index": 0,
    "usable": true,
    "grade": "A2",
    "reason": "보도자료 기반 정책 소식",
    "suggested_type": "스트레이트",
    "suggested_section": "뉴스",
    "suggested_subsection": "정책ㆍ사회"
  }}
]"""


def run_classify(draft_ids):
    """Step 1: Haiku로 배치 분류"""
    drafts = AiDraft.query.filter(AiDraft.id.in_(draft_ids)).all()
    if not drafts:
        return

    # 상태 업데이트
    for d in drafts:
        d.status = STATUS_CURATING
    db.session.commit()

    # 배치 처리 (5건씩 — JSON 잘림 방지 + rate limit 고려)
    batch_size = 5

    for i in range(0, len(drafts), batch_size):
        batch = drafts[i:i + batch_size]

        # 배치 간 딜레이 (첫 배치 제외)
        if i > 0:
            time.sleep(API_CALL_DELAY)
        articles_text = ''
        for idx, d in enumerate(batch):
            src = _safe_json_loads(d.source_data)
            title = src.get('title_ko') or src.get('title', '제목 없음')
            desc = src.get('description', '')[:200]
            source = src.get('source', '')
            articles_text += f"\n[{idx}] 제목: {title}\n출처: {source}\n설명: {desc}\n"

        try:
            result_text, usage = _call_ai(
                'AI_FLASH_MODEL',
                CLASSIFY_SYSTEM,
                CLASSIFY_USER.format(articles_text=articles_text),
                max_tokens=4096,
            )
            batch_tokens = usage['input_tokens'] + usage['output_tokens']
            per_draft_tokens = batch_tokens // len(batch) if batch else 0
            results = _parse_json_response(result_text)

            if results and isinstance(results, list):
                result_map = {r['index']: r for r in results if 'index' in r}
                for idx, d in enumerate(batch):
                    r = result_map.get(idx, {})
                    d.curation_result = json.dumps(r, ensure_ascii=False)
                    d.grade = r.get('grade', 'B')
                    d.article_type = r.get('suggested_type', '스트레이트')
                    d.total_tokens_used += per_draft_tokens
                    d.ai_models_used = usage['model']
                    if r.get('usable', False):
                        d.status = STATUS_PENDING
                    else:
                        d.status = STATUS_SKIPPED
                        d.skip_reason = r.get('reason', '사용 불가 판정')
            else:
                for d in batch:
                    d.status = STATUS_SKIPPED
                    d.skip_reason = 'AI 분류 응답 파싱 실패'

        except Exception as e:
            logger.error(f'분류 오류: {e}')
            for d in batch:
                d.status = STATUS_SKIPPED
                d.skip_reason = f'분류 오류: {str(e)[:100]}'

        db.session.commit()


# ── Step 0: 원문 스크래핑 + 관련기사 검색 ──

def run_scrape(draft_id):
    """Step 0: 원문 스크래핑 + Naver/Google 검색"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        return False

    draft.status = STATUS_SCRAPING
    db.session.commit()

    src = _safe_json_loads(draft.source_data)
    url = draft.original_url or src.get('link', '')
    title_ko = src.get('title_ko') or src.get('title', '')

    scraped = {'original': None, 'related': []}

    # 원문 스크래핑
    if url:
        result = scrape_article_content(url)
        scraped['original'] = result
        if not result.get('success'):
            draft.status = STATUS_SKIPPED
            draft.skip_reason = f"원문 접근 실패: {result.get('reason', '알 수 없음')}"
            draft.scraped_data = json.dumps(scraped, ensure_ascii=False)
            db.session.commit()
            return False

    # 관련 기사 검색 (Naver + Google 병렬)
    if title_ko:
        query = title_ko[:50]
        with ThreadPoolExecutor(max_workers=2) as pool:
            naver_future = pool.submit(search_naver, query, 5)
            google_future = pool.submit(search_google_cse, query, 5)
            naver_results = naver_future.result()
            google_results = google_future.result()

        all_links = []
        for r in naver_results:
            if r['link'] != url:
                all_links.append({'title': r['title'], 'link': r['link'], 'source': 'naver'})
        for r in google_results:
            if r['link'] != url:
                all_links.append({'title': r['title'], 'link': r['link'], 'source': 'google'})

        # 관련 기사 상위 5개 병렬 스크래핑
        related_scraped = []
        targets = all_links[:5]
        if targets:
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {pool.submit(scrape_article_content, item['link']): item for item in targets}
                for future in as_completed(futures):
                    item = futures[future]
                    r = future.result()
                    if r.get('success'):
                        related_scraped.append({
                            'title': item['title'],
                            'link': item['link'],
                            'text': r['text'][:3000],
                            'source': item['source'],
                        })
        scraped['related'] = related_scraped
        draft.related_urls = json.dumps(
            [{'title': r['title'], 'link': r['link']} for r in related_scraped],
            ensure_ascii=False
        )

    draft.scraped_data = json.dumps(scraped, ensure_ascii=False)
    db.session.commit()
    return True


# ── Step 2: Sonnet 자료 패키지 생성 ──

FACT_PACKAGE_SYSTEM = """당신은 팩트체크 전문 에디터입니다.
주어진 원문 기사와 관련 기사를 분석하여 자료 패키지(Fact Package)를 만듭니다.

## 핵심 규칙
1. verified_facts: 2개 이상의 출처에서 확인된 사실만 포함
2. quotes: 직접 인용문만 포함 (화자, 발언 내용, 출처 명시)
3. unverified: 1개 출처에서만 나온 사실 (기사에 사용 불가하지만 참고용)
4. fact_check: 등장 인물, 숫자/통계, 검증 필요 사항

JSON으로 응답하세요."""

FACT_PACKAGE_USER = """다음 기사 자료를 분석하여 자료 패키지를 생성하세요.

## 원문 기사
제목: {title}
본문:
{original_text}

## 관련 기사
{related_texts}

## 응답 형식 (JSON)
{{
  "verified_facts": [
    {{"fact": "...", "sources": ["출처1", "출처2"]}}
  ],
  "quotes": [
    {{"speaker": "...", "quote": "...", "source": "...", "context": "..."}}
  ],
  "unverified": [
    {{"fact": "...", "source": "..."}}
  ],
  "fact_check": {{
    "persons": [{{"name": "...", "title": "...", "verified": true}}],
    "numbers": [{{"value": "...", "context": "...", "sources": ["..."]}}],
    "needs_verification": ["..."]
  }},
  "source_grades": [
    {{"source": "...", "reliability": "A/B/C", "reason": "..."}}
  ],
  "summary": "핵심 요약 2~3문장"
}}"""


def generate_fact_package(draft_id):
    """Step 2: Sonnet으로 자료 패키지 생성"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft:
        return False

    draft.status = STATUS_GENERATING
    db.session.commit()

    scraped = _safe_json_loads(draft.scraped_data)
    src = _safe_json_loads(draft.source_data)

    original = scraped.get('original', {})
    original_text = original.get('text', '') if original else ''
    title = src.get('title_ko') or src.get('title', '')

    # 관련 기사 텍스트 조합
    related_texts = ''
    for i, r in enumerate(scraped.get('related', [])):
        related_texts += f"\n### 관련 기사 {i + 1}: {r.get('title', '')}\n"
        related_texts += f"출처: {r.get('link', '')}\n"
        related_texts += f"{r.get('text', '')[:2000]}\n"

    if not original_text:
        draft.status = STATUS_SKIPPED
        draft.skip_reason = '원문 텍스트 없음'
        db.session.commit()
        return False

    try:
        result_text, usage = _call_ai(
            'AI_PRO_MODEL',
            FACT_PACKAGE_SYSTEM,
            FACT_PACKAGE_USER.format(
                title=title,
                original_text=original_text[:5000],
                related_texts=related_texts,
            ),
            max_tokens=4096,
        )
        parsed = _parse_json_response(result_text)
        if parsed:
            draft.fact_package = json.dumps(parsed, ensure_ascii=False)
            _track_usage(draft, usage)
            db.session.commit()
            return True
        else:
            draft.status = STATUS_SKIPPED
            draft.skip_reason = '자료 패키지 JSON 파싱 실패'
            db.session.commit()
            return False
    except Exception as e:
        logger.error(f'자료 패키지 생성 오류 (draft {draft_id}): {e}')
        draft.status = STATUS_SKIPPED
        draft.skip_reason = f'자료 패키지 오류: {str(e)[:100]}'
        db.session.commit()
        return False


# ── Step 3: Sonnet 기사 작성 ──

ARTICLE_STRAIGHT_SYSTEM = """당신은 한국 뉴스 기사 전문 작성자입니다.
스트레이트(사실 전달) 기사를 작성합니다.

## 절대 규칙
1. **verified_facts에 있는 정보만 사용하세요.** 자료 패키지에 없는 정보는 절대 추가하지 마세요.
2. quotes에 있는 직접 인용문만 사용하세요.
3. 추측, 해석, 개인 의견을 넣지 마세요.
4. 번역체 표현을 사용하지 마세요 (예: ~라고 말했다 → ~라고 밝혔다).
5. 문장은 60자 이내로 작성하세요.
6. '~에 대해', '~에 있어서' 같은 불필요한 조사구를 최소화하세요.

## 기사 구성
- 리드: 핵심 사실 (5W1H) 1~2문장
- 본문: 중요도순 역피라미드
- 인용: 원문 인용 그대로 ("..." 형태)
- 출처: 각 사실의 출처를 본문에 자연스럽게 녹여 표기

JSON으로 응답하세요."""

ARTICLE_ANALYSIS_SYSTEM = """당신은 한국 뉴스 기사 전문 작성자입니다.
해설/분석 기사를 작성합니다.

## 절대 규칙
1. **verified_facts에 있는 정보만 사용하세요.** 자료 패키지에 없는 정보는 절대 추가하지 마세요.
2. quotes에 있는 직접 인용문만 사용하세요.
3. 기자의 추측이 아닌, 전문가 발언이나 데이터에 기반한 분석만 작성하세요.
4. 번역체 표현을 사용하지 마세요.
5. 문장은 60자 이내로 작성하세요.

## 기사 구성
- 리드: 이슈 핵심과 분석 방향 제시
- 본문: 배경 → 현황 → 쟁점 → 전문가 견해 → 전망
- 소제목: 2~3개 섹션 구분 (<h3> 태그)
- 인용: 원문 인용 그대로
- 출처: 각 사실의 출처를 본문에 명시

JSON으로 응답하세요."""

ARTICLE_USER = """다음 자료 패키지를 기반으로 기사를 작성하세요.
⚠️ verified_facts와 quotes에 있는 정보만 사용하세요. 추가 정보를 만들지 마세요.

## 자료 패키지
{fact_package_text}

## 응답 형식 (JSON)
{{
  "title": "기사 제목",
  "title_alternatives": ["대안 제목1", "대안 제목2"],
  "subtitle": "부제 (리드문 1~2문장)",
  "content": "<p>기사 본문 HTML...</p>",
  "summary": "기사 요약 (200자 이내)",
  "keywords": "키워드1, 키워드2, 키워드3",
  "source_links": ["출처 URL1", "출처 URL2"]
}}"""


def generate_article_draft(draft_id):
    """Step 3: Sonnet으로 기사 작성"""
    draft = db.session.get(AiDraft, draft_id)
    if not draft or not draft.fact_package:
        return False

    # grade에 따라 프롬프트 분기
    system = ARTICLE_ANALYSIS_SYSTEM if draft.grade == 'A1' else ARTICLE_STRAIGHT_SYSTEM

    try:
        result_text, usage = _call_ai(
            'AI_PRO_MODEL',
            system,
            ARTICLE_USER.format(fact_package_text=draft.fact_package[:8000]),
            max_tokens=4096,
        )
        parsed = _parse_json_response(result_text)
        if parsed:
            draft.article_result = json.dumps(parsed, ensure_ascii=False)
            draft.title = parsed.get('title', '')
            draft.subtitle = parsed.get('subtitle', '')
            draft.content = parsed.get('content', '')
            draft.summary = parsed.get('summary', '')
            draft.keywords = parsed.get('keywords', '')
            _track_usage(draft, usage)
            db.session.commit()
            return True
        else:
            draft.status = STATUS_SKIPPED
            draft.skip_reason = '기사 작성 JSON 파싱 실패'
            db.session.commit()
            return False
    except Exception as e:
        logger.error(f'기사 작성 오류 (draft {draft_id}): {e}')
        draft.status = STATUS_SKIPPED
        draft.skip_reason = f'기사 작성 오류: {str(e)[:100]}'
        db.session.commit()
        return False


# ── Step 4a: Haiku 기계적 검증 ──

VALIDATE_MECHANICAL_SYSTEM = """당신은 뉴스 기사 교정 에디터입니다.
기사의 기계적 품질을 검증합니다.

## 검증 항목
1. 문장 길이: 60자 초과 문장 찾기
2. 금지 표현: '~것으로 보인다', '~것으로 알려졌다', '~할 것으로 예상된다' 등 추측성 표현
3. 번역체: '~에 대해서', '~에 있어서', '~하는 것이 가능하다' 등
4. 인용 형식: 직접 인용이 "..." 형태로 올바르게 사용되었는지
5. 오탈자, 맞춤법

JSON으로 응답하세요."""

VALIDATE_MECHANICAL_USER = """다음 기사를 검증하세요.

제목: {title}
부제: {subtitle}
본문:
{content}

응답 형식 (JSON):
{{
  "issues": [
    {{"type": "long_sentence", "text": "문제 문장", "suggestion": "수정 제안"}},
    {{"type": "speculation", "text": "추측성 표현", "suggestion": "수정 제안"}}
  ],
  "score": 85,
  "summary": "검증 요약"
}}"""


def validate_draft_mechanical(draft_id):
    """Step 4a: Haiku로 기계적 검증

    Returns:
        dict: {issues, score, summary} — 항상 dict 반환
    """
    draft = db.session.get(AiDraft, draft_id)
    if not draft or not draft.content:
        return {'issues': [], 'score': 0, 'summary': '검증 대상 없음'}

    try:
        plain = _strip_html(draft.content)
        result_text, usage = _call_ai(
            'AI_FLASH_MODEL',
            VALIDATE_MECHANICAL_SYSTEM,
            VALIDATE_MECHANICAL_USER.format(
                title=draft.title,
                subtitle=draft.subtitle,
                content=plain[:5000],
            ),
            max_tokens=2048,
        )
        parsed = _parse_json_response(result_text)
        _track_usage(draft, usage)
        if parsed:
            return parsed
        return {'issues': [], 'score': 70, 'summary': '검증 응답 파싱 실패'}
    except Exception as e:
        logger.error(f'기계적 검증 오류 (draft {draft_id}): {e}')
        return {'issues': [], 'score': 0, 'summary': f'검증 오류: {str(e)[:100]}'}


# ── Step 4b: Sonnet 할루시네이션 대조 ──

VALIDATE_HALLUCINATION_SYSTEM = """당신은 팩트체크 전문가입니다.
기사 본문과 자료 패키지를 1:1 대조하여 할루시네이션(자료에 없는 사실)을 찾습니다.

## 검증 방법
1. 기사의 각 사실 주장을 자료 패키지의 verified_facts와 대조합니다.
2. 자료 패키지에 없는 사실이 기사에 포함되어 있으면 플래그합니다.
3. 인용문이 quotes와 일치하는지 확인합니다.
4. 숫자/통계가 fact_check.numbers와 일치하는지 확인합니다.

JSON으로 응답하세요."""

VALIDATE_HALLUCINATION_USER = """기사와 자료 패키지를 대조 검증하세요.

## 기사
제목: {title}
본문:
{content_plain}

## 자료 패키지
{fact_package}

응답 형식 (JSON):
{{
  "hallucinations": [
    {{"text": "자료에 없는 문장", "type": "fabricated_fact/misquote/wrong_number", "severity": "high/medium/low"}}
  ],
  "verified_count": 10,
  "total_claims": 12,
  "score": 83,
  "verdict": "pass/fix_minor/regenerate",
  "summary": "검증 요약"
}}"""


def validate_draft_hallucination(draft_id):
    """Step 4b: Sonnet으로 할루시네이션 대조 검증

    Returns:
        dict: {hallucinations, score, verdict, summary} — 항상 dict 반환
    """
    draft = db.session.get(AiDraft, draft_id)
    if not draft or not draft.content or not draft.fact_package:
        return {'hallucinations': [], 'score': 0, 'verdict': 'fix_minor', 'summary': '검증 대상 없음'}

    try:
        plain = _strip_html(draft.content)
        result_text, usage = _call_ai(
            'AI_PRO_MODEL',
            VALIDATE_HALLUCINATION_SYSTEM,
            VALIDATE_HALLUCINATION_USER.format(
                title=draft.title,
                content_plain=plain[:5000],
                fact_package=draft.fact_package[:6000],
            ),
            max_tokens=2048,
        )
        parsed = _parse_json_response(result_text)
        _track_usage(draft, usage)
        if parsed:
            return parsed
        return {'hallucinations': [], 'score': 50, 'verdict': 'fix_minor', 'summary': '검증 응답 파싱 실패'}
    except Exception as e:
        logger.error(f'할루시네이션 검증 오류 (draft {draft_id}): {e}')
        return {'hallucinations': [], 'score': 0, 'verdict': 'fix_minor', 'summary': f'검증 오류: {str(e)[:100]}'}


# ── 전체 파이프라인 오케스트레이터 ──

def run_generate_pipeline(draft_ids):
    """Step 0 → 2 → 3 → 4a → 4b 순차 실행 (각 draft 간, 단계 간 딜레이 포함)"""
    for idx, draft_id in enumerate(draft_ids):
        start_time = time.time()
        draft = db.session.get(AiDraft, draft_id)
        if not draft or draft.status in (STATUS_COMPLETED, STATUS_PUBLISHED, STATUS_SKIPPED):
            continue

        # draft 간 딜레이 (첫 건 제외)
        if idx > 0:
            logger.info(f'다음 초안 처리 전 {API_CALL_DELAY}초 대기')
            time.sleep(API_CALL_DELAY)

        try:
            # Step 0: 스크래핑 (API 호출 없으므로 딜레이 불필요)
            if not run_scrape(draft_id):
                continue

            # Step 2: 자료 패키지 (_call_ai 내부에 딜레이 있음)
            if not generate_fact_package(draft_id):
                continue

            # Step 3: 기사 작성
            if not generate_article_draft(draft_id):
                continue

            # Step 4: 검증 (병렬 실행 — 독립적인 API 호출)
            draft = db.session.get(AiDraft, draft_id)
            draft.status = STATUS_VALIDATING
            db.session.commit()

            with ThreadPoolExecutor(max_workers=2) as pool:
                mech_future = pool.submit(validate_draft_mechanical, draft_id)
                hall_future = pool.submit(validate_draft_hallucination, draft_id)
                mech_result = mech_future.result()
                hall_result = hall_future.result()

            # 검증 결과 통합
            draft = db.session.get(AiDraft, draft_id)
            draft.validation_result = json.dumps({
                'mechanical': mech_result,
                'hallucination': hall_result,
            }, ensure_ascii=False)
            draft.validation_score = int((mech_result.get('score', 0) + hall_result.get('score', 0)) / 2)

            # 상태 결정
            verdict = hall_result.get('verdict', 'fix_minor')
            if verdict == 'regenerate' or draft.validation_score < 40:
                draft.status = STATUS_SKIPPED
                draft.skip_reason = '검증 미통과 (재생성 필요)'
            else:
                draft.status = STATUS_COMPLETED
                draft.completed_at = datetime.now()

            draft.generation_time_sec = round(time.time() - start_time, 1)
            db.session.commit()

        except Exception as e:
            logger.error(f'파이프라인 오류 (draft {draft_id}): {e}')
            draft = db.session.get(AiDraft, draft_id)
            if draft:
                draft.status = STATUS_SKIPPED
                draft.skip_reason = f'파이프라인 오류: {str(e)[:100]}'
                draft.generation_time_sec = round(time.time() - start_time, 1)
                db.session.commit()
