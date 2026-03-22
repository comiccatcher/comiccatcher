import sys
import os
import asyncio
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

sys.path.append(os.getcwd())
from config import ConfigManager
from ui.app_layout import MainWindow

async def drive_issues():
    app = QApplication.instance() or QApplication(sys.argv)
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    window.show()
    
    browser = window.feed_browser
    
    print("Waiting for app to settle...")
    await asyncio.sleep(2)
    
    # 0. Simulate selecting the first feed to initialize the API Client
    feed_profile = config_manager.feeds[0]
    window.on_feed_selected(feed_profile)
    await asyncio.sleep(1)
    
    url_feed = "https://anville.duckdns.org:2700/codex/opds/v2.0/s/0/1?topGroup=s"
    print("Loading Issues feed...")
    await browser.load_url(url_feed)
    
    await asyncio.sleep(4)
    print(f"Pending requests after load: {browser._pending_page_requests}")
    print(f"Status label: {browser.status_label.text()}")
    print(f"Grid active: {browser.grid_view.isVisible()}")
    
    print("Scrolling to middle...")
    model = browser.grid_model
    middle_idx = model._total_count // 2
    
    print(f"Total count is {model._total_count}, Middle index is {middle_idx}")
    
    # Touch the middle index to trigger data
    model.data(model.index(middle_idx))
    # Actually scroll the view so that the status label updates correctly
    browser.grid_view.scrollTo(model.index(middle_idx))
    
    # Wait for debounce and network fetch
    await asyncio.sleep(5)
    
    item = model.get_item(middle_idx)
    if item:
        print(f"SUCCESS: Item populated: {item.title}")
    else:
        print("FAILURE: Item not populated")
        
    print(f"Status label after scroll: {browser.status_label.text()}")
    
    app.quit()

if __name__ == "__main__":
    loop = QEventLoop(QApplication(sys.argv))
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(drive_issues())
