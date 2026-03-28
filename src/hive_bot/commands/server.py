"""Implementation of the `/server` slash commands."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from hive_bot.pterodactyl import (
    ActionResult,
    AmbiguousServerMatch,
    BudgetResult,
    BudgetStatus,
    DiscoveredServer,
    DiscoveredServers,
    DiscoverServersResult,
    PanelUnavailable,
    ServerActionAccepted,
    ServerActionDenied,
    ServerActionNoOp,
    ServerNotFound,
    ServerStatus,
    ServerStatusResult,
)

LOGGER = logging.getLogger(__name__)


class ServerCommandBridge(Protocol):
    """Subset of bridge operations used by the `/server` commands."""

    async def discover_servers(self) -> DiscoverServersResult:
        """Return the currently discoverable servers."""

    async def get_server_status(self, query: str) -> ServerStatusResult:
        """Return status for a discoverable server."""

    async def get_budget_status(self) -> BudgetResult:
        """Return the current policy budget summary."""

    async def start_server(self, query: str) -> ActionResult:
        """Attempt to start a discoverable server."""

    async def stop_server(self, query: str) -> ActionResult:
        """Attempt to stop a discoverable server."""

    async def restart_server(self, query: str) -> ActionResult:
        """Attempt to restart a discoverable server."""


async def handle_server_list(interaction: Any, *, bridge: ServerCommandBridge) -> None:
    """Respond to `/server list`."""

    result = await bridge.discover_servers()
    await interaction.response.send_message(_format_discover_servers_result(result))


async def handle_server_status(
    interaction: Any,
    *,
    bridge: ServerCommandBridge,
    server: str,
) -> None:
    """Respond to `/server status`."""

    result = await bridge.get_server_status(server)
    await interaction.response.send_message(_format_server_status_result(result))


async def handle_server_budget(interaction: Any, *, bridge: ServerCommandBridge) -> None:
    """Respond to `/server budget`."""

    result = await bridge.get_budget_status()
    await interaction.response.send_message(_format_budget_result(result))


async def handle_server_help(interaction: Any) -> None:
    """Respond to `/server help`."""

    await interaction.response.send_message(_build_help_message())


async def handle_server_start(
    interaction: Any,
    *,
    bridge: ServerCommandBridge,
    server: str,
) -> None:
    """Respond to `/server start`."""

    result = await bridge.start_server(server)
    _audit_action_result(interaction, action="start", query=server, result=result)
    await interaction.response.send_message(_format_action_result(result))


async def handle_server_stop(
    interaction: Any,
    *,
    bridge: ServerCommandBridge,
    server: str,
) -> None:
    """Respond to `/server stop`."""

    result = await bridge.stop_server(server)
    _audit_action_result(interaction, action="stop", query=server, result=result)
    await interaction.response.send_message(_format_action_result(result))


async def handle_server_restart(
    interaction: Any,
    *,
    bridge: ServerCommandBridge,
    server: str,
) -> None:
    """Respond to `/server restart`."""

    result = await bridge.restart_server(server)
    _audit_action_result(interaction, action="restart", query=server, result=result)
    await interaction.response.send_message(_format_action_result(result))


def build_server_group(*, app_commands_module: Any, bridge: ServerCommandBridge) -> Any:
    """Create the `/server` slash command group."""

    group = app_commands_module.Group(
        name="server",
        description="Pterodactyl server commands",
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
        name="start",
        description="Start one discoverable server",
    )
    async def start_command(interaction: Any, server: str) -> None:
        await handle_server_start(interaction, bridge=bridge, server=server)

    @group.command(  # type: ignore[untyped-decorator]
        name="stop",
        description="Stop one discoverable server",
    )
    async def stop_command(interaction: Any, server: str) -> None:
        await handle_server_stop(interaction, bridge=bridge, server=server)

    @group.command(  # type: ignore[untyped-decorator]
        name="restart",
        description="Restart one discoverable server",
    )
    async def restart_command(interaction: Any, server: str) -> None:
        await handle_server_restart(interaction, bridge=bridge, server=server)

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
    if not isinstance(result, DiscoveredServers):
        message = f"Unsupported discover servers result: {type(result)!r}"
        raise AssertionError(message)
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


def _format_action_result(result: ActionResult) -> str:
    if isinstance(result, PanelUnavailable):
        return result.message
    if isinstance(result, ServerNotFound):
        return f"No discoverable server matched `{result.query}`."
    if isinstance(result, AmbiguousServerMatch):
        return _format_ambiguous_match_message(result)
    if isinstance(result, ServerActionAccepted):
        return _format_action_success_message(result)
    if isinstance(result, ServerActionNoOp):
        return _format_action_no_op_message(result)
    if isinstance(result, ServerActionDenied):
        return _format_action_denied_message(result)

    message = f"Unsupported action result: {type(result)!r}"
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
        # The config key remains `max_total_ram_gb`, but the bridge and policy
        # calculations intentionally treat that value as binary GiB.
        f"- Max RAM budget: {result.max_total_ram_gb} GiB",
        f"- Currently running: {result.running_server_count}",
    ]

    if result.consumed_memory_mib is None or result.remaining_memory_mib is None:
        lines.append("- Consumed RAM limit: unavailable (missing memory limits)")
        lines.append("- Remaining RAM headroom: unavailable")
        if result.missing_memory_limit_servers:
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


def _format_action_success_message(result: ServerActionAccepted) -> str:
    label = _format_server_label(result.server)
    return f"{result.action.capitalize()} request accepted for {label}."


def _format_action_no_op_message(result: ServerActionNoOp) -> str:
    label = _format_server_label(result.server)
    if result.reason == "already-running":
        return f"{label} is already running."
    if result.reason == "already-stopped":
        return f"{label} is already stopped."

    message = f"Unsupported action no-op reason: {result.reason!r}"
    raise AssertionError(message)


def _format_action_denied_message(result: ServerActionDenied) -> str:
    if result.reason == "max-running-servers":
        assert result.running_server_count is not None
        assert result.max_running_servers is not None
        label = _format_server_label(result.server)
        return (
            f"Start denied for {label}: running server limit reached "
            f"({result.running_server_count}/{result.max_running_servers})."
        )
    if result.reason == "missing-target-memory-limit":
        label = _format_server_label(result.server)
        return (
            f"Start denied for {label}: this server has no discoverable RAM limit, "
            "so the RAM budget cannot be enforced safely."
        )
    if result.reason == "missing-running-memory-limits":
        assert result.missing_memory_limit_servers
        label = _format_server_label(result.server)
        missing = ", ".join(
            _format_server_label(server) for server in result.missing_memory_limit_servers
        )
        return (
            f"Start denied for {label}: RAM budget cannot be computed safely because "
            f"these running servers have unknown RAM limits: {missing}."
        )
    if result.reason == "insufficient-ram-headroom":
        assert result.required_memory_mib is not None
        assert result.remaining_memory_mib is not None
        label = _format_server_label(result.server)
        return (
            f"Start denied for {label}: RAM budget would be exceeded "
            f"(needs {result.required_memory_mib} MiB, remaining "
            f"{result.remaining_memory_mib} MiB)."
        )
    if result.reason == "not-running":
        assert result.server is not None
        label = _format_server_label(result.server)
        return f"{label} is not running; use `/server start` instead."

    message = f"Unsupported action denial reason: {result.reason!r}"
    raise AssertionError(message)


def _format_server_label(server: DiscoveredServer | None) -> str:
    if server is None:
        return "the requested server"
    return f"{server.name} (`{server.identifier}`)"


def _audit_action_result(
    interaction: Any,
    *,
    action: str,
    query: str,
    result: ActionResult,
) -> None:
    user = getattr(interaction, "user", None)
    user_id = getattr(user, "id", "unknown")
    user_name = str(user) if user is not None else "unknown-user"
    resolved = _resolved_server_for_result(result)
    resolved_label = _format_server_label(resolved) if resolved is not None else "unresolved"
    outcome, reason, operation = _action_outcome_fields(result)
    LOGGER.info(
        "Pterodactyl audit: user=%s (%s) command=/server %s "
        "query=%r resolved=%s outcome=%s reason=%s operation=%s",
        user_name,
        user_id,
        action,
        query,
        resolved_label,
        outcome,
        reason,
        operation,
    )


def _resolved_server_for_result(result: ActionResult) -> DiscoveredServer | None:
    if isinstance(result, (ServerActionAccepted, ServerActionNoOp, ServerActionDenied)):
        return result.server
    return None


def _action_outcome_fields(result: ActionResult) -> tuple[str, str, str]:
    if isinstance(result, PanelUnavailable):
        return ("panel-unavailable", "panel-unavailable", result.operation)
    if isinstance(result, ServerNotFound):
        return ("not-found", "server-not-found", "-")
    if isinstance(result, AmbiguousServerMatch):
        return ("ambiguous", "ambiguous-match", "-")
    if isinstance(result, ServerActionAccepted):
        return ("accepted", "accepted", "-")
    if isinstance(result, ServerActionNoOp):
        return ("no-op", result.reason, "-")
    if isinstance(result, ServerActionDenied):
        return ("denied", result.reason, "-")

    message = f"Unsupported action result: {type(result)!r}"
    raise AssertionError(message)


def _build_help_message() -> str:
    return "\n".join(
        [
            "Available /server commands:",
            "- `/server list`: List discoverable Pterodactyl servers.",
            "- `/server status <server>`: Show status for one discoverable server.",
            "- `/server start <server>`: Start one discoverable server if policy allows it.",
            "- `/server stop <server>`: Stop one discoverable running server.",
            "- `/server restart <server>`: Restart one discoverable running server.",
            "- `/server budget`: Show policy budget and current headroom.",
            "- `/server help`: Show this help message.",
        ]
    )
