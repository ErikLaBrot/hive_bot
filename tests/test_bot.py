"""Tests for Discord client construction and startup."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from hive_bot.bot import create_bot, run_bot
from hive_bot.config import AppConfig, DiscordConfig


class FakeIntents:
    default_calls = 0

    @classmethod
    def default(cls) -> str:
        cls.default_calls += 1
        return "default-intents"


class FakeObject:
    def __init__(self, *, id: int) -> None:
        self.id = id


class FakeBot:
    def __init__(self, *, command_prefix: Any, intents: Any) -> None:
        self.command_prefix = command_prefix
        self.intents = intents
        self.tree = "tree"
        self.user: Any = None
        self.run_calls: list[tuple[str, Any]] = []

    def run(self, token: str, *, log_handler: Any) -> None:
        self.run_calls.append((token, log_handler))


class FakeCommandsModule:
    when_mentioned = "when-mentioned"
    Bot = FakeBot


class FakeDiscordModule:
    Intents = FakeIntents
    Object = FakeObject
    app_commands = "app-commands-module"


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id

    def __str__(self) -> str:
        return "HiveBot"


def build_config() -> AppConfig:
    return AppConfig(discord=DiscordConfig(token="token-value", guild_id=42), log_level="INFO")


def test_create_bot_builds_discord_bot_with_default_intents() -> None:
    FakeIntents.default_calls = 0
    register_calls: list[tuple[Any, Any]] = []
    sync_calls: list[tuple[Any, Any]] = []

    def fake_register_commands(tree: Any, *, app_commands_module: Any) -> None:
        register_calls.append((tree, app_commands_module))

    async def fake_sync_commands(tree: Any, *, guild: Any) -> list[str]:
        sync_calls.append((tree, guild))
        return ["ping"]

    bot = create_bot(
        build_config(),
        discord_module=FakeDiscordModule,
        commands_module=FakeCommandsModule,
        register_commands_func=fake_register_commands,
        sync_commands_func=fake_sync_commands,
    )

    assert bot.command_prefix == "when-mentioned"
    assert bot.intents == "default-intents"
    assert FakeIntents.default_calls == 1

    asyncio.run(bot.setup_hook())

    assert register_calls == [("tree", "app-commands-module")]
    assert len(sync_calls) == 1
    assert sync_calls[0][0] == "tree"
    assert isinstance(sync_calls[0][1], FakeObject)
    assert sync_calls[0][1].id == 42


def test_create_bot_logs_ready_state_with_connected_user(
    caplog: Any,
) -> None:
    bot = create_bot(
        build_config(),
        discord_module=FakeDiscordModule,
        commands_module=FakeCommandsModule,
    )
    bot.user = FakeUser(9001)

    with caplog.at_level(logging.INFO):
        asyncio.run(bot.on_ready())

    assert "Discord client ready as HiveBot (9001)" in caplog.text


def test_create_bot_logs_ready_state_without_user(caplog: Any) -> None:
    bot = create_bot(
        build_config(),
        discord_module=FakeDiscordModule,
        commands_module=FakeCommandsModule,
    )

    with caplog.at_level(logging.INFO):
        asyncio.run(bot.on_ready())

    assert "Discord client is ready" in caplog.text


def test_run_bot_starts_client_with_configured_token() -> None:
    config = build_config()
    created_bots: list[FakeBot] = []

    def fake_bot_factory(received_config: AppConfig) -> FakeBot:
        assert received_config == config
        bot = FakeBot(command_prefix="when-mentioned", intents="default-intents")
        created_bots.append(bot)
        return bot

    run_bot(config, bot_factory=fake_bot_factory)

    assert len(created_bots) == 1
    assert created_bots[0].run_calls == [("token-value", None)]
