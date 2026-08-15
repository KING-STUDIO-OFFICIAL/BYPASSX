import logging
import sys


def _redact_filter(record: logging.LogRecord) -> bool:
    msg = str(record.getMessage())
    lowered = msg.lower()
    sensitive_markers = ("token=", "discord_token", "authorization:", "bearer ")
    for marker in sensitive_markers:
        if marker in lowered:
            return False
    return True


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("bypassbot")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(_redact_filter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = setup_logger()
