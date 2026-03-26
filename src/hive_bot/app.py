"""Application startup entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from hive_bot.config import DEFAULT_CONFIG_PATH, AppConfig, ConfigError, load_config
from hive_bot.logging_config import configure_logging

LOGGER = logging.getLogger(__name__)


def bootstrap_application(
    config_path: Path,
    *,
    config_loader: Callable[[Path], AppConfig] = load_config,
    logging_configurer: Callable[[str], None] = configure_logging,
) -> AppConfig:
    """Load configuration and initialize application logging."""

    config = config_loader(config_path)
    logging_configurer(config.log_level)
    LOGGER.info("Application bootstrap complete for guild %s", config.discord.guild_id)
    return config


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the application entrypoint."""

    parser = argparse.ArgumentParser(description="Start the hive_bot application bootstrap.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the local TOML configuration file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application entrypoint."""

    args = build_parser().parse_args(argv)
    try:
        bootstrap_application(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    return 0

