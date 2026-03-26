"""Runtime configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

DEFAULT_CONFIG_PATH = Path("config.local.toml")
VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ConfigError(ValueError):
    """Raised when runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class DiscordConfig:
    """Discord-related runtime settings."""

    token: str
    guild_id: int


@dataclass(frozen=True)
class AppConfig:
    """Top-level runtime settings."""

    discord: DiscordConfig
    log_level: str = "INFO"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load and validate application configuration from TOML."""

    try:
        config_data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {path}") from exc

    return AppConfig(
        discord=DiscordConfig(
            token=_require_non_empty_string(config_data, ("discord", "token")),
            guild_id=_require_positive_int(config_data, ("discord", "guild_id")),
        ),
        log_level=_read_log_level(config_data),
    )


def _read_log_level(config_data: dict[str, object]) -> str:
    logging_section = _require_mapping(config_data, ("logging",), default={})
    raw_level = logging_section.get("level", "INFO")
    if not isinstance(raw_level, str):
        raise ConfigError("logging.level must be a string")

    normalized_level = raw_level.upper()
    if normalized_level not in VALID_LOG_LEVELS:
        supported = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigError(f"logging.level must be one of: {supported}")

    return normalized_level


def _require_non_empty_string(config_data: dict[str, object], path: tuple[str, ...]) -> str:
    value = _resolve_path(config_data, path)
    if not isinstance(value, str) or not value.strip():
        dotted_path = ".".join(path)
        raise ConfigError(f"{dotted_path} must be a non-empty string")
    return value


def _require_positive_int(config_data: dict[str, object], path: tuple[str, ...]) -> int:
    value = _resolve_path(config_data, path)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        dotted_path = ".".join(path)
        raise ConfigError(f"{dotted_path} must be a positive integer")
    return value


def _require_mapping(
    config_data: dict[str, object],
    path: tuple[str, ...],
    *,
    default: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        value = _resolve_path(config_data, path)
    except ConfigError:
        if default is not None:
            return default
        raise

    if not isinstance(value, dict):
        dotted_path = ".".join(path)
        raise ConfigError(f"{dotted_path} must be a table")

    return value


def _resolve_path(config_data: dict[str, object], path: tuple[str, ...]) -> object:
    value: object = config_data
    for part in path:
        if not isinstance(value, dict) or part not in value:
            dotted_path = ".".join(path)
            raise ConfigError(f"Missing required config value: {dotted_path}")
        value = value[part]
    return value
