"""Abstract base classes for input, output, and AI adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Awaitable, Optional, Tuple


@dataclass
class MessageData:
    """Common message format for all input adapters."""

    content: str
    author: str
    timestamp: datetime
    channel: str
    attachments: List[str]
    channel_type: str = "memo"


class BaseInputAdapter(ABC):
    """Abstract base class for input adapters."""

    @abstractmethod
    def __init__(
        self,
        config: dict,
        on_message_callback: Callable[[MessageData], Awaitable[Tuple[bool, Optional[str]]]],
    ):
        """
        Initialize the input adapter.

        Args:
            config: Configuration dictionary for this adapter
            on_message_callback: Async callback to handle received messages.
                                Returns (success, formatted_content) tuple.
        """
        pass

    @abstractmethod
    async def run(self) -> None:
        """Start the message monitoring loop."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the message monitoring loop."""
        pass


class BaseOutputAdapter(ABC):
    """Abstract base class for output adapters."""

    @abstractmethod
    def __init__(self, config: dict):
        """
        Initialize the output adapter.

        Args:
            config: Configuration dictionary for this adapter
        """
        pass

    @abstractmethod
    def save(self, filename: str, content: str, append: bool = False) -> bool:
        """
        Save content to the destination.

        Args:
            filename: Name of the file to save
            content: Content to save
            append: If True, append to existing file; otherwise overwrite

        Returns:
            True if save was successful, False otherwise
        """
        pass


class BaseAIAdapter(ABC):
    """Abstract base class for AI adapters."""

    @abstractmethod
    def __init__(self, config: dict):
        """
        Initialize the AI adapter.

        Args:
            config: Configuration dictionary for this adapter
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the AI service is reachable.

        Returns:
            True if the service is available
        """
        pass

    @abstractmethod
    def format_message(
        self,
        content: str,
        metadata: dict,
        existing_content: str = None,
    ) -> Optional[str]:
        """
        Format a message using AI.

        Args:
            content: Raw message content
            metadata: Message metadata (timestamp, author, channel, etc.)
            existing_content: Existing Obsidian file content to integrate with

        Returns:
            Formatted content string, or None if formatting failed
        """
        pass

    @abstractmethod
    def extract_book_title(self, content: str) -> Optional[str]:
        """
        Extract a book title from message content.

        Args:
            content: Raw message content mentioning a book

        Returns:
            Book title string, or None if extraction failed
        """
        pass
