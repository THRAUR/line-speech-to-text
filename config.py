"""Configuration management for the Meeting Bot."""
from __future__ import annotations

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration."""
    
    # LINE Bot settings
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
    
    # Groq API (Whisper transcription)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    # DeepSeek API (summarization) - OpenAI compatible
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    
    # Password configuration
    DAILY_PASSWORD_SEED = os.getenv("DAILY_PASSWORD_SEED", "default_seed")
    
    # Server settings
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of missing variables."""
        required = [
            ("LINE_CHANNEL_ACCESS_TOKEN", cls.LINE_CHANNEL_ACCESS_TOKEN),
            ("LINE_CHANNEL_SECRET", cls.LINE_CHANNEL_SECRET),
            ("GROQ_API_KEY", cls.GROQ_API_KEY),
            ("DEEPSEEK_API_KEY", cls.DEEPSEEK_API_KEY),
        ]
        return [name for name, value in required if not value]
