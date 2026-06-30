"""Shared logging configuration.

Each service logs to both stdout (captured by journald under systemd) and a
rotating file under ``LOG_DIR``. If ``LOG_DIR`` is not writable (e.g. running
locally without root), we fall back to a ``logs/`` directory beside the project.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from . import config

_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S %z"


def _resolve_log_dir() -> str:
    candidates = [
        config.LOG_DIR,
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs"),
    ]
    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            # Confirm we can actually write here.
            probe = os.path.join(path, ".write-test")
            with open(probe, "w") as fh:
                fh.write("")
            os.remove(probe)
            return path
        except OSError:
            continue
    return ""  # file logging disabled; stdout only


def setup_logging(name: str) -> logging.Logger:
    """Return a configured logger; idempotent per logger name."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    log_dir = _resolve_log_dir()
    if log_dir:
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, f"{name}.log"),
            maxBytes=1_000_000,
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    else:
        logger.warning("No writable log directory found; logging to stdout only")

    logger.propagate = False
    return logger
