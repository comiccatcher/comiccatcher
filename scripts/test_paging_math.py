import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from unittest.mock import MagicMock

from config import ConfigManager
from ui.app_layout import MainWindow
from models.opds import OPDSFeed, Metadata, Publication, Link

async def test_math():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    config_manager = ConfigManager()
    config_manager.set_scroll_method("viewport")
    
    window = MainWindow(config_manager)
    browser = window.browser_view
    
    # Mock API Client and Profile
    class MockProfile:
        def get_base_url(self): return "http://server"
    class MockClient:
        def __init__(self): self.profile = MockProfile()
    browser.api_client = MockClient()
    browser.image_manager = MagicMock()
    
    # 1. Simulate a large feed load (e.g. Page 1 of 213 items)
    print("--- Loading Mock Page 1 ---")
    pubs = [Publication(metadata=Metadata(title=f"Pub {i}"), links=[]) for i in range(100)]
    feed = OPDSFeed(
        metadata=Metadata(title="Test", numberOfItems=213, currentPage=1, itemsPerPage=100),
        publications=pubs,
        links=[Link(href="/page2", rel="next")]
    )
    browser.items_per_screen = 10
    browser.is_pub_mode = True
    
    # Manually trigger the post-load logic
    browser.total_items = feed.metadata.numberOfItems
    browser.items_buffer = feed.publications
    browser.next_url = "http://server/page2"
    browser.buffer_absolute_offset = 0
    browser.viewport_offset = 0
    
    browser._render_viewport_screen()
    print(f"UI: {browser.viewport_paging_bar.label_status.text()}")
    
    # 2. Page forward 3 times
    for _ in range(3):
        browser.next_viewport_screen()
    print(f"After 3 nexts: {browser.viewport_paging_bar.label_status.text()} (Offset: {browser.viewport_offset})")

    # 3. Simulate "End" click (Jump to Page 3 which has items 200-213)
    print("--- Jumping to Last Page ---")
    last_pubs = [Publication(metadata=Metadata(title=f"Last {i}"), links=[]) for i in range(13)]
    last_feed = OPDSFeed(
        metadata=Metadata(title="Test", numberOfItems=213, currentPage=3, itemsPerPage=100),
        publications=last_pubs,
        links=[Link(href="/page2", rel="prev")]
    )
    
    # Simulate _fetch_absolute_last results
    browser.items_buffer = last_feed.publications
    browser._update_after_fetch(last_feed, "http://server/last")
    
    # Align logic from browser.py:
    remainder = len(browser.items_buffer) % browser.items_per_screen # 13 % 10 = 3
    if remainder == 0:
        browser.viewport_offset = max(0, len(browser.items_buffer) - browser.items_per_screen)
    else:
        browser.viewport_offset = len(browser.items_buffer) - remainder # 13 - 3 = 10
        
    browser._render_viewport_screen()
    print(f"After End: {browser.viewport_paging_bar.label_status.text()}")
    print(f"Buffer Offset: {browser.viewport_offset}, Absolute Offset: {browser.buffer_absolute_offset}")
    
    # Final check: index 210 should be Screen 22
    # 200 (abs) + 10 (buf) = 210. 210 // 10 = 21. +1 = 22.
    # Total pages: 213 / 10 = 21.3 -> 22.
    
    print("Test complete.")
    app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(test_math())
