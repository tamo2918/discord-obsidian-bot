"""Message processor for converting messages to Markdown format."""
import logging
from datetime import datetime
from typing import Optional, Tuple

import pytz

from adapters.base import BaseAIAdapter, MessageData

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Process messages and convert them to Markdown format.

    Supports optional AI formatting with automatic fallback
    to plain Markdown when AI is unavailable.
    """

    def __init__(self, config: dict, ai_adapter: Optional[BaseAIAdapter] = None):
        """
        Initialize the message processor.

        Args:
            config: Processor configuration containing timezone and template
            ai_adapter: Optional AI adapter for message formatting
        """
        self.timezone = pytz.timezone(config.get("timezone", "UTC"))
        self.template = config.get("template", "daily")
        self.ai = ai_adapter

        if self.ai:
            logger.info("AI formatting enabled")
        else:
            logger.info("AI formatting disabled (plain Markdown mode)")

    def _convert_timezone(self, dt: datetime) -> datetime:
        """Convert datetime to configured timezone."""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(self.timezone)

    def _format_attachments(self, attachments: list) -> str:
        """Format attachments as Markdown image links."""
        if not attachments:
            return ""

        lines = []
        for url in attachments:
            lines.append(f"![]({url})")
        return "\n".join(lines)

    def _process_daily(self, message: MessageData) -> Tuple[str, str]:
        """
        Process message using daily template.

        Creates one file per day with messages appended.

        Args:
            message: Message data to process

        Returns:
            Tuple of (filename, content)
        """
        local_time = self._convert_timezone(message.timestamp)

        # Filename: YYYY-MM-DD.md
        filename = local_time.strftime("%Y-%m-%d.md")

        # Content format
        lines = [
            f"## {local_time.strftime('%H:%M')}",
            "",
            message.content,
        ]

        # Add attachments
        attachments_md = self._format_attachments(message.attachments)
        if attachments_md:
            lines.append("")
            lines.append(attachments_md)

        content = "\n".join(lines)

        return filename, content

    def _process_single(self, message: MessageData) -> Tuple[str, str]:
        """
        Process message using single template.

        Creates one file per message.

        Args:
            message: Message data to process

        Returns:
            Tuple of (filename, content)
        """
        local_time = self._convert_timezone(message.timestamp)

        # Filename: YYYY-MM-DD_HHMMSS.md
        filename = local_time.strftime("%Y-%m-%d_%H%M%S.md")

        # Content format with frontmatter
        lines = [
            "---",
            f"date: {local_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"author: {message.author}",
            f"channel: {message.channel}",
            "---",
            "",
            message.content,
        ]

        # Add attachments section
        if message.attachments:
            lines.extend([
                "",
                "## Attachments",
                "",
                self._format_attachments(message.attachments),
            ])

        content = "\n".join(lines)

        return filename, content

    def _try_ai_format(self, message: MessageData) -> Optional[str]:
        """
        Try to format message content using AI.

        Returns:
            AI-formatted content, or None if AI is unavailable or failed
        """
        if not self.ai:
            return None

        if not self.ai.is_available():
            logger.info("AI service unavailable, using fallback")
            return None

        local_time = self._convert_timezone(message.timestamp)

        metadata = {
            "timestamp": local_time.strftime("%Y-%m-%d %H:%M"),
            "author": message.author,
            "channel": message.channel,
            "attachments": message.attachments,
        }

        result = self.ai.format_message(message.content, metadata)

        if result:
            logger.info("Message formatted by AI")
        else:
            logger.info("AI formatting failed, using fallback")

        return result

    def process(self, message: MessageData) -> Tuple[str, str, bool]:
        """
        Process a message and return filename and content.

        If AI is configured and available, uses AI to format the content.
        Otherwise falls back to plain Markdown templates.

        Args:
            message: Message data to process

        Returns:
            Tuple of (filename, content, should_append)
            should_append is True for daily template
        """
        logger.debug(f"Processing message with template: {self.template}")

        # Determine filename based on template
        local_time = self._convert_timezone(message.timestamp)

        if self.template == "single":
            filename = local_time.strftime("%Y-%m-%d_%H%M%S.md")
            should_append = False
        else:
            filename = local_time.strftime("%Y-%m-%d.md")
            should_append = True

        # Try AI formatting first
        ai_content = self._try_ai_format(message)

        if ai_content:
            return filename, ai_content, should_append

        # Fallback: plain Markdown
        if self.template == "single":
            _, content = self._process_single(message)
        else:
            _, content = self._process_daily(message)

        return filename, content, should_append
