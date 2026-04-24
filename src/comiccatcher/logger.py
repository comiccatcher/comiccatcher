# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import logging
import sys
import os

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
    root_logger.setLevel(logging.DEBUG) 
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Standard output handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(console_handler)

    # Determine which categories are enabled
    spec = str(debug_spec).lower().strip()
    enabled_categories = set()
    
    is_all = spec in ("1", "all", "true")
    if spec and not is_all:
        enabled_categories = {s.strip() for s in spec.split(",") if s.strip()}

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
    noisy = ["httpx", "httpcore", "asyncio", "qasync", "PIL"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.INFO)
    
    # Final console handler level logic:
    # If ANY category is enabled, the console MUST be at DEBUG to show them.
    if is_all or enabled_categories:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)

    msg = f"Logging initialized. Categories enabled: {list(enabled_categories) if enabled_categories else ('ALL' if is_all else 'NONE')}."
    main_logger.info(msg)

def get_logger(name):
    """Returns a logger. If name is a known category, returns that sub-logger."""
    if name in CATEGORIES:
        return logging.getLogger(CATEGORIES[name])
    return logging.getLogger(f"comiccatcher.{name}")
