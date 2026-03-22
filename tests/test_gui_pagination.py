import sys
import os
import asyncio
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from pathlib import Path

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

from config import ConfigManager
from ui.app_layout import MainWindow, ViewIndex

async def drive_pagination_test():
    print("--- STARTING HYBRID GUI DRIVER TEST ---")
    
    # 1. Setup App
    app = QApplication.instance() or QApplication(sys.argv)
    loop = asyncio.get_event_loop()
    
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.show() # Headless but initialized
    
    print("App launched. Waiting for initial feed load...")
    await asyncio.sleep(2)
    
    # 2. Target the Large Series Feed (Known to have many pages)
    target_url = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/1?topGroup=p"
    print(f"Navigating to: {target_url}")
    await window.feed_browser.load_url(target_url)
    await asyncio.sleep(2)
    
    # 3. Verify Hybrid Layout
    browser = window.feed_browser
    model = browser.grid_model
    initial_count = model.rowCount()
    
    print(f"Browser State: {browser.status_label.text()}")
    print(f"Initial rowCount: {initial_count}")
    
    if initial_count < 100:
        print("ERROR: Grid model didn't load enough items for Page 1.")
        app.quit()
        sys.exit(1)

    # 4. SIMULATE SCROLL TO SKELETON
    # Row 150 should be a skeleton if Page 2 hasn't loaded
    print("Accessing Row #150 to trigger sparse fetch...")
    # This call to data() should trigger the signal
    index_150 = model.index(150)
    model.data(index_150)
    
    # 5. WAIT FOR FETCH
    print("Waiting for sparse page fetch...")
    for i in range(10):
        await asyncio.sleep(1)
        # Check if row 150 now has real data (not a skeleton)
        item = model.get_item(150)
        if item:
            print(f"SUCCESS: Row 150 now has data: {item.title}")
            print(f"Final Row Count: {model.rowCount()}")
            print("--- TEST PASSED ---")
            app.quit()
            return
        else:
            print(f"Still waiting... {i+1}/10")

    print(f"FAILURE: Row 150 is still empty after 10 seconds.")
    app.quit()
    sys.exit(1)

if __name__ == "__main__":
    loop = QEventLoop(QApplication(sys.argv))
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(drive_pagination_test())
