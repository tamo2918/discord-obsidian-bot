"""OpenAI-compatible AI adapter (works with OpenAI, Anthropic, etc.)."""
import logging
from typing import Optional

import requests

from adapters.ai.prompt import SYSTEM_PROMPT, build_user_prompt
from adapters.base import BaseAIAdapter

logger = logging.getLogger(__name__)


class OpenAICompatibleAI(BaseAIAdapter):
    """AI adapter for OpenAI-compatible APIs (/v1/chat/completions)."""

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.model = config.get("model", "gpt-4o-mini")
        self.api_key = config.get("api_key", "")
        self.timeout = int(config.get("timeout", 60))

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_available(self) -> bool:
        """Check if the API is reachable."""
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=5,
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.debug(f"OpenAI-compatible API not reachable: {e}")
            return False

    def format_message(self, content: str, metadata: dict) -> Optional[str]:
        """Format a message using OpenAI-compatible /v1/chat/completions."""
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(content, metadata)},
                ],
                "temperature": 0.3,
            }

            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                logger.error(
                    f"OpenAI API error: {resp.status_code} - {resp.text}"
                )
                return None

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                logger.warning("OpenAI API returned no choices")
                return None

            result = choices[0].get("message", {}).get("content", "")

            if not result.strip():
                logger.warning("OpenAI API returned empty response")
                return None

            logger.info(f"AI formatting successful (model={self.model})")
            return result.strip()

        except requests.exceptions.Timeout:
            logger.warning(f"OpenAI API request timed out after {self.timeout}s")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenAI API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in OpenAI adapter: {e}")
            return None
