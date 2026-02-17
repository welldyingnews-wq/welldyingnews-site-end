"""
Cloudinary 이미지 업로드 + Google Drive 첨부파일 업로드 유틸리티.

환경변수:
  Cloudinary: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
  Google Drive: GOOGLE_DRIVE_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_JSON (파일 경로)
"""
import os


# ── Cloudinary ──

def cloudinary_configured():
    """Cloudinary 환경변수가 설정되어 있는지 확인"""
    return bool(os.environ.get('CLOUDINARY_CLOUD_NAME')
                and os.environ.get('CLOUDINARY_API_KEY')
                and os.environ.get('CLOUDINARY_API_SECRET'))


def cloudinary_upload(file_or_path, folder='welldying', resource_type='image'):
    """
    Cloudinary에 이미지 업로드.
    file_or_path: FileStorage 객체 또는 로컬 파일 경로
    Returns: Cloudinary URL (str) or None on failure
    """
    if not cloudinary_configured():
        return None
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=os.environ['CLOUDINARY_CLOUD_NAME'],
            api_key=os.environ['CLOUDINARY_API_KEY'],
            api_secret=os.environ['CLOUDINARY_API_SECRET'],
            secure=True
        )
        result = cloudinary.uploader.upload(
            file_or_path, folder=folder, resource_type=resource_type
        )
        return result.get('secure_url')
    except Exception as e:
        print(f'Cloudinary upload error: {e}')
        return None


# ── Google Drive ──

def gdrive_configured():
    """Google Drive 서비스 계정이 설정되어 있는지 확인"""
    return bool(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
                and os.environ.get('GOOGLE_DRIVE_FOLDER_ID'))


def gdrive_upload(file_path, filename, mimetype='application/octet-stream'):
    """
    Google Drive에 파일 업로드.
    Returns: 공유 다운로드 URL (str) or None on failure
    """
    if not gdrive_configured():
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'],
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': filename,
            'parents': [os.environ['GOOGLE_DRIVE_FOLDER_ID']]
        }
        media = MediaFileUpload(file_path, mimetype=mimetype)
        uploaded = service.files().create(
            body=file_metadata, media_body=media, fields='id,webViewLink'
        ).execute()

        # 공유 링크 설정
        file_id = uploaded.get('id')
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        return f"https://drive.google.com/file/d/{file_id}/view"
    except Exception as e:
        print(f'Google Drive upload error: {e}')
        return None
