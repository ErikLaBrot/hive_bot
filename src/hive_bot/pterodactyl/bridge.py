"""Discovery-first bridge for the Pterodactyl client API."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import replace
from typing import Any, Protocol, cast

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
    ActionMonitorError,
    ActionMonitorResult,
    ActionMonitorSuccess,
    ActionMonitorTimeout,
    ActionMonitorUnconfirmed,
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
MONITOR_POLL_INTERVAL_SECONDS = 3.0
MONITOR_INACTIVITY_TIMEOUT_SECONDS = 15.0
MONITOR_HARD_TIMEOUT_SECONDS = 120.0


class MonitorWebsocketProtocol(Protocol):
    """Connected websocket interface used by completion monitoring."""

    async def authenticate(self) -> None:
        """Send websocket authentication using the temporary token."""

    async def request_stats(self) -> None:
        """Request stats events from the websocket."""

    def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded websocket events."""

    async def close(self) -> None:
        """Close the websocket connection."""


class WebsocketConnector(Protocol):
    """Callable interface for opening a connected server websocket."""

    async def __call__(
        self,
        *,
        socket_url: str,
        token: str,
        panel_url: str,
    ) -> MonitorWebsocketProtocol:
        """Open and return a connected websocket."""


class PterodactylBridge:
    """Encapsulate discovery-first access to Pterodactyl."""

    def __init__(
        self,
        config: PterodactylConfig,
        policy: PolicyConfig,
        *,
        client_factory: ClientFactory = create_client,
        websocket_connector: WebsocketConnector | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._policy = policy
        self._client_factory = client_factory
        self._websocket_connector = (
            _connect_monitor_websocket if websocket_connector is None else websocket_connector
        )
        self._logger = LOGGER if logger is None else logger

    async def discover_servers(self) -> DiscoverServersResult:
        """Return the servers currently discoverable by the client key."""

        try:
            async with self._open_client() as client:
                servers = await self._discover_live_servers_in_session(
                    client,
                    tolerate_state_failures=True,
                )
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

        try:
            async with self._open_client() as client:
                live_servers = await self._discover_live_servers_in_session(
                    client,
                    tolerate_state_failures=True,
                )
        except Exception as exc:
            return self._panel_unavailable("discover servers", exc)

        return self._build_budget_status(live_servers)

    async def start_server(self, query: str) -> ActionResult:
        """Start a resolved server if policy checks allow it."""

        try:
            async with self._open_client() as client:
                try:
                    live_servers = await self._discover_live_servers_in_session(
                        client,
                        tolerate_state_failures=False,
                    )
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                resolve_result = _resolve_from_servers(query, live_servers)
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

                budget_status = self._build_budget_status(live_servers)
                if budget_status.running_server_count >= self._policy.max_running_servers:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="max-running-servers",
                        server=target_server,
                        running_server_count=budget_status.running_server_count,
                        max_running_servers=self._policy.max_running_servers,
                    )

                if target_server.memory_limit_mib is None:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="missing-target-memory-limit",
                        server=target_server,
                    )

                if not budget_status.has_complete_memory_data:
                    return ServerActionDenied(
                        action="start",
                        query=query,
                        reason="missing-running-memory-limits",
                        server=target_server,
                        missing_memory_limit_servers=budget_status.missing_memory_limit_servers,
                    )

                required_memory_mib = target_server.memory_limit_mib
                assert budget_status.remaining_memory_mib is not None
                remaining_memory_mib = budget_status.remaining_memory_mib
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
                return ServerActionAccepted(
                    action="start",
                    query=query,
                    server=target_server,
                )
        except Exception as exc:
            return self._panel_unavailable("start server", exc)

    async def stop_server(self, query: str) -> ActionResult:
        """Stop a resolved server if it is currently running."""

        try:
            async with self._open_client() as client:
                try:
                    live_servers = await self._discover_live_servers_in_session(
                        client,
                        tolerate_state_failures=False,
                    )
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                resolve_result = _resolve_from_servers(query, live_servers)
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
                return ServerActionAccepted(
                    action="stop",
                    query=query,
                    server=target_server,
                )
        except Exception as exc:
            return self._panel_unavailable("stop server", exc)

    async def restart_server(self, query: str) -> ActionResult:
        """Restart a resolved server if it is currently running."""

        try:
            async with self._open_client() as client:
                try:
                    live_servers = await self._discover_live_servers_in_session(
                        client,
                        tolerate_state_failures=False,
                    )
                except Exception as exc:
                    return self._panel_unavailable("discover servers", exc)

                resolve_result = _resolve_from_servers(query, live_servers)
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
                return ServerActionAccepted(
                    action="restart",
                    query=query,
                    server=target_server,
                )
        except Exception as exc:
            return self._panel_unavailable("restart server", exc)

    async def monitor_action(self, accepted_result: ServerActionAccepted) -> ActionMonitorResult:
        """Watch an accepted power action until success or manual handoff."""

        server = accepted_result.server
        action = accepted_result.action

        try:
            async with self._open_client() as client:
                try:
                    websocket_info = await client.client.servers.get_websocket(server.identifier)
                    socket_url, token = _read_websocket_credentials(websocket_info)
                    websocket = await self._websocket_connector(
                        socket_url=socket_url,
                        token=token,
                        panel_url=self._config.panel_url,
                    )
                    await websocket.authenticate()
                    await websocket.request_stats()
                except Exception as exc:
                    self._logger.warning(
                        "Could not start websocket monitoring for %s (%s) after %s: %s",
                        server.name,
                        server.identifier,
                        action,
                        exc,
                    )
                    return ActionMonitorUnconfirmed(
                        action=action,
                        server=server,
                        reason="websocket-setup-failed",
                        last_state=server.state,
                    )

                activity = _WebsocketActivityTracker()
                listener_task = asyncio.create_task(
                    self._consume_websocket_events(websocket, activity=activity)
                )
                try:
                    return await self._wait_for_terminal_action_state(
                        client,
                        accepted_result=accepted_result,
                        activity=activity,
                    )
                except Exception as exc:
                    self._logger.exception(
                        "Unexpected monitoring failure after %s for %s (%s)",
                        action,
                        server.name,
                        server.identifier,
                    )
                    return ActionMonitorError(
                        action=action,
                        server=server,
                        reason=_exception_reason(exc),
                    )
                finally:
                    listener_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await listener_task
                    with suppress(Exception):
                        await websocket.close()
        except Exception as exc:
            self._logger.exception(
                "Unexpected monitor client failure after %s for %s (%s)",
                action,
                server.name,
                server.identifier,
            )
            return ActionMonitorError(
                action=action,
                server=server,
                reason=_exception_reason(exc),
            )

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

    async def _discover_live_servers_in_session(
        self,
        client: AsyncPterodactylClientProtocol,
        *,
        tolerate_state_failures: bool,
    ) -> tuple[DiscoveredServer, ...]:
        discovered_servers = await self._discover_servers_in_session(client)
        live_servers: list[DiscoveredServer] = []

        for server in discovered_servers:
            try:
                current_state = await self._get_live_state_in_session(
                    client,
                    server.identifier,
                    require_state=not tolerate_state_failures,
                )
            except Exception:
                if not tolerate_state_failures:
                    raise
                self._logger.warning(
                    "Could not fetch live state for %s (%s); showing unknown in inventory",
                    server.name,
                    server.identifier,
                )
                live_servers.append(replace(server, state=None))
                continue

            live_servers.append(_replace_server_state(server, current_state=current_state))

        return tuple(live_servers)

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

    async def _get_live_state_in_session(
        self,
        client: AsyncPterodactylClientProtocol,
        server_identifier: str,
        *,
        require_state: bool,
    ) -> str | None:
        utilization = await client.client.servers.get_server_utilization(server_identifier)
        current_state = _read_optional_string(_coerce_attributes(utilization).get("current_state"))
        if current_state is None and require_state:
            raise RuntimeError(f"Missing live current_state for server {server_identifier}")
        return current_state

    async def _consume_websocket_events(
        self,
        websocket: Any,
        *,
        activity: _WebsocketActivityTracker,
    ) -> None:
        async for _event in websocket.listen():
            activity.mark_event()

    async def _wait_for_terminal_action_state(
        self,
        client: AsyncPterodactylClientProtocol,
        *,
        accepted_result: ServerActionAccepted,
        activity: _WebsocketActivityTracker,
    ) -> ActionMonitorResult:
        action = accepted_result.action
        server = accepted_result.server
        last_state = server.state
        restart_left_running = False
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        while True:
            now = loop.time()
            if now - start_time >= MONITOR_HARD_TIMEOUT_SECONDS:
                return ActionMonitorTimeout(
                    action=action,
                    server=server,
                    timeout_kind="hard-timeout",
                    last_state=last_state,
                )
            if activity.seconds_since_event(now) >= MONITOR_INACTIVITY_TIMEOUT_SECONDS:
                return await self._handle_inactivity_timeout(
                    client,
                    accepted_result=accepted_result,
                    last_state=last_state,
                )

            current_state = await self._get_live_state_in_session(
                client,
                server.identifier,
                require_state=True,
            )
            assert current_state is not None
            last_state = current_state
            if action == "start" and _is_running_state(current_state):
                return ActionMonitorSuccess(
                    action=action,
                    server=_replace_server_state(server, current_state=current_state),
                    final_state=current_state,
                )
            if action == "stop" and _is_offline_state(current_state):
                return ActionMonitorSuccess(
                    action=action,
                    server=_replace_server_state(server, current_state=current_state),
                    final_state=current_state,
                )
            if action == "restart":
                if not _is_running_state(current_state):
                    restart_left_running = True
                elif restart_left_running:
                    return ActionMonitorSuccess(
                        action=action,
                        server=_replace_server_state(server, current_state=current_state),
                        final_state=current_state,
                    )

            sleep_seconds = min(
                MONITOR_POLL_INTERVAL_SECONDS,
                MONITOR_HARD_TIMEOUT_SECONDS - (now - start_time),
                MONITOR_INACTIVITY_TIMEOUT_SECONDS - activity.seconds_since_event(now),
            )
            if sleep_seconds <= 0:
                continue
            await asyncio.sleep(sleep_seconds)

    async def _handle_inactivity_timeout(
        self,
        client: AsyncPterodactylClientProtocol,
        *,
        accepted_result: ServerActionAccepted,
        last_state: str | None,
    ) -> ActionMonitorResult:
        action = accepted_result.action
        server = accepted_result.server

        # The websocket is tied to the current server process, so a clean stop
        # can legitimately make it go quiet. Double-check the panel once before
        # declaring the action unconfirmed.
        if action == "stop":
            try:
                current_state = await self._get_live_state_in_session(
                    client,
                    server.identifier,
                    require_state=False,
                )
            except Exception:
                current_state = last_state
            if _is_offline_state(current_state):
                assert current_state is not None
                return ActionMonitorSuccess(
                    action=action,
                    server=_replace_server_state(server, current_state=current_state),
                    final_state=current_state,
                )
            last_state = current_state if current_state is not None else last_state

        return ActionMonitorTimeout(
            action=action,
            server=server,
            timeout_kind="inactivity-timeout",
            last_state=last_state,
        )

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


