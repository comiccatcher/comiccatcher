import logging
import sys
import os

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def setup_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Set to lowest to allow handlers to filter
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(console_handler)
    
    # File Handler - Always log at DEBUG level to file for troubleshooting
    file_handler = logging.FileHandler("comiccatcher.log", mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)

    # Clamp noisy third-party loggers to INFO so ComicCatcher DEBUG logs stay readable.
    noisy = [
        "httpx",
        "httpcore",
        "asyncio",
        "qasync",
    ]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.INFO)
    
    logging.getLogger("comiccatcher").info(f"Logging initialized. Level: {'DEBUG' if debug else 'INFO'}. File: comiccatcher.log (Always DEBUG)")

def get_logger(name):
    return logging.getLogger(f"comiccatcher.{name}")
