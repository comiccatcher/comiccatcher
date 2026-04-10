import asyncio
from typing import Set, Tuple, Optional, Callable
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QListView
from comiccatcher.models.feed_page import FeedItem

class ViewportHelper:
    """
    Shared utilities for viewport visibility detection and resource fetching.
    Consolidates logic used by FeedBrowser, FeedDetailView, and others.
    """

    @staticmethod
    def get_visible_range(view: QListView, buffer: int = 0) -> Tuple[int, int]:
        """
        Calculates the range of visible row indices (first, last) in a QListView.
        Robust against margins and gutters by checking multiple probe points
        and adding a small safety buffer.
        """
        from comiccatcher.ui.theme_manager import UIConstants
        if not view or not view.isVisible():
            return 0, -1
            
        vp = view.viewport()
        if not vp:
            return 0, -1
            
        rect = vp.rect()
        w = rect.width()
        h = rect.height()
        
        # 1. Detect First Visible Item
        # Check top-left and top-center
        fi = view.indexAt(QPoint(UIConstants.VIEWPORT_MARGIN, UIConstants.VIEWPORT_MARGIN))
        if not fi.isValid():
            fi = view.indexAt(QPoint(w // 2, UIConstants.VIEWPORT_MARGIN))
            
        # 2. Detect Last Visible Item
        # Check bottom-right, bottom-center, and bottom-left
        li = view.indexAt(QPoint(w - UIConstants.VIEWPORT_MARGIN, h - UIConstants.VIEWPORT_MARGIN))
        if not li.isValid():
            li = view.indexAt(QPoint(w // 2, h - UIConstants.VIEWPORT_MARGIN))
        if not li.isValid():
            li = view.indexAt(QPoint(UIConstants.VIEWPORT_MARGIN, h - UIConstants.VIEWPORT_MARGIN))
        
        model = view.model()
        row_count = model.rowCount() if model else 0
        if row_count == 0:
            return 0, -1

        first = fi.row() if fi.isValid() else 0
        
        if li.isValid():
            last = li.row()
        else:
            # Fallback estimation: use viewport height and scroll position
            # We assume a standard card height if we can't detect one
            from comiccatcher.ui.theme_manager import UIConstants
            # Use unscaled BASE_CARD_HEIGHT as a safe minimum if scaling isn't init'd
            card_h = UIConstants.get_card_height(True) or 300 
            
            inner_scroll = view.verticalScrollBar().value()
            # Estimate row based on scroll
            first_est = max(0, (inner_scroll // card_h) * 2) # conservative 2 cols
            visible_rows = (h // card_h) + 2 # +2 rows for safety
            last = min(row_count - 1, first_est + (visible_rows * 10)) # very safe 10 cols

        # 3. Add safety buffer (usually 1 row) to prevent cancellation flickering
        # We assume 2-10 columns, so +10 is a safe "one row" buffer
        first = max(0, first - 5)
        last = min(row_count - 1, last + 10)
            
        if buffer > 0:
            first = max(0, first - buffer)
            last = min(row_count - 1, last + buffer)
            
        return first, last

    @staticmethod
    def get_visible_urls(view: QListView) -> Set[str]:
        """Returns a set of all cover URLs currently visible in the view's viewport."""
        urls = set()
        if not view or not view.isVisible():
            return urls
            
        model = view.model()
        if not model:
            return urls
            
        first, last = ViewportHelper.get_visible_range(view)
        if last < 0:
            return urls
            
        for row in range(first, last + 1):
            item = model.get_item(row)
            if isinstance(item, FeedItem) and item.cover_url:
                urls.add(item.cover_url)
        return urls

    @staticmethod
    async def fetch_cover_async(
        url: str, 
        image_manager, 
        pending_set: Set[str], 
        on_done_callback: Optional[Callable] = None,
        max_dim: int = 400,
        timeout: Optional[float] = None
    ):
        """
        Asynchronously fetches a cover thumbnail via ImageManager.
        Manages a 'pending_set' to prevent redundant concurrent requests.
        """
        if not url or url in pending_set:
            return
            
        pending_set.add(url)
        try:
            await image_manager.get_image_b64(url, max_dim=max_dim, timeout=timeout)
        except Exception:
            # Failures are logged by ImageManager
            pass
        finally:
            pending_set.discard(url)
            
        if on_done_callback:
            on_done_callback()
