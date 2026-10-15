from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.routes import router

# Initialize persistent file and console logging
setup_logging()

app = FastAPI(
    title=settings.APP_NAME,
    description="Local AI Flashcard Generator for Anki with Hexagonal Architecture",
    version="1.0.0",
)

# Enable CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "anki_connect_url": settings.ANKI_CONNECT_URL,
        "gemini_model": settings.GEMINI_MODEL,
    }
