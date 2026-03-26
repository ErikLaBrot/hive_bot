"""Tests for logging configuration."""

from __future__ import annotations

import logging
from typing import Any

from hive_bot.logging_config import LOG_FORMAT, configure_logging


def test_configure_logging_calls_basic_config(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_basic_config(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)

    configure_logging("INFO")

    assert calls == [{"level": "INFO", "format": LOG_FORMAT, "force": True}]
