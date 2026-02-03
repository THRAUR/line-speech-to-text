"""Transcription service using Groq Whisper API."""
from __future__ import annotations

import tempfile
import logging
from pathlib import Path
from groq import Groq

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Transcribes audio files using Groq's Whisper API.
    
    Uses Whisper Large V3 Turbo model for fast, accurate transcription.
    Supports Chinese (Mandarin) and English languages.
    """
    
    # Groq Whisper model - turbo is faster and cheaper
    MODEL = "whisper-large-v3-turbo"
    
    def __init__(self, api_key: str):
        """Initialize the transcription service.
        
        Args:
            api_key: Groq API key
        """
        self.client = Groq(api_key=api_key)
    
    def transcribe(
        self,
        audio_data: bytes,
        file_extension: str = "m4a",
        language: str | None = None,
    ) -> dict:
        """Transcribe audio data to text.
        
        Args:
            audio_data: Raw audio file bytes
            file_extension: Audio file extension (default: m4a for LINE)
            language: Optional language hint (e.g., 'zh' for Chinese, 'en' for English)
                     If not specified, Whisper auto-detects the language.
        
        Returns:
            Dictionary with 'text' (transcript) and 'language' (detected language)
        """
        # Save audio to temp file (Groq API requires file path)
        with tempfile.NamedTemporaryFile(
            suffix=f".{file_extension}",
            delete=False
        ) as temp_file:
            temp_file.write(audio_data)
            temp_path = Path(temp_file.name)
        
        try:
            logger.info(f"Transcribing audio file ({len(audio_data)} bytes)")
            
            # Prepare transcription parameters
            params = {
                "model": self.MODEL,
                "response_format": "verbose_json",  # Get language detection info
            }
            
            # Only set language if explicitly provided
            if language:
                params["language"] = language
            
            # Open file and transcribe
            with open(temp_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    file=audio_file,
                    **params
                )
            
            # Extract results
            transcript = response.text
            detected_language = getattr(response, "language", "unknown")
            duration = getattr(response, "duration", None)
            
            logger.info(
                f"Transcription complete: {len(transcript)} chars, "
                f"language={detected_language}, duration={duration}s"
            )
            
            return {
                "text": transcript,
                "language": detected_language,
                "duration": duration,
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
            
        finally:
            # Clean up temp file
            try:
                temp_path.unlink()
            except Exception:
                pass
    
    def transcribe_with_timestamps(
        self,
        audio_data: bytes,
        file_extension: str = "m4a"
    ) -> dict:
        """Transcribe audio with word-level timestamps.
        
        Args:
            audio_data: Raw audio file bytes
            file_extension: Audio file extension
            
        Returns:
            Dictionary with 'text', 'segments', and 'words' with timestamps
        """
        with tempfile.NamedTemporaryFile(
            suffix=f".{file_extension}",
            delete=False
        ) as temp_file:
            temp_file.write(audio_data)
            temp_path = Path(temp_file.name)
        
        try:
            with open(temp_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    file=audio_file,
                    model=self.MODEL,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"],
                )
            
            return {
                "text": response.text,
                "language": getattr(response, "language", "unknown"),
                "duration": getattr(response, "duration", None),
                "segments": getattr(response, "segments", []),
                "words": getattr(response, "words", []),
            }
            
        finally:
            try:
                temp_path.unlink()
            except Exception:
                pass
