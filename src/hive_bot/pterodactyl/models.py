"""Structured result types for Pterodactyl bridge operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiscoveredServer:
    """A server discovered from the live Pterodactyl inventory."""

    name: str
    identifier: str
    uuid: str | None
    internal_id: int | None
    state: str | None
    memory_limit_mib: int | None


@dataclass(frozen=True, slots=True)
class PanelUnavailable:
    """Pterodactyl could not be reached for the requested operation."""

    operation: str
    message: str = "Pterodactyl panel is currently unreachable."


@dataclass(frozen=True, slots=True)
class DiscoveredServers:
    """Collection of servers discovered from the panel."""

    servers: tuple[DiscoveredServer, ...]


@dataclass(frozen=True, slots=True)
class ResolvedServer:
    """A single server resolved from a user query."""

    query: str
    server: DiscoveredServer


@dataclass(frozen=True, slots=True)
class ServerNotFound:
    """No discovered server matched the requested query."""

    query: str


@dataclass(frozen=True, slots=True)
class AmbiguousServerMatch:
    """Multiple discovered servers matched the requested query."""

    query: str
    matches: tuple[DiscoveredServer, ...]


@dataclass(frozen=True, slots=True)
class ServerStatus:
    """Current status information for a single resolved server."""

    server: DiscoveredServer


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    """Current policy budget summary based on live discovery.

    `remaining_memory_mib` is signed. Negative values indicate the currently
    running discovered servers already exceed the configured RAM ceiling.
    """

    max_running_servers: int
    max_total_ram_gb: int
    running_server_count: int
    running_servers: tuple[DiscoveredServer, ...]
    consumed_memory_mib: int | None
    remaining_memory_mib: int | None
    has_complete_memory_data: bool
    missing_memory_limit_servers: tuple[DiscoveredServer, ...]


@dataclass(frozen=True, slots=True)
class ServerActionAccepted:
    """A power action request was accepted for a resolved server."""

    action: str
    query: str
    server: DiscoveredServer


@dataclass(frozen=True, slots=True)
class ServerActionNoOp:
    """A power action resolved cleanly but did not need to change state."""

    action: str
    query: str
    server: DiscoveredServer
    reason: str


@dataclass(frozen=True, slots=True)
class ServerActionDenied:
    """A power action was denied after validation or policy checks."""

    action: str
    query: str
    reason: str
    server: DiscoveredServer | None = None
    running_server_count: int | None = None
    max_running_servers: int | None = None
    required_memory_mib: int | None = None
    remaining_memory_mib: int | None = None
    missing_memory_limit_servers: tuple[DiscoveredServer, ...] = ()


type DiscoverServersResult = DiscoveredServers | PanelUnavailable
type ResolveServerResult = ResolvedServer | ServerNotFound | AmbiguousServerMatch | PanelUnavailable
type ServerStatusResult = ServerStatus | ServerNotFound | AmbiguousServerMatch | PanelUnavailable
type BudgetResult = BudgetStatus | PanelUnavailable
type ActionResult = (
    ServerActionAccepted
    | ServerActionNoOp
    | ServerActionDenied
    | ServerNotFound
    | AmbiguousServerMatch
    | PanelUnavailable
)
