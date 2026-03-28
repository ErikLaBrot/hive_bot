"""Tests for runtime configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from hive_bot.config import (
    AppConfig,
    ConfigError,
    DiscordConfig,
    PolicyConfig,
    PterodactylConfig,
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
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n\n"
            "[logging]\n"
            'level = "debug"\n'
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config == AppConfig(
        discord=DiscordConfig(token="token-value", guild_id=42),
        pterodactyl=PterodactylConfig(
            panel_url="https://panel.example.com",
            api_key="ptlc_test",
        ),
        policy=PolicyConfig(max_running_servers=2, max_total_ram_gb=10),
        log_level="DEBUG",
    )


def test_load_config_uses_default_log_level_when_section_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.log_level == "INFO"


def test_load_config_strips_surrounding_whitespace_from_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "  token-value  "\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = " https://panel.example.com/ "\n'
            'api_key = "  ptlc_test  "\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.discord.token == "token-value"
    assert config.pterodactyl.panel_url == "https://panel.example.com"
    assert config.pterodactyl.api_key == "ptlc_test"


def test_load_config_raises_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.toml"

    with pytest.raises(ConfigError, match="Config file does not exist"):
        load_config(missing_path)


def test_load_config_raises_for_invalid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[discord\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(config_path)


def test_load_config_raises_for_other_read_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    def fake_read_text(self: Path, *, encoding: str) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(ConfigError, match="Could not read config file"):
        load_config(config_path)


def test_load_config_raises_for_missing_required_value(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="discord.token"):
        load_config(config_path)


def test_load_config_raises_for_empty_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "   "\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="discord.token must be a non-empty string"):
        load_config(config_path)


def test_load_config_raises_for_non_string_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            "token = 123\n"
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

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
        (
            "[discord]\n"
            'token = "token-value"\n'
            f"guild_id = {guild_id}\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
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
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n\n"
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
        (
            'logging = "INFO"\n'
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="logging must be a table"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("config_contents", "expected_message"),
    [
        (
            (
                'pterodactyl = "https://panel.example.com"\n\n'
                "[discord]\n"
                'token = "token-value"\n'
                "guild_id = 42\n\n"
                "[policy]\n"
                "max_running_servers = 2\n"
                "max_total_ram_gb = 10\n"
            ),
            "pterodactyl must be a table",
        ),
        (
            (
                "policy = 10\n\n"
                "[discord]\n"
                'token = "token-value"\n'
                "guild_id = 42\n\n"
                "[pterodactyl]\n"
                'panel_url = "https://panel.example.com"\n'
                'api_key = "ptlc_test"\n\n'
            ),
            "policy must be a table",
        ),
    ],
)
def test_load_config_raises_for_invalid_new_sections(
    tmp_path: Path,
    config_contents: str,
    expected_message: str,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_contents, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected_message):
        load_config(config_path)


@pytest.mark.parametrize(
    ("config_contents", "expected_message"),
    [
        (
            (
                "[discord]\n"
                'token = "token-value"\n'
                "guild_id = 42\n\n"
                "[pterodactyl]\n"
                'api_key = "ptlc_test"\n\n'
                "[policy]\n"
                "max_running_servers = 2\n"
                "max_total_ram_gb = 10\n"
            ),
            "pterodactyl.panel_url",
        ),
        (
            (
                "[discord]\n"
                'token = "token-value"\n'
                "guild_id = 42\n\n"
                "[pterodactyl]\n"
                'panel_url = "https://panel.example.com"\n\n'
                "[policy]\n"
                "max_running_servers = 2\n"
                "max_total_ram_gb = 10\n"
            ),
            "pterodactyl.api_key",
        ),
    ],
)
def test_load_config_raises_for_missing_pterodactyl_values(
    tmp_path: Path,
    config_contents: str,
    expected_message: str,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_contents, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected_message):
        load_config(config_path)


def test_load_config_raises_for_panel_url_without_http_scheme(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="pterodactyl.panel_url must be a valid http:// or https:// URL",
    ):
        load_config(config_path)


def test_load_config_raises_for_panel_url_without_host(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            "max_running_servers = 2\n"
            "max_total_ram_gb = 10\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="pterodactyl.panel_url must be a valid http:// or https:// URL",
    ):
        load_config(config_path)


@pytest.mark.parametrize(
    ("max_running_servers", "max_total_ram_gb", "expected_message"),
    [
        ("0", "10", "policy.max_running_servers must be a positive integer"),
        ("2", "0", "policy.max_total_ram_gb must be a positive integer"),
        ("true", "10", "policy.max_running_servers must be a positive integer"),
    ],
)
def test_load_config_raises_for_invalid_policy_values(
    tmp_path: Path,
    max_running_servers: str,
    max_total_ram_gb: str,
    expected_message: str,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "[discord]\n"
            'token = "token-value"\n'
            "guild_id = 42\n\n"
            "[pterodactyl]\n"
            'panel_url = "https://panel.example.com"\n'
            'api_key = "ptlc_test"\n\n'
            "[policy]\n"
            f"max_running_servers = {max_running_servers}\n"
            f"max_total_ram_gb = {max_total_ram_gb}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected_message):
        load_config(config_path)


def test_policy_config_converts_gib_to_mib() -> None:
    policy = PolicyConfig(max_running_servers=2, max_total_ram_gb=10)

    assert policy.max_total_ram_mib == 10240


def test_require_mapping_reraises_when_default_is_not_provided() -> None:
    with pytest.raises(ConfigError, match="missing.value"):
        _require_mapping({}, ("missing", "value"))


def test_require_mapping_raises_when_value_is_not_a_table() -> None:
    with pytest.raises(ConfigError, match="logging must be a table"):
        _require_mapping({"logging": "INFO"}, ("logging",))
