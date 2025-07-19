import logging
import os

def get_logger(name, logfile_path):
    os.makedirs(os.path.dirname(logfile_path), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent adding duplicate handlers
    if not logger.handlers:
        handler = logging.FileHandler(logfile_path, encoding='utf-8')  # ✅ Use UTF-8
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
