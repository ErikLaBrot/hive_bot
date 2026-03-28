"""Implementation of the read-only `/server` slash commands."""

from __future__ import annotations

from typing import Any, Protocol

from hive_bot.pterodactyl import (
    AmbiguousServerMatch,
    BudgetResult,
    BudgetStatus,
    DiscoveredServer,
    DiscoverServersResult,
    PanelUnavailable,
    ServerNotFound,
    ServerStatus,
    ServerStatusResult,
)


class ReadOnlyServerBridge(Protocol):
    """Subset of bridge operations used by the read-only `/server` commands."""

    async def discover_servers(self) -> DiscoverServersResult:
        """Return the currently discoverable servers."""

    async def get_server_status(self, query: str) -> ServerStatusResult:
        """Return status for a discoverable server."""

    async def get_budget_status(self) -> BudgetResult:
        """Return the current policy budget summary."""


async def handle_server_list(interaction: Any, *, bridge: ReadOnlyServerBridge) -> None:
    """Respond to `/server list`."""

    result = await bridge.discover_servers()
    await interaction.response.send_message(_format_discover_servers_result(result))


async def handle_server_status(
    interaction: Any,
    *,
    bridge: ReadOnlyServerBridge,
    server: str,
) -> None:
    """Respond to `/server status`."""

    result = await bridge.get_server_status(server)
    await interaction.response.send_message(_format_server_status_result(result))


async def handle_server_budget(interaction: Any, *, bridge: ReadOnlyServerBridge) -> None:
    """Respond to `/server budget`."""

    result = await bridge.get_budget_status()
    await interaction.response.send_message(_format_budget_result(result))


async def handle_server_help(interaction: Any) -> None:
    """Respond to `/server help`."""

    await interaction.response.send_message(_build_help_message())


def build_server_group(*, app_commands_module: Any, bridge: ReadOnlyServerBridge) -> Any:
    """Create the `/server` slash command group."""

    group = app_commands_module.Group(
        name="server",
        description="Read-only Pterodactyl server commands",
    )

    @group.command(  # type: ignore[untyped-decorator]
        name="list",
        description="List discoverable Pterodactyl servers",
    )
    async def list_command(interaction: Any) -> None:
        await handle_server_list(interaction, bridge=bridge)

    @group.command(  # type: ignore[untyped-decorator]
        name="status",
        description="Show status for one discoverable server",
    )
    async def status_command(interaction: Any, server: str) -> None:
        await handle_server_status(interaction, bridge=bridge, server=server)

    @group.command(  # type: ignore[untyped-decorator]
        name="budget",
        description="Show current policy headroom",
    )
    async def budget_command(interaction: Any) -> None:
        await handle_server_budget(interaction, bridge=bridge)

    @group.command(  # type: ignore[untyped-decorator]
        name="help",
        description="Show the available /server commands",
    )
    async def help_command(interaction: Any) -> None:
        await handle_server_help(interaction)

    return group


def _format_discover_servers_result(result: DiscoverServersResult) -> str:
    if isinstance(result, PanelUnavailable):
        return result.message
    if not result.servers:
        return "No Pterodactyl servers are currently discoverable by the bot."

    lines = ["Discoverable Pterodactyl servers:"]
    lines.extend(_format_server_summary_line(server) for server in result.servers)
    return "\n".join(lines)


def _format_server_status_result(result: ServerStatusResult) -> str:
    if isinstance(result, PanelUnavailable):
        return result.message
    if isinstance(result, ServerNotFound):
        return f"No discoverable server matched `{result.query}`."
    if isinstance(result, AmbiguousServerMatch):
        return _format_ambiguous_match_message(result)
    if isinstance(result, ServerStatus):
        return _format_server_status_message(result.server)

    message = f"Unsupported server status result: {type(result)!r}"
    raise AssertionError(message)


def _format_budget_result(result: BudgetResult) -> str:
    if isinstance(result, PanelUnavailable):
        return result.message
    if isinstance(result, BudgetStatus):
        return _format_budget_status_message(result)

    message = f"Unsupported budget result: {type(result)!r}"
    raise AssertionError(message)


def _format_server_summary_line(server: DiscoveredServer) -> str:
    state = server.state if server.state is not None else "unknown"
    memory_limit = _format_memory_limit(server.memory_limit_mib)
    return f"- {server.name} (`{server.identifier}`): {state}; RAM limit {memory_limit}"


def _format_server_status_message(server: DiscoveredServer) -> str:
    lines = [
        f"Server status for {server.name} (`{server.identifier}`):",
        f"State: {server.state if server.state is not None else 'unknown'}",
        f"RAM limit: {_format_memory_limit(server.memory_limit_mib)}",
    ]
    return "\n".join(lines)


def _format_budget_status_message(result: BudgetStatus) -> str:
    lines = [
        "Server budget status:",
        f"- Max running servers: {result.max_running_servers}",
        f"- Max RAM budget: {result.max_total_ram_gb} GiB",
        f"- Currently running: {result.running_server_count}",
    ]

    if result.consumed_memory_mib is None or result.remaining_memory_mib is None:
        lines.append("- Consumed RAM limit: unavailable (missing memory limits)")
        lines.append("- Remaining RAM headroom: unavailable")
        missing = ", ".join(
            f"{server.name} (`{server.identifier}`)"
            for server in result.missing_memory_limit_servers
        )
        lines.append(f"- Missing RAM limit data for: {missing}")
    else:
        lines.append(f"- Consumed RAM limit: {result.consumed_memory_mib} MiB")
        if result.remaining_memory_mib < 0:
            headroom = result.remaining_memory_mib
            lines.append(f"- Remaining RAM headroom: {headroom} MiB (over budget)")
        else:
            lines.append(f"- Remaining RAM headroom: {result.remaining_memory_mib} MiB")

    if result.running_servers:
        running = ", ".join(
            f"{server.name} (`{server.identifier}`)" for server in result.running_servers
        )
        lines.append(f"- Running servers: {running}")
    else:
        lines.append("- Running servers: none")

    return "\n".join(lines)


def _format_ambiguous_match_message(result: AmbiguousServerMatch) -> str:
    matches = ", ".join(f"{server.name} (`{server.identifier}`)" for server in result.matches)
    return f"Multiple discoverable servers matched `{result.query}`: {matches}"


def _format_memory_limit(memory_limit_mib: int | None) -> str:
    if memory_limit_mib is None:
        return "unknown"
    return f"{memory_limit_mib} MiB"


def _build_help_message() -> str:
    return "\n".join(
        [
            "Available /server commands:",
            "- `/server list`: List discoverable Pterodactyl servers.",
            "- `/server status <server>`: Show status for one discoverable server.",
            "- `/server budget`: Show policy budget and current headroom.",
            "- `/server help`: Show this help message.",
        ]
    )
