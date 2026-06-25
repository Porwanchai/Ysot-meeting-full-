from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    railway_public_domain: str = ""

    # Google Drive
    meet_recordings_folder_id: str = ""

    # Email
    sender_email: str = ""
    sender_name: str = "ระบบการประชุม ยสท."

    # Frontend URL (สำหรับ redirect หลัง OAuth)
    frontend_url: str = ""

    # Server — Railway inject PORT เป็น env var อัตโนมัติ
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
    "profile",
]

WHISPER_MAX_MB = 24
WHISPER_MODEL = "whisper-1"
CLAUDE_MODEL = "claude-sonnet-4-6"

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav",
    "audio/m4a", "video/mp4", "audio/ogg", "audio/webm",
}
# force redeploy Thu Jun 25 13:10:10 UTC 2026
