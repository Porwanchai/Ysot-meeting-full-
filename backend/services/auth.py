"""
Google OAuth2 Service — simplified session handling
"""
import os
import secrets
import json
import base64
from typing import Optional

# ต้องตั้งก่อน import google-auth library
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "0"

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from config import get_settings, GOOGLE_SCOPES

settings = get_settings()

# In-memory session store
_sessions: dict[str, dict] = {}


def create_oauth_flow() -> Flow:
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


def _encode_state(session_id: str) -> str:
    """ฝัง session_id ใน state"""
    payload = json.dumps({"sid": session_id})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_state(state: str) -> str:
    """ถอด session_id จาก state — คืนค่า session_id หรือ state เดิมถ้า decode ไม่ได้"""
    try:
        # เติม padding กลับ
        padding = 4 - len(state) % 4
        if padding != 4:
            state += "=" * padding
        payload = base64.urlsafe_b64decode(state.encode()).decode()
        data = json.loads(payload)
        return data.get("sid", state)
    except Exception:
        # ถ้า decode ไม่ได้ ใช้ state เป็น session_id ตรง ๆ
        return state


def get_authorization_url(session_id: Optional[str] = None) -> dict:
    """สร้าง URL สำหรับ login Google"""
    flow = create_oauth_flow()
    sid = session_id or secrets.token_urlsafe(32)

    # ฝัง session_id ใน state
    state_value = _encode_state(sid)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        state=state_value,
    )

    _sessions[sid] = {"credentials": None}

    return {
        "auth_url": auth_url,
        "session_id": sid,
        "state": state_value,
    }


def exchange_code_for_tokens(code: str, state: str) -> dict:
    """รับ code + state จาก Google แลกเป็น token"""
    # ถอด session_id จาก state
    session_id = _decode_state(state)

    if not session_id:
        raise ValueError("ไม่พบ session_id ใน state")

    # สร้าง flow และแลก token
    flow = create_oauth_flow()

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        raise ValueError(f"แลก token ไม่สำเร็จ: {str(e)}")

    creds: Credentials = flow.credentials
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }

    # บันทึก session (ถ้ายังมีอยู่) หรือสร้างใหม่
    _sessions[session_id] = {"credentials": token_data}

    return {"session_id": session_id, **token_data}


def get_session_credentials(session_id: str) -> Optional[dict]:
    session = _sessions.get(session_id)
    if session:
        return session.get("credentials")
    return None


def clear_session(session_id: str):
    _sessions.pop(session_id, None)
