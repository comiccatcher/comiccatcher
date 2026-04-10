import os
import sys
import asyncio
import time
import shutil
from pathlib import Path

# Force offscreen rendering for E2E
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure we can find the app modules
# Work from project root (where comiccatcher/src is located)
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from qasync import QEventLoop
from comiccatcher.config import ConfigManager, CACHE_DIR
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher.models.feed_page import ItemType
import comiccatcher.logger as logger
import logging

async def drive_selection_download():
    print("🚀 Starting E2E Selection & Download Test...")
    logger.setup_logging(debug=True)
    
    # 1. Setup Environment
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.resize(1200, 800)
    window.show()
    
    # 2. Add/Find a Feed (Stump)
    target_url = os.environ.get("CC_STUMP_URL")
    target_token = os.environ.get("CC_STUMP_TOKEN")
    
    if not target_url or not target_token:
        print("❌ FAILED: CC_STUMP_URL and CC_STUMP_TOKEN must be set in environment.")
        app.quit()
        return
    
    feed = next((f for f in config_manager.feeds if f.url == target_url), None)
    if not feed:
        print("[*] Adding Stump feed to config...")
        feed = config_manager.add_feed("Stump E2E", target_url, token=target_token)
    
    # 3. Navigate to feed
    print(f"[*] Navigating to feed: {feed.name}")
    window.on_feed_selected(feed)
    
    # 4. Wait for dashboard load
    print("[*] Waiting for feed load...")
    browser = window.feed_browser
    timeout = 15
    start = time.time()
    while time.time() - start < timeout:
        QApplication.processEvents()
        if browser.stack.currentWidget() != browser.loading_view:
            break
        await asyncio.sleep(0.5)
    
    if browser.stack.currentWidget() == browser.loading_view:
        print("❌ FAILED: Feed stuck on loading.")
        app.quit()
        return

    print("✅ Feed loaded.")
    await asyncio.sleep(2) # Settle layout
    QApplication.processEvents()

    # 5. Enable Select Mode
    print("[*] Enabling Select Mode...")
    browser.toggle_selection_mode(True)
    QApplication.processEvents()
    
    if not browser.selection_bar.isVisible():
        print("❌ FAILED: Selection bar not visible.")
        app.quit()
        return
    print("✅ Selection bar visible.")

    # 6. Find a book to select
    # We'll look into the active subview (Paged or Scrolled)
    subview = browser.scrolled_view if browser._paging_mode == "scrolled" else browser.paged_view
    print(f"[*] Active subview: {type(subview).__name__}")
    
    # Wait for views to populate (scrolled view creates grids/ribbons as it computes positions)
    views = []
    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        QApplication.processEvents()
        if hasattr(subview, '_section_views'):
            views = subview._section_views
        if hasattr(subview, '_grids'):
            views.extend(list(subview._grids.values()))
        if hasattr(subview, '_ribbons'):
            views.extend(list(subview._ribbons.values()))
            
        if views:
            break
        await asyncio.sleep(0.5)

    if not views:
        # One last try: maybe they are nested children
        from PyQt6.QtWidgets import QListView
        views = subview.findChildren(QListView)
        print(f"[*] Fallback: found {len(views)} QListView children")

    if not views:
        print("❌ FAILED: No views found in subview.")
        # Print children to see what IS there
        for child in subview.children():
            print(f"    - Child: {child}")
        app.quit()
        return

    # 7. Find books to select across ALL views
    target_items = [] # (view, model, row, item)
    
    for view in views:
        model = view.model()
        for row in range(model.rowCount()):
            item = model.get_item(row)
            if item and item.type == ItemType.BOOK and item.download_url:
                target_items.append((view, model, row, item))
                print(f"[*] Found downloadable book in view {type(view).__name__} at row {row}: {item.title}")
                if len(target_items) >= 2:
                    break
        if len(target_items) >= 2:
            break
            
    if not target_items:
        print("❌ FAILED: No downloadable book found in feed.")
        app.quit()
        return

    # 8. Select the items
    for view, model, row, item in target_items:
        print(f"[*] Selecting row {row} in {type(view).__name__}...")
        view.selectionModel().select(
            model.index(row, 0), 
            view.selectionModel().SelectionFlag.Select
        )
    
    # CRITICAL: process events so signals fire
    for _ in range(10):
        QApplication.processEvents()
        time.sleep(0.1)
    await asyncio.sleep(0.5)

    # 9. Verify Download Button state
    print("[*] Verifying 'Download Selected' button...")
    selected = subview.get_selected_items()
    print(f"[*] Subview reported {len(selected)} selected items")
    
    if not browser.btn_sel_download.isEnabled():
        print(f"❌ FAILED: Download button not enabled. Counter text: '{browser.label_sel_count.text()}'")
        # Check if maybe the signal connection is broken
        print("[!] Forcing UI update to see if it helps...")
        browser._update_selection_ui()
        QApplication.processEvents()
        if browser.btn_sel_download.isEnabled():
            print("⚠️ WARNING: UI only updated after manual trigger!")
        else:
            print("❌ FAILED: Download button STILL not enabled after manual trigger.")
            app.quit()
            return
            
    print(f"✅ Download button enabled! Text: '{browser.label_sel_count.text()}'")

    # 10. Trigger Download
    print("[*] Clicking 'Download Selected'...")
    initial_tasks = len(window.download_manager.tasks)
    browser.btn_sel_download.click()
    QApplication.processEvents()
    await asyncio.sleep(1)

    # 11. Verify Queue
    print("[*] Verifying download manager queue...")
    new_tasks = len(window.download_manager.tasks)
    if new_tasks > initial_tasks:
        print(f"✅ SUCCESS: {new_tasks - initial_tasks} task(s) added to queue.")
        # Print details of added tasks
        for task in window.download_manager.tasks.values():
            print(f"    - Task: {task.title} | Status: {task.status}")
    else:
        print("❌ FAILED: No tasks added to download manager.")

    # 12. Verify Select Mode exited
    if browser._selection_mode:
        print("❌ FAILED: Select mode did not exit after download trigger.")
    else:
        print("✅ Select mode exited successfully.")

    app.quit()

if __name__ == "__main__":
    asyncio.run(drive_selection_download())
