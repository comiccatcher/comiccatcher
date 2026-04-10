from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import IntEnum
from .opds import Publication, Link, Metadata

class ItemType(IntEnum):
    BOOK = 1
    FOLDER = 2 # Series, Subsection, etc.
    HEADER = 3 # Section Title
    EMPTY = 4  # Skeleton placeholder

class FeedItem(BaseModel):
    """A single visual card or header in the grid."""
    type: ItemType
    title: str
    subtitle: Optional[str] = None
    series: Optional[str] = None
    imprint: Optional[str] = None
    year: Optional[str] = None
    cover_url: Optional[str] = None
    download_url: Optional[str] = None
    download_format: Optional[str] = None
    
    # Original data for actions
    raw_pub: Optional[Publication] = None
    raw_link: Optional[Link] = None # For Folders
    
    # Identifier for deduplication and sparse matching
    identifier: str
    
    # For pagination: which page does this item belong to?
    page_index: Optional[int] = None

class SectionLayout(IntEnum):
    RIBBON = 1 # Horizontal
    GRID = 2   # Vertical (The "Main Event")

class FeedSection(BaseModel):
    """A logical grouping of items (e.g. 'Latest', 'All Series')."""
    title: str
    layout: SectionLayout = SectionLayout.RIBBON
    items: List[FeedItem] = []
    
    # Pagination metadata
    total_items: Optional[int] = None
    current_page: int = 1
    items_per_page: Optional[int] = None
    next_url: Optional[str] = None
    self_url: Optional[str] = None
    
    # Unique ID to reconcile across paginated responses
    section_id: str
    is_main: bool = False
    
    # Debug info: what OPDS element produced this?
    source_element: Optional[str] = None

class FeedPage(BaseModel):
    """The entire state of a feed view."""
    title: str
    current_page: int = 1
    total_pages: Optional[int] = None
    sections: List[FeedSection] = []
    facets: List[Any] = [] # List of Group objects or dicts for filters

    pagination_template: Optional[str] = None # {page}
    search_template: Optional[str] = None     # {query} or {searchTerms}
    is_offset_based: bool = False
    is_paginated: bool = False
    feed_items_per_page: Optional[int] = None
    main_section_id: Optional[str] = None

    # Breadcrumbs for navigation

    breadcrumbs: List[Dict[str, str]] = [] # [{"title": "Home", "url": "..."}]

    @property
    def main_section(self) -> Optional[FeedSection]:
        """Identifies the primary content section for continuous scrolling."""
        if not self.sections:
            return None

        # 0. Check for explicitly marked main section
        if self.main_section_id:
            for s in self.sections:
                if s.section_id == self.main_section_id:
                    return s
        
        # 1. Only consider feeds that indicate pagination at the root level
        if not self.is_paginated:
            return None
            
        # 2. Iterate over root candidate sources in priority order
        for target_source in ("root:publications", "root:navigation"):
            for s in self.sections:
                if s.source_element == target_source:
                    if self.feed_items_per_page is not None and len(s.items) == self.feed_items_per_page:
                        return s
        
        # 3. If no root candidate found, iterate over groups:
        # 3a. Grouped publication elements
        for s in self.sections:
            if s.source_element and s.source_element.startswith("group[") and "publications" in s.source_element:
                if self.feed_items_per_page is not None and len(s.items) == self.feed_items_per_page:
                    return s
        
        # 3b. Grouped navigation elements
        for s in self.sections:
            if s.source_element and s.source_element.startswith("group[") and "navigation" in s.source_element:
                if self.feed_items_per_page is not None and len(s.items) == self.feed_items_per_page:
                    return s
                        
        return None

