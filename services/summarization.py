"""Summarization service using DeepSeek API."""
from __future__ import annotations

import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class SummarizationService:
    """Generates meeting summaries using DeepSeek API.
    
    DeepSeek is OpenAI-compatible, so we use the OpenAI SDK.
    Uses DeepSeek Chat model for cost-effective summarization.
    Supports bilingual summaries (Chinese and English).
    """
    
    # DeepSeek API base URL
    BASE_URL = "https://api.deepseek.com"
    
    # DeepSeek Chat model
    MODEL = "deepseek-chat"
    
    # Maximum tokens for the summary (approx 4000 words)
    MAX_TOKENS = 4096
    
    # System prompt for meeting summarization
    SYSTEM_PROMPT = """You are an expert meeting summarizer. Your task is to analyze meeting transcripts and create well-organized meeting summaries.

Instructions:
1. Analyze the transcript carefully to identify key information
2. Create a structured summary in the SAME LANGUAGE as the transcript
3. If the transcript is in Chinese, respond in Chinese
4. If the transcript is in English, respond in English
5. If the transcript is mixed, use the dominant language
6. Be concise but comprehensive
7. Extract action items even if not explicitly stated as such
8. Identify decisions made during the meeting
9. Note any follow-up items or next steps mentioned"""

    SUMMARY_TEMPLATE = """Please analyze this meeting transcript and create a structured summary.

## Transcript:
{transcript}

## Required Output Format:

# 會議摘要 / Meeting Summary

**日期/Date:** [Extract from transcript or use "Not specified"]
**參與者/Attendees:** [List attendees if mentioned, otherwise "Not explicitly mentioned"]

## 重點討論 / Key Discussion Points
[List the main topics discussed as bullet points]

## 決議事項 / Decisions Made
[List any decisions made during the meeting]

## 待辦事項 / Action Items
[List action items with owners if mentioned, format: - [Action] (Owner: [Name])]

## 後續步驟 / Next Steps
[List any follow-up items or next meeting plans]

---

## 完整逐字稿 / Full Transcript
[Include the original transcript here]"""

    def __init__(self, api_key: str):
        """Initialize the summarization service.
        
        Args:
            api_key: DeepSeek API key
        """
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.BASE_URL
        )
    
    def summarize(
        self,
        transcript: str,
        detected_language: str | None = None,
        additional_context: str | None = None
    ) -> str:
        """Generate a meeting summary from a transcript.
        
        Args:
            transcript: The meeting transcript text
            detected_language: Optional language hint from transcription
            additional_context: Optional additional context about the meeting
            
        Returns:
            Formatted meeting summary as a string
        """
        # Prepare the prompt
        prompt = self.SUMMARY_TEMPLATE.format(transcript=transcript)
        
        # Add language hint if available
        if detected_language:
            prompt = f"[Detected language: {detected_language}]\n\n" + prompt
        
        # Add additional context if provided
        if additional_context:
            prompt = f"[Context: {additional_context}]\n\n" + prompt
        
        logger.info(f"Generating summary for transcript ({len(transcript)} chars)")
        
        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            
            summary = response.choices[0].message.content
            
            # Log token usage for cost tracking
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            logger.info(
                f"Summary generated: {len(summary)} chars, "
                f"tokens: {input_tokens} input / {output_tokens} output"
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            raise
    
    def estimate_cost(self, transcript: str, summary: str) -> dict:
        """Estimate the cost of a summarization request.
        
        Args:
            transcript: Original transcript
            summary: Generated summary
            
        Returns:
            Dictionary with token counts and estimated cost
        """
        # Rough estimation: 1 token ≈ 4 characters for English, 1.5 for Chinese
        input_tokens = len(transcript) // 3 + len(self.SYSTEM_PROMPT) // 4
        output_tokens = len(summary) // 3
        
        # DeepSeek pricing: very cheap ~$0.14/MTok input, ~$0.28/MTok output
        input_cost = (input_tokens / 1_000_000) * 0.14
        output_cost = (output_tokens / 1_000_000) * 0.28
        
        return {
            "input_tokens_est": input_tokens,
            "output_tokens_est": output_tokens,
            "cost_usd_est": input_cost + output_cost,
        }
