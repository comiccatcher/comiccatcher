import logging
import sys
import os
from pathlib import Path

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def get_app_data_dir() -> Path:
    """Get the persistent app data directory for ComicCatcher."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    
    path = Path(base) / "comiccatcher"
    path.mkdir(parents=True, exist_ok=True)
    return path

def setup_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Allow handlers to filter
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Console Handler (Windowed mode guard: sys.stdout can be None)
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(console_handler)
    
    # File Handler
    log_dir = get_app_data_dir()
    log_file = log_dir / "comiccatcher.log"
    file_handler = logging.FileHandler(str(log_file), mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)

    noisy = ["httpx", "httpcore", "asyncio", "qasync", "PIL"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.INFO)
    
    logging.getLogger("comiccatcher").info(f"Logging initialized. Level: {'DEBUG' if debug else 'INFO'}. File: {log_file}")

def get_logger(name):
    return logging.getLogger(f"comiccatcher.{name}")
