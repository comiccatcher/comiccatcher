# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

#!/usr/bin/env python3
import os
import sys
import argparse
import asyncio
from pathlib import Path

from typing import Optional, Tuple
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from qasync import QEventLoop

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher import logger

def _ensure_desktop_entry():
    """
    Write ~/.local/share/applications/comiccatcher.desktop so GNOME can match the
    running window (WM_CLASS=comiccatcher) to our icon and show it in the dock.
    Uses an absolute Icon= path so no icon-theme cache update is required.
    Only writes/updates when the file is missing or the Exec path has changed.
    """
    if sys.platform != "linux":
        return
    try:
        app_dir = Path(__file__).parent.resolve()
        icon_path = app_dir / "resources" / "app.png"
        if not icon_path.exists():
            return

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = desktop_dir / "comiccatcher.desktop"

        # When installed as a package, we should ideally use the entry point command
        # but sys.executable main.py works for development mode too.
        # Let's check if we are in a package or dev mode.
        if "site-packages" in str(app_dir):
            exec_line = "Exec=comiccatcher"
        else:
            exec_line = f"Exec={sys.executable} {app_dir / 'main.py'}"

        if desktop_file.exists() and exec_line in desktop_file.read_text():
            return  # already up to date

        desktop_file.write_text("\n".join([
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            "Name=ComicCatcher",
            "Comment=OPDS Comic Reader for Codex, Komga and Stump",
            f"Icon={icon_path}",
            exec_line,
            "Terminal=false",
            "Categories=Graphics;Viewer;",
            "StartupWMClass=comiccatcher",
            "StartupNotify=true",
            "",
        ]))

        import subprocess
        subprocess.run(
            ["update-desktop-database", str(desktop_dir)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _warmup_comicbox_sync():
    """Pre-warm comicbox's marshmallow/glom schema compilation in a worker thread."""
    import io, zipfile, tempfile, os
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('ComicInfo.xml', b'<?xml version="1.0"?><ComicInfo><Title>Warmup</Title></ComicInfo>')
        z.writestr('cover.jpg', bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
                                       0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
                                       0xFF, 0xD9]))
    buf.seek(0)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.cbz', delete=False) as f:
            f.write(buf.getvalue())
            tmp = f.name
        from comicbox.box import Comicbox
        with Comicbox(tmp) as cb:
            cb.to_dict()
    except Exception:
        pass
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


async def async_main(args):
    log = logger.get_logger("main")
    log.info(f"Starting ComicCatcher PyQt6... (Debug Level: {args.debug})")

    debug_spec = args.debug or os.getenv("DEBUG") or ""
    config_manager = ConfigManager()
    window = MainWindow(config_manager, debug_spec=debug_spec)
    window.show()
    asyncio.create_task(asyncio.to_thread(_warmup_comicbox_sync))
    
    # E2E Driver Injection
    if args.e2e_driver:
        try:
            import importlib.util
            driver_path = Path(args.e2e_driver).resolve()
            log.info(f"Injecting E2E Driver: {driver_path}")
            spec = importlib.util.spec_from_file_location("e2e_driver_module", str(driver_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "drive"):
                asyncio.create_task(module.drive(window))
            else:
                log.error("E2E Driver script must define an 'async def drive(window)' function.")
        except Exception as e:
            log.error(f"Failed to load E2E Driver: {e}")

    # Create an event that we'll wait on until the app quits
    exit_event = asyncio.Event()
    QApplication.instance().aboutToQuit.connect(exit_event.set)
    
    if args.timeout > 0:
        log.info(f"Application will exit in {args.timeout} seconds...")
        async def _timeout():
            await asyncio.sleep(args.timeout)
            QApplication.instance().quit()
        asyncio.create_task(_timeout())

    # Wait for the app to quit (either via window close, timeout, or Ctrl+C)
    await exit_event.wait()
    log.info("Application exit event received.")

def main():
    parser = argparse.ArgumentParser(description="ComicCatcher OPDS Reader (PyQt6)")
    parser.add_argument('--debug', type=str, default="", help='Enable debug logging. Use "all" or comma-separated categories: nav, net, opds, lib, reader, ui.')
    parser.add_argument('--auto-open-local', type=str, default="", help='Debug: auto-open a local CBZ.')
    parser.add_argument('--timeout', type=int, default=0, help='Exit after N seconds (useful for CI/testing).')
    parser.add_argument('--e2e-driver', type=str, default="", help='Path to a python script to drive the app (async def drive(window)).')
    args = parser.parse_args()
    
    debug_spec = args.debug or os.getenv("DEBUG") or ""
    if debug_spec:
        os.environ["DEBUG"] = debug_spec
        
    logger.setup_logging(debug_spec=debug_spec)

    app = QApplication(sys.argv)
    app.setApplicationName("ComicCatcher")
    app.setApplicationDisplayName("ComicCatcher")
    app.setDesktopFileName("comiccatcher")

    # Set Application Icon (window decorations + alt-tab)
    icon_path = Path(__file__).parent / "resources" / "app.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Ensure .desktop file exists so GNOME dock shows the right icon
    _ensure_desktop_entry()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Handle Ctrl+C (SIGINT)
    import signal
    signal.signal(signal.SIGINT, lambda *args: QApplication.instance().quit())
    
    # Periodic timer to allow Python interpreter to process signals
    from PyQt6.QtCore import QTimer
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    try:
        loop.run_until_complete(async_main(args))
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    except RuntimeError as e:
        if str(e) != "Event loop stopped before Future completed.":
            raise
    finally:
        # qasync loop closing can be tricky; usually best to just let it go if it's already stopping
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"Application crashed: {e}")
        traceback.print_exc()
        sys.exit(1)
