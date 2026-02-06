"""Google Gemini AI adapter using the REST API."""
import logging
from typing import Optional

import requests

from adapters.ai.prompt import get_system_prompt, build_user_prompt, BOOK_TITLE_EXTRACTION_PROMPT
from adapters.base import BaseAIAdapter

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiAI(BaseAIAdapter):
    """AI adapter for Google Gemini REST API."""

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-2.5-flash")
        self.timeout = int(config.get("timeout", 60))

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    def _generate(self, system_prompt: str, user_prompt: str, temperature: float) -> Optional[str]:
        """
        Call the Gemini generateContent endpoint.

        Args:
            system_prompt: System instruction text
            user_prompt: User message text
            temperature: Sampling temperature

        Returns:
            Generated text, or None on failure
        """
        url = f"{GEMINI_API_BASE}/models/{self.model}:generateContent"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                },
            ],
            "generation_config": {
                "temperature": temperature,
            },
        }

        resp = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            logger.error(f"Gemini API error: {resp.status_code} - {resp.text}")
            return None

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("Gemini API returned no candidates")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            logger.warning("Gemini API returned no content parts")
            return None

        text = parts[0].get("text", "")
        if not text.strip():
            logger.warning("Gemini API returned empty response")
            return None

        return text.strip()

    def is_available(self) -> bool:
        """Check if the Gemini API is reachable."""
        if not self.api_key:
            logger.debug("Gemini API key not configured")
            return False
        try:
            resp = requests.get(
                f"{GEMINI_API_BASE}/models/{self.model}",
                headers=self._headers(),
                timeout=5,
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.debug(f"Gemini API not reachable: {e}")
            return False

    def format_message(
        self,
        content: str,
        metadata: dict,
        existing_content: str = None,
    ) -> Optional[str]:
        """Format a message using Gemini generateContent."""
        try:
            channel_type = metadata.get("channel_type", "memo")
            system_prompt = get_system_prompt(channel_type)
            user_prompt = build_user_prompt(content, metadata, existing_content)

            result = self._generate(system_prompt, user_prompt, temperature=0.3)

            if result:
                logger.info(f"AI formatting successful (model={self.model})")
            return result

        except requests.exceptions.Timeout:
            logger.warning(f"Gemini API request timed out after {self.timeout}s")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Gemini API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Gemini adapter: {e}")
            return None

    def extract_book_title(self, content: str) -> Optional[str]:
        """Extract a book title from message content using Gemini."""
        try:
            title = self._generate(
                BOOK_TITLE_EXTRACTION_PROMPT, content, temperature=0.0
            )

            if not title or title == "不明":
                logger.info("Could not extract book title from message")
                return None

            logger.info(f"Extracted book title: {title}")
            return title

        except Exception as e:
            logger.error(f"Book title extraction failed: {e}")
            return None
