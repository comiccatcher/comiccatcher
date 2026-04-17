# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import List, Optional, Dict, Set, Any
from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QSize, pyqtSignal
from comiccatcher.models.feed_page import FeedItem, ItemType as FeedItemType
from comiccatcher.ui.theme_manager import UIConstants
from enum import Enum

class CompositeItemType(Enum):
    HEADER = 1
    RIBBON = 2
    GRID_ITEM = 3

class CompositeItem:
    def __init__(self, type: CompositeItemType, section_id: str, data: Any = None, absolute_index: int = -1):
        self.type = type
        self.section_id = section_id
        self.data = data # FeedSection for HEADER/RIBBON, FeedItem for GRID_ITEM
        self.absolute_index = absolute_index # For grid items, their index in the sparse buffer

class FeedBrowserModel(QAbstractListModel):
    """
    A unified model for the Composite Virtual Dashboard.
    Supports mixing embedded widgets (headers, ribbons) with thousands of virtualized grid items.
    """
    
    ItemDataRole = Qt.ItemDataRole.UserRole + 1
    IsCollapsedRole = Qt.ItemDataRole.UserRole + 2
    CompositeTypeRole = Qt.ItemDataRole.UserRole + 3

    page_request_needed = pyqtSignal(int)
    cover_request_needed = pyqtSignal(str)

    def __init__(self, items_per_page: int = None, collapsed_sections: Optional[Set[str]] = None):
        super().__init__()
        self._items_per_page = items_per_page or UIConstants.DEFAULT_PAGING_STRIDE
        
        # Sparse buffer for the MAIN grid section: { absolute_index: FeedItem }
        self._sparse_items: Dict[int, FeedItem] = {}
        self._total_grid_items = 0
        self._grid_section_id = None
        
        self._requested_pages = set()
        self._loaded_pages = set()
        self._requested_covers = set()
        
        # The flattened list of items currently visible in the QListView
        self._logical_items: List[CompositeItem] = []
        
        # Raw sections for rebuilding the map
        self._raw_sections = []
        # Share the collapsed state with the parent view if provided
        self._collapsed_sections = collapsed_sections if collapsed_sections is not None else set()

    def update_total_count(self, count: int):
        """Standard method for updating total items, used by Detail View Carousels."""
        self.beginResetModel()
        self._total_grid_items = count
        self._rebuild_logical_map()
        self.endResetModel()

    def set_sections(self, sections: List[Any], main_grid_section_id: Optional[str] = None):
        """Configures the dashboard structure."""
        self.beginResetModel()
        self._raw_sections = sections
        self._grid_section_id = main_grid_section_id
        
        # If we have a main grid, initialize its total count
        for s in sections:
            if s.section_id == main_grid_section_id:
                self._total_grid_items = s.total_items or len(s.items)
                if s.items and s.current_page:
                    self._loaded_pages.add(s.current_page)
                break
        
        self._rebuild_logical_map()
        self.endResetModel()

    def toggle_section(self, section_id: str):
        self.beginResetModel()
        if section_id in self._collapsed_sections:
            self._collapsed_sections.discard(section_id)
        else:
            self._collapsed_sections.add(section_id)
        self._rebuild_logical_map()
        self.endResetModel()

    def expand_all(self):
        self.beginResetModel()
        self._collapsed_sections.clear()
        self._rebuild_logical_map()
        self.endResetModel()

    def collapse_all(self):
        self.beginResetModel()
        for section in self._raw_sections:
            self._collapsed_sections.add(section.section_id)
        self._rebuild_logical_map()
        self.endResetModel()

    def _rebuild_logical_map(self):
        self._logical_items = []
        
        # If we only have one section, don't prepend a redundant HEADER row
        # unless it's the main grid section.
        multi_section = len(self._raw_sections) > 1

        for section in self._raw_sections:
            sid = section.section_id
            
            # 1. Add Header row only in multi-section mode
            if multi_section:
                self._logical_items.append(CompositeItem(CompositeItemType.HEADER, sid, section))
            
            if sid in self._collapsed_sections:
                continue
                
            # 2. Content row(s)
            if sid == self._grid_section_id:
                # This is the massive grid. Flatten every single potential item.
                for i in range(self._total_grid_items):
                    self._logical_items.append(CompositeItem(CompositeItemType.GRID_ITEM, sid, absolute_index=i))
            else:
                from comiccatcher.models.feed_page import SectionLayout
                if getattr(section, 'layout', None) == SectionLayout.RIBBON:
                    # Ribbons are a single row (the ribbon widget)
                    # Note: In Dashboard mode, the 'view' is the ribbon, so it shouldn't contain itself
                    if multi_section:
                        self._logical_items.append(CompositeItem(CompositeItemType.RIBBON, sid, section))
                    else:
                        # Single-section ribbon: the model just holds the items
                        for i, item in enumerate(section.items):
                            self._logical_items.append(CompositeItem(CompositeItemType.GRID_ITEM, sid, data=item))
                else:
                    # Small grids: add individual items
                    for i, item in enumerate(section.items):
                        self._logical_items.append(CompositeItem(CompositeItemType.GRID_ITEM, sid, data=item))

    @property
    def items(self):
        """Compatibility property for older code accessing the item buffer."""
        return self._sparse_items

    def rowCount(self, parent=QModelIndex()):
        if self._logical_items:
            return len(self._logical_items)
        return len(self._sparse_items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        row = index.row()
        
        # Suppress tooltips for cards in the feed view
        if role == Qt.ItemDataRole.ToolTipRole:
            return None

        # 1. Handle Composite Type Role
        if role == self.CompositeTypeRole:
            if row < len(self._logical_items):
                return self._logical_items[row].type
            return CompositeItemType.GRID_ITEM # Default for standard/dashboard models
            
        if row >= len(self._logical_items):
            # Fallback for standard/dashboard models without logical map
            if role == self.IsCollapsedRole: return False
            
            # Simple list behavior
            abs_idx = row
            item = self._sparse_items.get(abs_idx)
            
            if role == Qt.ItemDataRole.DisplayRole:
                return item.title if item else "Loading..."
            if role == self.ItemDataRole:
                return item
            return None

        logical_item = self._logical_items[row]

        # For Headers and Ribbons, return the section object
        if logical_item.type in (CompositeItemType.HEADER, CompositeItemType.RIBBON):
            if role == self.ItemDataRole:
                return logical_item.data
            return None

        # For Grid Items, handle the sparse buffer
        if logical_item.type == CompositeItemType.GRID_ITEM:
            item = None
            abs_idx = -1
            
            if logical_item.section_id == self._grid_section_id:
                # Main Grid (Sparse)
                abs_idx = logical_item.absolute_index
                item = self._sparse_items.get(abs_idx)
            else:
                # Small Grid (Pre-loaded)
                item = logical_item.data

            if role == Qt.ItemDataRole.DisplayRole:
                return item.title if item else "Loading..."

            if role == self.ItemDataRole:
                if item is None and abs_idx != -1:
                    # Trigger pagination
                    page_idx = (abs_idx // self._items_per_page) + 1
                    if page_idx not in self._requested_pages:
                        self._requested_pages.add(page_idx)
                        self.page_request_needed.emit(page_idx)
                    
                    return FeedItem(type=FeedItemType.EMPTY, title="Loading...", identifier=f"empty_{abs_idx}")
                
                if item and item.cover_url and item.cover_url not in self._requested_covers:
                    self._requested_covers.add(item.cover_url)
                    self.cover_request_needed.emit(item.cover_url)
                    
                return item
                
        # Fallback for simple models (e.g. ribbon) that use sparse_items directly
        item = self._sparse_items.get(row)
        if role == self.ItemDataRole and item and item.cover_url:
            if item.cover_url not in self._requested_covers:
                self._requested_covers.add(item.cover_url)
                self.cover_request_needed.emit(item.cover_url)
        return item

    def append_items(self, items: List[FeedItem]):
        """Appends items dynamically to the end of the sparse buffer for infinite scrolling."""
        self.beginResetModel()
        
        start_row = self._total_grid_items
        for i, item in enumerate(items):
            idx = start_row + i
            self._sparse_items[idx] = item
            # Mark the page containing this index as loaded
            page_idx = (idx // self._items_per_page) + 1
            self._loaded_pages.add(page_idx)
        
        self._total_grid_items += len(items)
        self._rebuild_logical_map()
        self.endResetModel()

    def set_items_for_page(self, page_index: int, items: List[FeedItem], offset: int = 0):
        """Injects fetched items into the sparse buffer."""
        start_row = (page_index - 1) * self._items_per_page
        for i, item in enumerate(items):
            self._sparse_items[start_row + i] = item

        self._loaded_pages.add(page_index)

        # If we just loaded items beyond our current total, expand the total
        max_idx = start_row + len(items)
        if max_idx > self._total_grid_items:
            self.beginResetModel()
            self._total_grid_items = max_idx
            self._rebuild_logical_map()
            self.endResetModel()
        else:
            self.layoutChanged.emit() # Notify the view

    def is_page_loaded(self, page_index: int) -> bool:
        """Checks if a page has already been loaded into the sparse buffer."""
        return page_index in self._loaded_pages

    def clear(self):
        self.beginResetModel()
        self._sparse_items = {}
        self._logical_items = []
        self._raw_sections = []
        self._requested_pages = set()
        self._loaded_pages = set()
        self._requested_covers = set()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[FeedItem]:
        if 0 <= row < len(self._logical_items):
            logical = self._logical_items[row]
            if logical.type == CompositeItemType.GRID_ITEM:
                if logical.section_id == self._grid_section_id:
                    return self._sparse_items.get(logical.absolute_index)
                return logical.data
        # Fallback for simple models (e.g. ribbon) that populate sparse_items directly
        return self._sparse_items.get(row)
