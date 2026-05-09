from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "Scholar Desk"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = True
    MONGODB_URL: str = "mongodb+srv://infozodex_db_user:absolutions@data.yycywiw.mongodb.net/school_management3"
    DB_NAME: str = "school_management3"
    SECRET_KEY: str = "edumanage-pro-secret-key-2024-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "pdf", "doc", "docx"]
    ALLOWED_ORIGINS: List[str] = ["*"]
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
