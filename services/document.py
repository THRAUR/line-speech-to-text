"""Document generation service."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta


class DocumentGenerator:
    """Generates formatted meeting documents.
    
    Currently outputs Markdown format suitable for LINE messages.
    Can be extended to support PDF/DOCX if needed.
    """
    
    # Taiwan timezone
    TW_TIMEZONE = timezone(timedelta(hours=8))
    
    def format_for_line(self, summary: str, duration_seconds: float | None = None) -> str:
        """Format the summary for LINE message display.
        
        Args:
            summary: The meeting summary from Claude
            duration_seconds: Optional audio duration in seconds
            
        Returns:
            Formatted string for LINE message
        """
        # Add header with timestamp
        now = datetime.now(self.TW_TIMEZONE)
        header = f"📋 Meeting Summary\n📅 {now.strftime('%Y-%m-%d %H:%M')}\n"
        
        if duration_seconds:
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            header += f"⏱️ Duration: {minutes}m {seconds}s\n"
        
        header += "─" * 20 + "\n\n"
        
        return header + summary
    
    def split_for_line(self, text: str, max_length: int = 4500) -> list[str]:
        """Split long text into multiple LINE messages.
        
        LINE has a 5000 character limit per message.
        We use 4500 to leave room for formatting.
        
        Args:
            text: Full text to split
            max_length: Maximum characters per message
            
        Returns:
            List of message chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by lines to avoid breaking mid-sentence
        lines = text.split("\n")
        
        for line in lines:
            # If adding this line would exceed limit, start new chunk
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        
        # Add the last chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Add part indicators if multiple chunks
        if len(chunks) > 1:
            chunks = [
                f"📄 Part {i+1}/{len(chunks)}\n\n{chunk}"
                for i, chunk in enumerate(chunks)
            ]
        
        return chunks
    
    def create_error_message(self, error_type: str) -> str:
        """Create a user-friendly error message.
        
        Args:
            error_type: Type of error that occurred
            
        Returns:
            Formatted error message
        """
        messages = {
            "transcription": (
                "❌ Transcription Error\n\n"
                "Sorry, I couldn't transcribe your voice message. "
                "This might happen if:\n"
                "• The audio quality is too low\n"
                "• The file is corrupted\n"
                "• The audio is too short or silent\n\n"
                "Please try recording again."
            ),
            "summarization": (
                "❌ Summarization Error\n\n"
                "I transcribed your audio but couldn't generate a summary. "
                "Please try again in a moment."
            ),
            "download": (
                "❌ Download Error\n\n"
                "Sorry, I couldn't download your voice message. "
                "Please try sending it again."
            ),
            "general": (
                "❌ Error\n\n"
                "An unexpected error occurred. "
                "Please try again in a moment."
            ),
        }
        return messages.get(error_type, messages["general"])
    
    def create_processing_message(self) -> str:
        """Create a message to show while processing."""
        return (
            "🎤 Voice message received!\n\n"
            "⏳ Processing your audio...\n"
            "• Transcribing speech\n"
            "• Generating summary\n\n"
            "This may take a moment for longer recordings."
        )
    
    def create_welcome_message(self) -> str:
        """Create a welcome message for authenticated users."""
        return (
            "✅ Welcome to Meeting Summary Bot!\n\n"
            "📝 How to use:\n"
            "1. Send a voice message with your meeting recording\n"
            "2. Wait for the transcription and summary\n"
            "3. Receive a formatted meeting document\n\n"
            "🌐 Supported languages: Chinese (中文) & English\n\n"
            "Ready when you are! 🎤"
        )
