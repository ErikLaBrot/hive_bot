"""Discovery-first bridge for the Pterodactyl client API."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, cast

import aiohttp
from pydactyl.exceptions import PydactylError  # type: ignore[import-untyped]

from hive_bot.config import PolicyConfig, PterodactylConfig
from hive_bot.pterodactyl.client import (
    AsyncPterodactylClientProtocol,
    ClientContextManager,
    ClientFactory,
    create_client,
)
from hive_bot.pterodactyl.models import (
    ActionResult,
    AmbiguousServerMatch,
    BudgetResult,
    BudgetStatus,
    DiscoveredServer,
    DiscoveredServers,
    DiscoverServersResult,
    PanelUnavailable,
    ResolvedServer,
    ResolveServerResult,
    ServerActionAccepted,
    ServerActionDenied,
    ServerActionNoOp,
    ServerNotFound,
    ServerStatus,
    ServerStatusResult,
)

LOGGER = logging.getLogger(__name__)


class PterodactylBridge:
    """Encapsulate discovery-first access to Pterodactyl."""

    def __init__(
        self,
        config: PterodactylConfig,
        policy: PolicyConfig,
        *,
        client_factory: ClientFactory = create_client,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._policy = policy
        self._client_factory = client_factory
        self._logger = LOGGER if logger is None else logger

    async def discover_servers(self) -> DiscoverServersResult:
        """Return the servers currently discoverable by the client key."""

        try:
            async with self._open_client() as client:
                servers = await self._discover_servers_in_session(client)
        except Exception as exc:
            return self._panel_unavailable("discover servers", exc)

        return DiscoveredServers(servers=servers)

    async def resolve_server(self, query: str) -> ResolveServerResult:
        """Resolve a server by exact case-insensitive name or identifier."""

        discovered_result = await self.discover_servers()
        if isinstance(discovered_result, PanelUnavailable):
            return discovered_result

        return _resolve_from_servers(query, discovered_result.servers)

    async def get_server_status(self, query: str) -> ServerStatusResult:
        """Return current server status for a resolved server."""

        try:
            async with self._open_client() as client:
                try:
                    # Discovery failures keep their own operation label so
                    # callers can distinguish inventory lookup from later
                    # status/utilization failures.
                    discovered_servers = await self._discover_servers_in_session(client)
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                # Resolution is a pure in-memory step; keep it inside the
                # shared session block so discovery and utilization still reuse
                # the same client lifecycle.
                resolve_result = _resolve_from_servers(query, discovered_servers)
                if not isinstance(resolve_result, ResolvedServer):
                    return resolve_result

                utilization = await client.client.servers.get_server_utilization(
                    resolve_result.server.identifier
                )
        except Exception as exc:
            return self._panel_unavailable("get server status", exc)

        current_state = _read_optional_string(_coerce_attributes(utilization).get("current_state"))
        return ServerStatus(
            server=_replace_server_state(resolve_result.server, current_state=current_state),
        )

    async def get_budget_status(self) -> BudgetResult:
        """Compute current policy budget information from live discovery."""

        discovered_result = await self.discover_servers()
        if isinstance(discovered_result, PanelUnavailable):
            return discovered_result

        return self._build_budget_status(discovered_result.servers)

    async def start_server(self, query: str) -> ActionResult:
        """Start a resolved server if policy checks allow it."""

        try:
            async with self._open_client() as client:
                try:
                    discovered_servers = await self._discover_servers_in_session(client)
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                resolve_result = _resolve_from_servers(query, discovered_servers)
                if not isinstance(resolve_result, ResolvedServer):
                    return resolve_result

                target_server = resolve_result.server
                if _is_running_state(target_server.state):
                    return ServerActionNoOp(
                        action="start",
                        query=query,
                        server=target_server,
                        reason="already-running",
                    )

                running_servers = tuple(
                    server for server in discovered_servers if _is_running_state(server.state)
                )
                if len(running_servers) >= self._policy.max_running_servers:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="max-running-servers",
                        server=target_server,
                        running_server_count=len(running_servers),
                        max_running_servers=self._policy.max_running_servers,
                    )

                if target_server.memory_limit_mib is None:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="missing-target-memory-limit",
                        server=target_server,
                    )

                budget_status = self._build_budget_status(discovered_servers)
                if not budget_status.has_complete_memory_data:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="missing-running-memory-limits",
                        server=target_server,
                        missing_memory_limit_servers=budget_status.missing_memory_limit_servers,
                    )

                required_memory_mib = target_server.memory_limit_mib
                remaining_memory_mib = cast(int, budget_status.remaining_memory_mib)
                if required_memory_mib > remaining_memory_mib:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="insufficient-ram-headroom",
                        server=target_server,
                        required_memory_mib=required_memory_mib,
                        remaining_memory_mib=remaining_memory_mib,
                    )

                await client.client.servers.send_power_action(target_server.identifier, "start")
        except Exception as exc:
            return self._panel_unavailable("start server", exc)

        return ServerActionAccepted(action="start", query=query, server=target_server)

    async def stop_server(self, query: str) -> ActionResult:
        """Stop a resolved server if it is currently running."""

        try:
            async with self._open_client() as client:
                try:
                    discovered_servers = await self._discover_servers_in_session(client)
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                resolve_result = _resolve_from_servers(query, discovered_servers)
                if not isinstance(resolve_result, ResolvedServer):
                    return resolve_result

                target_server = resolve_result.server
                if not _is_running_state(target_server.state):
                    return ServerActionNoOp(
                        action="stop",
                        query=query,
                        server=target_server,
                        reason="already-stopped",
                    )

                await client.client.servers.send_power_action(target_server.identifier, "stop")
        except Exception as exc:
            return self._panel_unavailable("stop server", exc)

        return ServerActionAccepted(action="stop", query=query, server=target_server)

    async def restart_server(self, query: str) -> ActionResult:
        """Restart a resolved server if it is currently running."""

        try:
            async with self._open_client() as client:
                try:
                    discovered_servers = await self._discover_servers_in_session(client)
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                resolve_result = _resolve_from_servers(query, discovered_servers)
                if not isinstance(resolve_result, ResolvedServer):
                    return resolve_result

                target_server = resolve_result.server
                if not _is_running_state(target_server.state):
                    return ServerActionDenied(
                        action="restart",
                        query=query,
                        reason="not-running",
                        server=target_server,
                    )

                await client.client.servers.send_power_action(target_server.identifier, "restart")
        except Exception as exc:
            return self._panel_unavailable("restart server", exc)

        return ServerActionAccepted(action="restart", query=query, server=target_server)

    def _open_client(self) -> ClientContextManager:
        return self._client_factory(self._config)

    def _build_budget_status(self, servers: tuple[DiscoveredServer, ...]) -> BudgetStatus:
        running_servers = tuple(server for server in servers if _is_running_state(server.state))
        missing_memory_servers = tuple(
            server for server in running_servers if server.memory_limit_mib is None
        )
        has_complete_memory_data = not missing_memory_servers
        consumed_memory_mib = (
            sum(cast(int, server.memory_limit_mib) for server in running_servers)
            if has_complete_memory_data
            else None
        )
        remaining_memory_mib = (
            # Keep this signed so callers can report exact over-budget amounts.
            self._policy.max_total_ram_mib - consumed_memory_mib
            if consumed_memory_mib is not None
            else None
        )

        return BudgetStatus(
            max_running_servers=self._policy.max_running_servers,
            max_total_ram_gb=self._policy.max_total_ram_gb,
            running_server_count=len(running_servers),
            running_servers=running_servers,
            consumed_memory_mib=consumed_memory_mib,
            remaining_memory_mib=remaining_memory_mib,
            has_complete_memory_data=has_complete_memory_data,
            missing_memory_limit_servers=missing_memory_servers,
        )

    async def _discover_servers_in_session(
        self,
        client: AsyncPterodactylClientProtocol,
    ) -> tuple[DiscoveredServer, ...]:
        raw_items = await self._list_server_items(client)
        return tuple(sorted((self._parse_server(item) for item in raw_items), key=_server_sort_key))

    async def _list_server_items(
        self,
        client: AsyncPterodactylClientProtocol,
    ) -> list[dict[str, Any]]:
        response = await client.client.servers.list_servers(params={"per_page": 100})
        if isinstance(response, list):
            # Older/compat py-dactyl responses may already be flattened to a
            # single page list, so this warning is only about that shim path.
            # Use >= 100 because the compat response gives us no pagination
            # metadata, so exactly 100 results may still mean "there were more."
            # Paginated responses are handled by collect_async() below.
            if len(response) >= 100:
                self._logger.warning(
                    "Received %s servers from a plain-list py-dactyl response; "
                    "results may be truncated at the per-page limit",
                    len(response),
                )
            return response

        return await response.collect_async()

    def _parse_server(self, payload: dict[str, Any]) -> DiscoveredServer:
        attributes = _coerce_attributes(payload)
        uuid = _read_optional_string(attributes.get("uuid"))
        internal_id = _read_optional_int(attributes.get("internal_id"))
        name = _read_optional_string(attributes.get("name"))
        identifier = _read_optional_string(attributes.get("identifier"))

        if name is None:
            name = _fallback_server_identity(
                "unnamed-server",
                identifier=identifier,
                uuid=uuid,
                internal_id=internal_id,
            )
            self._logger.warning("Discovered server missing name; using fallback %s", name)

        if identifier is None:
            identifier = _fallback_server_identity(
                "unknown-identifier",
                uuid=uuid,
                internal_id=internal_id,
            )
            self._logger.warning(
                "Discovered server missing identifier; using fallback %s",
                identifier,
            )

        return DiscoveredServer(
            name=name,
            identifier=identifier,
            uuid=uuid,
            internal_id=internal_id,
            state=_read_optional_string(attributes.get("current_state")),
            memory_limit_mib=_read_memory_limit(attributes),
        )

    def _panel_unavailable(self, operation: str, exc: Exception) -> PanelUnavailable:
        """Log and convert a caught exception into a user-safe unavailable result.

        This helper is intended to be called from inside an ``except`` block so
        ``logger.exception`` retains the active traceback for unexpected errors.
        """

        if isinstance(exc, (aiohttp.ClientError, PydactylError, TimeoutError)):
            self._logger.warning(
                "Pterodactyl panel unavailable while trying to %s: %s",
                operation,
                exc,
            )
        else:
            self._logger.exception("Unexpected bridge failure while trying to %s", operation)
        return PanelUnavailable(operation=operation)


def _resolve_from_servers(query: str, servers: tuple[DiscoveredServer, ...]) -> ResolveServerResult:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return ServerNotFound(query=query)

    matches = tuple(server for server in servers if _matches_query(server, normalized_query))
    if not matches:
        return ServerNotFound(query=query)
    if len(matches) > 1:
        return AmbiguousServerMatch(query=query, matches=matches)
    return ResolvedServer(query=query, server=matches[0])


def _matches_query(server: DiscoveredServer, normalized_query: str) -> bool:
    return (
        server.name.casefold() == normalized_query
        or server.identifier.casefold() == normalized_query
    )


def _coerce_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        return attributes
    return payload


def _fallback_server_identity(
    prefix: str,
    *,
    identifier: str | None = None,
    uuid: str | None = None,
    internal_id: int | None = None,
) -> str:
    if identifier is not None:
        return f"{prefix}-{identifier}"
    if uuid is not None:
        return f"{prefix}-{uuid}"
    if internal_id is not None:
        return f"{prefix}-{internal_id}"
    return prefix


def _read_optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _read_optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _read_memory_limit(attributes: dict[str, Any]) -> int | None:
    limits = attributes.get("limits")
    if not isinstance(limits, dict):
        return None

    memory_limit = limits.get("memory")
    if isinstance(memory_limit, bool) or not isinstance(memory_limit, int):
        return None
    # 0 means unlimited in Pterodactyl; treat it as unknown for budget checks.
    if memory_limit <= 0:
        return None
    return memory_limit


def _replace_server_state(
    server: DiscoveredServer,
    *,
    current_state: str | None,
) -> DiscoveredServer:
    return replace(
        server,
        state=current_state if current_state is not None else server.state,
    )


def _server_sort_key(server: DiscoveredServer) -> tuple[str, str]:
    return (server.name.casefold(), server.identifier.casefold())


def _is_running_state(state: str | None) -> bool:
    return state is not None and state.casefold() == "running"
