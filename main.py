import flet as ft
import os
import sys
import argparse
from pathlib import Path
import asyncio
from config import ConfigManager
from ui.app_layout import AppLayout
import logger
from ui.snack import show_snack

COLORS = getattr(ft, "colors", ft.Colors)

def main(page: ft.Page):
    # Global Flet Error Handler to catch silent UI crashes
    def on_error(e):
        log = logger.get_logger("flet.error")
        log.error(f"Flet Unhandled Exception: {e.data}")
        try:
            show_snack(page, f"UI Error: {e.data}", text_color=COLORS.ERROR)
        except: pass
        
    page.on_error = on_error
    
    page.title = "ComicCatcher"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    
    config_manager = ConfigManager()
    
    # Ensure assets/cache symlink exists for local image serving
    try:
        from config import CACHE_DIR
        project_root = Path(__file__).parent
        assets_dir = project_root / "assets"
        assets_dir.mkdir(exist_ok=True)
        asset_cache = assets_dir / "cache"
        if not asset_cache.exists():
            # Use relative symlink if possible, or absolute if not
            os.symlink(str(CACHE_DIR), str(asset_cache))
            log = logger.get_logger("main")
            log.info(f"Created assets symlink: {asset_cache} -> {CACHE_DIR}")
    except Exception as e:
        log = logger.get_logger("main")
        log.error(f"Failed to create assets symlink: {e}")

    app_layout = AppLayout(page, config_manager)
    page.add(app_layout)
    page.update()

    # Optional automation: jump directly into a local comic on startup (debugging).
    auto_local = os.getenv("COMICCATCHER_AUTO_OPEN_LOCAL", "").strip()
    if auto_local:
        p = Path(auto_local).expanduser()
        try:
            # Schedule after first frame so the client is fully mounted.
            async def _auto_open_local():
                await asyncio.sleep(0.1)
                app_layout.on_read_local_comic(p)
            page.run_task(_auto_open_local)
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ComicCatcher OPDS Reader")
    parser.add_argument('--debug', nargs='?', const=1, type=int, default=0, help='Enable debug logging. Optional level (1=basic, 2=verbose)')
    parser.add_argument('--web', action='store_true', help='Run in web server mode (no desktop socket transport).')
    parser.add_argument('--web-browser', action='store_true', help='Run in web server mode and open a browser tab.')
    parser.add_argument('--host', type=str, default="127.0.0.1", help='Host/IP to bind web server to (web modes).')
    parser.add_argument('--port', type=int, default=0, help='TCP port to bind web server to (web modes). 0 chooses a random free port.')
    parser.add_argument('--auto-open-local', type=str, default="", help='Debug: auto-open a local CBZ in the local reader (path).')
    parser.add_argument('--disable-gpu', action='store_true', help='Force software rendering (Linux only, sets LIBGL_ALWAYS_SOFTWARE=1).')
    args = parser.parse_args()
    
    is_debug = args.debug > 0 or os.getenv("DEBUG") == "1"
    
    if is_debug:
        os.environ["DEBUG"] = "1"
        os.environ["DEBUG_LEVEL"] = str(args.debug)
    if args.auto_open_local:
        os.environ["COMICCATCHER_AUTO_OPEN_LOCAL"] = args.auto_open_local
    if args.disable_gpu:
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
        os.environ["FLET_DESKTOP_RENDERER"] = "software"
        
    logger.setup_logging(debug=is_debug)
    log = logger.get_logger("main")
    log.info(f"Starting ComicCatcher... (Debug Level: {args.debug})")
    
    try:
        # Prefer ft.run() (ft.app() is deprecated in Flet 0.80+).
        if args.web_browser:
            ft.run(main, view=ft.AppView.WEB_BROWSER, host=args.host, port=args.port)
        elif args.web or os.getenv("COMICCATCHER_WEB") == "1":
            # Web server without opening an external browser. Useful for automation (Playwright).
            ft.run(main, view=ft.AppView.FLET_APP_WEB, host=args.host, port=args.port)
        else:
            ft.run(main, view=ft.AppView.FLET_APP)
    except Exception as e:
        log.critical(f"Application crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
