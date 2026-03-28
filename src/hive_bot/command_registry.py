"""Slash command registration and sync infrastructure."""

from __future__ import annotations

import logging
from typing import Any, cast

from hive_bot.commands.ping import build_ping_command
from hive_bot.commands.server import build_server_group

LOGGER = logging.getLogger(__name__)


def register_commands(tree: Any, *, app_commands_module: Any, pterodactyl_bridge: Any) -> None:
    """Register the milestone slash commands on a command tree."""

    tree.add_command(build_ping_command(app_commands_module=app_commands_module), override=True)
    tree.add_command(
        build_server_group(app_commands_module=app_commands_module, bridge=pterodactyl_bridge),
        override=True,
    )


async def sync_commands(tree: Any, *, guild: Any) -> list[Any]:
    """Copy global commands into the target guild and sync them."""

    guild_identifier = getattr(guild, "id", repr(guild))

    try:
        tree.copy_global_to(guild=guild)
        synced_commands = cast(list[Any], await tree.sync(guild=guild))
    except Exception:
        LOGGER.exception("Failed to register commands to guild %s", guild_identifier)
        raise

    LOGGER.info("Synced %s commands to guild %s", len(synced_commands), guild_identifier)
    return synced_commands
