"""Message processor for converting messages to Markdown format."""
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

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

    def generate_daily_template(self, date_str: str, channel_type: str) -> str:
        """
        Generate a frontmatter template for a daily file (memo or diary).

        This is called at the start of each day (or on bot startup) to
        pre-create files with correct frontmatter, so AI only needs to
        handle the body content.

        Args:
            date_str: Date string in YYYY-MM-DD format
            channel_type: "memo" or "diary"

        Returns:
            Markdown string with YAML frontmatter and section structure
        """
        if channel_type == "diary":
            return (
                "---\n"
                "type: diary\n"
                f"created: {date_str}\n"
                "tags: []\n"
                "mood: 5\n"
                "energy: 5\n"
                "---\n"
                "\n"
                "## 今日のログ\n"
                "\n"
                "### やったこと\n"
                "-\n"
                "\n"
                "### あったこと\n"
                "-\n"
                "\n"
                "### 考えたこと\n"
                "-\n"
                "\n"
                "### 明日やること\n"
                "-\n"
                "\n"
                "## 習慣\n"
                "- [ ] 読書\n"
                "- [ ] 運動\n"
                "- [ ] 振り返り\n"
                "\n"
                "## リンク\n"
                "- 関連:\n"
            )
        else:
            # memo (Inbox)
            return (
                "---\n"
                "type: memo\n"
                f"created: {date_str}\n"
                "processed: false\n"
                "tags: []\n"
                "---\n"
                "\n"
                "## メモ\n"
            )

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

    def _try_ai_format(
        self,
        message: MessageData,
        existing_content: str = None,
        content_override: str = None,
    ) -> Optional[str]:
        """
        Try to format message content using AI.

        Args:
            message: Message data to format
            existing_content: Existing Obsidian file content to integrate with
            content_override: If provided, use this instead of message.content

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
            "channel_type": message.channel_type,
        }

        content = content_override if content_override else message.content
        result = self.ai.format_message(content, metadata, existing_content)

        if result:
            if existing_content:
                logger.info("Message integrated with existing content by AI")
            else:
                logger.info("Message formatted by AI")
        else:
            logger.info("AI formatting failed, using fallback")

        return result

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """
        Remove YAML frontmatter from content.

        When appending to an existing daily file, the AI-generated
        frontmatter must be stripped to avoid duplicates.

        Args:
            content: Markdown content possibly starting with frontmatter

        Returns:
            Content without frontmatter
        """
        stripped = content.strip()
        if stripped.startswith("---"):
            # Find the closing ---
            end = stripped.find("---", 3)
            if end != -1:
                body = stripped[end + 3:].strip()
                return body
        return stripped

    @staticmethod
    def _new_kanban_board(card: str) -> str:
        """
        Create a new Kanban board with a single card in Backlog.

        Args:
            card: A kanban card line (e.g. "- [ ] task @{2026-02-04}")

        Returns:
            Complete Kanban board Markdown string
        """
        return (
            "---\n"
            "kanban-plugin: board\n"
            "---\n"
            "\n"
            "## Backlog\n"
            "\n"
            f"{card}\n"
            "\n"
            "## Today\n"
            "\n"
            "## In Progress\n"
            "\n"
            "## Done\n"
            "**Complete**\n"
            "\n"
            "***\n"
            "\n"
            "## Archive\n"
            "\n"
            "%% kanban:settings\n"
            "```json\n"
            '{"kanban-plugin":"board","lane-width":272,"show-checkboxes":true,'
            '"new-card-insertion-method":"append","show-archive-all":true,'
            '"date-format":"YYYY-MM-DD","date-trigger":"@",'
            '"move-dates":true,"move-tags":true}\n'
            "```\n"
            "%%\n"
        )

    @staticmethod
    def _split_todo_items(text: str) -> List[str]:
        """
        Split a casual message into individual kanban card lines.

        Splits on Japanese comma (、), English comma (,), and newlines.
        Each item is trimmed and empty items are discarded.

        Args:
            text: Raw message text from Discord

        Returns:
            List of kanban card lines (e.g. ["- [ ] task1", "- [ ] task2"])
        """
        items = re.split(r"[、,\n]+", text)
        cards = []
        for item in items:
            item = item.strip()
            if item:
                cards.append(f"- [ ] {item}")
        return cards if cards else [f"- [ ] {text.strip()}"]

    @staticmethod
    def _insert_kanban_card(board_content: str, card: str) -> str:
        """
        Insert a new card into the Inbox lane of an existing Kanban board.

        Finds the heading containing "Inbox" and appends the card after
        existing cards in that lane (before the next ## heading).

        Args:
            board_content: Existing Kanban board Markdown
            card: A kanban card line to insert

        Returns:
            Updated board Markdown string
        """
        lines = board_content.split("\n")
        result = []
        inserted = False
        in_inbox = False

        for line in lines:
            stripped = line.strip()

            # Detect Inbox lane (e.g. "## 🧠 Inbox", "## Inbox")
            if stripped.startswith("## ") and "Inbox" in stripped:
                in_inbox = True
                result.append(line)
                continue

            # Detect next lane (end of Inbox)
            if in_inbox and stripped.startswith("## "):
                if not inserted:
                    result.append(card)
                    result.append("")
                    inserted = True
                in_inbox = False

            result.append(line)

        # If Inbox was the last section
        if in_inbox and not inserted:
            result.append(card)

        return "\n".join(result)

    @staticmethod
    def extract_book_title_from_format(content: str) -> Optional[Tuple[str, str]]:
        """
        Extract book title from 【タイトル】 or [タイトル] format at the start.

        Args:
            content: Raw message content

        Returns:
            Tuple of (title, remaining_content) if found, None otherwise
        """
        # Match 【タイトル】 or [タイトル] at the start of the message
        match = re.match(r"^[【\[](.+?)[】\]]\s*", content)
        if match:
            title = match.group(1).strip()
            remaining = content[match.end():].strip()
            return title, remaining
        return None

    def extract_book_title(self, content: str) -> Optional[str]:
        """
        Extract a book title from message content.

        First tries to extract from 【タイトル】 or [タイトル] format.
        Falls back to AI extraction if format not found.

        Args:
            content: Raw message content

        Returns:
            Book title string, or None if extraction failed
        """
        # First try format-based extraction
        result = self.extract_book_title_from_format(content)
        if result:
            title, _ = result
            logger.info(f"Extracted book title from format: {title}")
            return title

        # Fall back to AI extraction
        if not self.ai:
            logger.warning(
                "No book title format found and AI unavailable. "
                "Use 【タイトル】 format to specify the book."
            )
            return None
        if not self.ai.is_available():
            logger.warning(
                "No book title format found and AI unavailable. "
                "Use 【タイトル】 format to specify the book."
            )
            return None

        logger.info("No book title format found, falling back to AI extraction")
        return self.ai.extract_book_title(content)

    def process(
        self,
        message: MessageData,
        existing_content: str = None,
        book_title: str = None,
    ) -> Tuple[str, str, bool]:
        """
        Process a message and return filename and content.

        If AI is configured and available, uses AI to format the content.
        When existing_content is provided, AI integrates the new message
        with existing file content (returning a complete file to overwrite).
        Otherwise falls back to plain Markdown templates.

        For reading channel type, book_title determines the filename
        (e.g. "Clean Code.md") and content is always overwritten.

        For daily (append) mode without existing content, frontmatter is
        stripped from AI output to prevent duplicates.

        Args:
            message: Message data to process
            existing_content: Existing Obsidian file content for AI integration
            book_title: Book title for reading channel (determines filename)

        Returns:
            Tuple of (filename, content, should_append)
            should_append is False when AI successfully integrates existing content
        """
        logger.debug(f"Processing message with template: {self.template}")

        local_time = self._convert_timezone(message.timestamp)

        # Todo channel: fixed filename TODO.md, always overwrite
        if message.channel_type == "todo":
            filename = "TODO.md"

            ai_content = self._try_ai_format(message, existing_content)
            if ai_content:
                return filename, ai_content, False

            # Fallback: split by comma/newline and append as kanban cards to Inbox
            cards = self._split_todo_items(message.content)

            if existing_content:
                content = existing_content
                for card in cards:
                    content = self._insert_kanban_card(content, card)
            else:
                content = self._new_kanban_board("\n".join(cards))

            return filename, content, False

        # Reading channel: filename = book title, always overwrite
        if message.channel_type == "reading" and book_title:
            filename = f"{book_title}.md"

            # Strip title from content if it was specified in 【タイトル】 format
            cleaned_content = message.content
            format_result = self.extract_book_title_from_format(message.content)
            if format_result:
                _, cleaned_content = format_result

            ai_content = self._try_ai_format(
                message, existing_content, content_override=cleaned_content
            )
            if ai_content:
                return filename, ai_content, False

            # Fallback: plain markdown with book title
            _, content = self._process_single(message)
            return filename, content, False

        # Determine filename based on template
        if self.template == "single":
            filename = local_time.strftime("%Y-%m-%d_%H%M%S.md")
            should_append = False
        else:
            filename = local_time.strftime("%Y-%m-%d.md")
            should_append = True

        # Try AI formatting first (with existing content if available)
        ai_content = self._try_ai_format(message, existing_content)

        if ai_content:
            if existing_content:
                # AI integrated existing + new content → overwrite the file
                return filename, ai_content, False
            if should_append:
                # No existing content but append mode → strip frontmatter
                ai_content = self._strip_frontmatter(ai_content)
            return filename, ai_content, should_append

        # Fallback: plain Markdown
        if self.template == "single":
            _, content = self._process_single(message)
        else:
            _, content = self._process_daily(message)

        return filename, content, should_append
