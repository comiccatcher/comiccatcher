import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QListView
from PyQt6.QtCore import QTimer

# Ensure we can import from the project root
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "comiccatcher"))

from ui.views.feed_browser import FeedBrowser
from models.feed_page import FeedPage, FeedSection, FeedItem, ItemType, SectionLayout
from models.opds import OPDSFeed, Metadata

# Create a QApplication instance for testing PyQt widgets
app = QApplication.instance() or QApplication(sys.argv)

class TestSurgicalUIUpdates(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_opds = MagicMock()
        self.mock_images = MagicMock()
        # Mock image_manager._get_cache_path to return a mock path
        self.mock_images._get_cache_path.return_value.exists.return_value = False
        
        self.browser = FeedBrowser(self.mock_opds, self.mock_images)
        
        # Mock recalculate to avoid layout math in units
        self.browser._recalculate_section_heights = MagicMock()

    def test_collapse_all_surgical(self):
        # Setup mock sections and views
        section1 = FeedSection(section_id="s1", title="S1", items=[])
        section2 = FeedSection(section_id="s2", title="S2", items=[])
        self.browser._last_page = FeedPage(title="Test", sections=[section1, section2])
        
        view1 = MagicMock(spec=QListView)
        view2 = MagicMock(spec=QListView)
        self.browser._section_views = [view1, view2]
        
        self.browser.collapse_all()
        
        # Assertions
        self.assertIn("s1", self.browser._collapsed_sections)
        self.assertIn("s2", self.browser._collapsed_sections)
        view1.setVisible.assert_called_with(False)
        view1.setFixedHeight.assert_called_with(0)
        view2.setVisible.assert_called_with(False)
        view2.setFixedHeight.assert_called_with(0)

    def test_expand_all_surgical(self):
        # Setup
        self.browser._collapsed_sections = {"s1", "s2"}
        view1 = MagicMock(spec=QListView)
        view2 = MagicMock(spec=QListView)
        self.browser._section_views = [view1, view2]
        
        self.browser.expand_all()
        
        # Assertions
        self.assertEqual(len(self.browser._collapsed_sections), 0)
        view1.setVisible.assert_called_with(True)
        view2.setVisible.assert_called_with(True)
        self.browser._recalculate_section_heights.assert_called()

    @patch("api.feed_reconciler.FeedReconciler.reconcile")
    async def test_prefetch_adjacent_pages(self, mock_reconcile):
        # Setup
        self.browser._paging_urls = {
            "next": "http://example.com/p2",
            "previous": "http://example.com/p0",
            "last": "http://example.com/p99"
        }
        self.browser._current_context_id = 123.456
        
        # Mock OPDS response
        mock_feed = MagicMock(spec=OPDSFeed)
        self.mock_opds.get_feed.return_value = asyncio.Future()
        self.mock_opds.get_feed.return_value.set_result(mock_feed)
        
        # Mock Reconciler output using real Pydantic models
        item = FeedItem(
            identifier="i1",
            title="Item 1",
            type=ItemType.BOOK,
            cover_url="http://example.com/cover.jpg"
        )
        mock_page = FeedPage(title="Page X", sections=[
            FeedSection(section_id="sx", title="SX", items=[item])
        ])
        mock_reconcile.return_value = mock_page
        
        # We can now await directly with IsolatedAsyncioTestCase
        await self.browser._prefetch_adjacent_pages()
        
        # Verify calls
        self.assertEqual(self.mock_opds.get_feed.call_count, 3)
        self.assertIn("http://example.com/p2", self.browser._page_cache)
        self.assertIn("http://example.com/p0", self.browser._page_cache)
        self.assertIn("http://example.com/p99", self.browser._page_cache)
        
        # Verify cover prefetch was triggered
        self.assertTrue(len(self.browser._active_cover_tasks) > 0)

if __name__ == "__main__":
    unittest.main()
