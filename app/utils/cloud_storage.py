"""
파일 업로드 유틸리티.

Cloudinary 환경변수 설정 시 → Cloudinary 업로드 (실패 시 로컬 폴백 없음)
미설정 시 → 로컬 저장소 사용
"""
import logging
import os

logger = logging.getLogger(__name__)

# 워터마크 로고 경로
_WATERMARK_LOGO = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'logo.png'
)


def _is_cloudinary_configured():
    return bool(
        os.environ.get('CLOUDINARY_CLOUD_NAME')
        and os.environ.get('CLOUDINARY_API_KEY')
        and os.environ.get('CLOUDINARY_API_SECRET')
    )


def _apply_watermark(filepath):
    """Pillow로 이미지에 워터마크 로고를 우하단에 합성."""
    try:
        from PIL import Image
        img = Image.open(filepath).convert('RGBA')
        logo = Image.open(_WATERMARK_LOGO).convert('RGBA')

        # 로고 크기: 이미지 너비의 20%, 최소 80px
        logo_w = max(int(img.width * 0.2), 80)
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

        # 반투명 처리 (opacity 40%)
        alpha = logo.getchannel('A')
        alpha = alpha.point(lambda a: int(a * 0.4))
        logo.putalpha(alpha)

        # 우하단 배치 (15px 여백)
        x = img.width - logo_w - 15
        y = img.height - logo_h - 15
        img.paste(logo, (x, y), logo)

        # RGBA → RGB 변환 후 저장 (JPEG 호환)
        if filepath.lower().endswith(('.jpg', '.jpeg')):
            img = img.convert('RGB')
        img.save(filepath)
        logger.info(f'워터마크 적용 완료: {filepath}')
        return True
    except Exception as e:
        logger.error(f'워터마크 적용 실패: {e}')
        return False


def upload_file(filepath, folder='welldying', resource_type='image',
                watermark=False):
    """
    설정에 따라 Cloudinary 또는 로컬 저장소에 업로드.

    - Cloudinary 설정 시: Cloudinary 업로드 (실패 시 폴백 없이 에러)
    - Cloudinary 미설정 시: 로컬 파일 URL 반환

    filepath: 로컬에 저장된 파일 경로 (app/static/ 하위)
    watermark: True이면 이미지에 워터마크 적용
    Returns: URL 문자열
    """
    # 워터마크: 업로드 전에 로컬에서 합성
    if watermark and resource_type == 'image':
        _apply_watermark(filepath)

    if _is_cloudinary_configured():
        return _cloudinary_upload(filepath, folder, resource_type)

    # 로컬 모드: /static/... URL 반환
    normalized = filepath.replace('\\', '/')
    idx = normalized.find('/static/')
    if idx >= 0:
        return normalized[idx:]
    return '/static/uploads/' + os.path.basename(filepath)


def delete_file(url):
    """Cloudinary URL로부터 public_id를 추출하여 삭제."""
    if not _is_cloudinary_configured():
        return
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=os.environ['CLOUDINARY_CLOUD_NAME'],
        api_key=os.environ['CLOUDINARY_API_KEY'],
        api_secret=os.environ['CLOUDINARY_API_SECRET'],
        secure=True,
    )
    # URL에서 public_id 추출: .../upload/v1234/welldying/articles/abc.jpg → welldying/articles/abc
    import re
    m = re.search(r'/upload/(?:v\d+/)?(.*)\.\w+$', url)
    if m:
        public_id = m.group(1)
        result = cloudinary.uploader.destroy(public_id)
        logger.info(f'Cloudinary 삭제: public_id={public_id}, result={result}')
        return result
    logger.warning(f'Cloudinary public_id 추출 실패: {url}')


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

    result = cloudinary.uploader.upload(filepath, folder=folder,
                                        resource_type=resource_type)
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
