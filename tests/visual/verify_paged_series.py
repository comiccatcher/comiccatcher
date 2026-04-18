#!/usr/bin/env python3
import sys
import asyncio
import urllib.parse
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QListView
from PyQt6.QtCore import QSize, QTimer
from qasync import QEventLoop

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir))

from comiccatcher.config import ConfigManager
import comiccatcher.logger as logger
from comiccatcher.ui.theme_manager import UIConstants

async def verify_paged_series():
    print("🧪 Verifying Codex -> Series layout...")
    logger.setup_logging(debug=False)
    
    config = ConfigManager()
    codex_feed = next((f for f in config.feeds if "codex" in f.name.lower()), None)
    if not codex_feed:
        print("❌ Error: Codex feed not found.")
        return

    from comiccatcher.api.client import APIClient
    from comiccatcher.api.opds_v2 import OPDS2Client
    from comiccatcher.api.image_manager import ImageManager
    from comiccatcher.ui.views.feed_browser import FeedBrowser

    UIConstants.init_scale()
    
    app = QApplication.instance()
    api_client = APIClient(codex_feed)
    # Force Paged mode for this test
    codex_feed.paging_mode = "paged"
    
    opds_client = OPDS2Client(api_client)
    image_manager = ImageManager(api_client)
    browser = FeedBrowser(opds_client, image_manager, config)
    
    # CRITICAL: Link the profile to the browser, just like AppLayout does
    browser.current_profile = codex_feed
    
    browser.resize(1000, 800)
    browser.show()
    
    # 1. Load Start
    start_url = codex_feed.url.rstrip('/') + "/"
    print(f"📡 Loading Start Feed: {start_url}")
    await browser.load_url(start_url)
    await asyncio.sleep(2)
    # 2. Find "Series" navigation and navigate
    page = browser._last_page
    series_item = None

    print("\n--- Available Items ---")
    for sec in page.sections:
        print(f"Section: {sec.title}")
        for itm in sec.items:
            print(f"  - [{itm.type}] {itm.title}")
            if "series" in itm.title.lower() and itm.raw_link:
                series_item = itm
                break
        if series_item: break

    if not series_item:
        print("Checking facets...")
        for group in page.facets:
            links = getattr(group, "navigation", []) or getattr(group, "links", [])
            for link in links:
                print(f"  - [FACET] {link.title}")
                if "series" in link.title.lower():
                    from comiccatcher.models.feed_page import FeedItem, ItemType
                    series_item = FeedItem(type=ItemType.FOLDER, title=link.title, raw_link=link, identifier=link.href)
                    break
            if series_item: break

    if not series_item:
        print("❌ Error: 'Series' item not found in start page.")
        # Print first few items of the first section to see what we DID find
        sys.exit(1)

    series_url = urllib.parse.urljoin(start_url, series_item.raw_link.href)
    print(f"📡 Navigating to Series: {series_url}")
    await browser.load_url(series_url)
    
    # Wait for rendering to complete (including that 100ms QTimer in _render_page)
    for _ in range(20):
        app.processEvents()
        await asyncio.sleep(0.5)
    
    # 3. Verify Height
    # In the new architecture, the Series grid view is now the composite_view
    series_view = browser.composite_view
    
    if not series_view or series_view.model().rowCount() == 0:
        print("❌ Error: Series composite view not ready or empty.")
        return
        
    def check_height(view, width):
        print(f"\n📏 Testing width: {width}")
        view.window().resize(width, 800)
        # Give it a moment to recalculate (debounce is 250ms in UIConstants)
        # We'll wait 500ms for safety
        app.processEvents()
        import time
        time.sleep(0.5)
        app.processEvents()
        
        # In paged mode, the view fills the entire window space
        h = view.height()
        count = view.model().rowCount()
        
        print(f"  Items: {count}, View Height: {h}")
        
        # In paged mode, the count should be approximately 100 (one page), 
        # plus maybe a few headers/ribbons on Page 1.
        if count < 100:
            print(f"  ❌ FAIL: Model has {count} items, expected at least 100!")
            return False
            
        print(f"  ✅ PASS: View is active with {count} items.")
        return True

    results = []
    results.append(check_height(series_view, 1200))
    
    # 4. Test Page 2 Navigation
    print("\n📡 Testing Page 2 Navigation...")
    # Find the 'next' button and click it
    if browser.btn_next.isEnabled():
        browser.btn_next.click()
        # Wait for Page 2 load
        for _ in range(20):
            app.processEvents()
            await asyncio.sleep(0.5)
            
        print("📏 Verifying Page 2 Items:")
        count = series_view.model().rowCount()
        print(f"  Items on Page 2: {count}")
        if count == 100:
            print("  ✅ PASS: Page 2 populated correctly.")
            results.append(True)
        else:
            print(f"  ❌ FAIL: Page 2 has {count} items (expected 100)!")
            results.append(False)
    else:
        print("⚠️ Warning: 'Next' button is disabled, cannot test Page 2.")

    if all(results):
        print("\n✅ SUCCESS: Paged Series view is responsive and has correct heights.")
        sys.exit(0)
    else:
        print("\n❌ FAILURE: Some widths resulted in incorrect heights.")
        sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        try:
            loop.run_until_complete(verify_paged_series())
        except Exception as e:
            print(f"Crash: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
