"""Logging setup helpers."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str) -> None:
    """Configure the root logger for the application."""

    logging.basicConfig(level=getattr(logging, level), format=LOG_FORMAT, force=True)

