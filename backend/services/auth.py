"""
Google OAuth2 Service
- ฝัง session_id ใน state parameter เพื่อให้ callback รู้ว่าเป็น session ไหน
- Google จะส่ง state กลับมาพร้อม code ใน callback เสมอ
"""
import secrets
import json
import base64
from typing import Optional

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


def _encode_state(session_id: str, nonce: str) -> str:
    """ฝัง session_id ใน state โดย encode เป็น base64"""
    payload = json.dumps({"sid": session_id, "n": nonce})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_state(state: str) -> dict:
    """ถอด session_id จาก state"""
    try:
        payload = base64.urlsafe_b64decode(state.encode()).decode()
        return json.loads(payload)
    except Exception:
        return {}


def get_authorization_url(session_id: Optional[str] = None) -> dict:
    """สร้าง URL สำหรับ login Google — ฝัง session_id ใน state"""
    flow = create_oauth_flow()
    sid = session_id or secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)

    # ฝัง session_id ใน state
    state_value = _encode_state(sid, nonce)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        state=state_value,
    )

    _sessions[sid] = {"nonce": nonce, "credentials": None}

    return {
        "auth_url": auth_url,
        "session_id": sid,
        "state": state_value,
    }


def exchange_code_for_tokens(code: str, state: str) -> dict:
    """
    รับ code + state จาก Google callback
    ถอด session_id จาก state แล้วแลก token
    """
    # ถอด session_id จาก state
    state_data = _decode_state(state)
    session_id = state_data.get("sid")
    nonce = state_data.get("n")

    if not session_id:
        raise ValueError("ไม่พบ session_id ใน state — กรุณา login ใหม่")

    session = _sessions.get(session_id)
    if not session:
        raise ValueError("ไม่พบ session — กรุณา login ใหม่")

    if session.get("nonce") != nonce:
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
    return {"session_id": session_id, **token_data}


def get_session_credentials(session_id: str) -> Optional[dict]:
    session = _sessions.get(session_id)
    if session:
        return session.get("credentials")
    return None


def clear_session(session_id: str):
    _sessions.pop(session_id, None)
