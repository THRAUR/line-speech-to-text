"""Transcription service using Groq Whisper API with chunking support."""
from __future__ import annotations

import tempfile
import logging
import subprocess
import os
from pathlib import Path
from groq import Groq

logger = logging.getLogger(__name__)

# Maximum file size for Groq free tier (25MB)
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB in bytes

# Chunk duration in seconds (10 minutes per chunk to stay under 25MB)
CHUNK_DURATION = 600


class TranscriptionService:
    """Transcribes audio files using Groq's Whisper API.
    
    Uses Whisper Large V3 Turbo model for fast, accurate transcription.
    Supports Chinese (Mandarin) and English languages.
    Automatically chunks large files to handle 1+ hour recordings.
    """
    
    # Groq Whisper model - turbo is faster and cheaper
    MODEL = "whisper-large-v3-turbo"
    
    def __init__(self, api_key: str):
        """Initialize the transcription service.
        
        Args:
            api_key: Groq API key
        """
        self.client = Groq(api_key=api_key)
    
    def _get_audio_duration(self, file_path: Path) -> float | None:
        """Get audio duration using ffprobe if available."""
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'quiet', '-show_entries',
                    'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(file_path)
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Could not get duration with ffprobe: {e}")
        return None
    
    def _split_audio(self, file_path: Path, chunk_duration: int = CHUNK_DURATION) -> list[Path]:
        """Split audio into chunks using ffmpeg.
        
        Args:
            file_path: Path to the audio file
            chunk_duration: Duration of each chunk in seconds
            
        Returns:
            List of paths to chunk files
        """
        chunks = []
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Get total duration
            duration = self._get_audio_duration(file_path)
            if not duration:
                # If we can't get duration, just return original file
                logger.warning("Could not determine audio duration, using original file")
                return [file_path]
            
            logger.info(f"Audio duration: {duration:.1f}s, splitting into {chunk_duration}s chunks")
            
            # Calculate number of chunks needed
            num_chunks = int(duration // chunk_duration) + (1 if duration % chunk_duration > 0 else 0)
            
            if num_chunks == 1:
                return [file_path]
            
            # Split using ffmpeg
            for i in range(num_chunks):
                start_time = i * chunk_duration
                output_path = temp_dir / f"chunk_{i:03d}.m4a"
                
                try:
                    result = subprocess.run(
                        [
                            'ffmpeg', '-y', '-i', str(file_path),
                            '-ss', str(start_time), '-t', str(chunk_duration),
                            '-c:a', 'aac', '-b:a', '64k',  # Compress to reduce size
                            str(output_path)
                        ],
                        capture_output=True,
                        timeout=120
                    )
                    
                    if result.returncode == 0 and output_path.exists():
                        chunks.append(output_path)
                        logger.info(f"Created chunk {i+1}/{num_chunks}: {output_path.stat().st_size / 1024:.1f}KB")
                    else:
                        logger.error(f"FFmpeg failed for chunk {i}: {result.stderr.decode()}")
                        
                except Exception as e:
                    logger.error(f"Error creating chunk {i}: {e}")
            
            return chunks if chunks else [file_path]
            
        except Exception as e:
            logger.error(f"Audio splitting failed: {e}")
            return [file_path]
    
    def _transcribe_single(
        self,
        file_path: Path,
        language: str | None = None
    ) -> dict:
        """Transcribe a single audio file."""
        params = {
            "model": self.MODEL,
            "response_format": "verbose_json",
        }
        
        if language:
            params["language"] = language
        
        with open(file_path, "rb") as audio_file:
            response = self.client.audio.transcriptions.create(
                file=audio_file,
                **params
            )
        
        return {
            "text": response.text,
            "language": getattr(response, "language", "unknown"),
            "duration": getattr(response, "duration", None),
        }
    
    def transcribe(
        self,
        audio_data: bytes,
        file_extension: str = "m4a",
        language: str | None = None,
    ) -> dict:
        """Transcribe audio data to text. Handles large files automatically.
        
        Args:
            audio_data: Raw audio file bytes
            file_extension: Audio file extension (default: m4a for LINE)
            language: Optional language hint (e.g., 'zh' for Chinese, 'en' for English)
                     If not specified, Whisper auto-detects the language.
        
        Returns:
            Dictionary with 'text' (transcript) and 'language' (detected language)
        """
        # Save audio to temp file
        with tempfile.NamedTemporaryFile(
            suffix=f".{file_extension}",
            delete=False
        ) as temp_file:
            temp_file.write(audio_data)
            temp_path = Path(temp_file.name)
        
        file_size = len(audio_data)
        logger.info(f"Transcribing audio: {file_size / 1024 / 1024:.2f}MB")
        
        chunks_to_cleanup = []
        
        try:
            # Check if we need to split the file
            if file_size > MAX_FILE_SIZE:
                logger.info(f"File exceeds {MAX_FILE_SIZE / 1024 / 1024}MB limit, splitting...")
                chunk_paths = self._split_audio(temp_path)
                chunks_to_cleanup = [p for p in chunk_paths if p != temp_path]
            else:
                chunk_paths = [temp_path]
            
            # Transcribe each chunk
            all_transcripts = []
            total_duration = 0
            detected_language = "unknown"
            
            for i, chunk_path in enumerate(chunk_paths):
                if len(chunk_paths) > 1:
                    logger.info(f"Transcribing chunk {i+1}/{len(chunk_paths)}")
                
                try:
                    result = self._transcribe_single(chunk_path, language)
                    all_transcripts.append(result["text"])
                    
                    if result.get("duration"):
                        total_duration += result["duration"]
                    
                    # Use first detected language
                    if detected_language == "unknown" and result.get("language"):
                        detected_language = result["language"]
                        
                except Exception as e:
                    logger.error(f"Failed to transcribe chunk {i}: {e}")
                    # Continue with other chunks even if one fails
                    all_transcripts.append(f"[Chunk {i+1} failed: {str(e)[:50]}]")
            
            # Combine all transcripts
            full_transcript = "\n\n".join(all_transcripts)
            
            logger.info(
                f"Transcription complete: {len(full_transcript)} chars, "
                f"language={detected_language}, duration={total_duration:.1f}s"
            )
            
            return {
                "text": full_transcript,
                "language": detected_language,
                "duration": total_duration if total_duration > 0 else None,
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {type(e).__name__}: {e}")
            raise
            
        finally:
            # Clean up temp files
            try:
                temp_path.unlink()
            except Exception:
                pass
            
            for chunk in chunks_to_cleanup:
                try:
                    chunk.unlink()
                except Exception:
                    pass
            
            # Clean up chunk temp directory
            for chunk in chunks_to_cleanup:
                try:
                    chunk.parent.rmdir()
                except Exception:
                    pass
