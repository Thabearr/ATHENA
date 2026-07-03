from loguru import logger
import os

os.makedirs("logs", exist_ok=True)

logger.add(
    "logs/athena.log",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
)

def get_logger():
    return logger
