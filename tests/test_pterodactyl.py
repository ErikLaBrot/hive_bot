"""Tests for the Pterodactyl bridge foundation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from pydactyl.exceptions import PterodactylApiError  # type: ignore[import-untyped]

import hive_bot.pterodactyl as pterodactyl
from hive_bot.config import PolicyConfig, PterodactylConfig
from hive_bot.pterodactyl import (
    AmbiguousServerMatch,
    BudgetStatus,
    DiscoveredServers,
    PanelUnavailable,
    PterodactylBridge,
    ResolvedServer,
    ServerNotFound,
    ServerStatus,
    create_client,
)


class FakePaginatedResponse:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items

    async def collect_async(self) -> list[dict[str, Any]]:
        return list(self.items)


class FakeServersApi:
    def __init__(
        self,
        *,
        list_result: Any,
        utilization_by_identifier: dict[str, Any] | None = None,
        detail_by_identifier: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.list_result = list_result
        self.utilization_by_identifier = utilization_by_identifier or {}
        self.detail_by_identifier = detail_by_identifier or {}

    async def list_servers(
        self,
        includes: Any = None,
        params: dict[str, object] | None = None,
    ) -> Any:
        del includes, params
        if isinstance(self.list_result, Exception):
            raise self.list_result
        return self.list_result

    async def get_server(
        self,
        server_id: str,
        detail: bool = False,
        includes: Any = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        del detail, includes, params
        return self.detail_by_identifier[server_id]

    async def get_server_utilization(
        self,
        server_id: str,
        detail: bool = False,
    ) -> dict[str, Any]:
        del detail
        result = self.utilization_by_identifier[server_id]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, dict)
        return result


class FakeClientApi:
    def __init__(self, servers_api: FakeServersApi) -> None:
        self.servers = servers_api


class FakeClientContext:
    def __init__(self, servers_api: FakeServersApi) -> None:
        self._client = FakeClientApi(servers_api)

    @property
    def client(self) -> FakeClientApi:
        return self._client

    async def __aenter__(self) -> FakeClientContext:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        del exc_type, exc_val, exc_tb


def build_bridge(
    *,
    list_result: Any,
    utilization_by_identifier: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> PterodactylBridge:
    servers_api = FakeServersApi(
        list_result=list_result,
        utilization_by_identifier=utilization_by_identifier,
    )

    def fake_client_factory(config: PterodactylConfig) -> FakeClientContext:
        assert config == PterodactylConfig(
            panel_url="https://panel.example.com",
            api_key="ptlc_test",
        )
        return FakeClientContext(servers_api)

    return PterodactylBridge(
        PterodactylConfig(panel_url="https://panel.example.com", api_key="ptlc_test"),
        PolicyConfig(max_running_servers=2, max_total_ram_gb=10),
        client_factory=fake_client_factory,
        logger=logger,
    )


def discovered_item(
    *,
    name: str,
    identifier: str,
    state: str | None,
    memory_limit_mib: int | None,
    uuid: str | None = None,
    internal_id: int | None = None,
) -> dict[str, Any]:
    limits: dict[str, Any] = {}
    if memory_limit_mib is not None:
        limits["memory"] = memory_limit_mib

    return {
        "attributes": {
            "name": name,
            "identifier": identifier,
            "uuid": uuid,
            "internal_id": internal_id,
            "current_state": state,
            "limits": limits,
        }
    }


def test_create_client_passes_runtime_config_to_py_dactyl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, str, logging.Logger]] = []

    class FakeAsyncPterodactylClient:
        def __init__(self, *, url: str, api_key: str, logger: logging.Logger) -> None:
            captured.append((url, api_key, logger))

    monkeypatch.setattr(
        "hive_bot.pterodactyl.client.AsyncPterodactylClient",
        FakeAsyncPterodactylClient,
    )
    logger = logging.getLogger("test-client")

    client = create_client(
        PterodactylConfig(panel_url="https://panel.example.com", api_key="ptlc_test"),
        logger=logger,
    )

    assert isinstance(client, FakeAsyncPterodactylClient)
    assert captured == [("https://panel.example.com", "ptlc_test", logger)]


def test_pterodactyl_package_exports_foundation_symbols() -> None:
    exported_names = {
        "AmbiguousServerMatch",
        "BudgetStatus",
        "DiscoveredServer",
        "DiscoveredServers",
        "PanelUnavailable",
        "PterodactylBridge",
        "ResolvedServer",
        "ServerNotFound",
        "ServerStatus",
        "create_client",
    }

    assert exported_names.issubset(set(pterodactyl.__all__))


def test_discover_servers_collects_paginated_results_and_sorts_servers() -> None:
    bridge = build_bridge(
        list_result=FakePaginatedResponse(
            [
                discovered_item(
                    name="Beta",
                    identifier="beta-1",
                    state="offline",
                    memory_limit_mib=2048,
                    uuid="uuid-beta",
                    internal_id=2,
                ),
                discovered_item(
                    name="Alpha",
                    identifier="alpha-1",
                    state="running",
                    memory_limit_mib=4096,
                    uuid="uuid-alpha",
                    internal_id=1,
                ),
            ]
        )
    )

    result = asyncio.run(bridge.discover_servers())

    assert isinstance(result, DiscoveredServers)
    assert tuple(server.name for server in result.servers) == ("Alpha", "Beta")
    assert result.servers[0].identifier == "alpha-1"
    assert result.servers[0].memory_limit_mib == 4096


def test_discover_servers_accepts_plain_list_results_and_uses_fallback_values() -> None:
    bridge = build_bridge(
        list_result=[
            {
                "name": "   ",
                "identifier": "",
                "uuid": None,
                "internal_id": "bad-int",
                "current_state": None,
                "limits": {"memory": 0},
            }
        ]
    )

    result = asyncio.run(bridge.discover_servers())

    assert isinstance(result, DiscoveredServers)
    assert result.servers == (
        result.servers[0],
    )
    assert result.servers[0].name == "unknown"
    assert result.servers[0].identifier == "unknown"
    assert result.servers[0].uuid is None
    assert result.servers[0].internal_id is None
    assert result.servers[0].state is None
    assert result.servers[0].memory_limit_mib is None


def test_discover_servers_returns_panel_unavailable_for_expected_api_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = build_bridge(list_result=PterodactylApiError("panel down"))

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(bridge.discover_servers())

    assert result == PanelUnavailable(operation="discover servers")
    assert "Pterodactyl panel unavailable while trying to discover servers" in caplog.text


@pytest.mark.parametrize(
    ("query", "expected_identifier"),
    [("Alpha", "alpha-1"), ("ALPHA-1", "alpha-1")],
)
def test_resolve_server_matches_exact_name_or_identifier_case_insensitively(
    query: str,
    expected_identifier: str,
) -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            ),
            discovered_item(
                name="Beta",
                identifier="beta-1",
                state="offline",
                memory_limit_mib=2048,
            ),
        ]
    )

    result = asyncio.run(bridge.resolve_server(query))

    assert isinstance(result, ResolvedServer)
    assert result.server.identifier == expected_identifier


@pytest.mark.parametrize("query", ["", "missing"])
def test_resolve_server_returns_not_found_when_query_does_not_match(query: str) -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            )
        ]
    )

    result = asyncio.run(bridge.resolve_server(query))

    assert result == ServerNotFound(query=query)


def test_resolve_server_returns_ambiguous_match_when_multiple_servers_match() -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            ),
            discovered_item(
                name="alpha",
                identifier="alpha-2",
                state="offline",
                memory_limit_mib=2048,
            ),
        ]
    )

    result = asyncio.run(bridge.resolve_server("alpha"))

    assert isinstance(result, AmbiguousServerMatch)
    assert tuple(server.identifier for server in result.matches) == ("alpha-1", "alpha-2")


def test_get_server_status_uses_live_utilization_state_when_available() -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
                uuid="uuid-alpha",
                internal_id=1,
            )
        ],
        utilization_by_identifier={"alpha-1": {"current_state": "running"}},
    )

    result = asyncio.run(bridge.get_server_status("alpha"))

    assert isinstance(result, ServerStatus)
    assert result.server.name == "Alpha"
    assert result.server.state == "running"
    assert result.server.memory_limit_mib == 4096


def test_get_server_status_falls_back_to_discovered_state_when_utilization_is_empty() -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            )
        ],
        utilization_by_identifier={"alpha-1": {}},
    )

    result = asyncio.run(bridge.get_server_status("alpha"))

    assert isinstance(result, ServerStatus)
    assert result.server.state == "offline"


def test_get_server_status_returns_panel_unavailable_for_unexpected_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="offline",
                memory_limit_mib=4096,
            )
        ],
        utilization_by_identifier={"alpha-1": RuntimeError("boom")},
    )

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(bridge.get_server_status("alpha"))

    assert result == PanelUnavailable(operation="get server status")
    assert "Unexpected bridge failure while trying to get server status" in caplog.text


def test_get_budget_status_returns_complete_budget_summary() -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            ),
            discovered_item(
                name="Beta",
                identifier="beta-1",
                state="offline",
                memory_limit_mib=2048,
            ),
            discovered_item(
                name="Gamma",
                identifier="gamma-1",
                state="running",
                memory_limit_mib=2048,
            ),
        ]
    )

    result = asyncio.run(bridge.get_budget_status())

    assert isinstance(result, BudgetStatus)
    assert result == BudgetStatus(
        max_running_servers=2,
        max_total_ram_gb=10,
        running_server_count=2,
        running_servers=result.running_servers,
        consumed_memory_mib=6144,
        remaining_memory_mib=4096,
        has_complete_memory_data=True,
        missing_memory_limit_servers=(),
    )
    assert tuple(server.identifier for server in result.running_servers) == ("alpha-1", "gamma-1")


def test_get_budget_status_marks_missing_memory_data_as_partial() -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            ),
            discovered_item(
                name="Gamma",
                identifier="gamma-1",
                state="running",
                memory_limit_mib=0,
            ),
        ]
    )

    result = asyncio.run(bridge.get_budget_status())

    assert isinstance(result, BudgetStatus)
    assert result.running_server_count == 2
    assert result.consumed_memory_mib is None
    assert result.remaining_memory_mib is None
    assert result.has_complete_memory_data is False
    assert tuple(server.identifier for server in result.missing_memory_limit_servers) == (
        "gamma-1",
    )


def test_resolve_server_returns_panel_unavailable_when_discovery_fails() -> None:
    bridge = build_bridge(list_result=PterodactylApiError("panel down"))

    result = asyncio.run(bridge.resolve_server("alpha"))

    assert result == PanelUnavailable(operation="discover servers")


def test_get_server_status_returns_resolution_failures_without_fetching_utilization() -> None:
    bridge = build_bridge(
        list_result=[
            discovered_item(
                name="Alpha",
                identifier="alpha-1",
                state="running",
                memory_limit_mib=4096,
            ),
            discovered_item(
                name="alpha",
                identifier="alpha-2",
                state="offline",
                memory_limit_mib=2048,
            ),
        ]
    )

    result = asyncio.run(bridge.get_server_status("alpha"))

    assert isinstance(result, AmbiguousServerMatch)


def test_get_budget_status_returns_panel_unavailable_when_discovery_fails() -> None:
    bridge = build_bridge(list_result=PterodactylApiError("panel down"))

    result = asyncio.run(bridge.get_budget_status())

    assert result == PanelUnavailable(operation="discover servers")


def test_discover_servers_treats_missing_or_invalid_memory_limits_as_unknown() -> None:
    bridge = build_bridge(
        list_result=[
            {"attributes": {"name": "Alpha", "identifier": "alpha-1", "current_state": "running"}},
            {
                "attributes": {
                    "name": "Beta",
                    "identifier": "beta-1",
                    "current_state": "running",
                    "limits": {"memory": "4096"},
                }
            },
        ]
    )

    result = asyncio.run(bridge.discover_servers())

    assert isinstance(result, DiscoveredServers)
    assert result.servers[0].memory_limit_mib is None
    assert result.servers[1].memory_limit_mib is None
