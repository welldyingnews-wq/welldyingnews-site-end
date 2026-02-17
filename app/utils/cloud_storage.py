"""
파일 업로드 유틸리티.

Cloudinary 환경변수 설정 시 → Cloudinary 업로드 (실패 시 로컬 폴백 없음)
미설정 시 → 로컬 저장소 사용
"""
import logging
import os

logger = logging.getLogger(__name__)


def _is_cloudinary_configured():
    return bool(
        os.environ.get('CLOUDINARY_CLOUD_NAME')
        and os.environ.get('CLOUDINARY_API_KEY')
        and os.environ.get('CLOUDINARY_API_SECRET')
    )


def upload_file(filepath, folder='welldying', resource_type='image'):
    """
    설정에 따라 Cloudinary 또는 로컬 저장소에 업로드.

    - Cloudinary 설정 시: Cloudinary 업로드 (실패 시 폴백 없이 에러)
    - Cloudinary 미설정 시: 로컬 파일 URL 반환

    filepath: 로컬에 저장된 파일 경로 (app/static/ 하위)
    Returns: URL 문자열
    """
    if _is_cloudinary_configured():
        return _cloudinary_upload(filepath, folder, resource_type)

    # 로컬 모드: /static/... URL 반환
    normalized = filepath.replace('\\', '/')
    idx = normalized.find('/static/')
    if idx >= 0:
        return normalized[idx:]
    return '/static/uploads/' + os.path.basename(filepath)


def _cloudinary_upload(filepath, folder='welldying', resource_type='image'):
    """Cloudinary에 파일 업로드. 성공 후 로컬 임시 파일 삭제."""
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.environ['CLOUDINARY_CLOUD_NAME'],
        api_key=os.environ['CLOUDINARY_API_KEY'],
        api_secret=os.environ['CLOUDINARY_API_SECRET'],
        secure=True,
    )
    logger.info(f'Cloudinary 업로드 시도: folder={folder}, resource_type={resource_type}')
    result = cloudinary.uploader.upload(
        filepath, folder=folder, resource_type=resource_type
    )
    url = result.get('secure_url')
    logger.info(f'Cloudinary 업로드 성공: secure_url={url}, public_id={result.get("public_id")}')

    # 업로드 성공 후 로컬 임시 파일 삭제
    if os.path.isfile(filepath):
        try:
            os.remove(filepath)
            logger.info(f'로컬 임시 파일 삭제: {filepath}')
        except OSError as e:
            logger.warning(f'로컬 임시 파일 삭제 실패: {e}')

    return url
