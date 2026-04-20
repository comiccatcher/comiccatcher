# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

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
    subtitle: Optional[str] = None
    current_page: int = 1
    total_pages: Optional[int] = None
    next_url: Optional[str] = None
    sections: List[FeedSection] = []
    facets: List[Any] = [] # List of Group objects or dicts for filters

    pagination_template: Optional[str] = None # {page}
    pagination_base_number: int = 1           # Does page 1 use index 0 or 1?
    first_page_url: Optional[str] = None      # Explicit URL for page 1
    search_template: Optional[str] = None     # {query} or {searchTerms}
    is_offset_based: bool = False
    is_paginated: bool = False
    feed_items_per_page: Optional[int] = None
    main_section_id: Optional[str] = None

    # Breadcrumbs for navigation

    breadcrumbs: List[Dict[str, str]] = [] # [{"title": "Home", "url": "..."}]

    @property
    def main_section(self) -> Optional[FeedSection]:
        """
        Identifies the primary content section for continuous scrolling.
        
        Logic:
        1. If main_section_id is explicitly set, use it.
        2. If feed is not paginated, return None.
        3. If feed_items_per_page is known, prefer an EXACT match (full page).
        4. Fallback to the first non-empty section matching source priority.
        """
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

        # Tiered Heuristic:
        # Tier A: Exact matches (len == items_per_page)
        # Tier B: Partial matches (0 < len <= items_per_page)
        # Within each tier, we follow source priority: root:pubs > root:nav > group:pubs > group:nav

        def find_in_tier(exact_only: bool) -> Optional[FeedSection]:
            # Priority 1: Root Publications
            for s in self.sections:
                if s.source_element == "root:publications":
                    if self.feed_items_per_page is not None:
                        if len(s.items) == self.feed_items_per_page: return s
                        if not exact_only and 0 < len(s.items) < self.feed_items_per_page: return s
                    elif not exact_only and s.items: return s
            
            # Priority 2: Root Navigation
            for s in self.sections:
                if s.source_element == "root:navigation":
                    if self.feed_items_per_page is not None:
                        if len(s.items) == self.feed_items_per_page: return s
                        if not exact_only and 0 < len(s.items) < self.feed_items_per_page: return s
                    elif not exact_only and s.items: return s

            # Priority 3: Grouped Publications
            for s in self.sections:
                if s.source_element and s.source_element.startswith("group[") and "publications" in s.source_element:
                    if self.feed_items_per_page is not None:
                        if len(s.items) == self.feed_items_per_page: return s
                        if not exact_only and 0 < len(s.items) < self.feed_items_per_page: return s
                    elif not exact_only and s.items: return s

            # Priority 4: Grouped Navigation
            for s in self.sections:
                if s.source_element and s.source_element.startswith("group[") and "navigation" in s.source_element:
                    if self.feed_items_per_page is not None:
                        if len(s.items) == self.feed_items_per_page: return s
                        if not exact_only and 0 < len(s.items) < self.feed_items_per_page: return s
                    elif not exact_only and s.items: return s
            return None

        # Try Tier A first (Exact Match)
        if self.feed_items_per_page is not None:
            res = find_in_tier(exact_only=True)
            if res: return res
        
        # If we have no exact match (either because items_per_page was nullified by 
        # a sanity check or because we are on a short last page), we only 
        # designate a 'main' section if the choice is unambiguous.
        content_sections = [s for s in self.sections if s.items]
        if len(content_sections) == 1:
            return content_sections[0]
            
        # Last Page Heuristic: If we have multiple sections, but one is a root 
        # collection (pubs/nav) and it contains more items than others, it is likely the main content.
        root_sections = [s for s in content_sections if s.source_element in ("root:publications", "root:navigation")]
        if len(root_sections) == 1:
            # If the root section has more items than any other content section, pick it
            others = [s for s in content_sections if s.section_id != root_sections[0].section_id]
            max_other_count = max([len(s.items) for s in others]) if others else 0
            if len(root_sections[0].items) >= max_other_count:
                return root_sections[0]

        return None

