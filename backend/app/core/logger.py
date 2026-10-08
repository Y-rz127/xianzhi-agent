"""统一日志配置。"""
import sys

from loguru import logger

from app.core.config import BACKEND_ROOT, settings

logger.remove()
# 仅 stderr 输出。CloudBase/容器平台同时捕获 stdout 和 stderr，
# 双写会导致每条日志在日志面板重复两次。
# 本地终端和 CloudBase 日志面板都只读 stderr 即可。
_fmt = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
logger.add(sys.stderr, level="DEBUG" if settings.debug else "INFO", format=_fmt)
# 日志落盘路径锚定 backend/ 根目录：原先写相对路径 "logs/..."，从仓库根目录
# 启动（如跑 pytest）时会在仓库根再长出一个 logs/，日志被劈成两份。
logger.add(
    str(BACKEND_ROOT / "logs" / "xianzhi_{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="14 days",
    level="DEBUG",
    encoding="utf-8",
)
log = logger
