"""统一日志配置。"""
import os
import sys
from loguru import logger
from app.config import settings

logger.remove()
# 本地终端仅 stderr 输出（避免 stdout/stderr 双写导致日志重复）；
# 容器环境（CloudBase/ docker）stdout 是日志面板主采集源，需双写
_in_container = os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST") is not None
_fmt = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
if _in_container:
    logger.add(sys.stdout, level="DEBUG" if settings.debug else "INFO", format=_fmt)
logger.add(sys.stderr, level="DEBUG" if settings.debug else "INFO", format=_fmt)
logger.add("logs/xianzhi_{time:YYYY-MM-DD}.log", rotation="00:00", retention="14 days", level="DEBUG", encoding="utf-8")
log = logger
