"""백그라운드 큐 — AI 작업을 순차 처리하는 데몬 워커"""
import logging
import queue
import threading
import time

logger = logging.getLogger(__name__)

_task_queue = queue.Queue(maxsize=100)
_current_task = {}  # 현재 처리 중인 작업 정보
_last_error = ''  # 마지막 에러 메시지
_lock = threading.Lock()


def init_background_worker(app):
    """Flask 앱 시작 시 백그라운드 워커 스레드 시작"""
    def worker():
        while True:
            task = _task_queue.get()
            try:
                with _lock:
                    _current_task['type'] = task['type']
                    _current_task['draft_ids'] = task.get('draft_ids', [])
                    _current_task['started_at'] = time.time()

                with app.app_context():
                    from app.services.ai_draft import run_classify, run_generate_pipeline
                    if task['type'] == 'classify':
                        run_classify(task['draft_ids'])
                    elif task['type'] == 'generate':
                        run_generate_pipeline(task['draft_ids'])
            except Exception as e:
                logger.error(f'백그라운드 작업 오류: {e}')
                with _lock:
                    global _last_error
                    _last_error = f'{task.get("type", "")}: {str(e)[:200]}'
            finally:
                with _lock:
                    _current_task.clear()
                _task_queue.task_done()

    t = threading.Thread(target=worker, daemon=True, name='ai-draft-worker')
    t.start()
    logger.info('AI 초안 백그라운드 워커 시작')


def enqueue_task(task_type, draft_ids):
    """큐에 작업 추가

    Args:
        task_type: 'classify' 또는 'generate'
        draft_ids: AiDraft ID 리스트
    """
    _task_queue.put({
        'type': task_type,
        'draft_ids': draft_ids,
    })


def get_queue_status():
    """큐 상태 반환 (프론트엔드 폴링용)"""
    with _lock:
        current = dict(_current_task)
        error = _last_error
    return {
        'queue_size': _task_queue.qsize(),
        'is_processing': bool(current),
        'current_task': current,
        'last_error': error,
    }
