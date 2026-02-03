"""Ollama AI adapter using the native Ollama API."""
import logging
from typing import Optional

import requests

from adapters.ai.prompt import get_system_prompt, build_user_prompt, BOOK_TITLE_EXTRACTION_PROMPT
from adapters.base import BaseAIAdapter

logger = logging.getLogger(__name__)


class OllamaAI(BaseAIAdapter):
    """AI adapter for Ollama's native API (/api/chat)."""

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "http://localhost:11434").rstrip("/")
        self.model = config.get("model", "gemma2")
        self.timeout = int(config.get("timeout", 60))

    def is_available(self) -> bool:
        """Check if Ollama is reachable and the model is loaded."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            if resp.status_code != 200:
                return False

            models = [m["name"] for m in resp.json().get("models", [])]
            # Match "gemma2" against "gemma2:latest" etc.
            available = any(
                m == self.model or m.startswith(f"{self.model}:")
                for m in models
            )
            if not available:
                logger.warning(
                    f"Ollama is reachable but model '{self.model}' not found. "
                    f"Available: {models}"
                )
            return available

        except requests.exceptions.RequestException as e:
            logger.debug(f"Ollama not reachable: {e}")
            return False

    def format_message(
        self,
        content: str,
        metadata: dict,
        existing_content: str = None,
    ) -> Optional[str]:
        """Format a message using Ollama's /api/chat endpoint."""
        try:
            channel_type = metadata.get("channel_type", "memo")
            system_prompt = get_system_prompt(channel_type)

            user_prompt = build_user_prompt(content, metadata, existing_content)

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                },
            }

            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                logger.error(f"Ollama API error: {resp.status_code} - {resp.text}")
                return None

            data = resp.json()
            result = data.get("message", {}).get("content", "")

            if not result.strip():
                logger.warning("Ollama returned empty response")
                return None

            logger.info(f"AI formatting successful (model={self.model})")
            return result.strip()

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama request timed out after {self.timeout}s")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Ollama adapter: {e}")
            return None

    def extract_book_title(self, content: str) -> Optional[str]:
        """Extract a book title from message content using Ollama."""
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": BOOK_TITLE_EXTRACTION_PROMPT},
                    {"role": "user", "content": content},
                ],
                "stream": False,
                "options": {"temperature": 0.0},
            }

            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=30,
            )

            if resp.status_code != 200:
                logger.error(f"Ollama title extraction error: {resp.status_code}")
                return None

            title = resp.json().get("message", {}).get("content", "").strip()

            if not title or title == "不明":
                logger.info("Could not extract book title from message")
                return None

            logger.info(f"Extracted book title: {title}")
            return title

        except Exception as e:
            logger.error(f"Book title extraction failed: {e}")
            return None
