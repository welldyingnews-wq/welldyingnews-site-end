"""
Cloudinary 이미지/파일 업로드 유틸리티.

환경변수: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
- resource_type='image': 이미지 (jpg, png, gif, heic 등)
- resource_type='raw': 그 외 파일 (zip, pdf, hwp, doc 등)
"""
import logging
import os

logger = logging.getLogger(__name__)


def cloudinary_upload(file_or_path, folder='welldying', resource_type='image'):
    """
    Cloudinary에 파일 업로드.
    file_or_path: FileStorage 객체 또는 로컬 파일 경로
    resource_type: 'image' (이미지), 'raw' (첨부파일), 'video' (동영상)
    Returns: Cloudinary URL (str)
    Raises: RuntimeError if Cloudinary is not configured
    """
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    if not (cloud_name and api_key and api_secret):
        raise RuntimeError('Cloudinary 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.')

    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    logger.info(f'Cloudinary 업로드 시도: folder={folder}, resource_type={resource_type}')
    result = cloudinary.uploader.upload(
        file_or_path, folder=folder, resource_type=resource_type
    )
    url = result.get('secure_url')
    logger.info(f'Cloudinary 업로드 성공: secure_url={url}, public_id={result.get("public_id")}')

    # 업로드 성공 후 로컬 임시 파일 삭제
    if isinstance(file_or_path, str) and os.path.isfile(file_or_path):
        try:
            os.remove(file_or_path)
            logger.info(f'로컬 임시 파일 삭제: {file_or_path}')
        except OSError as e:
            logger.warning(f'로컬 임시 파일 삭제 실패: {e}')

    return url
