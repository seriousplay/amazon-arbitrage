"""
日志配置 - Loguru
"""

from loguru import logger
import sys
from pathlib import Path

def get_logger(name: str):
    return logger.bind(name=name)

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>: <level>{message}</level>",
    level="INFO",
    colorize=True
)
logger.add(
    log_dir / "app-{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}: {message}",
    level="DEBUG",
    rotation="1 day",
    retention="7 days",
    compression="zip"
)
