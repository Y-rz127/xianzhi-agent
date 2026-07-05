"""统一日志配置。"""
import sys
from loguru import logger
from app.config import settings

logger.remove()
logger.add(sys.stderr, level="DEBUG" if settings.debug else "INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>")
logger.add("logs/xianzhi_{time:YYYY-MM-DD}.log", rotation="00:00", retention="14 days", level="DEBUG", encoding="utf-8")
log = logger
