"""Transcription service using Groq Whisper API with parallel chunking."""
from __future__ import annotations

import tempfile
import logging
import subprocess
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from groq import Groq

logger = logging.getLogger(__name__)

# Maximum file size for Groq free tier (25MB)
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB in bytes

# Chunk duration in seconds (25 minutes = much fewer chunks)
CHUNK_DURATION = 1500  # 25 minutes

# Max parallel workers (keep low to avoid rate limits)
MAX_WORKERS = 2


class TranscriptionService:
    """Transcribes audio files using Groq's Whisper API.
    
    Uses Whisper Large V3 Turbo model for fast, accurate transcription.
    Supports Chinese (Mandarin) and English languages.
    Automatically chunks large files and processes them in PARALLEL.
    """
    
    # Groq Whisper model - turbo is faster and cheaper
    MODEL = "whisper-large-v3-turbo"
    
    def __init__(self, api_key: str):
        """Initialize the transcription service.
        
        Args:
            api_key: Groq API key
        """
        self.api_key = api_key
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
        """Split audio into chunks using ffmpeg (fast, no re-encoding).
        
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
                logger.warning("Could not determine audio duration, using original file")
                return [file_path]
            
            # Calculate number of chunks needed
            num_chunks = int(duration // chunk_duration) + (1 if duration % chunk_duration > 0 else 0)
            
            logger.info(f"Audio: {duration/60:.1f} min, splitting into {num_chunks} chunks of {chunk_duration/60:.0f} min each")
            
            if num_chunks == 1:
                return [file_path]
            
            # Get file extension
            ext = file_path.suffix or '.m4a'
            
            # Split using ffmpeg with stream copy (FAST - no re-encoding)
            for i in range(num_chunks):
                start_time = i * chunk_duration
                output_path = temp_dir / f"chunk_{i:03d}{ext}"
                
                try:
                    result = subprocess.run(
                        [
                            'ffmpeg', '-y', '-i', str(file_path),
                            '-ss', str(start_time), '-t', str(chunk_duration),
                            '-c', 'copy',  # Stream copy = FAST, no re-encoding
                            '-avoid_negative_ts', 'make_zero',
                            str(output_path)
                        ],
                        capture_output=True,
                        timeout=60
                    )
                    
                    if result.returncode == 0 and output_path.exists():
                        size_kb = output_path.stat().st_size / 1024
                        chunks.append(output_path)
                        logger.info(f"Chunk {i+1}/{num_chunks}: {size_kb:.0f}KB")
                    else:
                        # If stream copy fails, try with re-encoding
                        logger.warning(f"Stream copy failed for chunk {i}, trying with re-encode")
                        result = subprocess.run(
                            [
                                'ffmpeg', '-y', '-i', str(file_path),
                                '-ss', str(start_time), '-t', str(chunk_duration),
                                '-c:a', 'aac', '-b:a', '64k',
                                str(output_path)
                            ],
                            capture_output=True,
                            timeout=120
                        )
                        if result.returncode == 0 and output_path.exists():
                            chunks.append(output_path)
                        
                except Exception as e:
                    logger.error(f"Error creating chunk {i}: {e}")
            
            return chunks if chunks else [file_path]
            
        except Exception as e:
            logger.error(f"Audio splitting failed: {e}")
            return [file_path]
    
    def _transcribe_single(
        self,
        file_path: Path,
        chunk_index: int,
        total_chunks: int,
        language: str | None = None,
        max_retries: int = 3
    ) -> dict:
        """Transcribe a single audio file with retry logic for rate limits."""
        import time
        import re
        
        # Create a new client for this thread (thread safety)
        client = Groq(api_key=self.api_key)
        
        params = {
            "model": self.MODEL,
            "response_format": "verbose_json",
        }
        
        if language:
            params["language"] = language
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"🎤 Transcribing chunk {chunk_index + 1}/{total_chunks}..." + 
                           (f" (retry {attempt})" if attempt > 0 else ""))
                
                with open(file_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        file=audio_file,
                        **params
                    )
                
                logger.info(f"✅ Chunk {chunk_index + 1}/{total_chunks} done!")
                
                return {
                    "index": chunk_index,
                    "text": response.text,
                    "language": getattr(response, "language", "unknown"),
                    "duration": getattr(response, "duration", None),
                }
                
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_str or "rate_limit" in error_str.lower():
                    # Try to extract wait time from error message
                    wait_match = re.search(r'try again in (\d+)m?([\d.]+)?s?', error_str)
                    if wait_match:
                        minutes = int(wait_match.group(1)) if wait_match.group(1) else 0
                        seconds = float(wait_match.group(2)) if wait_match.group(2) else 0
                        wait_time = minutes * 60 + seconds + 5  # Add 5 sec buffer
                    else:
                        wait_time = 60 * (attempt + 1)  # Exponential: 60s, 120s, 180s
                    
                    if attempt < max_retries:
                        logger.warning(f"⏳ Rate limited on chunk {chunk_index + 1}, waiting {wait_time:.0f}s...")
                        time.sleep(wait_time)
                        continue
                
                # If not rate limit or max retries exceeded, raise
                logger.error(f"❌ Chunk {chunk_index + 1} failed after {attempt + 1} attempts: {e}")
                raise
    
    def transcribe(
        self,
        audio_data: bytes,
        file_extension: str = "m4a",
        language: str | None = None,
    ) -> dict:
        """Transcribe audio data to text. Handles large files with PARALLEL processing.
        
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
        logger.info(f"📁 Transcribing audio: {file_size / 1024 / 1024:.2f}MB")
        
        chunks_to_cleanup = []
        
        try:
            # Check if we need to split the file
            if file_size > MAX_FILE_SIZE:
                logger.info(f"⚡ File exceeds {MAX_FILE_SIZE / 1024 / 1024}MB limit, splitting for parallel processing...")
                chunk_paths = self._split_audio(temp_path)
                chunks_to_cleanup = [p for p in chunk_paths if p != temp_path]
            else:
                chunk_paths = [temp_path]
            
            total_chunks = len(chunk_paths)
            
            # PARALLEL TRANSCRIPTION
            if total_chunks > 1:
                logger.info(f"🚀 Processing {total_chunks} chunks in PARALLEL...")
                results = []
                
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    # Submit all chunks for parallel processing
                    future_to_index = {
                        executor.submit(
                            self._transcribe_single, 
                            chunk_path, 
                            i, 
                            total_chunks, 
                            language
                        ): i
                        for i, chunk_path in enumerate(chunk_paths)
                    }
                    
                    # Collect results as they complete
                    for future in as_completed(future_to_index):
                        chunk_index = future_to_index[future]
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            logger.error(f"❌ Chunk {chunk_index} failed: {e}")
                            results.append({
                                "index": chunk_index,
                                "text": f"[Chunk {chunk_index + 1} failed: {str(e)[:50]}]",
                                "language": "unknown",
                                "duration": None
                            })
                
                # Sort by index to maintain order
                results.sort(key=lambda x: x["index"])
                
            else:
                # Single file, no parallel needed
                results = [self._transcribe_single(chunk_paths[0], 0, 1, language)]
            
            # Combine all transcripts
            all_transcripts = [r["text"] for r in results]
            full_transcript = "\n\n".join(all_transcripts)
            
            # Calculate totals
            total_duration = sum(r.get("duration") or 0 for r in results)
            detected_language = next(
                (r["language"] for r in results if r.get("language") != "unknown"),
                "unknown"
            )
            
            logger.info(
                f"✅ Transcription complete: {len(full_transcript)} chars, "
                f"language={detected_language}, duration={total_duration/60:.1f}min"
            )
            
            return {
                "text": full_transcript,
                "language": detected_language,
                "duration": total_duration if total_duration > 0 else None,
            }
            
        except Exception as e:
            logger.error(f"❌ Transcription failed: {type(e).__name__}: {e}")
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
