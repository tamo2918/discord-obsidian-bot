"""Discord input adapter for receiving messages."""
import io
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable, List, Optional, Tuple

import discord
from discord import Intents, app_commands

from adapters.base import BaseInputAdapter, MessageData

# Discord message character limit (leave room for code block markers)
_DISCORD_MAX_INLINE_LENGTH = 1800


async def _send_formatted_content(
    send_func,
    content: str,
    filename: str = "formatted.md",
) -> None:
    """Send formatted markdown content to Discord.

    Uses an inline code block for short content, or a file attachment
    when the content exceeds Discord's character limit.

    Args:
        send_func: Async callable (e.g. message.reply or interaction.followup.send)
        content: Formatted markdown content to send
        filename: Filename to use when sending as a file attachment
    """
    if len(content) <= _DISCORD_MAX_INLINE_LENGTH:
        await send_func(f"```md\n{content}\n```")
    else:
        file = discord.File(
            io.BytesIO(content.encode("utf-8")),
            filename=filename,
        )
        await send_func(file=file)

logger = logging.getLogger(__name__)

# Slash command definitions: (name, description, label for response)
_SLASH_COMMANDS = [
    ("diary", "日記をObsidianに保存", "日記"),
    ("reading", "読書メモをObsidianに保存", "読書メモ"),
    ("todo", "タスクをObsidianに保存", "タスク"),
    ("glossary", "用語集に追加", "用語集"),
    ("youtube", "YouTube文字起こしノートを作成", "YouTubeノート"),
]


class DiscordInput(BaseInputAdapter):
    """Discord input adapter that monitors specified channels for messages."""

    def __init__(
        self,
        config: dict,
        on_message_callback: Callable[[MessageData], Awaitable[Tuple[bool, Optional[str]]]],
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
        self.tree = app_commands.CommandTree(self.client)
        self._setup_event_handlers()
        self._setup_slash_commands()

    def _setup_event_handlers(self) -> None:
        """Set up Discord event handlers."""

        @self.client.event
        async def on_ready():
            await self.tree.sync()
            logger.info(f"Discord bot logged in as {self.client.user}")
            logger.info(f"Monitoring channels: {self.channels}")
            logger.info("Slash commands synced")

        @self.client.event
        async def on_message(message: discord.Message):
            await self._handle_message(message)

    def _setup_slash_commands(self) -> None:
        """Register slash commands for all channel types."""

        for cmd_name, cmd_desc, cmd_label in _SLASH_COMMANDS:
            self._register_slash_command(cmd_name, cmd_desc, cmd_label)

    def _register_slash_command(
        self, name: str, description: str, label: str
    ) -> None:
        """Register a single slash command."""

        @self.tree.command(name=name, description=description)
        @app_commands.describe(
            content="保存する内容",
            attachment="添付ファイル（画像など）",
        )
        async def slash_handler(
            interaction: discord.Interaction,
            content: str,
            attachment: Optional[discord.Attachment] = None,
            _name: str = name,
            _label: str = label,
        ):
            await self._handle_slash_command(
                interaction, content, _name, _label, attachment
            )

    async def _handle_slash_command(
        self,
        interaction: discord.Interaction,
        content: str,
        channel_type: str,
        label: str,
        attachment: Optional[discord.Attachment],
    ) -> None:
        """Handle a slash command interaction."""
        await interaction.response.defer()

        logger.info(
            f"Slash command /{channel_type} from {interaction.user.name}: "
            f"{content[:50]}..."
        )

        attachments = [attachment.url] if attachment else []
        channel_name = (
            interaction.channel.name
            if interaction.channel and hasattr(interaction.channel, "name")
            else "slash-command"
        )

        message_data = MessageData(
            content=content,
            author=interaction.user.display_name,
            timestamp=interaction.created_at or datetime.now(timezone.utc),
            channel=channel_name,
            attachments=attachments,
            channel_type=channel_type,
        )

        try:
            success, formatted_content = await self.on_message_callback(message_data)
            if success:
                await interaction.followup.send(f"✅ {label}を保存しました")
                if formatted_content:
                    await _send_formatted_content(
                        interaction.followup.send,
                        formatted_content,
                        filename=f"{channel_type}.md",
                    )
            else:
                await interaction.followup.send(f"❌ {label}の保存に失敗しました")
        except Exception as e:
            logger.error(f"Error processing slash command /{channel_type}: {e}")
            try:
                await interaction.followup.send(f"❌ エラーが発生しました: {e}")
            except Exception:
                pass

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
            success, formatted_content = await self.on_message_callback(message_data)

            # Add reaction based on result
            if success:
                await message.add_reaction("✅")
                logger.info("Message processed successfully")
                if formatted_content:
                    try:
                        await _send_formatted_content(
                            message.reply,
                            formatted_content,
                            filename=f"{channel_type}.md",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send formatted content reply: {e}")
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
