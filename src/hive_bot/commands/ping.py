"""Implementation of the `/ping` slash command."""

from __future__ import annotations

from typing import Any


async def handle_ping(interaction: Any) -> None:
    """Respond to the `/ping` slash command."""

    await interaction.response.send_message("pong")


def build_ping_command(*, app_commands_module: Any) -> Any:
    """Create the `/ping` slash command object."""

    @app_commands_module.command(  # type: ignore[untyped-decorator]
        name="ping",
        description="Respond with pong",
    )
    async def ping_command(interaction: Any) -> None:
        await handle_ping(interaction)

    return ping_command
