import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from qasync import QEventLoop

from config import ConfigManager
from ui.app_layout import MainWindow
from ui.views.browser import BrowserView

async def test_viewport_logic():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    config_manager = ConfigManager()
    # Force viewport mode for test
    config_manager.set_scroll_method("viewport")
    
    window = MainWindow(config_manager)
    browser = window.browser_view
    
    # Mock API Client and Profile
    class MockProfile:
        def get_base_url(self): return "http://test-server"
    class MockClient:
        def __init__(self): self.profile = MockProfile()
    browser.api_client = MockClient()
    
    print(f"Initial method: {config_manager.get_scroll_method()}")
    
    # Mock some items in the buffer
    class MockItem:
        def __init__(self, title, href="/"):
            self.title = title
            self.href = href
            self.rel = []
            self.links = []
            self.images = []
            self.metadata = type('obj', (object,), {'title': title})()

    browser.items_buffer = [MockItem(f"Item {i}") for i in range(100)]
    browser.items_per_screen = 10
    browser.viewport_offset = 0
    browser.is_pub_mode = False # List mode for simplicity
    
    # Manually trigger render to setup total pages
    browser._render_viewport_screen()
    print(f"Buffer size: {len(browser.items_buffer)}")
    print(f"Items per screen: {browser.items_per_screen}")
    print(f"Initial offset: {browser.viewport_offset}")
    
    # Test Next
    browser.next_viewport_screen()
    print(f"Offset after Next: {browser.viewport_offset}")
    
    # Test Prev
    browser.prev_viewport_screen()
    print(f"Offset after Prev: {browser.viewport_offset}")
    
    # Test Key Event Simulation
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    browser.keyPressEvent(event)
    print(f"Offset after Key Right: {browser.viewport_offset}")
    
    # Test Jump to End (Buffer based)
    browser.jump_to_viewport_offset(len(browser.items_buffer) - browser.items_per_screen)
    print(f"Offset after Jump to End: {browser.viewport_offset}")

    print("Test finished successfully.")
    app.quit()

if __name__ == "__main__":
    asyncio.run(test_viewport_logic())
