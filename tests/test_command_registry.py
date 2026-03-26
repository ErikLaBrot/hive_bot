"""Tests for slash command registration infrastructure."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from hive_bot.command_registry import register_commands, sync_commands


class FakeCommandTree:
    def __init__(self) -> None:
        self.added_commands: list[tuple[Any, bool]] = []
        self.copied_guilds: list[Any] = []
        self.synced_guilds: list[Any] = []
        self.sync_result: list[Any] = ["ping"]

    def add_command(self, command: Any, *, override: bool) -> None:
        self.added_commands.append((command, override))

    def copy_global_to(self, *, guild: Any) -> None:
        self.copied_guilds.append(guild)

    async def sync(self, *, guild: Any) -> list[Any]:
        self.synced_guilds.append(guild)
        return self.sync_result


class FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


def test_register_commands_adds_ping_command(monkeypatch: Any) -> None:
    tree = FakeCommandTree()
    received_modules: list[Any] = []

    def fake_build_ping_command(*, app_commands_module: Any) -> str:
        received_modules.append(app_commands_module)
        return "ping-command"

    monkeypatch.setattr("hive_bot.command_registry.build_ping_command", fake_build_ping_command)

    register_commands(tree, app_commands_module="app-commands-module")

    assert received_modules == ["app-commands-module"]
    assert tree.added_commands == [("ping-command", True)]


def test_sync_commands_copies_globals_and_syncs(caplog: Any) -> None:
    tree = FakeCommandTree()
    guild = FakeGuild(202)

    with caplog.at_level(logging.INFO):
        synced_commands = asyncio.run(sync_commands(tree, guild=guild))

    assert synced_commands == ["ping"]
    assert tree.copied_guilds == [guild]
    assert tree.synced_guilds == [guild]
    assert "Synced 1 commands to guild 202" in caplog.text
