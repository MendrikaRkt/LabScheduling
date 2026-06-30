"""Centralized logging configuration for the application.

Loads ``config/logging.yaml`` (dictConfig format) and applies it. The log
level can be overridden at runtime with the ``LOG_LEVEL`` environment variable
(for example ``LOG_LEVEL=DEBUG``), which is convenient in production where the
configuration file is baked into the image.

Usage::

    from infrastructure.logging_config import setup_logging
    setup_logging()              # call once, at process start-up

Then in any module::

    import logging
    logger = logging.getLogger(__name__)
"""
from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path
from typing import Optional

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "logging.yaml"

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_configured = False


def _ensure_log_dir(config: dict) -> None:
    """Create parent directories for every file-based handler.

    RotatingFileHandler does not create missing directories, so we create them
    up front to avoid a start-up crash when ``logs/`` does not exist yet.
    """
    for handler in config.get("handlers", {}).values():
        filename = handler.get("filename")
        if filename:
            path = Path(filename)
            if not path.is_absolute():
                path = _PROJECT_ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            handler["filename"] = str(path)


def _apply_level_override(config: dict, level: str) -> None:
    """Force every logger and handler to the requested level."""
    config.setdefault("root", {})["level"] = level
    for logger_cfg in config.get("loggers", {}).values():
        logger_cfg["level"] = level
    for handler in config.get("handlers", {}).values():
        # Keep dedicated error handlers at ERROR so they stay focused.
        if handler.get("level") != "ERROR":
            handler["level"] = level


def setup_logging(config_path: Optional[str] = None,
                level: Optional[str] = None,
                force: bool = False) -> None:
    """Configure logging for the whole application.

    Args:
        config_path: optional path to a dictConfig YAML file. Defaults to
            ``config/logging.yaml``.
        level: optional log level override. Falls back to the ``LOG_LEVEL``
            environment variable, then to the value declared in the file.
        force: re-apply the configuration even if it was already applied.
    """
    global _configured
    if _configured and not force:
        return

    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    env_level = (level or os.getenv("LOG_LEVEL", "")).strip().upper()

    try:
        with open(path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        _ensure_log_dir(config)
        if env_level in _VALID_LEVELS:
            _apply_level_override(config, env_level)
        logging.config.dictConfig(config)
    except Exception as exc:  # pragma: no cover - defensive fallback
        # Never let logging setup crash the application: fall back to a basic
        # console configuration so the process can still start and report.
        logging.basicConfig(
            level=env_level if env_level in _VALID_LEVELS else "INFO",
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logging.getLogger(__name__).warning(
            "Falling back to basic logging config (%s): %s", path, exc)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger, setting up logging on first use."""
    if not _configured:
        setup_logging()
    return logging.getLogger(name)
