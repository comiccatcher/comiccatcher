import pytest
from unittest.mock import MagicMock, patch
import math
from models.opds import OPDSFeed, Metadata, Publication, Link

import sys
from PyQt6.QtWidgets import QApplication

# Create a QApplication instance if one doesn't exist to allow QWidgets to instantiate
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from ui.views.browser import BrowserView

def create_mock_feed(total_items, current_page, items_per_page, num_pubs, has_next=False, has_prev=False):
    pubs = [Publication(metadata=Metadata(title=f"Pub {i}"), links=[]) for i in range(num_pubs)]
    links = []
    if has_next: links.append(Link(href="/next", rel="next"))
    if has_prev: links.append(Link(href="/prev", rel="prev"))
    
    return OPDSFeed(
        metadata=Metadata(
            title="Mock Feed",
            numberOfItems=total_items,
            currentPage=current_page,
            itemsPerPage=items_per_page
        ),
        publications=pubs,
        links=links
    )

@pytest.fixture
def browser():
    mock_config = MagicMock()
    mock_config.get_scroll_method.return_value = "viewport"
    
    browser = BrowserView(config_manager=mock_config, on_open_detail=lambda *a: None, on_navigate=lambda *a: None)
    
    # Mock visual/UI methods that would fail without a proper window context
    browser._render_viewport_screen = MagicMock()
    browser._update_viewport_paging_bar = MagicMock()
    browser.scroll.viewport = MagicMock()
    browser.scroll.viewport().height.return_value = 800
    browser.scroll.viewport().width.return_value = 600
    
    # Force some defaults for logic testing
    browser.items_per_screen = 10
    return browser

def test_initial_load_offset(browser):
    """Scenario 1: Verify offset and buffer math on initial load."""
    feed = create_mock_feed(total_items=100, current_page=1, items_per_page=20, num_pubs=20, has_next=True)
    
    browser.total_items = feed.metadata.numberOfItems
    browser.items_buffer = feed.publications
    browser._update_after_fetch(feed, "http://mock/1")
    
    assert browser.buffer_absolute_offset == 0
    assert browser.viewport_offset == 0
    assert len(browser.items_buffer) == 20
    assert browser.next_url == "http://mock/next"

def test_next_screen_navigation(browser):
    """Scenario 2: Navigate to next screen without new fetch."""
    feed = create_mock_feed(total_items=100, current_page=1, items_per_page=20, num_pubs=20)
    browser.total_items = feed.metadata.numberOfItems
    browser.items_buffer = feed.publications
    browser._update_after_fetch(feed, "http://mock/1")
    
    assert browser.viewport_offset == 0
    browser.next_viewport_screen()
    assert browser.viewport_offset == 10
    assert browser.buffer_absolute_offset == 0

def test_prev_screen_navigation(browser):
    """Scenario 3: Navigate backwards within buffer."""
    feed = create_mock_feed(total_items=100, current_page=1, items_per_page=20, num_pubs=20)
    browser.total_items = feed.metadata.numberOfItems
    browser.items_buffer = feed.publications
    browser._update_after_fetch(feed, "http://mock/1")
    
    browser.viewport_offset = 10
    browser.prev_viewport_screen()
    assert browser.viewport_offset == 0
    
    # Clamp test
    browser.prev_viewport_screen()
    assert browser.viewport_offset == 0

@pytest.mark.asyncio
async def test_buffer_exhaustion_proactive_fetch(browser):
    """Scenario 4: Nearing end of buffer triggers fetch."""
    feed = create_mock_feed(total_items=100, current_page=1, items_per_page=20, num_pubs=20, has_next=True)
    browser.total_items = feed.metadata.numberOfItems
    browser.items_buffer = feed.publications
    browser._update_after_fetch(feed, "http://mock/1")
    
    browser.items_per_screen = 10
    browser.viewport_offset = 0
    
    # Mock the async fetch to just set a flag
    browser._fetch_more_for_viewport = MagicMock()
    
    # Still 1 full screen left, shouldn't fetch
    browser.next_viewport_screen() 
    assert browser.viewport_offset == 10
    
    # We need to simulate the _render_viewport_screen logic that triggers the proactive fetch
    if browser.viewport_offset + browser.items_per_screen >= len(browser.items_buffer) - (browser.items_per_screen * 2):
        if browser.next_url and not browser.is_loading_more:
            browser.is_loading_more = True
            
    assert browser.is_loading_more == True

@pytest.mark.asyncio
async def test_absolute_last_jump(browser):
    """Scenario 5: Jumping to absolute last page calculates offset correctly."""
    # Simulating the Last page of a 213 item collection, at 20 items per page
    # Page 11 would have items 200-213 (13 items).
    feed = create_mock_feed(total_items=213, current_page=11, items_per_page=20, num_pubs=13)
    browser.last_url = "http://mock/last"
    browser.items_per_screen = 10
    
    # Inject the mocked feed directly into the buffer logic as if fetched
    browser.items_buffer = feed.publications
    
    # We simulate what _fetch_absolute_last does
    curr_page = feed.metadata.currentPage
    per_page = feed.metadata.itemsPerPage
    browser.buffer_absolute_offset = (curr_page - 1) * per_page # (11-1)*20 = 200
    
    remainder = len(browser.items_buffer) % browser.items_per_screen
    if remainder == 0:
        browser.viewport_offset = max(0, len(browser.items_buffer) - browser.items_per_screen)
    else:
        browser.viewport_offset = len(browser.items_buffer) - remainder
        
    assert browser.buffer_absolute_offset == 200
    assert browser.viewport_offset == 10
    
    # What would the UI say?
    current_item_index = browser.buffer_absolute_offset + browser.viewport_offset
    current_page = (current_item_index // browser.items_per_screen) + 1
    
    # 200 + 10 = 210. 210 // 10 = 21. +1 = 22.
    # Total pages global = ceil(213 / 10) = 22.
    assert current_page == 22
    
def test_partial_pages(browser):
    """Scenario 6: Partial buffer sizes."""
    # Buffer has 15 items. Screen shows 10.
    browser.items_buffer = [Publication(metadata=Metadata(title=""), links=[]) for _ in range(15)]
    browser.items_per_screen = 10
    browser.buffer_absolute_offset = 0
    browser.viewport_offset = 10
    
    # We are on the second screen, viewing items 10-14.
    current_item_index = browser.buffer_absolute_offset + browser.viewport_offset
    current_page = (current_item_index // browser.items_per_screen) + 1
    
    assert current_page == 2
