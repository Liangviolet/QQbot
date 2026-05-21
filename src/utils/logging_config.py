"""日志配置 — structlog + 文件轮转"""

import logging
from logging.handlers import RotatingFileHandler

import structlog

from src.config import AppConfig


def setup_logging(config: AppConfig) -> None:
    """配置 structlog 日志系统"""
    log_cfg = config.logging

    # 文件 Handler (轮转)
    file_handler = RotatingFileHandler(
        log_cfg.file,
        maxBytes=log_cfg.max_bytes,
        backupCount=log_cfg.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_cfg.level.upper(), logging.INFO))
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    # 控制台 Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_cfg.level.upper(), logging.INFO))

    # structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(getattr(logging, log_cfg.level.upper(), logging.INFO))
