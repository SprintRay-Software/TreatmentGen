import sys
from datetime import datetime

from loguru import logger as _logger

from app.core.config import APP_ROOT


def get_logger(
    print_level: str = "INFO", log_file_level: str = "DEBUG", name: str = ""
):
    cur_date = datetime.now().strftime("%Y%m%d%H%M%S")
    log_file_name = f"{name}_{cur_date}" if name else cur_date

    _logger.remove()
    _logger.add(sys.stderr, level=print_level)
    _logger.add(APP_ROOT / f"logs/{log_file_name}.log", level=log_file_level)

    return _logger


logger = get_logger()
