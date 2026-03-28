"""Tests for the `/server` slash commands."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest

from hive_bot.commands import server as server_commands
from hive_bot.commands.server import (
    build_server_group,
    handle_server_budget,
    handle_server_help,
    handle_server_list,
    handle_server_restart,
    handle_server_start,
    handle_server_status,
    handle_server_stop,
)
from hive_bot.pterodactyl import (
    ActionResult,
    AmbiguousServerMatch,
    BudgetStatus,
    DiscoveredServer,
    DiscoveredServers,
    PanelUnavailable,
    ServerActionAccepted,
    ServerActionDenied,
    ServerActionNoOp,
    ServerNotFound,
    ServerStatus,
)


class FakeResponse:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.messages: list[str] = []
        self.error = error

    async def send_message(self, message: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(message)


class FakeInteraction:
    def __init__(
        self,
        *,
        user: Any | None = None,
        response_error: Exception | None = None,
    ) -> None:
        self.response = FakeResponse(error=response_error)
        self.user = FakeUser() if user is None else user


class FakeUser:
    def __init__(self, *, user_id: int = 42, name: str = "TestUser") -> None:
        self.id = user_id
        self.name = name

    def __str__(self) -> str:
        return self.name


class FakeSubcommand:
    def __init__(self, *, name: str, description: str, callback: Any) -> None:
        self.name = name
        self.description = description
        self.callback = callback


class FakeGroup:
    def __init__(self, *, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self.commands: list[FakeSubcommand] = []

    def command(self, *, name: str, description: str) -> Any:
        def decorator(callback: Any) -> FakeSubcommand:
            command = FakeSubcommand(name=name, description=description, callback=callback)
            self.commands.append(command)
            return command

        return decorator


class FakeAppCommandsModule:
    Group = FakeGroup


class FakeBridge:
    def __init__(
        self,
        *,
        discover_result: Any | None = None,
        status_result: Any | None = None,
        budget_result: Any | None = None,
        start_result: ActionResult | None = None,
        stop_result: ActionResult | None = None,
        restart_result: ActionResult | None = None,
    ) -> None:
        self.discover_result = discover_result
        self.status_result = status_result
        self.budget_result = budget_result
        self.start_result = start_result
        self.stop_result = stop_result
        self.restart_result = restart_result
        self.calls: list[tuple[str, Any]] = []

    async def discover_servers(self) -> Any:
        self.calls.append(("discover_servers", None))
        return self.discover_result

    async def get_server_status(self, query: str) -> Any:
        self.calls.append(("get_server_status", query))
        return self.status_result

    async def get_budget_status(self) -> Any:
        self.calls.append(("get_budget_status", None))
        return self.budget_result

    async def start_server(self, query: str) -> ActionResult:
        self.calls.append(("start_server", query))
        assert self.start_result is not None
        return self.start_result

    async def stop_server(self, query: str) -> ActionResult:
        self.calls.append(("stop_server", query))
        assert self.stop_result is not None
        return self.stop_result

    async def restart_server(self, query: str) -> ActionResult:
        self.calls.append(("restart_server", query))
        assert self.restart_result is not None
        return self.restart_result


def discovered_server(
    *,
    name: str,
    identifier: str,
    state: str | None,
    memory_limit_mib: int | None,
) -> DiscoveredServer:
    return DiscoveredServer(
        name=name,
        identifier=identifier,
        uuid=None,
        internal_id=None,
        state=state,
        memory_limit_mib=memory_limit_mib,
    )


def test_handle_server_list_formats_discovered_servers() -> None:
    bridge = FakeBridge(
        discover_result=DiscoveredServers(
            servers=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
                discovered_server(
                    name="Beta",
                    identifier="beta-1",
                    state=None,
                    memory_limit_mib=None,
                ),
            )
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_list(interaction, bridge=bridge))

    assert bridge.calls == [("discover_servers", None)]
    assert interaction.response.messages == [
        (
            "Discoverable Pterodactyl servers:\n"
            "- Alpha (`alpha-1`): running; RAM limit 4096 MiB\n"
            "- Beta (`beta-1`): unknown; RAM limit unknown"
        )
    ]


def test_handle_server_list_handles_empty_inventory() -> None:
    bridge = FakeBridge(discover_result=DiscoveredServers(servers=()))
    interaction = FakeInteraction()

    asyncio.run(handle_server_list(interaction, bridge=bridge))

    assert interaction.response.messages == [
        "No Pterodactyl servers are currently discoverable by the bot."
    ]


def test_handle_server_list_handles_panel_unavailable() -> None:
    bridge = FakeBridge(discover_result=PanelUnavailable(operation="discover servers"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_list(interaction, bridge=bridge))

    assert interaction.response.messages == ["Pterodactyl panel is currently unreachable."]


def test_handle_server_status_formats_server_status() -> None:
    bridge = FakeBridge(
        status_result=ServerStatus(
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            )
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_status(interaction, bridge=bridge, server="Alpha"))

    assert bridge.calls == [("get_server_status", "Alpha")]
    assert interaction.response.messages == [
        (
            "Server status for Alpha (`alpha-1`):\n"
            "State: running\n"
            "RAM limit: 4096 MiB"
        )
    ]


def test_handle_server_status_handles_not_found() -> None:
    bridge = FakeBridge(status_result=ServerNotFound(query="ghost"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_status(interaction, bridge=bridge, server="ghost"))

    assert interaction.response.messages == ["No discoverable server matched `ghost`."]


def test_handle_server_status_handles_ambiguous_match() -> None:
    bridge = FakeBridge(
        status_result=AmbiguousServerMatch(
            query="alpha",
            matches=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
                discovered_server(
                    name="alpha",
                    identifier="alpha-2",
                    state="offline",
                    memory_limit_mib=2048,
                ),
            ),
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_status(interaction, bridge=bridge, server="alpha"))

    assert interaction.response.messages == [
        "Multiple discoverable servers matched `alpha`: Alpha (`alpha-1`), alpha (`alpha-2`)"
    ]


def test_handle_server_status_handles_panel_unavailable() -> None:
    bridge = FakeBridge(status_result=PanelUnavailable(operation="get server status"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_status(interaction, bridge=bridge, server="alpha"))

    assert interaction.response.messages == ["Pterodactyl panel is currently unreachable."]


def test_handle_server_budget_formats_complete_budget_status() -> None:
    bridge = FakeBridge(
        budget_result=BudgetStatus(
            max_running_servers=2,
            max_total_ram_gb=10,
            running_server_count=1,
            running_servers=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
            ),
            consumed_memory_mib=4096,
            remaining_memory_mib=6144,
            has_complete_memory_data=True,
            missing_memory_limit_servers=(),
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert bridge.calls == [("get_budget_status", None)]
    assert interaction.response.messages == [
        (
            "Server budget status:\n"
            "- Max running servers: 2\n"
            "- Max RAM budget: 10 GiB\n"
            "- Currently running: 1\n"
            "- Consumed RAM limit: 4096 MiB\n"
            "- Remaining RAM headroom: 6144 MiB\n"
            "- Running servers: Alpha (`alpha-1`)"
        )
    ]


def test_handle_server_budget_formats_partial_budget_status() -> None:
    bridge = FakeBridge(
        budget_result=BudgetStatus(
            max_running_servers=2,
            max_total_ram_gb=10,
            running_server_count=2,
            running_servers=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
                discovered_server(
                    name="Gamma",
                    identifier="gamma-1",
                    state="running",
                    memory_limit_mib=None,
                ),
            ),
            consumed_memory_mib=None,
            remaining_memory_mib=None,
            has_complete_memory_data=False,
            missing_memory_limit_servers=(
                discovered_server(
                    name="Gamma",
                    identifier="gamma-1",
                    state="running",
                    memory_limit_mib=None,
                ),
            ),
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert interaction.response.messages == [
        (
            "Server budget status:\n"
            "- Max running servers: 2\n"
            "- Max RAM budget: 10 GiB\n"
            "- Currently running: 2\n"
            "- Consumed RAM limit: unavailable (missing memory limits)\n"
            "- Remaining RAM headroom: unavailable\n"
            "- Missing RAM limit data for: Gamma (`gamma-1`)\n"
            "- Running servers: Alpha (`alpha-1`), Gamma (`gamma-1`)"
        )
    ]


def test_handle_server_budget_omits_empty_missing_memory_line() -> None:
    bridge = FakeBridge(
        budget_result=BudgetStatus(
            max_running_servers=2,
            max_total_ram_gb=10,
            running_server_count=1,
            running_servers=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=None,
                ),
            ),
            consumed_memory_mib=None,
            remaining_memory_mib=None,
            has_complete_memory_data=False,
            missing_memory_limit_servers=(),
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert interaction.response.messages == [
        (
            "Server budget status:\n"
            "- Max running servers: 2\n"
            "- Max RAM budget: 10 GiB\n"
            "- Currently running: 1\n"
            "- Consumed RAM limit: unavailable (missing memory limits)\n"
            "- Remaining RAM headroom: unavailable\n"
            "- Running servers: Alpha (`alpha-1`)"
        )
    ]


def test_handle_server_budget_formats_over_budget_headroom() -> None:
    bridge = FakeBridge(
        budget_result=BudgetStatus(
            max_running_servers=2,
            max_total_ram_gb=10,
            running_server_count=2,
            running_servers=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=8192,
                ),
                discovered_server(
                    name="Gamma",
                    identifier="gamma-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
            ),
            consumed_memory_mib=12288,
            remaining_memory_mib=-2048,
            has_complete_memory_data=True,
            missing_memory_limit_servers=(),
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert "Remaining RAM headroom: -2048 MiB (over budget)" in interaction.response.messages[0]


def test_handle_server_budget_handles_panel_unavailable() -> None:
    bridge = FakeBridge(budget_result=PanelUnavailable(operation="discover servers"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert interaction.response.messages == ["Pterodactyl panel is currently unreachable."]


def test_handle_server_budget_formats_no_running_servers() -> None:
    bridge = FakeBridge(
        budget_result=BudgetStatus(
            max_running_servers=2,
            max_total_ram_gb=10,
            running_server_count=0,
            running_servers=(),
            consumed_memory_mib=0,
            remaining_memory_mib=10240,
            has_complete_memory_data=True,
            missing_memory_limit_servers=(),
        )
    )
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert interaction.response.messages == [
        (
            "Server budget status:\n"
            "- Max running servers: 2\n"
            "- Max RAM budget: 10 GiB\n"
            "- Currently running: 0\n"
            "- Consumed RAM limit: 0 MiB\n"
            "- Remaining RAM headroom: 10240 MiB\n"
            "- Running servers: none"
        )
    ]


def test_handle_server_start_formats_acceptance_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = FakeBridge(
        start_result=ServerActionAccepted(
            action="start",
            query="alpha",
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            ),
        )
    )
    interaction = FakeInteraction()

    with caplog.at_level(logging.INFO, logger="hive_bot.commands.server"):
        asyncio.run(handle_server_start(interaction, bridge=bridge, server="alpha"))

    assert bridge.calls == [("start_server", "alpha")]
    assert interaction.response.messages == ["Start request accepted for Alpha (`alpha-1`)."]
    assert "command=/server start" in caplog.text
    assert "outcome=accepted" in caplog.text
    assert "resolved=Alpha (`alpha-1`)" in caplog.text
    assert "reason=accepted operation=-" in caplog.text


def test_handle_server_start_audits_before_response_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = FakeBridge(
        start_result=ServerActionAccepted(
            action="start",
            query="alpha",
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            ),
        )
    )
    interaction = FakeInteraction(response_error=RuntimeError("send failed"))

    with caplog.at_level(logging.INFO, logger="hive_bot.commands.server"):
        with pytest.raises(RuntimeError, match="send failed"):
            asyncio.run(handle_server_start(interaction, bridge=bridge, server="alpha"))

    assert "command=/server start" in caplog.text
    assert "outcome=accepted" in caplog.text
    assert "operation=-" in caplog.text


def test_handle_server_start_formats_policy_denial_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = FakeBridge(
        start_result=ServerActionDenied(
            action="start",
            query="alpha",
            reason="max-running-servers",
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            ),
            running_server_count=2,
            max_running_servers=2,
        )
    )
    interaction = FakeInteraction()

    with caplog.at_level(logging.INFO, logger="hive_bot.commands.server"):
        asyncio.run(handle_server_start(interaction, bridge=bridge, server="alpha"))

    assert interaction.response.messages == [
        "Start denied for Alpha (`alpha-1`): running server limit reached (2/2)."
    ]
    assert "outcome=denied" in caplog.text
    assert "reason=max-running-servers" in caplog.text
    assert "operation=-" in caplog.text


def test_handle_server_stop_formats_no_op_and_audits(caplog: pytest.LogCaptureFixture) -> None:
    bridge = FakeBridge(
        stop_result=ServerActionNoOp(
            action="stop",
            query="alpha",
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            ),
            reason="already-stopped",
        )
    )
    interaction = FakeInteraction()

    with caplog.at_level(logging.INFO, logger="hive_bot.commands.server"):
        asyncio.run(handle_server_stop(interaction, bridge=bridge, server="alpha"))

    assert interaction.response.messages == ["Alpha (`alpha-1`) is already stopped."]
    assert "command=/server stop" in caplog.text
    assert "outcome=no-op" in caplog.text
    assert "reason=already-stopped" in caplog.text
    assert "operation=-" in caplog.text


def test_handle_server_restart_formats_denial_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = FakeBridge(
        restart_result=ServerActionDenied(
            action="restart",
            query="alpha",
            reason="not-running",
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            ),
        )
    )
    interaction = FakeInteraction()

    with caplog.at_level(logging.INFO, logger="hive_bot.commands.server"):
        asyncio.run(handle_server_restart(interaction, bridge=bridge, server="alpha"))

    assert interaction.response.messages == [
        "Alpha (`alpha-1`) is not running; use `/server start` instead."
    ]
    assert "command=/server restart" in caplog.text
    assert "outcome=denied" in caplog.text
    assert "reason=not-running" in caplog.text
    assert "operation=-" in caplog.text


def test_handle_server_help_is_static() -> None:
    interaction = FakeInteraction()

    asyncio.run(handle_server_help(interaction))

    assert interaction.response.messages == [
        (
            "Available /server commands:\n"
            "- `/server list`: List discoverable Pterodactyl servers.\n"
            "- `/server status <server>`: Show status for one discoverable server.\n"
            "- `/server start <server>`: Start one discoverable server if policy allows it.\n"
            "- `/server stop <server>`: Stop one discoverable running server.\n"
            "- `/server restart <server>`: Restart one discoverable running server.\n"
            "- `/server budget`: Show policy budget and current headroom.\n"
            "- `/server help`: Show this help message."
        )
    ]


def test_build_server_group_creates_named_subcommands() -> None:
    bridge = FakeBridge(
        discover_result=DiscoveredServers(servers=()),
        status_result=ServerNotFound(query="ghost"),
        start_result=ServerActionAccepted(
            action="start",
            query="alpha",
            server=discovered_server(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            ),
        ),
        stop_result=ServerActionNoOp(
            action="stop",
            query="ghost",
            server=discovered_server(
                name="Ghost",
                identifier="ghost-1",
                state="offline",
                memory_limit_mib=1024,
            ),
            reason="already-stopped",
        ),
        restart_result=ServerActionDenied(
            action="restart",
            query="ghost",
            reason="not-running",
            server=discovered_server(
                name="Ghost",
                identifier="ghost-1",
                state="offline",
                memory_limit_mib=1024,
            ),
        ),
        budget_result=PanelUnavailable(operation="discover servers"),
    )
    group = build_server_group(app_commands_module=FakeAppCommandsModule, bridge=bridge)

    assert group.name == "server"
    assert group.description == "Pterodactyl server commands"
    assert [command.name for command in group.commands] == [
        "list",
        "status",
        "start",
        "stop",
        "restart",
        "budget",
        "help",
    ]

    list_interaction = FakeInteraction()
    status_interaction = FakeInteraction()
    start_interaction = FakeInteraction()
    stop_interaction = FakeInteraction()
    restart_interaction = FakeInteraction()
    budget_interaction = FakeInteraction()
    help_interaction = FakeInteraction()

    asyncio.run(group.commands[0].callback(list_interaction))
    asyncio.run(group.commands[1].callback(status_interaction, "ghost"))
    asyncio.run(group.commands[2].callback(start_interaction, "alpha"))
    asyncio.run(group.commands[3].callback(stop_interaction, "ghost"))
    asyncio.run(group.commands[4].callback(restart_interaction, "ghost"))
    asyncio.run(group.commands[5].callback(budget_interaction))
    asyncio.run(group.commands[6].callback(help_interaction))

    assert list_interaction.response.messages == [
        "No Pterodactyl servers are currently discoverable by the bot."
    ]
    assert status_interaction.response.messages == ["No discoverable server matched `ghost`."]
    assert start_interaction.response.messages == [
        "Start request accepted for Alpha (`alpha-1`)."
    ]
    assert stop_interaction.response.messages == ["Ghost (`ghost-1`) is already stopped."]
    assert restart_interaction.response.messages == [
        "Ghost (`ghost-1`) is not running; use `/server start` instead."
    ]
    assert budget_interaction.response.messages == ["Pterodactyl panel is currently unreachable."]
    assert help_interaction.response.messages == [
        (
            "Available /server commands:\n"
            "- `/server list`: List discoverable Pterodactyl servers.\n"
            "- `/server status <server>`: Show status for one discoverable server.\n"
            "- `/server start <server>`: Start one discoverable server if policy allows it.\n"
            "- `/server stop <server>`: Stop one discoverable running server.\n"
            "- `/server restart <server>`: Restart one discoverable running server.\n"
            "- `/server budget`: Show policy budget and current headroom.\n"
            "- `/server help`: Show this help message."
        )
    ]


def test_format_server_status_result_rejects_unsupported_type() -> None:
    with pytest.raises(AssertionError, match="Unsupported server status result"):
        server_commands._format_server_status_result(cast(Any, object()))


def test_format_discover_servers_result_rejects_unsupported_type() -> None:
    with pytest.raises(AssertionError, match="Unsupported discover servers result"):
        server_commands._format_discover_servers_result(cast(Any, object()))


def test_format_budget_result_rejects_unsupported_type() -> None:
    with pytest.raises(AssertionError, match="Unsupported budget result"):
        server_commands._format_budget_result(cast(Any, object()))


def test_format_action_result_handles_panel_unavailable() -> None:
    assert (
        server_commands._format_action_result(PanelUnavailable(operation="start server"))
        == "Pterodactyl panel is currently unreachable."
    )


def test_format_action_result_handles_not_found() -> None:
    assert (
        server_commands._format_action_result(ServerNotFound(query="ghost"))
        == "No discoverable server matched `ghost`."
    )


def test_format_action_result_handles_ambiguous_match() -> None:
    assert server_commands._format_action_result(
        AmbiguousServerMatch(
            query="alpha",
            matches=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
                discovered_server(
                    name="alpha",
                    identifier="alpha-2",
                    state="offline",
                    memory_limit_mib=2048,
                ),
            ),
        )
    ) == "Multiple discoverable servers matched `alpha`: Alpha (`alpha-1`), alpha (`alpha-2`)"


def test_format_action_result_rejects_unsupported_type() -> None:
    with pytest.raises(AssertionError, match="Unsupported action result"):
        server_commands._format_action_result(cast(Any, object()))


def test_format_action_no_op_message_handles_already_running() -> None:
    assert (
        server_commands._format_action_no_op_message(
            ServerActionNoOp(
                action="start",
                query="alpha",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
                reason="already-running",
            )
        )
        == "Alpha (`alpha-1`) is already running."
    )


def test_format_action_no_op_message_rejects_unknown_reason() -> None:
    with pytest.raises(AssertionError, match="Unsupported action no-op reason"):
        server_commands._format_action_no_op_message(
            ServerActionNoOp(
                action="stop",
                query="alpha",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=4096,
                ),
                reason="mystery",
            )
        )


def test_format_action_denied_message_handles_missing_target_memory_limit() -> None:
    assert (
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="missing-target-memory-limit",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=None,
                ),
            )
        )
        == "Start denied for Alpha (`alpha-1`): this server has no discoverable RAM limit, "
        "so the RAM budget cannot be enforced safely."
    )


def test_format_action_denied_message_handles_missing_running_memory_limits() -> None:
    assert (
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="missing-running-memory-limits",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=2048,
                ),
                missing_memory_limit_servers=(
                    discovered_server(
                        name="Beta",
                        identifier="beta-1",
                        state="running",
                        memory_limit_mib=None,
                    ),
                ),
            )
        )
        == "Start denied for Alpha (`alpha-1`): RAM budget cannot be computed safely because "
        "these running servers have unknown RAM limits: Beta (`beta-1`)."
    )


def test_format_action_denied_message_handles_insufficient_ram_headroom() -> None:
    assert (
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="insufficient-ram-headroom",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=4096,
                ),
                required_memory_mib=4096,
                remaining_memory_mib=2048,
            )
        )
        == "Start denied for Alpha (`alpha-1`): RAM budget would be exceeded "
        "(needs 4096 MiB, remaining 2048 MiB)."
    )


def test_format_action_denied_message_rejects_missing_running_limit_fields() -> None:
    with pytest.raises(AssertionError):
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="max-running-servers",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=4096,
                ),
            )
        )


def test_format_action_denied_message_rejects_empty_missing_running_servers() -> None:
    with pytest.raises(AssertionError):
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="missing-running-memory-limits",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=4096,
                ),
            )
        )


def test_format_action_denied_message_rejects_missing_ram_headroom_fields() -> None:
    with pytest.raises(AssertionError):
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="insufficient-ram-headroom",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=4096,
                ),
            )
        )


def test_format_action_denied_message_rejects_unknown_reason() -> None:
    with pytest.raises(AssertionError, match="Unsupported action denial reason"):
        server_commands._format_action_denied_message(
            ServerActionDenied(
                action="start",
                query="alpha",
                reason="mystery",
                server=discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="offline",
                    memory_limit_mib=4096,
                ),
            )
        )


def test_format_server_label_returns_placeholder_when_server_is_missing() -> None:
    assert server_commands._format_server_label(None) == "the requested server"


def test_resolved_server_for_result_returns_none_for_unresolved_results() -> None:
    assert (
        server_commands._resolved_server_for_result(PanelUnavailable(operation="start server"))
        is None
    )


def test_action_outcome_fields_cover_unresolved_results() -> None:
    assert server_commands._action_outcome_fields(
        PanelUnavailable(operation="start server")
    ) == ("panel-unavailable", "panel-unavailable", "start server")
    assert server_commands._action_outcome_fields(ServerNotFound(query="ghost")) == (
        "not-found",
        "server-not-found",
        "-",
    )
    assert server_commands._action_outcome_fields(
        AmbiguousServerMatch(
            query="alpha",
            matches=(
                discovered_server(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                ),
                discovered_server(
                    name="alpha",
                    identifier="alpha-2",
                    state="offline",
                    memory_limit_mib=2048,
                ),
            ),
        )
    ) == ("ambiguous", "ambiguous-match", "-")


def test_action_outcome_fields_rejects_unsupported_type() -> None:
    with pytest.raises(AssertionError, match="Unsupported action result"):
        server_commands._action_outcome_fields(cast(Any, object()))
