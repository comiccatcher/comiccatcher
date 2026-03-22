from typing import List, Optional, Dict
from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QSize, pyqtSignal
from models.feed_page import FeedItem, ItemType

class FeedBrowserModel(QAbstractListModel):
    """
    A Qt model that supports a 'Sparse Buffer' for zero-jump scrolling.
    Can pre-allocate thousands of rows and signal when missing data is scrolled into view.
    """
    
    # Custom roles
    ItemDataRole = Qt.ItemDataRole.UserRole + 1
    
    # Signals
    page_request_needed = pyqtSignal(int) # page_index
    cover_request_needed = pyqtSignal(str) # cover_url

    def __init__(self, total_count: int = 0, items_per_page: int = 100):
        super().__init__()
        self._total_count = total_count
        self._items_per_page = items_per_page
        
        # We use a dict for the sparse buffer: { index: FeedItem }
        self._items: Dict[int, FeedItem] = {}
        self._requested_pages = set()
        self._requested_covers = set()

    def rowCount(self, parent=QModelIndex()):
        return self._total_count

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < self._total_count):
            return None
        
        row = index.row()
        item = self._items.get(row)
        
        # 1. Handle Missing Data (Trigger Pagination)
        if item is None:
            page_idx = (row // self._items_per_page) + 1
            if page_idx not in self._requested_pages:
                self._requested_pages.add(page_idx)
                self.page_request_needed.emit(page_idx)
            
            # Return a "Skeleton" item
            if role == self.ItemDataRole:
                return FeedItem(
                    type=ItemType.EMPTY,
                    title="Loading...",
                    identifier=f"empty_{row}"
                )
            return None

        # 2. Handle Existing Data
        if role == self.ItemDataRole:
            # TRIGGER COVER FETCH IF NOT ALREADY REQUESTED
            if item.cover_url and item.cover_url not in self._requested_covers:
                self._requested_covers.add(item.cover_url)
                self.cover_request_needed.emit(item.cover_url)
            return item
        elif role == Qt.ItemDataRole.DisplayRole:
            return item.title
        
        return None

    def update_total_count(self, new_total: int):
        """Pre-allocate the scrollbar height."""
        if new_total == self._total_count:
            return
            
        self.beginResetModel()
        self._total_count = new_total
        self.endResetModel()

    def set_items_for_page(self, page_index: int, items: List[FeedItem]):
        """Inject fetched items into their correct sparse slots."""
        if not items:
            return
            
        start_row = (page_index - 1) * self._items_per_page
        
        for i, item in enumerate(items):
            row = start_row + i
            if row >= self._total_count:
                # If server sent more than we expected, expand (rare)
                self._total_count = row + 1
                
            self._items[row] = item
            
        # Notify view that these rows changed (replaces Skeletons with real cards)
        self.dataChanged.emit(
            self.index(start_row), 
            self.index(start_row + len(items) - 1)
        )

    def clear(self):
        self.beginResetModel()
        self._items = {}
        self._requested_pages = set()
        self._requested_covers = set()
        self._total_count = 0
        self.endResetModel()
        
    def get_item(self, row: int) -> Optional[FeedItem]:
        return self._items.get(row)
