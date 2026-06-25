"""
Email Service (Gmail API)
- ส่งอีเมลรายงานการประชุมพร้อมไฟล์แนบ
- รองรับผู้รับหลายคน
- ใช้ Gmail API ผ่าน OAuth2 ของ Google Workspace ยสท.
"""
import base64
import mimetypes
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import get_settings

settings = get_settings()


def get_gmail_service(credentials: dict):
    """สร้าง Gmail service จาก OAuth credentials"""
    creds = Credentials(
        token=credentials["access_token"],
        refresh_token=credentials.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    return build("gmail", "v1", credentials=creds)


def build_email_message(
    to_emails: list[str],
    subject: str,
    body_text: str,
    attachments: list[str] | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
) -> dict:
    """
    สร้าง email message object
    attachments: list ของ path ไฟล์ที่จะแนบ
    คืนค่า: dict ที่พร้อมส่งผ่าน Gmail API
    """
    sender = sender_email or settings.sender_email
    name = sender_name or settings.sender_name
    from_header = f"{name} <{sender}>"

    msg = MIMEMultipart("mixed")
    msg["From"] = from_header
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject

    # เนื้อหาอีเมล (plain text + html)
    body_part = MIMEMultipart("alternative")

    # Plain text
    body_part.attach(MIMEText(body_text, "plain", "utf-8"))

    # HTML version
    html_body = _text_to_html(body_text)
    body_part.attach(MIMEText(html_body, "html", "utf-8"))

    msg.attach(body_part)

    # ไฟล์แนบ
    if attachments:
        for filepath in attachments:
            if not os.path.exists(filepath):
                continue
            _attach_file(msg, filepath)

    # encode เป็น base64 URL-safe สำหรับ Gmail API
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def _attach_file(msg: MIMEMultipart, filepath: str):
    """แนบไฟล์เข้ากับ email message"""
    filename = os.path.basename(filepath)
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type is None:
        mime_type = "application/octet-stream"

    main_type, sub_type = mime_type.split("/", 1)

    with open(filepath, "rb") as f:
        data = f.read()

    part = MIMEBase(main_type, sub_type)
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", filename),
    )
    msg.attach(part)


def _text_to_html(text: str) -> str:
    """แปลง plain text เป็น HTML อย่างง่าย"""
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            html_lines.append(f"<h3 style='color:#1B4332'>{stripped.lstrip('#').strip()}</h3>")
        elif stripped.startswith("**") and stripped.endswith("**"):
            html_lines.append(f"<strong>{stripped.strip('*')}</strong><br>")
        elif stripped.startswith(("-", "•")):
            html_lines.append(f"&bull; {stripped.lstrip('-•').strip()}<br>")
        elif stripped == "---":
            html_lines.append("<hr style='border-color:#1B4332'>")
        elif stripped:
            html_lines.append(f"{stripped}<br>")
        else:
            html_lines.append("<br>")

    body = "\n".join(html_lines)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Sarabun,sans-serif;font-size:14px;line-height:1.7;
             color:#333;max-width:700px;margin:0 auto;padding:20px">
  <div style="border-top:4px solid #1B4332;padding-top:16px;margin-bottom:24px">
    <img style="height:32px" alt="ยสท.">
    <span style="font-size:18px;font-weight:bold;color:#1B4332;margin-left:8px">
      การยาสูบแห่งประเทศไทย
    </span>
  </div>
  {body}
  <div style="margin-top:32px;padding-top:16px;border-top:1px solid #ddd;
              font-size:12px;color:#888">
    อีเมลนี้จัดทำโดยระบบอัตโนมัติ — กรุณาอย่าตอบกลับ
  </div>
</body>
</html>"""


def send_meeting_report(
    credentials: dict,
    to_emails: list[str],
    subject: str,
    body_text: str,
    attachments: list[str] | None = None,
) -> dict:
    """
    ส่งอีเมลรายงานการประชุม
    คืนค่า: {success, message_id, recipients_count}
    """
    if not to_emails:
        raise ValueError("กรุณาระบุผู้รับอีเมลอย่างน้อย 1 ท่าน")

    service = get_gmail_service(credentials)
    email_message = build_email_message(
        to_emails=to_emails,
        subject=subject,
        body_text=body_text,
        attachments=attachments,
    )

    sent = service.users().messages().send(
        userId="me",
        body=email_message,
    ).execute()

    return {
        "success": True,
        "message_id": sent.get("id"),
        "recipients_count": len(to_emails),
        "recipients": to_emails,
    }
