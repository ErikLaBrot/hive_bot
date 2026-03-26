"""Tests for the `/ping` slash command."""

from __future__ import annotations

import asyncio
from typing import Any

from hive_bot.commands.ping import build_ping_command, handle_ping


class FakeResponse:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, message: str) -> None:
        self.messages.append(message)


class FakeInteraction:
    def __init__(self) -> None:
        self.response = FakeResponse()


class FakeCommand:
    def __init__(self, *, name: str, description: str, callback: Any) -> None:
        self.name = name
        self.description = description
        self.callback = callback


class FakeAppCommandsModule:
    @staticmethod
    def command(*, name: str, description: str) -> Any:
        def decorator(callback: Any) -> FakeCommand:
            return FakeCommand(name=name, description=description, callback=callback)

        return decorator


def test_handle_ping_responds_with_pong() -> None:
    interaction = FakeInteraction()

    asyncio.run(handle_ping(interaction))

    assert interaction.response.messages == ["pong"]


def test_build_ping_command_creates_named_command() -> None:
    command = build_ping_command(app_commands_module=FakeAppCommandsModule)
    interaction = FakeInteraction()

    asyncio.run(command.callback(interaction))

    assert command.name == "ping"
    assert command.description == "Respond with pong"
    assert interaction.response.messages == ["pong"]
