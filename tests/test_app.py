"""Tests for the application entrypoint."""

from __future__ import annotations

from pathlib import Path
import runpy

import pytest

from hive_bot import app
from hive_bot.config import AppConfig, ConfigError, DiscordConfig


def test_bootstrap_application_loads_config_and_logging() -> None:
    config = AppConfig(discord=DiscordConfig(token="token-value", guild_id=42), log_level="DEBUG")
    received_paths: list[Path] = []
    log_levels: list[str] = []

    def fake_config_loader(path: Path) -> AppConfig:
        received_paths.append(path)
        return config

    def fake_logging_configurer(level: str) -> None:
        log_levels.append(level)

    result = app.bootstrap_application(
        Path("config.local.toml"),
        config_loader=fake_config_loader,
        logging_configurer=fake_logging_configurer,
    )

    assert result is config
    assert received_paths == [Path("config.local.toml")]
    assert log_levels == ["DEBUG"]


def test_build_parser_uses_expected_default() -> None:
    parser = app.build_parser()

    parsed = parser.parse_args([])

    assert parsed.config == Path("config.local.toml")


def test_main_returns_zero_for_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    received_paths: list[Path] = []

    def fake_bootstrap_application(config_path: Path) -> AppConfig:
        received_paths.append(config_path)
        return AppConfig(discord=DiscordConfig(token="token-value", guild_id=42))

    monkeypatch.setattr(app, "bootstrap_application", fake_bootstrap_application)

    result = app.main(["--config", "custom.toml"])

    assert result == 0
    assert received_paths == [Path("custom.toml")]


def test_main_returns_error_for_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_bootstrap_application(config_path: Path) -> AppConfig:
        raise ConfigError(f"bad config: {config_path}")

    monkeypatch.setattr(app, "bootstrap_application", fake_bootstrap_application)

    result = app.main(["--config", "broken.toml"])

    assert result == 2
    assert "Configuration error: bad config: broken.toml" in capsys.readouterr().err


def test_module_entrypoint_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(app, "main", fake_main)

    try:
        runpy.run_module("hive_bot", run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0

    assert calls == [None]
