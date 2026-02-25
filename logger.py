"""Logging configuration for TCP-Over-SSL-Tunnel."""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "tcp-tunnel",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    verbose: bool = False,
    quiet: bool = False,
) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name
        level: Base logging level
        log_file: Optional file path for file logging
        verbose: If True, set level to DEBUG
        quiet: If True, set level to WARNING

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "tcp-tunnel") -> logging.Logger:
    """Get an existing logger or create a basic one."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
