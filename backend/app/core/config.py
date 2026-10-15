from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application configuration settings loaded from environment or .env file."""

    APP_NAME: str = "AnkiCraft AI"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Gemini AI configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_TIER_MODELS: List[str] = [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
    ]
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    HEDGED_REQUEST_TIMEOUT_SECONDS: float = 6.0
    THINKING_LEVEL: str = "LOW"
    THINKING_BUDGET: int = 0

    # Additional LLM Provider Configuration (Cascade Fallback 2026)
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "meta/llama-3.2-90b-vision-instruct"
    NVIDIA_FALLBACK_MODEL: str = "meta/llama-3.2-11b-vision-instruct"

    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_TEXT_MODEL: str = "qwen/qwen3.8-27b"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openrouter/free"

    # AnkiConnect configuration
    ANKI_CONNECT_URL: str = "http://localhost:8765"
    ANKI_CONNECT_TIMEOUT_SECONDS: float = 5.0

    # CORS configuration for local development
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=[".env", str(BACKEND_DIR / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