class _AiohttpMonitorWebsocket:
    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        websocket: aiohttp.ClientWebSocketResponse,
        token: str,
    ) -> None:
        self._session = session
        self._websocket = websocket
        self._token = token

    async def authenticate(self) -> None:
        await self._websocket.send_json({"event": "auth", "args": [self._token]})

    async def request_stats(self) -> None:
        await self._websocket.send_json({"event": "send stats", "args": []})

    async def close(self) -> None:
        await self._websocket.close()
        await self._session.close()

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        async for message in self._websocket:
            if message.type == aiohttp.WSMsgType.TEXT:
                try:
                    payload = json.loads(message.data)
                except ValueError:
                    continue
                if isinstance(payload, dict):
                    yield payload
            elif message.type == aiohttp.WSMsgType.ERROR:
                break


async def _connect_monitor_websocket(
    *,
    socket_url: str,
    token: str,
    panel_url: str,
) -> MonitorWebsocketProtocol:
    session = aiohttp.ClientSession()
    try:
        websocket = await session.ws_connect(
            socket_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": panel_url,
            },
        )
    except Exception:
        await session.close()
        raise
    return _AiohttpMonitorWebsocket(
        session=session,
        websocket=websocket,
        token=token,
    )


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


def _read_websocket_credentials(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Missing websocket data payload")

    socket_url = _read_optional_string(data.get("socket"))
    token = _read_optional_string(data.get("token"))
    if socket_url is None or token is None:
        raise RuntimeError("Missing websocket socket URL or token")
    return socket_url, token


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


class _WebsocketActivityTracker:
    def __init__(self) -> None:
        self._last_event_at = asyncio.get_running_loop().time()

    def mark_event(self) -> None:
        self._last_event_at = asyncio.get_running_loop().time()

    def seconds_since_event(self, now: float) -> float:
        return now - self._last_event_at


def _is_running_state(state: str | None) -> bool:
    return state is not None and state.casefold() == "running"


def _is_offline_state(state: str | None) -> bool:
    return state is not None and state.casefold() == "offline"


def _exception_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__
