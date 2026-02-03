"""Discord input adapter for receiving messages."""
import logging
from typing import Callable, Awaitable, List

import discord
from discord import Intents

from adapters.base import BaseInputAdapter, MessageData

logger = logging.getLogger(__name__)


class DiscordInput(BaseInputAdapter):
    """Discord input adapter that monitors specified channels for messages."""

    def __init__(
        self,
        config: dict,
        on_message_callback: Callable[[MessageData], Awaitable[bool]],
    ):
        """
        Initialize the Discord input adapter.

        Args:
            config: Discord configuration containing token and channel_map
            on_message_callback: Async callback to handle received messages
        """
        self.token = config["token"]
        self.on_message_callback = on_message_callback

        # channel_map: {"channel_id": "type"} e.g. {"123": "memo", "456": "diary"}
        # Backward compatible: "channels" list is treated as memo type
        if "channel_map" in config:
            self.channel_map: dict = config["channel_map"]
        else:
            self.channel_map = {ch: "memo" for ch in config.get("channels", [])}

        self.channels: List[str] = list(self.channel_map.keys())

        # Set up intents
        intents = Intents.default()
        intents.message_content = True
        intents.guild_messages = True

        self.client = discord.Client(intents=intents)
        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Set up Discord event handlers."""

        @self.client.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.client.user}")
            logger.info(f"Monitoring channels: {self.channels}")

        @self.client.event
        async def on_message(message: discord.Message):
            await self._handle_message(message)

    async def _handle_message(self, message: discord.Message) -> None:
        """
        Handle incoming Discord message.

        Args:
            message: Discord message object
        """
        # Ignore messages from bots
        if message.author.bot:
            return

        # Check if message is from monitored channel
        if str(message.channel.id) not in self.channels:
            return

        logger.info(
            f"Received message from {message.author.name} "
            f"in #{message.channel.name}: {message.content[:50]}..."
        )

        # Determine channel type from map
        channel_type = self.channel_map.get(str(message.channel.id), "memo")

        # Extract message data
        message_data = MessageData(
            content=message.content,
            author=message.author.display_name,
            timestamp=message.created_at,
            channel=message.channel.name,
            attachments=[att.url for att in message.attachments],
            channel_type=channel_type,
        )

        try:
            # Process message through callback
            success = await self.on_message_callback(message_data)

            # Add reaction based on result
            if success:
                await message.add_reaction("✅")
                logger.info("Message processed successfully")
            else:
                await message.add_reaction("❌")
                logger.warning("Message processing failed")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            try:
                await message.add_reaction("❌")
            except Exception:
                pass

    async def run(self) -> None:
        """Start the Discord bot."""
        logger.info("Starting Discord bot...")
        await self.client.start(self.token)

    async def stop(self) -> None:
        """Stop the Discord bot."""
        logger.info("Stopping Discord bot...")
        await self.client.close()
