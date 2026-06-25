"""
Google Drive Service
- ดึงรายการไฟล์จาก Meet Recordings folder
- ดาวน์โหลดไฟล์เสียง/วิดีโอ
"""
import io
import os
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import get_settings

settings = get_settings()


def get_drive_service(credentials: dict):
    """สร้าง Drive service จาก OAuth credentials"""
    creds = Credentials(
        token=credentials["access_token"],
        refresh_token=credentials.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    return build("drive", "v3", credentials=creds)


def list_meeting_recordings(credentials: dict, folder_id: Optional[str] = None) -> list[dict]:
    """
    ดึงรายการไฟล์การประชุมจาก Google Drive
    - ค้นหาใน folder Meet Recordings โดย default
    - กรองเฉพาะไฟล์เสียง/วิดีโอ
    """
    service = get_drive_service(credentials)
    target_folder = folder_id or settings.meet_recordings_folder_id

    query_parts = [
        "trashed = false",
        "(mimeType contains 'audio/' or mimeType contains 'video/')",
    ]
    if target_folder:
        query_parts.append(f"'{target_folder}' in parents")

    query = " and ".join(query_parts)

    results = service.files().list(
        q=query,
        orderBy="createdTime desc",
        pageSize=50,
        fields="files(id, name, size, mimeType, createdTime, webViewLink)",
    ).execute()

    files = results.get("files", [])

    # แปลง size เป็น MB และจัดรูปแบบ date
    for f in files:
        size_bytes = int(f.get("size", 0))
        f["size_mb"] = round(size_bytes / (1024 * 1024), 1)
        created = f.get("createdTime", "")
        f["created_display"] = created[:10] if created else "-"

    return files


def download_file(credentials: dict, file_id: str, dest_path: str) -> str:
    """
    ดาวน์โหลดไฟล์จาก Drive ไปยัง dest_path
    คืนค่า path ของไฟล์ที่ดาวน์โหลดแล้ว
    """
    service = get_drive_service(credentials)

    # ดึง metadata ก่อนเพื่อรู้ชื่อไฟล์
    meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
    filename = meta["name"]
    local_path = os.path.join(dest_path, filename)

    request = service.files().get_media(fileId=file_id)
    buf = io.FileIO(local_path, "wb")
    downloader = MediaIoBaseDownload(buf, request, chunksize=10 * 1024 * 1024)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    buf.close()
    return local_path


def upload_file_to_drive(
    credentials: dict,
    local_path: str,
    folder_id: str,
    filename: str,
    mime_type: str = "application/pdf",
) -> str:
    """
    อัปโหลดไฟล์รายงานกลับไป Drive
    คืนค่า web link ของไฟล์ที่อัปโหลด
    """
    from googleapiclient.http import MediaFileUpload

    service = get_drive_service(credentials)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    return uploaded.get("webViewLink", "")
