#!/usr/bin/env python3
import sys
import asyncio
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
import logging

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir))

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow
import comiccatcher.logger as logger

async def drive_app():
    print("🚀 Initializing E2E Scrub Test...")
    logger.setup_logging(debug=True)
    log = logger.get_logger("e2e_test")
    
    config = ConfigManager()
    
    # 1. Ensure we have Codex
    codex_feed = next((f for f in config.feeds if "codex" in f.name.lower()), None)
    if not codex_feed:
        print("❌ Codex feed not found in config. Please add it first.")
        QApplication.instance().quit()
        return

    app = QApplication.instance()
    window = MainWindow(config)
    window.show()
    browser = window.feed_browser
    
    # 2. Load Codex Start Page
    print(f"📡 Loading Codex: {codex_feed.url}")
    await browser.load_url(codex_feed.url)
    
    # Wait for settle
    await asyncio.sleep(3)
    
    # 3. Navigate to 'Issues'
    issues_url = codex_feed.url.rstrip('/') + "/s/0/1?topGroup=s"
    print(f"📡 Navigating to Issues: {issues_url}")
    await browser.load_url(issues_url)
    
    # Wait for load and total count detection
    await asyncio.sleep(3)
    
    if not browser._main_grid_model:
        print("❌ Main grid model not found.")
        QApplication.instance().quit()
        return

    # 4. Ensure Continuous Mode
    print("⚙️ Switching to Continuous mode...")
    browser._on_paging_mode_changed("scrolled")
    await asyncio.sleep(1)
    
    total_count = browser._main_grid_model.rowCount()
    print(f"📊 Total items detected: {total_count}")

    # 5. PERFORM SCRUB TO END
    print("\n💨 SCRUBBING TO 100%...")
    # Determine which scrollbar to use
    active_scroll = browser.dash_scroll if browser.stack.currentWidget() == browser.dash_scroll else browser.grid_view
    scrollbar = active_scroll.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    
    # Monitor for settle
    for i in range(15):
        await asyncio.sleep(1)
        active = len(browser._active_sparse_tasks)
        pending = len(browser._pending_page_requests)
        first, last = browser._get_visible_row_range()
        print(f"  [End] Rows {first}-{last}, Active Tasks: {active}, Pending: {pending}")
        
        # Check if rows are actually loaded
        item = browser._main_grid_model.get_item(last)
        if item and item.type != 4: # Not EMPTY
             print(f"  ✅ Data at end is LOADED: {item.title}")
             # Give one more second for UI to paint
             await asyncio.sleep(1)
             # Take a screenshot to verify!
             from PyQt6.QtGui import QPixmap
             pix = QPixmap(window.size())
             window.render(pix)
             pix.save("/tmp/scrub_end_verify.png")
             print("  📸 Saved /tmp/scrub_end_verify.png")
             break
        else:
             print(f"  ⏳ Data at end is still skeleton or loading...")

    print("\n🏁 Test Complete.")
    app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        try:
            loop.run_until_complete(drive_app())
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
