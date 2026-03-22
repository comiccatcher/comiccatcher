import sys
import os
import asyncio
import time
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

from config import ConfigManager
from ui.app_layout import MainWindow

async def drive_surgical_test():
    print("--- STARTING SURGICAL FETCHING TEST ---")
    app = QApplication.instance() or QApplication(sys.argv)
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.show()
    
    browser = window.feed_browser
    
    # 1. TEST CONTEXT ISOLATION
    # Rapidly switch between two feeds
    url_issues = "https://anville.duckdns.org:2700/codex/opds/v2.0/s/0/1?topGroup=s"
    url_series = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/1?topGroup=p"
    
    print(f"Switching Context: Issues -> Series...")
    # Fire load for Issues
    asyncio.create_task(browser.load_url(url_issues))
    # IMMEDIATELY switch to Series (within 50ms)
    await asyncio.sleep(0.05)
    await browser.load_url(url_series)
    
    # Wait for load to finish
    await asyncio.sleep(3)
    
    print(f"Current View Status: {browser.status_label.text()}")
    if "Series" not in browser.status_label.text():
        print("FAILURE: Context switch failed. Status should be 'All Series'.")
        sys.exit(1)
    
    # 2. TEST SCROLL DEBOUNCE
    # We are in Series (3,193 items). We will rapidly "touch" rows to exceed the 3-page limit
    print("Simulating rapid scroll flick (Rows 100 -> 500 -> 1000 -> 1500 -> 2000)...")
    model = browser.grid_model
    
    # Touch 5 different pages in < 150ms
    model.data(model.index(100))
    await asyncio.sleep(0.02)
    model.data(model.index(500))
    await asyncio.sleep(0.02)
    model.data(model.index(1000))
    await asyncio.sleep(0.02)
    model.data(model.index(1500))
    await asyncio.sleep(0.02)
    model.data(model.index(2000))
    
    # Actually scroll the view to row 2000 so the viewport filtering sees it as visible
    browser.grid_view.scrollTo(model.index(2000))
    
    # Verify the debounce set (should have 5 items pending)
    print(f"Model total count: {browser.grid_model._total_count}")
    print(f"Pagination template: {browser._pagination_template}")
    print(f"Model requested pages: {browser.grid_model._requested_pages}")
    print(f"Pending page requests in debounce set: {browser._pending_page_requests}")
    
    # Wait for debounce timeout (150ms) and network
    print("Waiting for debounce timeout and fetch...")
    await asyncio.sleep(2)
    
    # Check Row 2000 (Page 21 approx)
    item_2000 = model.get_item(2000)
    if item_2000:
        print(f"SUCCESS: Row 2000 populated: {item_2000.title}")
    else:
        print("FAILURE: Row 2000 was not populated.")
        sys.exit(1)

    # 3. TEST SCROLLING BACK (DROPPED REQUESTS)
    print("Simulating scrolling back to Row 100 (which was dropped)...")
    # Touch row 100 again (Page 2)
    model.data(model.index(100))
    browser.grid_view.scrollTo(model.index(100))
    
    print(f"Pending page requests after scrolling back: {browser._pending_page_requests}")
    if len(browser._pending_page_requests) == 0:
        print("FAILURE: Page request for Row 100 was not re-queued!")
        sys.exit(1)
        
    print("Waiting for fetch...")
    await asyncio.sleep(2)
    
    item_100 = model.get_item(100)
    if item_100:
        print(f"SUCCESS: Row 100 populated after scrolling back: {item_100.title}")
    else:
        print("FAILURE: Row 100 was not populated after scrolling back.")
        sys.exit(1)

    print("--- SURGICAL TEST PASSED ---")
    app.quit()

if __name__ == "__main__":
    loop = QEventLoop(QApplication(sys.argv))
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(drive_surgical_test())
