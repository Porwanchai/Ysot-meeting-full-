from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    railway_public_domain: str = ""  # ตั้งค่าใน Railway env vars

    # Google Drive
    meet_recordings_folder_id: str = ""

    # Email
    sender_email: str = ""
    sender_name: str = "ระบบการประชุม ยสท."

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Google OAuth scopes ที่ต้องการ
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
    "profile",
]

# Whisper รองรับไฟล์ขนาดสูงสุด 25MB — ต้องตัดก่อนส่ง
WHISPER_MAX_MB = 24
WHISPER_MODEL = "whisper-1"

# Claude model
CLAUDE_MODEL = "claude-sonnet-4-6"

# ประเภทไฟล์ที่รองรับ
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav",
    "audio/m4a", "video/mp4", "audio/ogg", "audio/webm",
}
