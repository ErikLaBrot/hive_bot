"""Discord client construction and startup helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

import discord
from discord.ext import commands

from hive_bot.command_registry import register_commands, sync_commands
from hive_bot.config import AppConfig
from hive_bot.pterodactyl import PterodactylBridge

LOGGER = logging.getLogger(__name__)


def create_bot(
    config: AppConfig,
    *,
    discord_module: Any = discord,
    commands_module: Any = commands,
    register_commands_func: Callable[..., None] = register_commands,
    sync_commands_func: Callable[..., Any] = sync_commands,
    pterodactyl_bridge_factory: Callable[..., Any] = PterodactylBridge,
) -> Any:
    """Construct the Discord bot and attach milestone startup hooks."""

    # Bridge construction is pure dependency wiring; all panel I/O remains in
    # command-time bridge methods.
    pterodactyl_bridge = pterodactyl_bridge_factory(config.pterodactyl, config.policy)

    async def setup_hook(self: Any) -> None:
        register_commands_func(
            self.tree,
            app_commands_module=discord_module.app_commands,
            pterodactyl_bridge=pterodactyl_bridge,
        )
        guild = discord_module.Object(id=config.discord.guild_id)
        await sync_commands_func(self.tree, guild=guild)

    async def on_ready(bot_instance: Any) -> None:
        user = bot_instance.user
        if user is None:
            LOGGER.warning("Discord client ready event fired before bot user was available")
            return

        LOGGER.info("Discord client ready as %s (%s)", user, user.id)

    hive_bot_class = cast(
        type[Any],
        type("HiveBot", (commands_module.Bot,), {"setup_hook": setup_hook}),
    )

    bot = hive_bot_class(
        command_prefix=commands_module.when_mentioned,
        intents=discord_module.Intents.default(),
    )
    bot.add_listener(lambda: on_ready(bot), "on_ready")
    return bot


def run_bot(config: AppConfig, *, bot_factory: Callable[[AppConfig], Any] = create_bot) -> None:
    """Start the Discord client with the configured token."""

    bot = bot_factory(config)
    # Logging is configured centrally during application bootstrap.
    bot.run(config.discord.token, log_handler=None)
