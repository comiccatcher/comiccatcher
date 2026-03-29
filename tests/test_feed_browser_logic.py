import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication

# Ensure we can import from the project root
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "comiccatcher"))

from ui.views.feed_browser import FeedBrowser
from models.opds import OPDSFeed, Metadata, Link

app = QApplication(sys.argv)

class TestFeedBrowserLogic(unittest.TestCase):
    def setUp(self):
        self.mock_images = MagicMock()
        self.browser = FeedBrowser(MagicMock(), self.mock_images)
        self._real_create_task = asyncio.create_task
        asyncio.create_task = MagicMock()

    def tearDown(self):
        asyncio.create_task = self._real_create_task

    def test_detect_template_path(self):
        feed = OPDSFeed(
            metadata=Metadata(title="Test", itemsPerPage=100),
            links=[Link(href="/codex/opds/v2.0/p/0/2", rel="next")]
        )
        self.browser._last_loaded_url = "https://example.com/codex/opds/v2.0/p/0/1"
        self.browser._detect_template(feed)
        self.assertEqual(self.browser._pagination_template, "https://example.com/codex/opds/v2.0/p/0/{page}")

    def test_detect_template_query_page(self):
        feed = OPDSFeed(
            metadata=Metadata(title="Test", itemsPerPage=50),
            links=[Link(href="?page=2", rel="next")]
        )
        self.browser._last_loaded_url = "https://example.com/feed"
        self.browser._detect_template(feed)
        self.assertEqual(self.browser._pagination_template, "https://example.com/feed?page={page}")

    def test_surgical_prioritization(self):
        # Test that debounce prioritization picks the MOST RECENT requests that are visible
        self.browser._pagination_template = "https://example.com/{page}"
        
        # Setup View Geometry
        self.browser._main_grid_view = MagicMock()
        self.browser._main_grid_view.isVisible.return_value = True
        self.browser._main_grid_view.width.return_value = 800
        self.browser._main_grid_view.height.return_value = 1000000 # Large height for scroll coordinate
        self.browser._main_grid_view.gridSize.return_value.isValid.return_value = False
        self.browser._main_grid_view.spacing.return_value = 10
        
        mock_delegate = MagicMock()
        mock_delegate.card_width = 120
        mock_delegate.card_height = 180
        self.browser._main_grid_view.itemDelegate.return_value = mock_delegate

        # Dashboard Mode
        self.browser.stack = MagicMock()
        self.browser.stack.currentWidget.return_value = self.browser.dash_scroll

        self.browser._main_grid_model = self.browser.grid_model
        self.browser.grid_model.update_total_count(1500)
        self.browser.grid_model._items = {}
        self.browser.grid_model._requested_pages = set()

        # Visible Region (Pages 9, 10, 11, 12, 13)
        # item_h = 190. row 900 / 6 = 150. y = 150 * 190 = 28500
        from PyQt6.QtCore import QPoint
        def mock_map_from(view, pt):
            if pt.x() == 0 and pt.y() == 0: return QPoint(0, 28500)
            return QPoint(800, 35000)
        self.browser._main_grid_view.mapFrom.side_effect = mock_map_from

        # Setup Pending Queue
        self.browser._pending_page_requests = [1, 2, 3, 9, 10, 11]
        # Mark as requested so proactive logic doesn't re-add everything, but 12, 13 will be added.
        self.browser.grid_model._requested_pages.update([1, 2, 3, 9, 10, 11])
        
        self.browser._fetch_sparse_page_to_model = MagicMock()
        self.browser._do_update_status()

        calls = self.browser._fetch_sparse_page_to_model.call_args_list
        # Priority should be bottom-up visible: 13, 12, 11
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][0][1], 13)
        self.assertEqual(calls[1][0][1], 12)
        self.assertEqual(calls[2][0][1], 11)

if __name__ == "__main__":
    unittest.main()
