"""
Meeting Transcription & Summary Bot

A LINE bot that transcribes voice messages and generates meeting summaries.
Uses Groq Whisper for transcription and Claude for summarization.
"""
from __future__ import annotations

import logging
import threading
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    AudioMessageContent,
    FileMessageContent,
)

from config import Config
from auth import PasswordManager
from services import TranscriptionService, SummarizationService, DocumentGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Validate configuration
missing = Config.validate()
if missing:
    logger.error(f"Missing required configuration: {missing}")
    raise EnvironmentError(f"Missing environment variables: {missing}")

# Initialize Flask app
app = Flask(__name__)

# Initialize LINE SDK
configuration = Configuration(access_token=Config.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(Config.LINE_CHANNEL_SECRET)

# Initialize services
password_manager = PasswordManager(Config.DAILY_PASSWORD_SEED)
transcription_service = TranscriptionService(Config.GROQ_API_KEY)
summarization_service = SummarizationService(Config.DEEPSEEK_API_KEY)
document_generator = DocumentGenerator()


@app.route("/callback", methods=["POST"])
def callback():
    """LINE webhook callback endpoint.
    
    Receives webhook events from LINE and dispatches to handlers.
    """
    # Get X-Line-Signature header
    signature = request.headers.get("X-Line-Signature", "")
    
    # Get request body as text
    body = request.get_data(as_text=True)
    logger.info("Received webhook request")
    
    # Verify signature and handle event
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        abort(400)
    
    return "OK"


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "active_sessions": password_manager.get_session_count(),
        "today_password_hint": f"meeting{password_manager.get_today_date_string()[5:7]}{password_manager.get_today_date_string()[8:10]}",
    }


def send_message(user_id: str, text: str):
    """Send a push message to a user.
    
    Args:
        user_id: LINE user ID
        text: Message text to send
    """
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        
        # Split long messages
        chunks = document_generator.split_for_line(text)
        
        for chunk in chunks:
            messaging_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=chunk)]
                )
            )


def reply_message(reply_token: str, text: str):
    """Reply to a message using reply token.
    
    Args:
        reply_token: LINE reply token
        text: Message text to send
    """
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


def process_audio_async(user_id: str, message_id: str):
    """Process audio message asynchronously.
    
    This is run in a background thread to avoid blocking the webhook response.
    
    Args:
        user_id: LINE user ID
        message_id: LINE message ID for the audio
    """
    try:
        logger.info(f"Starting audio processing for message {message_id}")
        
        # Download audio from LINE
        with ApiClient(configuration) as api_client:
            blob_api = MessagingApiBlob(api_client)
            audio_data = blob_api.get_message_content(message_id)
        
        logger.info(f"Downloaded audio: {len(audio_data)} bytes")
        
        # Transcribe audio
        try:
            transcription_result = transcription_service.transcribe(
                audio_data,
                file_extension="m4a"  # LINE audio is M4A format
            )
            transcript = transcription_result["text"]
            duration = transcription_result.get("duration")
            detected_language = transcription_result.get("language")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            send_message(user_id, document_generator.create_error_message("transcription"))
            return
        
        if not transcript or transcript.strip() == "":
            send_message(user_id, "⚠️ No speech detected in the audio. Please try again with a clearer recording.")
            return
        
        logger.info(f"Transcription complete: {len(transcript)} chars, language={detected_language}")
        
        # Generate summary
        try:
            summary = summarization_service.summarize(
                transcript,
                detected_language=detected_language
            )
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Still send the transcript even if summary fails
            send_message(
                user_id,
                f"⚠️ Summary generation failed, but here's the transcript:\n\n{transcript}"
            )
            return
        
        # Format and send the result
        formatted_document = document_generator.format_for_line(summary, duration)
        send_message(user_id, formatted_document)
        
        logger.info(f"Successfully processed audio for user {user_id}")
        
    except Exception as e:
        logger.error(f"Audio processing failed: {e}")
        send_message(user_id, document_generator.create_error_message("general"))


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    """Handle incoming text messages.
    
    Used for password authentication.
    """
    user_id = event.source.user_id
    text = event.message.text.strip()
    
    logger.info(f"Received text from {user_id}: {text[:20]}...")
    
    # Check if already authenticated
    if password_manager.is_authenticated(user_id):
        reply_message(
            event.reply_token,
            "You're already authenticated! Send me a voice message to transcribe."
        )
        return
    
    # Attempt authentication
    success, message = password_manager.authenticate_user(user_id, text)
    
    if success:
        # Send welcome message after successful auth
        reply_message(event.reply_token, document_generator.create_welcome_message())
    else:
        reply_message(event.reply_token, message)


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio_message(event: MessageEvent):
    """Handle incoming audio/voice messages.
    
    This is the main functionality - transcribe and summarize voice recordings.
    """
    user_id = event.source.user_id
    message_id = event.message.id
    
    logger.info(f"Received audio from {user_id}, message_id: {message_id}")
    
    # Check authentication
    if not password_manager.is_authenticated(user_id):
        reply_message(
            event.reply_token,
            password_manager.get_unauthenticated_message()
        )
        return
    
    # Send immediate confirmation
    reply_message(
        event.reply_token,
        document_generator.create_processing_message()
    )
    
    # Process audio in background thread
    thread = threading.Thread(
        target=process_audio_async,
        args=(user_id, message_id)
    )
    thread.start()


@handler.add(MessageEvent, message=FileMessageContent)
def handle_file_message(event: MessageEvent):
    """Handle incoming file messages (uploaded audio files).
    
    This allows users to upload M4A, MP3, WAV files instead of recording in LINE.
    """
    user_id = event.source.user_id
    message_id = event.message.id
    file_name = event.message.file_name.lower() if event.message.file_name else ""
    
    logger.info(f"Received file from {user_id}: {file_name}")
    
    # Check authentication
    if not password_manager.is_authenticated(user_id):
        reply_message(
            event.reply_token,
            password_manager.get_unauthenticated_message()
        )
        return
    
    # Check if it's an audio file
    audio_extensions = ('.m4a', '.mp3', '.wav', '.ogg', '.flac', '.mp4', '.mpeg', '.mpga', '.webm')
    if not file_name.endswith(audio_extensions):
        reply_message(
            event.reply_token,
            f"⚠️ Please send an audio file.\n\nSupported formats: M4A, MP3, WAV, OGG, FLAC\n\nReceived: {file_name}"
        )
        return
    
    # Get file extension for transcription
    file_ext = file_name.split('.')[-1] if '.' in file_name else 'm4a'
    
    # Send immediate confirmation
    reply_message(
        event.reply_token,
        f"📁 File received: {event.message.file_name}\n\n" + document_generator.create_processing_message()
    )
    
    # Process audio in background thread
    thread = threading.Thread(
        target=process_audio_async,
        args=(user_id, message_id)
    )
    thread.start()


if __name__ == "__main__":
    logger.info(f"Starting server on port {Config.PORT}")
    logger.info(f"Today's password: {password_manager.get_today_password()}")
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)

