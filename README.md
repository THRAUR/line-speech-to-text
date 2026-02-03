# Meeting Transcription & Summary Bot

A LINE bot that transcribes voice messages and generates organized meeting summaries.

## Features

- 🎤 Voice message transcription (Chinese & English)
- 📝 AI-generated meeting summaries
- 🔐 Daily rotating password authentication
- 📱 LINE messaging platform integration

## Quick Start

### 1. Get API Keys

| Service | URL | Notes |
|---------|-----|-------|
| LINE Developers | https://developers.line.biz/ | Create Official Account → Enable Messaging API |
| Groq | https://console.groq.com/ | Free tier available |
| DeepSeek | https://platform.deepseek.com/ | Very affordable AI |

### 2. LINE Setup

1. Create a [LINE Official Account](https://manager.line.biz/)
2. Enable Messaging API in Settings
3. Go to [LINE Developers Console](https://developers.line.biz/)
4. Find your channel → Get Channel Secret & Access Token
5. Set webhook URL to: `https://your-app.onrender.com/callback`
6. Enable "Use webhook" toggle

### 3. Local Development

```bash
# Clone and setup
cd "Meeting translation tool"
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run locally
python app.py
```

### 4. Test with ngrok

```bash
# In another terminal
ngrok http 5000

# Copy the https URL to LINE Developers webhook settings
```

### 5. Deploy to Render

1. Push to GitHub
2. Connect repo to [Render](https://render.com/)
3. Add environment variables in Render dashboard
4. Deploy!

## Environment Variables

```
LINE_CHANNEL_ACCESS_TOKEN=your_line_token
LINE_CHANNEL_SECRET=your_line_secret
GROQ_API_KEY=your_groq_key
DEEPSEEK_API_KEY=your_deepseek_key
DAILY_PASSWORD_SEED=any_secret_string
```

## Usage

1. **Authenticate**: Send today's password (format: `meetingMMDD`, e.g., `meeting0203`)
2. **Send Voice**: Record and send a voice message
3. **Receive Summary**: Bot replies with formatted meeting summary

## Daily Password

The password changes daily based on the date:
- Format: `meeting` + month + day
- Example for Feb 3rd: `meeting0203`

## Cost Estimate

| 1-Hour Meeting | Cost |
|---------------|------|
| Groq Whisper | ~$0.04 (free tier available) |
| DeepSeek | ~$0.01 (very affordable!) |
| **Total** | **~$0.05** |
