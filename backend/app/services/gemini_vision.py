"""
Google Gemini Flash Vision Service for StudyGraph.
Relies on Decision D08: Google Gemini Flash for scans and handwriting.
Handles sending images or scanned PDF pages to Gemini Flash and returns
transcribed text with exact token usage for cost tracking.
"""

import logging
from typing import Optional, Tuple
from google import genai
from google.genai import types

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

VISION_PROMPT = """
You are an expert academic document transcriber.
Your task is to transcribe all readable text, formulas, diagrams, labels, and bullet points from this handwritten or scanned lecture note page.

Rules:
1. Preserve structural headings, subheadings, bullet points, and numbered lists.
2. Transcribe handwritten text accurately.
3. If diagrams or flowcharts are present, describe their relationships or text labels in bracketed text, e.g. [Diagram: Process A -> Process B].
4. Do NOT hallucinate, summarize, or add external explanations. Output ONLY what is visible on the page.
5. If the page is blank or completely illegible, respond with an empty string.
"""


class GeminiVisionService:
    def __init__(self):
        self.model_name = settings.GEMINI_VISION_MODEL
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set in your .env file.\n"
                "Please add your Google AI Studio API key to .env: GEMINI_API_KEY=AIzaSy..."
            )
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def transcribe_page(
        self,
        image_or_pdf_bytes: bytes,
        mime_type: str = "image/png",
    ) -> Tuple[str, dict]:
        """
        Transcribes a single scanned page or image of notes using Gemini Flash.
        Returns:
            Tuple of (transcribed_text, token_usage_dict)
            where token_usage_dict contains {'prompt_tokens': int, 'completion_tokens': int, 'total_tokens': int}
        """
        client = self._get_client()

        # Build image or document part
        content_part = types.Part.from_bytes(
            data=image_or_pdf_bytes,
            mime_type=mime_type,
        )

        # Models to try in order of preference
        models_to_try = [self.model_name]
        for fallback in ("gemini-3.5-flash", "gemini-flash-latest", "gemini-3.8-flash"):
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        response = None
        last_error = None

        for model in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[content_part, VISION_PROMPT],
                )
                self.model_name = model
                break
            except Exception as e:
                logger.warning(f"[Vision OCR] Model {model} failed: {e}. Trying next fallback...")
                last_error = e

        if response is None:
            raise RuntimeError(f"All vision models failed. Last error: {last_error}")

        text = response.text or ""

        # Extract token usage
        token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        if response.usage_metadata:
            token_usage["prompt_tokens"] = response.usage_metadata.prompt_token_count or 0
            token_usage["completion_tokens"] = response.usage_metadata.candidates_token_count or 0
            token_usage["total_tokens"] = response.usage_metadata.total_token_count or 0

        logger.info(
            f"[Vision OCR] Model: {self.model_name} | "
            f"Prompt Tokens: {token_usage['prompt_tokens']} | "
            f"Completion Tokens: {token_usage['completion_tokens']} | "
            f"Total Tokens: {token_usage['total_tokens']}"
        )
        print(
            f"  [Cost Tracker] Page Vision Call -> "
            f"Prompt tokens: {token_usage['prompt_tokens']}, "
            f"Completion tokens: {token_usage['completion_tokens']} "
            f"(Total: {token_usage['total_tokens']} tokens)"
        )

        return text.strip(), token_usage


gemini_vision_service = GeminiVisionService()

