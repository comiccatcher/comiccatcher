import os
import sys
import asyncio
import time
import logging
from pathlib import Path

# Force offscreen rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure we can find the app modules
sys.path.insert(0, os.path.join(os.getcwd(), 'comiccatcher/src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint
from qasync import QEventLoop
from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow, ViewIndex
from comiccatcher.logger import setup_logging

async def reproduce():
    print("🚀 Starting Repro Script...")
    setup_logging(debug=True)
    
    # Force all loggers to DEBUG
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).setLevel(logging.DEBUG)

    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.resize(1200, 800)
    window.show()
    
    # 1. Find the Codex Feed
    feed = next((f for f in config_manager.feeds if "codex" in f.name.lower()), None)
    if not feed:
        print("❌ FAILED: Codex feed not found in config.")
        return

    from comiccatcher.api.feed_reconciler import FeedReconciler
    from comiccatcher.ui.views.scrolled_feed_view import ScrolledFeedView
    
    orig_fetch = ScrolledFeedView._fetch_page
    async def patched_fetch(self, page_idx: int, url: str, ctx_id: float):
        print(f"    [REPRO] _fetch_page(p={page_idx}, url={url})")
        try:
            feed = await self.opds_client.get_feed(url)
            if ctx_id != self._current_context_id:
                return
            page = FeedReconciler.reconcile(feed, url)
            
            print(f"    [REPRO] Fetched Data: main_sid={self._main_grid_sid}")
            for s in page.sections:
                 print(f"      Section in fetched data: sid={s.section_id}, title={s.title}")

            main = None
            for s in page.sections:
                if s.section_id == self._main_grid_sid:
                    main = s
                    break
            
            if not main:
                print(f"    [REPRO] SID Match Fail. main_section heuristic: {page.main_section.section_id if page.main_section else 'None'}")
                main = page.main_section

            if main:
                model = self._models.get(self._main_grid_sid)
                if model:
                    model.set_items_for_page(page_idx, main.items)
                    print(f"    [REPRO] Successfully set {len(main.items)} items for page {page_idx}")
                else:
                    print(f"    [REPRO] No model for {self._main_grid_sid}")
            else:
                print(f"    [REPRO] No main section found.")
        except Exception as e:
            print(f"    [REPRO] ERROR: {e}")

    ScrolledFeedView._fetch_page = patched_fetch
    
    print(f"[*] Navigating to feed: {feed.name}")
    window.on_feed_selected(feed)
    
    # 2. Wait for dashboard load
    print("[*] Waiting for dashboard...")
    browser = window.feed_browser
    while browser.stack.currentWidget() == browser.loading_view:
        await asyncio.sleep(0.5)
        QApplication.processEvents()
    
    print(f"[*] Current View: {type(browser.stack.currentWidget()).__name__}")
    
    # 3. Find 'Publishers' nav item and click it
    # We need to wait for the view to render its items
    await asyncio.sleep(1)
    QApplication.processEvents()
    
    paged_view = browser.paged_view
    scrolled_view = browser.scrolled_view
    
    # Find Publishers in the current view
    publishers_item = None
    target_view = browser.stack.currentWidget()
    
    print(f"[*] Searching for 'Publishers' in {type(target_view).__name__}...")
    
    # Get items from subview if possible
    items = []
    if hasattr(target_view, '_raw_sections'): # FeedPage structure
         for sec in target_view._raw_sections:
             items.extend(sec.items)
    elif hasattr(target_view, 'get_all_items'):
        items = target_view.get_all_items()
    
    for item in items:
        if item.title == "Publishers":
            publishers_item = item
            break
    
    if not publishers_item:
        # Check model directly as fallback
        if browser._last_page:
            for sec in browser._last_page.sections:
                for item in sec.items:
                    if item.title == "Publishers":
                        publishers_item = item
                        break
                if publishers_item: break
    
    if not publishers_item:
        print("❌ FAILED: 'Publishers' nav item not found.")
        return

    print(f"[*] Found Publishers. Navigating...")
    browser._on_item_clicked(publishers_item, [])
    
    # 4. Wait for Publishers feed to load
    while browser.stack.currentWidget() == browser.loading_view:
        await asyncio.sleep(0.5)
        QApplication.processEvents()
    
    print(f"[*] Stack is now on: {type(browser.stack.currentWidget()).__name__}")
    
    # 5. Ensure we are in Scrolled View
    if browser._paging_mode != "scrolled":
        print("[*] Switching to Scrolled View...")
        browser._on_paging_mode_changed("scrolled")
        await asyncio.sleep(1)
    
    # 6. Scroll to the bottom to trigger infinite fetches
    print("[*] Scrolling to bottom...")
    sv = browser.scrolled_view
    sb = sv._sb
    
    # Scroll incrementally to simulate user behavior
    for i in range(5):
        sb.setValue(sb.maximum())
        await asyncio.sleep(1)
        QApplication.processEvents()
        print(f"    Scroll: {sb.value()}/{sb.maximum()} | Height: {sv._total_height}")

    print("[*] At bottom. Monitoring for 10s. Look for endless logs...")
    # Monitor for 10 seconds
    start_mon = time.time()
    while time.time() - start_mon < 10:
        await asyncio.sleep(1)
        QApplication.processEvents()
        
        # Check if the last items are loaded
        model = sv._models.get(sv._main_grid_sid)
        if model:
            total = model.rowCount()
            loaded = len(model._sparse_items)
            pages = sorted(list(model._loaded_pages))
            print(f"    Status: MainSID={sv._main_grid_sid} Total={total}, Loaded_Items={loaded}, Loaded_Pages={pages}")
            
            # Log all available section IDs in the current model
            if model._raw_sections:
                sids = [s.section_id for s in model._raw_sections]
                print(f"    Available SIDs in model: {sids}")
            
    print("[*] Repro finished. Check logs above.")
    app.quit()

if __name__ == "__main__":
    try:
        asyncio.run(reproduce())
    except Exception as e:
        print(f"💥 Crash: {e}")
        import traceback
        traceback.print_exc()
