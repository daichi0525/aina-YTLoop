import logging
import os
from datetime import datetime
import yaml

# グローバルロガーインスタンスを初期化
logger = logging.getLogger('aina_ytloop')

def setup_logging(settings):
    log_settings = settings.get('logging', {})

    log_dir = log_settings.get('log_directory', 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file_name_timestamp_format = log_settings.get('log_file_name_timestamp_format', '%Y%m%d_%H%M%S')
    log_filename = datetime.now().strftime(f"app_{log_file_name_timestamp_format}.log")
    log_filepath = os.path.join(log_dir, log_filename)

    # Prevent adding multiple handlers if setup_logging is called multiple times
    if not logger.handlers:
        log_level_str = log_settings.get('level', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)

        # Create formatters
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Console handler
        if log_settings.get('log_to_console', True):
            c_handler = logging.StreamHandler()
            c_handler.setLevel(log_level)
            c_handler.setFormatter(formatter)
            logger.addHandler(c_handler)

        # File handler
        if log_settings.get('log_to_file', True):
            f_handler = logging.FileHandler(log_filepath, encoding='utf-8')
            f_handler.setLevel(log_level)
            f_handler.setFormatter(formatter)
            logger.addHandler(f_handler)