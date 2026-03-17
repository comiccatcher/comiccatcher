#!/usr/bin/env python3
import os
import sys
import argparse
import asyncio
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from config import ConfigManager
from ui.app_layout import MainWindow
import logger

async def async_main(args):
    log = logger.get_logger("main")
    log.info(f"Starting ComicCatcher PyQt6... (Debug Level: {args.debug})")

    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.show()
    
    # Keep the application alive
    while True:
        await asyncio.sleep(3600)

def main():
    parser = argparse.ArgumentParser(description="ComicCatcher OPDS Reader (PyQt6)")
    parser.add_argument('--debug', nargs='?', const=1, type=int, default=0, help='Enable debug logging.')
    parser.add_argument('--auto-open-local', type=str, default="", help='Debug: auto-open a local CBZ.')
    args = parser.parse_args()
    
    is_debug = args.debug > 0 or os.getenv("DEBUG") == "1"
    if is_debug:
        os.environ["DEBUG"] = "1"
        os.environ["DEBUG_LEVEL"] = str(args.debug)
        
    logger.setup_logging(debug=is_debug)

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Handle Ctrl+C (SIGINT)
    import signal
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    
    # Periodic timer to allow Python interpreter to process signals
    from PyQt6.QtCore import QTimer
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    try:
        loop.run_until_complete(async_main(args))
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"Application crashed: {e}")
        traceback.print_exc()
        sys.exit(1)
