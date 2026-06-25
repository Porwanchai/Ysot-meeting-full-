"""
Google OAuth2 Service
- สร้าง authorization URL
- แลก code เป็น tokens
- เก็บ session ผ่าน in-memory store (production ควรใช้ Redis)
"""
import secrets
from typing import Optional

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from config import get_settings, GOOGLE_SCOPES

settings = get_settings()

# In-memory session store — production ควรเปลี่ยนเป็น Redis
_sessions: dict[str, dict] = {}


def create_oauth_flow() -> Flow:
    """สร้าง Google OAuth Flow"""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


def get_authorization_url(session_id: Optional[str] = None) -> dict:
    """
    สร้าง URL สำหรับ login Google
    คืนค่า: {auth_url, session_id, state}
    """
    flow = create_oauth_flow()
    sid = session_id or secrets.token_urlsafe(32)

    auth_url, state = flow.authorization_url(
        access_type="offline",          # ขอ refresh_token ด้วย
        include_granted_scopes="true",
        prompt="consent",               # บังคับแสดง consent ทุกครั้ง
    )

    # เก็บ state ไว้ verify ตอน callback
    _sessions[sid] = {"state": state, "credentials": None}

    return {
        "auth_url": auth_url,
        "session_id": sid,
        "state": state,
    }


def exchange_code_for_tokens(code: str, state: str, session_id: str) -> dict:
    """
    รับ authorization code จาก Google callback
    แลกเป็น access_token + refresh_token
    """
    session = _sessions.get(session_id)
    if not session:
        raise ValueError("ไม่พบ session — กรุณา login ใหม่")
    if session.get("state") != state:
        raise ValueError("State mismatch — อาจมีความเสี่ยง CSRF")

    flow = create_oauth_flow()
    flow.fetch_token(code=code)

    creds: Credentials = flow.credentials
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }

    _sessions[session_id]["credentials"] = token_data
    return token_data


def get_session_credentials(session_id: str) -> Optional[dict]:
    """ดึง credentials จาก session"""
    session = _sessions.get(session_id)
    if session:
        return session.get("credentials")
    return None


def clear_session(session_id: str):
    """ลบ session"""
    _sessions.pop(session_id, None)
