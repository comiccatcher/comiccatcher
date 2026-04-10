import os
import sys
import asyncio
import time
import shutil
from pathlib import Path

# Force offscreen rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure we can find the app modules
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize, Qt
from qasync import QEventLoop
from comiccatcher.config import ConfigManager, CACHE_DIR
from comiccatcher.ui.app_layout import MainWindow, ViewIndex
from comiccatcher.models.feed import FeedProfile
from comiccatcher.models.feed_page import ItemType
import comiccatcher.logger as logger

async def inspect_ui():
    print("🚀 Starting Visual Inspection Driver...")
    logger.setup_logging(debug=True)
    
    # 1. Setup Environment
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    config_manager = ConfigManager()
    # Force Light Theme
    config_manager.set_theme("light")
    
    window = MainWindow(config_manager)
    window.resize(1200, 900)
    window.show()
    
    # 2. Add/Find the Stump Feed
    target_url = os.environ.get("CC_STUMP_URL")
    target_token = os.environ.get("CC_STUMP_TOKEN")
    
    if not target_url or not target_token:
        print("❌ FAILED: CC_STUMP_URL and CC_STUMP_TOKEN must be set in environment.")
        sys.exit(1)
    
    feed = next((f for f in config_manager.feeds if f.url == target_url), None)
    if not feed:
        feed = config_manager.add_feed("Stump E2E", target_url, token=target_token)
    
    print(f"[*] Navigating to feed: {feed.name}")
    window.on_feed_selected(feed)
    
    # 3. Wait for dashboard load
    print("[*] Waiting for feed load...")
    await asyncio.sleep(5)
    QApplication.processEvents()
    
    # 4. Find first book and open details
    print("[*] Searching for first available book in feed...")
    browser = window.feed_browser
    target_pub = None
    
    # Iterate through all sections in the reconciled page
    if hasattr(browser, '_last_page') and browser._last_page:
        for section in browser._last_page.sections:
            for item in section.items:
                if item.type == ItemType.BOOK and item.raw_pub:
                    target_pub = item.raw_pub
                    print(f"[*] Found book: {item.title} in section: {section.title}")
                    break
            if target_pub: break
            
    if not target_pub:
        print("❌ FAILED: No books found in feed.")
        app.quit()
        return

    # Trigger navigation to detail view
    window.on_open_detail(target_pub, None)

    # 5. Wait for detail view to render
    print("[*] Waiting for Detail View...")
    await asyncio.sleep(3)
    QApplication.processEvents()
    
    # 6. Capture Screenshot
    screenshot_path = "feed_details_light_theme.png"
    print(f"[*] Capturing screenshot to {screenshot_path}...")
    
    # Take a screenshot of the whole window
    pixmap = window.grab()
    pixmap.save(screenshot_path)
    
    print(f"✅ SUCCESS: Screenshot saved. Please inspect {screenshot_path}")
    app.quit()

if __name__ == "__main__":
    try:
        asyncio.run(inspect_ui())
    except Exception as e:
        print(f"💥 Crash: {e}")
        import traceback
        traceback.print_exc()
