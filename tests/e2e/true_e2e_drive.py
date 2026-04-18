#!/usr/bin/env python3
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
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from comiccatcher.config import ConfigManager, CACHE_DIR
from comiccatcher.ui.app_layout import MainWindow, ViewIndex
from comiccatcher.models.feed import FeedProfile
import comiccatcher.logger as logger
import logging

async def drive_app():
    print("🚀 Starting True E2E App Driver...")
    logger.setup_logging(debug=True)
    # Force all loggers to DEBUG
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).setLevel(logging.DEBUG)
    
    # 1. Setup Environment
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print("🧹 Cache cleared.")

    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.resize(1200, 800)
    window.show()
    
    # 2. Add/Find the Stump Feed
    target_url = os.environ.get("CC_STUMP_URL")
    target_token = os.environ.get("CC_STUMP_TOKEN")
    
    if not target_url or not target_token:
        print("❌ FAILED: CC_STUMP_URL and CC_STUMP_TOKEN must be set in environment.")
        sys.exit(1)
    
    feed = next((f for f in config_manager.feeds if f.url == target_url), None)
    if not feed:
        print("[*] Adding Stump feed to config...")
        feed = config_manager.add_feed("Stump E2E", target_url, token=target_token)
    
    # 3. Simulate User selecting the feed
    print(f"[*] Navigating to feed: {feed.name}")
    window.on_feed_selected(feed)
    
    # 4. Wait for dashboard load
    print("[*] Waiting for initial feed load...")
    browser = window.feed_browser
    timeout = 15
    start = time.time()
    while time.time() - start < timeout:
        QApplication.processEvents()
        current_view = browser.stack.currentWidget()
        if current_view != browser.loading_view:
            print(f"[*] Stack switched to: {type(current_view).__name__}")
            break
        await asyncio.sleep(0.5)
    
    current_view = browser.stack.currentWidget()
    if current_view == browser.loading_view:
        print("[!] Still on LoadingOverlay, forcing stack to PagedFeedView for test...")
        browser.stack.setCurrentWidget(browser.paged_view)
        await asyncio.sleep(1)
        current_view = browser.stack.currentWidget()

    print(f"[*] Dashboard Widget: {type(current_view).__name__}")
    if current_view == browser.loading_view:
        print("❌ FAILED: Feed stuck on LoadingOverlay.")
        app.quit()
        return

    print("✅ Dashboard ready.")
    await asyncio.sleep(2) # Give layout more time to settle
    QApplication.processEvents()

    # 5. Verify the Trigger
    print(f"[*] Active Sub-View: {type(current_view).__name__}")
    
    # Explicitly trigger the check
    if current_view == window.feed_browser.paged_view:
        print("[*] PagedFeedView active - items should be requesting covers automatically...")
    else:
        print("[*] Triggering Scrolled visibility check...")
        window.feed_browser.scrolled_view._ensure_covers_for_grid()
    
    # 6. Monitor Cache & ImageManager
    print("[*] Monitoring for book cover fetches (15s)...")
    success = False
    for i in range(15):
        # Count files on disk
        files = list(CACHE_DIR.glob("**/*"))
        num_files = len([f for f in files if f.is_file()])
        
        # Check internal state
        mem_cache = len(window.image_manager._memory_cache)
        
        # Look for a book thumbnail specifically
        # Stump thumbnails often have 'thumbnail' in the URL
        book_covers = [k for k in window.image_manager._memory_cache.keys() if "thumb" in k.lower()]
        
        print(f"    T+{i+1}s | Cache: {num_files} files | Memory: {mem_cache} | Thumbnails: {len(book_covers)}")
        
        if len(book_covers) > 0:
            print(f"✅ SUCCESS: Thumbnails detected in memory! ({book_covers[0]})")
            # Check file size
            path = window.image_manager._get_cache_path(book_covers[0])
            if path.exists():
                size = path.stat().st_size
                print(f"[+] Thumbnail size on disk: {size/1024:.1f} KB")
                success = True
                break
            else:
                print("...waiting for disk write...")
                
        await asyncio.sleep(1)
    
    if not success:
        print("❌ FAILED: Thumbnails did not populate.")
        # Print logs to see what happened
        log_path = Path("comiccatcher.log")
        if log_path.exists():
            print("\n--- APPLICATION LOGS ---")
            print(log_path.read_text())
            print("------------------------\n")

    app.quit()

if __name__ == "__main__":
    try:
        asyncio.run(drive_app())
    except Exception as e:
        print(f"💥 Crash: {e}")
        import traceback
        traceback.print_exc()
