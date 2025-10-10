import logging
import os
from logging.config import dictConfig

from config import config


def configure_logging() -> None:
    if not os.path.exists("logs"):
        os.makedirs("logs")
        print("Directory 'logs' created")

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "correlation_id": {
                    "()": "asgi_correlation_id.CorrelationIdFilter",
                    "uuid_length": 8,
                    "default_value": "-",
                }
            },
            "formatters": {
                "console": {
                    "class": "logging.Formatter",
                    "dateftm": "%Y-%m-%dT%H:%M:%S",
                    "format": "(%(correlation_id)s) %(name)s:%(lineno)d - %(message)s",
                },
                "file": {
                    "class": "logging.Formatter",
                    "dateftm": "%Y-%m-%dT%H:%M:%S",
                    "format": "%(asctime)s.%(msecs)03dZ | %(levelname)-8s | [%(correlation_id)s] %(name)s:%(lineno)d - %(message)s",
                },
                "file_json": {
                    "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "dateftm": "%Y-%m-%dT%H:%M:%S",
                    "format": "%(asctime)s %(msecs)03d %(levelname)-8s %(correlation_id)s %(name)s %(lineno)d %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "class": "rich.logging.RichHandler",
                    "level": "DEBUG",
                    "formatter": "console",
                    "filters": ["correlation_id"],
                },
                "rotating_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "DEBUG",
                    "formatter": "file_json",
                    "filename": "logs/chatbot.log",
                    "maxBytes": 1024 * 1024,  # 1MB
                    "backupCount": 5,
                    "encoding": "utf8",
                    "filters": ["correlation_id"],
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default", "rotating_file"], "level": "INFO"},
                "databases": {
                    "handlers": ["default", "rotating_file"],
                    "level": "WARNING",
                },
                "aiosqlite": {
                    "handlers": ["default", "rotating_file"],
                    "level": "WARNING",
                },
                "app": {
                    "handlers": ["default", "rotating_file"],
                    "level": "DEBUG" if config.ENV_STATE == "dev" else "INFO",
                    "propagate": False,
                },
            },
        }
    )


configure_logging()
logger = logging.getLogger("app")
