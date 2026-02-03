"""Main entry point for Discord-Obsidian Bot."""
import asyncio
import logging
import os
import re
import sys
from typing import Any, Dict

import yaml

from adapters.base import MessageData
from adapters.inputs.discord_input import DiscordInput
from adapters.outputs.github_output import GitHubOutput
from processor import MessageProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
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


class Bot:
    """Main bot class that coordinates input, processing, and output."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the bot.

        Args:
            config: Configuration dictionary
        """
        self.config = config

        # Initialize processor
        self.processor = MessageProcessor(config.get("processor", {}))

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

        Args:
            message: Message data from input adapter

        Returns:
            True if message was processed successfully
        """
        try:
            # Process message
            filename, content, append = self.processor.process(message)

            logger.info(f"Saving to {filename} (append={append})")

            # Save to output
            success = self.output.save(filename, content, append=append)

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
    # Get config path from environment or use default
    config_path = os.environ.get("CONFIG_PATH", "/app/config.yaml")

    # For local development, check current directory
    if not os.path.exists(config_path):
        local_config = "config.yaml"
        if os.path.exists(local_config):
            config_path = local_config
        else:
            logger.error(f"Configuration file not found: {config_path}")
            sys.exit(1)

    logger.info(f"Loading configuration from {config_path}")
    config = load_config(config_path)

    # Validate required configuration
    if not config.get("discord", {}).get("token"):
        logger.error("Discord token is required")
        sys.exit(1)

    if not config.get("github", {}).get("token"):
        logger.error("GitHub token is required")
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
