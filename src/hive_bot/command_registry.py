"""Slash command registration and sync infrastructure."""

from __future__ import annotations

import logging
from typing import Any, cast

from hive_bot.commands.ping import build_ping_command

LOGGER = logging.getLogger(__name__)


def register_commands(tree: Any, *, app_commands_module: Any) -> None:
    """Register the milestone slash commands on a command tree."""

    tree.add_command(build_ping_command(app_commands_module=app_commands_module), override=True)


async def sync_commands(tree: Any, *, guild: Any) -> list[Any]:
    """Copy global commands into the target guild and sync them."""

    tree.copy_global_to(guild=guild)
    try:
        synced_commands = cast(list[Any], await tree.sync(guild=guild))
    except Exception:
        LOGGER.exception("Failed to sync commands to guild %s", guild.id)
        raise

    LOGGER.info("Synced %s commands to guild %s", len(synced_commands), guild.id)
    return synced_commands
