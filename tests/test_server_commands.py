"""Tests for the read-only `/server` slash commands."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from hive_bot.commands import server as server_commands
from hive_bot.commands.server import (
    build_server_group,
    handle_server_budget,
    handle_server_help,
    handle_server_list,
    handle_server_status,
)
from hive_bot.pterodactyl import (
    AmbiguousServerMatch,
    BudgetStatus,
    DiscoveredServer,
    DiscoveredServers,
    PanelUnavailable,
    ServerNotFound,
    ServerStatus,
)


class FakeResponse:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, message: str) -> None:
        self.messages.append(message)


class FakeInteraction:
    def __init__(self) -> None:
        self.response = FakeResponse()


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


class FakeReadOnlyBridge:
    def __init__(
        self,
        *,
        discover_result: Any | None = None,
        status_result: Any | None = None,
        budget_result: Any | None = None,
    ) -> None:
        self.discover_result = discover_result
        self.status_result = status_result
        self.budget_result = budget_result
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
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(discover_result=DiscoveredServers(servers=()))
    interaction = FakeInteraction()

    asyncio.run(handle_server_list(interaction, bridge=bridge))

    assert interaction.response.messages == [
        "No Pterodactyl servers are currently discoverable by the bot."
    ]


def test_handle_server_list_handles_panel_unavailable() -> None:
    bridge = FakeReadOnlyBridge(discover_result=PanelUnavailable(operation="discover servers"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_list(interaction, bridge=bridge))

    assert interaction.response.messages == ["Pterodactyl panel is currently unreachable."]


def test_handle_server_status_formats_server_status() -> None:
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(status_result=ServerNotFound(query="ghost"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_status(interaction, bridge=bridge, server="ghost"))

    assert interaction.response.messages == ["No discoverable server matched `ghost`."]


def test_handle_server_status_handles_ambiguous_match() -> None:
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(status_result=PanelUnavailable(operation="get server status"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_status(interaction, bridge=bridge, server="alpha"))

    assert interaction.response.messages == ["Pterodactyl panel is currently unreachable."]


def test_handle_server_budget_formats_complete_budget_status() -> None:
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(
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
    bridge = FakeReadOnlyBridge(budget_result=PanelUnavailable(operation="discover servers"))
    interaction = FakeInteraction()

    asyncio.run(handle_server_budget(interaction, bridge=bridge))

    assert interaction.response.messages == ["Pterodactyl panel is currently unreachable."]


def test_handle_server_budget_formats_no_running_servers() -> None:
    bridge = FakeReadOnlyBridge(
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


def test_handle_server_help_is_static() -> None:
    interaction = FakeInteraction()

    asyncio.run(handle_server_help(interaction))

    assert interaction.response.messages == [
        (
            "Available /server commands:\n"
            "- `/server list`: List discoverable Pterodactyl servers.\n"
            "- `/server status <server>`: Show status for one discoverable server.\n"
            "- `/server budget`: Show policy budget and current headroom.\n"
            "- `/server help`: Show this help message."
        )
    ]


def test_build_server_group_creates_named_subcommands() -> None:
    bridge = FakeReadOnlyBridge(
        discover_result=DiscoveredServers(servers=()),
        status_result=ServerNotFound(query="ghost"),
        budget_result=PanelUnavailable(operation="discover servers"),
    )
    group = build_server_group(app_commands_module=FakeAppCommandsModule, bridge=bridge)

    assert group.name == "server"
    assert group.description == "Read-only Pterodactyl server commands"
    assert [command.name for command in group.commands] == ["list", "status", "budget", "help"]

    list_interaction = FakeInteraction()
    status_interaction = FakeInteraction()
    budget_interaction = FakeInteraction()
    help_interaction = FakeInteraction()

    asyncio.run(group.commands[0].callback(list_interaction))
    asyncio.run(group.commands[1].callback(status_interaction, "ghost"))
    asyncio.run(group.commands[2].callback(budget_interaction))
    asyncio.run(group.commands[3].callback(help_interaction))

    assert list_interaction.response.messages == [
        "No Pterodactyl servers are currently discoverable by the bot."
    ]
    assert status_interaction.response.messages == ["No discoverable server matched `ghost`."]
    assert budget_interaction.response.messages == ["Pterodactyl panel is currently unreachable."]
    assert help_interaction.response.messages == [
        (
            "Available /server commands:\n"
            "- `/server list`: List discoverable Pterodactyl servers.\n"
            "- `/server status <server>`: Show status for one discoverable server.\n"
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
