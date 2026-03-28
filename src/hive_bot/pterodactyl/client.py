"""Thin wrappers for creating Pterodactyl API clients."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, cast

from pydactyl import AsyncPterodactylClient  # type: ignore[import-untyped]

from hive_bot.config import PterodactylConfig

LOGGER = logging.getLogger(__name__)


class AsyncPaginatedResponse(Protocol):
    """Protocol for paginated py-dactyl responses."""

    async def collect_async(self) -> list[Any]:
        """Collect all pages into a single list."""


class AsyncServerApi(Protocol):
    """Subset of the py-dactyl client API used by the bridge."""

    async def list_servers(
        self,
        includes: Iterable[str] | None = None,
        params: dict[str, object] | None = None,
    ) -> AsyncPaginatedResponse | list[dict[str, Any]]:
        """List servers available to the client key."""

    async def get_server(
        self,
        server_id: str,
        detail: bool = False,
        includes: Iterable[str] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        """Fetch details for a single server."""

    async def get_server_utilization(self, server_id: str, detail: bool = False) -> dict[str, Any]:
        """Fetch resource utilization for a single server."""

    async def send_power_action(self, server_id: str, signal: str) -> object:
        """Send a power signal to a single server."""


class AsyncClientApi(Protocol):
    """Subset of the py-dactyl client namespace used by the bridge."""

    @property
    def servers(self) -> AsyncServerApi:
        """Return the client server API."""


class AsyncPterodactylClientProtocol(Protocol):
    """Async context manager protocol for py-dactyl clients."""

    @property
    def client(self) -> AsyncClientApi:
        """Return the client-scoped API namespace."""

    async def __aenter__(self) -> AsyncPterodactylClientProtocol:
        """Enter an async client session."""

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the async client session."""


type ClientContextManager = AbstractAsyncContextManager[AsyncPterodactylClientProtocol]


class ClientFactory(Protocol):
    """Callable interface for constructing short-lived Pterodactyl clients."""

    def __call__(
        self,
        config: PterodactylConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> ClientContextManager:
        """Create an async client context manager for the provided config."""


def create_client(
    config: PterodactylConfig,
    *,
    logger: logging.Logger | None = None,
) -> ClientContextManager:
    """Construct a short-lived async py-dactyl client."""

    return cast(
        ClientContextManager,
        AsyncPterodactylClient(
            url=config.panel_url,
            api_key=config.api_key,
            logger=LOGGER if logger is None else logger,
        ),
    )
