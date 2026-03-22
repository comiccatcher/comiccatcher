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

# Create a QApplication instance for testing PyQt widgets
app = QApplication(sys.argv)

class TestFeedBrowserLogic(unittest.TestCase):
    def setUp(self):
        self.mock_opds = MagicMock()
        self.mock_images = MagicMock()
        self.browser = FeedBrowser(self.mock_opds, self.mock_images)
        # Mock asyncio.create_task to avoid needing a running loop
        self._real_create_task = asyncio.create_task
        asyncio.create_task = MagicMock()

    def tearDown(self):
        asyncio.create_task = self._real_create_task

    def test_detect_template_path(self):
        # Case 1: Codex-style path
        feed = OPDSFeed(
            metadata=Metadata(title="Test", itemsPerPage=100),
            links=[Link(href="/codex/opds/v2.0/p/0/2", rel="next")]
        )
        self.browser._last_loaded_url = "https://example.com/codex/opds/v2.0/p/0/1"
        self.browser._detect_template(feed)
        
        self.assertEqual(self.browser._pagination_template, "https://example.com/codex/opds/v2.0/p/0/{page}")
        self.assertFalse(self.browser._is_offset_based)

    def test_detect_template_query_page(self):
        # Case 2: Query-style page
        feed = OPDSFeed(
            metadata=Metadata(title="Test", itemsPerPage=50),
            links=[Link(href="?page=2", rel="next")]
        )
        self.browser._last_loaded_url = "https://example.com/feed"
        self.browser._detect_template(feed)
        
        self.assertEqual(self.browser._pagination_template, "https://example.com/feed?page={page}")
        self.assertFalse(self.browser._is_offset_based)

    def test_detect_template_query_offset(self):
        # Case 3: Query-style offset
        feed = OPDSFeed(
            metadata=Metadata(title="Test", itemsPerPage=100),
            links=[Link(href="?offset=100", rel="next")]
        )
        self.browser._last_loaded_url = "https://example.com/feed"
        self.browser._detect_template(feed)
        
        self.assertEqual(self.browser._pagination_template, "https://example.com/feed?offset={page}")
        self.assertTrue(self.browser._is_offset_based)

    def test_surgical_prioritization(self):
        # Test that debounce prioritization picks the MOST RECENT requests that are visible
        self.browser._pagination_template = "https://example.com/{page}"
        self.browser._pending_page_requests = [1, 2, 3, 4, 5, 10]
        self.browser.grid_model._requested_pages.update([1, 2, 3, 4, 5, 10])
        
        # Mock indexAt to simulate that we scrolled to the bottom (row 900-1000)
        from PyQt6.QtCore import QModelIndex
        def mock_index_at(point):
            idx = MagicMock(spec=QModelIndex)
            idx.isValid.return_value = True
            # if point is 0,0 return row 900 (page 10)
            if point.x() == 0 and point.y() == 0:
                idx.row.return_value = 900
            else:
                idx.row.return_value = 999
            return idx
            
        self.browser.grid_view.indexAt = mock_index_at
        
        # We want to see if it picks the last few visible ones.
        # Visible pages: 9 to 11.
        self.browser._pending_page_requests = [1, 2, 3, 9, 10, 11]
        self.browser.grid_model._requested_pages.update([1, 2, 3, 9, 10, 11])
        
        # We need to mock _fetch_sparse_page_to_model to avoid actual network/async issues
        self.browser._fetch_sparse_page_to_model = MagicMock()
        self.browser.grid_view.setVisible(True)
        self.browser.grid_model.update_total_count(1000)
        
        # Trigger actual work
        self.browser._do_update_status()
        
        # Check that it called _fetch_sparse_page_to_model for the right ones
        # Calls were for 11, 10, 9 in that order (reversed)
        calls = self.browser._fetch_sparse_page_to_model.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][0][1], 11)
        self.assertEqual(calls[1][0][1], 10)
        self.assertEqual(calls[2][0][1], 9)
        
        # Note: In the refactored version, we cleared pending requests but didn't 
        # explicitly discard from model's set to keep it simple. 
        # If we need that, we can re-add it. For now, we only verify it fetched correctly.

if __name__ == "__main__":
    unittest.main()
