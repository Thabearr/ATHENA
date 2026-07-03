from loguru import logger
import os

os.makedirs("logs", exist_ok=True)

logger.remove()  # Remove default logger

logger.add(
    "logs/athena.log",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    enqueue=True,
)

def get_logger():
    return logger 
