"""Abstract base classes for input and output adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Awaitable


@dataclass
class MessageData:
    """Common message format for all input adapters."""

    content: str
    author: str
    timestamp: datetime
    channel: str
    attachments: List[str]


class BaseInputAdapter(ABC):
    """Abstract base class for input adapters."""

    @abstractmethod
    def __init__(
        self,
        config: dict,
        on_message_callback: Callable[[MessageData], Awaitable[bool]],
    ):
        """
        Initialize the input adapter.

        Args:
            config: Configuration dictionary for this adapter
            on_message_callback: Async callback to handle received messages.
                                Returns True if message was processed successfully.
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
