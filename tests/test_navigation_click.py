import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication

# Ensure we can import from the project root
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "comiccatcher"))

from ui.app_layout import MainWindow
from config import ConfigManager
from models.feed_page import FeedItem, ItemType, Link

# Create a QApplication instance for testing PyQt widgets
app = QApplication.instance() or QApplication(sys.argv)

class TestNavigationClick(unittest.TestCase):
    def setUp(self):
        from PyQt6.QtGui import QIcon
        self.config = MagicMock(spec=ConfigManager)
        self.config.feeds = []
        # Avoid side-effects in MainWindow init
        with patch('ui.app_layout.MainWindow._restore_last_state'), \
             patch('ui.theme_manager.ThemeManager.get_icon', return_value=QIcon()), \
             patch('asyncio.create_task'):
            self.window = MainWindow(self.config)

    def test_folder_click_navigates(self):
        # Mock on_navigate_to_url
        self.window.on_navigate_to_url = MagicMock()
        self.window.feed_browser._last_loaded_url = "http://base/"
        
        # Create a folder item
        folder_item = FeedItem(
            type=ItemType.FOLDER,
            title="Publishers",
            identifier="pub_id",
            raw_link=Link(href="publishers/")
        )
        
        # Trigger the click handler
        self.window._on_feed_item_clicked(folder_item)
        
        # Verify on_navigate_to_url was called with correct absolute URL
        self.window.on_navigate_to_url.assert_called_once_with(
            "http://base/publishers/", "Publishers"
        )

if __name__ == "__main__":
    unittest.main()
