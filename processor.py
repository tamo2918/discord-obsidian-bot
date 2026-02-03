"""Message processor for converting messages to Markdown format."""
import logging
from datetime import datetime
from typing import Tuple

import pytz

from adapters.base import MessageData

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Process messages and convert them to Markdown format."""

    def __init__(self, config: dict):
        """
        Initialize the message processor.

        Args:
            config: Processor configuration containing timezone and template
        """
        self.timezone = pytz.timezone(config.get("timezone", "UTC"))
        self.template = config.get("template", "daily")

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

    def process(self, message: MessageData) -> Tuple[str, str, bool]:
        """
        Process a message and return filename and content.

        Args:
            message: Message data to process

        Returns:
            Tuple of (filename, content, should_append)
            should_append is True for daily template
        """
        logger.debug(f"Processing message with template: {self.template}")

        if self.template == "daily":
            filename, content = self._process_daily(message)
            return filename, content, True
        elif self.template == "single":
            filename, content = self._process_single(message)
            return filename, content, False
        else:
            logger.warning(f"Unknown template '{self.template}', using daily")
            filename, content = self._process_daily(message)
            return filename, content, True
