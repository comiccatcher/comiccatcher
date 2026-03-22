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
    cover_url: Optional[str] = None
    
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

class FeedPage(BaseModel):
    """The entire state of a feed view."""
    title: str
    sections: List[FeedSection] = []
    facets: List[Any] = [] # List of Group objects or dicts for filters
    
    # Breadcrumbs for navigation
    breadcrumbs: List[Dict[str, str]] = [] # [{"title": "Home", "url": "..."}]
