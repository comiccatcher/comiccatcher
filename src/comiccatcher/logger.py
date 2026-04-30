# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import logging
import sys
import os
from pathlib import Path

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Broad Debug Categories
CATEGORIES = {
    "nav": "comiccatcher.nav",       # UI Navigation & Focus
    "net": "comiccatcher.net",       # Network & Progression
    "opds": "comiccatcher.opds",     # Feed Data & Syncing
    "lib": "comiccatcher.lib",       # Local Management
    "reader": "comiccatcher.reader", # Reader Engine
    "ui": "comiccatcher.ui",         # Generic Widgets
}

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

def setup_logging(debug_spec=""):
    """
    Setup logging with granular category support.
    debug_spec can be:
      - "1" or "all": Enable all categories at DEBUG level.
      - "nav,net": Enable specific categories.
      - "": Standard INFO logging.
    """
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Allow handlers to filter
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Determine which categories are enabled
    spec = str(debug_spec).lower().strip()
    enabled_categories = set()
    
    is_all = spec in ("1", "all", "true")
    if spec and not is_all:
        enabled_categories = {s.strip() for s in spec.split(",") if s.strip()}

    # Standard output handler (Windowed mode guard: sys.stdout can be None)
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        
        # If ANY category is enabled, the console MUST be at DEBUG to show them.
        if is_all or enabled_categories:
            console_handler.setLevel(logging.DEBUG)
        else:
            console_handler.setLevel(logging.INFO)
            
        root_logger.addHandler(console_handler)

    # File Handler (Always at DEBUG to a persistent file)
    try:
        log_dir = get_app_data_dir()
        log_file = log_dir / "comiccatcher.log"
        file_handler = logging.FileHandler(str(log_file), mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to setup file logging: {e}", file=sys.stderr)
        log_file = "None"

    # Set default level for our main logger
    main_logger = logging.getLogger("comiccatcher")
    main_logger.setLevel(logging.DEBUG if is_all else logging.INFO)

    # Configure sub-loggers
    for key, logger_name in CATEGORIES.items():
        logger = logging.getLogger(logger_name)
        if is_all or key in enabled_categories:
            logger.setLevel(logging.DEBUG)
            # Ensure they don't get filtered by the parent if it's at INFO
            logger.propagate = True 
        else:
            logger.setLevel(logging.INFO)

    # Clamp noisy third-party loggers
    noisy = ["asyncio", "qasync", "PIL"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.INFO)

    # Configure network-related third party loggers (httpx, httpcore)
    # These will follow the 'net' category or 'all' spec.
    net_loggers = ["httpx", "httpcore"]
    for name in net_loggers:
        logger = logging.getLogger(name)
        if is_all or "net" in enabled_categories:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    msg = f"Logging initialized. Categories enabled: {list(enabled_categories) if enabled_categories else ('ALL' if is_all else 'NONE')}. File: {log_file}"
    main_logger.info(msg)

def get_logger(name):
    """Returns a logger. If name is a known category, returns that sub-logger."""
    if name in CATEGORIES:
        return logging.getLogger(CATEGORIES[name])
    return logging.getLogger(f"comiccatcher.{name}")
