"""Tests for runtime configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from hive_bot.config import (
    AppConfig,
    ConfigError,
    DiscordConfig,
    _require_mapping,
    load_config,
)


def test_load_config_reads_valid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[logging]\n"
            'level = "debug"\n'
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config == AppConfig(
        discord=DiscordConfig(token="token-value", guild_id=42),
        log_level="DEBUG",
    )


def test_load_config_uses_default_log_level_when_section_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[discord]\ntoken = "token-value"\nguild_id = 42\n', encoding="utf-8")

    config = load_config(config_path)

    assert config.log_level == "INFO"


def test_load_config_raises_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.toml"

    with pytest.raises(ConfigError, match="Config file does not exist"):
        load_config(missing_path)


def test_load_config_raises_for_invalid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[discord\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(config_path)


def test_load_config_raises_for_other_read_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    def fake_read_text(self: Path, *, encoding: str) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(ConfigError, match="Could not read config file"):
        load_config(config_path)


def test_load_config_raises_for_missing_required_value(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[discord]\nguild_id = 42\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="discord.token"):
        load_config(config_path)


def test_load_config_raises_for_empty_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[discord]\ntoken = "   "\nguild_id = 42\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="discord.token must be a non-empty string"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("guild_id", "expected_message"),
    [
        ("0", "discord.guild_id must be a positive integer"),
        ("true", "discord.guild_id must be a positive integer"),
        ('"abc"', "discord.guild_id must be a positive integer"),
    ],
)
def test_load_config_raises_for_invalid_guild_id(
    tmp_path: Path,
    guild_id: str,
    expected_message: str,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[discord]\ntoken = "token-value"\nguild_id = {guild_id}\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected_message):
        load_config(config_path)


@pytest.mark.parametrize(
    ("log_level", "expected_message"),
    [
        ("10", "logging.level must be a string"),
        ('"verbose"', "logging.level must be one of"),
    ],
)
def test_load_config_raises_for_invalid_log_level(
    tmp_path: Path,
    log_level: str,
    expected_message: str,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[logging]\n"
            f"level = {log_level}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected_message):
        load_config(config_path)


def test_load_config_raises_for_logging_section_that_is_not_a_table(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'logging = "INFO"\n[discord]\ntoken = "token-value"\nguild_id = 42\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="logging must be a table"):
        load_config(config_path)


def test_require_mapping_reraises_when_default_is_not_provided() -> None:
    with pytest.raises(ConfigError, match="missing.value"):
        _require_mapping({}, ("missing", "value"))


def test_require_mapping_raises_when_value_is_not_a_table() -> None:
    with pytest.raises(ConfigError, match="logging must be a table"):
        _require_mapping({"logging": "INFO"}, ("logging",))
