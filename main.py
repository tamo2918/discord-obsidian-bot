"""Main entry point for Discord-Obsidian Bot."""
import asyncio
import logging
import os
import re
import sys
from typing import Any, Dict, Optional

import yaml

from adapters.base import BaseAIAdapter, MessageData
from adapters.inputs.discord_input import DiscordInput
from adapters.outputs.github_output import GitHubOutput
from processor import MessageProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_config_from_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Environment variables in the format ${VAR_NAME} are replaced
    with their values.

    Args:
        config_path: Path to the configuration file

    Returns:
        Configuration dictionary
    """
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace environment variables
    def replace_env_var(match):
        var_name = match.group(1)
        value = os.environ.get(var_name, "")
        if not value:
            logger.warning(f"Environment variable {var_name} is not set")
        return value

    content = re.sub(r"\$\{(\w+)\}", replace_env_var, content)

    return yaml.safe_load(content)


def _parse_channels(env_value: str) -> list:
    """Parse comma-separated channel IDs into a list."""
    return [ch.strip() for ch in env_value.split(",") if ch.strip()]


def load_config_from_env() -> Dict[str, Any]:
    """
    Load configuration from environment variables.

    Channel configuration (at least one required):
        - CHANNEL_MEMO: Comma-separated memo channel IDs
        - CHANNEL_DIARY: Comma-separated diary channel IDs
        - CHANNEL_READING: Comma-separated reading channel IDs
        - DISCORD_CHANNELS: (Backward compat) treated as memo channels

    Path configuration:
        - GITHUB_PATH_MEMO: Save path for memos (default: Inbox)
        - GITHUB_PATH_DIARY: Save path for diary (default: Diary)
        - GITHUB_PATH_READING: Save path for reading notes (default: Reading)

    Returns:
        Configuration dictionary
    """
    # Build channel_map: {channel_id: type}
    channel_map: Dict[str, str] = {}

    # Memo channels (CHANNEL_MEMO or fallback to DISCORD_CHANNELS)
    memo_channels = _parse_channels(os.environ.get("CHANNEL_MEMO", ""))
    if not memo_channels:
        memo_channels = _parse_channels(os.environ.get("DISCORD_CHANNELS", ""))
    for ch in memo_channels:
        channel_map[ch] = "memo"

    # Diary channels
    diary_channels = _parse_channels(os.environ.get("CHANNEL_DIARY", ""))
    for ch in diary_channels:
        channel_map[ch] = "diary"

    # Reading channels
    reading_channels = _parse_channels(os.environ.get("CHANNEL_READING", ""))
    for ch in reading_channels:
        channel_map[ch] = "reading"

    # Path map: channel_type -> save path
    path_map = {
        "memo": os.environ.get(
            "GITHUB_PATH_MEMO", os.environ.get("GITHUB_PATH", "Inbox")
        ),
        "diary": os.environ.get("GITHUB_PATH_DIARY", "Diary"),
        "reading": os.environ.get("GITHUB_PATH_READING", "Reading"),
    }

    config = {
        "discord": {
            "token": os.environ.get("DISCORD_TOKEN", ""),
            "channel_map": channel_map,
        },
        "github": {
            "token": os.environ.get("GITHUB_TOKEN", ""),
            "repo": os.environ.get("GITHUB_REPO", ""),
            "branch": os.environ.get("GITHUB_BRANCH", "main"),
            "path": os.environ.get("GITHUB_PATH", "Inbox"),
        },
        "path_map": path_map,
        "processor": {
            "timezone": os.environ.get("PROCESSOR_TIMEZONE", "Asia/Tokyo"),
            "template": os.environ.get("PROCESSOR_TEMPLATE", "daily"),
        },
        "ai": {
            "enabled": os.environ.get("AI_ENABLED", "false").lower() == "true",
            "provider": os.environ.get("AI_PROVIDER", "ollama"),
            "base_url": os.environ.get("AI_BASE_URL", "http://localhost:11434"),
            "model": os.environ.get("AI_MODEL", "gemma2"),
            "api_key": os.environ.get("AI_API_KEY", ""),
            "timeout": os.environ.get("AI_TIMEOUT", "60"),
        },
    }

    return config


def load_config() -> Dict[str, Any]:
    """
    Load configuration from file or environment variables.

    First tries to load from config.yaml file, then falls back to
    environment variables if the file is not found.

    Returns:
        Configuration dictionary
    """
    # Check for config file
    config_path = os.environ.get("CONFIG_PATH", "/app/config.yaml")

    # For local development, check current directory
    if not os.path.exists(config_path):
        local_config = "config.yaml"
        if os.path.exists(local_config):
            config_path = local_config

    # Try to load from file first
    if os.path.exists(config_path):
        logger.info(f"Loading configuration from {config_path}")
        return load_config_from_file(config_path)

    # Fall back to environment variables
    logger.info("Config file not found, loading from environment variables")
    return load_config_from_env()


def create_ai_adapter(config: Dict[str, Any]) -> Optional[BaseAIAdapter]:
    """
    Create an AI adapter based on configuration.

    Args:
        config: AI configuration dictionary

    Returns:
        AI adapter instance, or None if AI is disabled
    """
    if not config.get("enabled", False):
        logger.info("AI formatting is disabled")
        return None

    provider = config.get("provider", "ollama")

    if provider == "ollama":
        from adapters.ai.ollama_ai import OllamaAI
        adapter = OllamaAI(config)
        logger.info(
            f"AI adapter: Ollama (url={config.get('base_url')}, "
            f"model={config.get('model')})"
        )
    elif provider == "openai":
        from adapters.ai.openai_ai import OpenAICompatibleAI
        adapter = OpenAICompatibleAI(config)
        logger.info(
            f"AI adapter: OpenAI-compatible (url={config.get('base_url')}, "
            f"model={config.get('model')})"
        )
    else:
        logger.warning(f"Unknown AI provider '{provider}', AI disabled")
        return None

    return adapter


class Bot:
    """Main bot class that coordinates input, processing, and output."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the bot.

        Args:
            config: Configuration dictionary
        """
        self.config = config

        # Path map: channel_type -> save path (e.g. {"memo": "Inbox", "diary": "Diary"})
        self.path_map = config.get("path_map", {"memo": "Inbox"})

        # Initialize AI adapter (optional)
        ai_adapter = create_ai_adapter(config.get("ai", {}))

        # Initialize processor (with optional AI)
        self.processor = MessageProcessor(config.get("processor", {}), ai_adapter)

        # Initialize output adapter
        self.output = GitHubOutput(config["github"])

        # Initialize input adapter
        self.input = DiscordInput(
            config["discord"],
            on_message_callback=self._handle_message,
        )

    async def _handle_message(self, message: MessageData) -> bool:
        """
        Handle incoming message.

        Routes to the correct save path based on channel type.
        Fetches existing file content from GitHub so AI can integrate
        new messages with existing notes.

        For reading channels, extracts the book title first to determine
        the filename, then fetches existing book note for integration.

        Args:
            message: Message data from input adapter

        Returns:
            True if message was processed successfully
        """
        try:
            # Determine save path based on channel type
            save_path = self.path_map.get(message.channel_type, "Inbox")

            book_title = None
            existing_content = None

            if message.channel_type == "reading":
                # Reading channel: extract book title → use as filename
                book_title = self.processor.extract_book_title(message.content)

                if book_title:
                    filename_hint = f"{book_title}.md"
                    existing_content = self.output.get_existing_content(
                        filename_hint, base_path=save_path
                    )
                    if existing_content:
                        logger.info(
                            f"Found existing book note {save_path}/{filename_hint}, "
                            "passing to AI for integration"
                        )
                else:
                    logger.warning(
                        "Could not extract book title, "
                        "falling back to date-based filename"
                    )
            else:
                # Memo/Diary: date-based filename
                local_time = self.processor._convert_timezone(message.timestamp)
                if self.processor.template == "single":
                    filename_hint = local_time.strftime("%Y-%m-%d_%H%M%S.md")
                else:
                    filename_hint = local_time.strftime("%Y-%m-%d.md")

                existing_content = self.output.get_existing_content(
                    filename_hint, base_path=save_path
                )
                if existing_content:
                    logger.info(
                        f"Found existing file {save_path}/{filename_hint}, "
                        "passing to AI for integration"
                    )

            # Process message
            filename, content, append = self.processor.process(
                message,
                existing_content=existing_content,
                book_title=book_title,
            )

            logger.info(
                f"Saving to {save_path}/{filename} "
                f"(type={message.channel_type}, append={append})"
            )

            # Save to output
            success = self.output.save(
                filename, content, append=append, base_path=save_path
            )

            return success
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return False

    async def run(self) -> None:
        """Run the bot."""
        logger.info("Starting Discord-Obsidian Bot...")
        await self.input.run()

    async def stop(self) -> None:
        """Stop the bot."""
        logger.info("Stopping Discord-Obsidian Bot...")
        await self.input.stop()


async def main():
    """Main entry point."""
    # Load configuration (from file or environment variables)
    config = load_config()

    # Validate required configuration
    if not config.get("discord", {}).get("token"):
        logger.error("Discord token is required (set DISCORD_TOKEN)")
        sys.exit(1)

    # Check for channels (either channel_map or channels list)
    discord_cfg = config.get("discord", {})
    has_channels = (
        discord_cfg.get("channel_map")
        or discord_cfg.get("channels")
    )
    if not has_channels:
        logger.error(
            "Discord channels are required "
            "(set CHANNEL_MEMO, CHANNEL_DIARY, CHANNEL_READING, "
            "or DISCORD_CHANNELS)"
        )
        sys.exit(1)

    if not config.get("github", {}).get("token"):
        logger.error("GitHub token is required (set GITHUB_TOKEN)")
        sys.exit(1)

    if not config.get("github", {}).get("repo"):
        logger.error("GitHub repo is required (set GITHUB_REPO)")
        sys.exit(1)

    # Create and run bot
    bot = Bot(config)

    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
