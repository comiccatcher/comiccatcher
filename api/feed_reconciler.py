import urllib.parse
import re
from typing import List, Optional, Dict, Any
from models.opds import OPDSFeed, Publication, Link, Group
from models.feed_page import FeedPage, FeedSection, FeedItem, ItemType, SectionLayout
from logger import get_logger

logger = get_logger("api.feed_reconciler")

class FeedReconciler:
    """
    Transforms raw OPDS feeds into a unified structure.
    """
    
    @staticmethod
    def reconcile(feed: OPDSFeed, base_url: str) -> FeedPage:
        page_title = feed.metadata.title or "Feed"
        sections = []
        facets = []
        
        # Robust logical ID
        self_url = base_url
        if feed.links:
            for l in feed.links:
                if l.rel == "self" or (isinstance(l.rel, list) and "self" in l.rel):
                    self_url = urllib.parse.urljoin(base_url, l.href)
                    break
        
        # Sanitize to create a stable ID for the entire logical feed.
        # Example: /codex/opds/v2.0/p/0/1 -> /codex/opds/v2.0/p/
        logical_id = re.sub(r'/[a-z]/\d+/\d+', lambda m: m.group(0)[:3], self_url).split('?')[0]
        
        logger.debug(f"FeedReconciler: base_url={base_url} -> logical_id={logical_id}")

        has_top_start = any(l.rel == "start" for l in feed.links) if feed.links else False
        
        # 0. Extract Facets
        if hasattr(feed, 'facets') and feed.facets:
            facets.extend(feed.facets)
        if feed.groups:
            for group in feed.groups:
                if getattr(group, "navigation", None):
                    has_facet = False
                    for n in group.navigation:
                        rel_str = "".join(n.rel or []) if isinstance(n.rel, list) else (n.rel or "")
                        if "facet" in rel_str or "http://opds-spec.org/facet" in rel_str:
                            has_facet = True
                            break
                    if has_facet:
                        facets.append(group)

        # 1. Handle Top-level Navigation
        if feed.navigation:
            nav_items = []
            for link in feed.navigation:
                nav_items.append(FeedItem(
                    type=ItemType.FOLDER,
                    title=link.title or "Untitled",
                    raw_link=link,
                    identifier=link.href
                ))
            
            if nav_items:
                sec_id = feed.metadata.identifier or f"nav_{logical_id}"
                
                # Heuristic: Is this a Dashboard (Start page) or a pure Folder List (All Series)?
                # If there are any publications anywhere (top-level or in groups), the top navigation is just a menu ribbon.
                # If there are NO publications anywhere, this navigation list IS the main content (e.g. Series list).
                has_any_pubs = bool(feed.publications) or any(bool(g.publications) for g in (feed.groups or []))
                
                if not has_any_pubs:
                    # It's a pure folder list, inherit global counts
                    total = feed.metadata.numberOfItems if feed.metadata.numberOfItems is not None else len(nav_items)
                    next_url = FeedReconciler._find_next(feed.links, base_url)
                    # Folders in a pure folder list should be a grid
                    layout = SectionLayout.GRID
                else:
                    # It's a dashboard menu, don't inherit global counts
                    total = len(nav_items)
                    next_url = None
                    layout = SectionLayout.RIBBON
                
                sections.append(FeedSection(
                    title="Subsections",
                    section_id=sec_id,
                    items=nav_items,
                    total_items=total,
                    items_per_page=feed.metadata.itemsPerPage,
                    current_page=feed.metadata.currentPage or 1,
                    next_url=next_url,
                    layout=layout
                ))

        # 2. Handle Groups
        if feed.groups:
            for group in feed.groups:
                group_items = []
                if group.publications:
                    for pub in group.publications:
                        group_items.append(FeedReconciler._pub_to_item(pub, base_url))
                
                if group.navigation:
                    for link in group.navigation:
                        rel_str = "".join(link.rel or []) if isinstance(link.rel, list) else (link.rel or "")
                        if "facet" in rel_str or "http://opds-spec.org/facet" in rel_str: continue
                        if has_top_start and ("start" in rel_str): continue
                            
                        group_items.append(FeedItem(
                            type=ItemType.FOLDER,
                            title=link.title or "Untitled",
                            raw_link=link,
                            identifier=link.href
                        ))
                
                if group_items:
                    g_total = group.metadata.numberOfItems if (group.metadata and group.metadata.numberOfItems) else len(group_items)
                    g_self = next((urllib.parse.urljoin(base_url, l.href) for l in (group.links or []) if l.rel == "self"), None)
                    g_next = FeedReconciler._find_next(group.links, base_url)
                    
                    # If the group is paginated, it's a main results set, use GRID.
                    layout = SectionLayout.GRID if g_next else SectionLayout.RIBBON
                    
                    sections.append(FeedSection(
                        title=group.metadata.title or "Group",
                        section_id=group.metadata.identifier or f"group_{group.metadata.title}",
                        items=group_items,
                        total_items=g_total,
                        items_per_page=group.metadata.itemsPerPage,
                        current_page=group.metadata.currentPage or 1,
                        next_url=g_next,
                        self_url=g_self,
                        layout=layout
                    ))

        # 3. Handle Top-level Publications
        if feed.publications:
            pub_items = []
            for pub in feed.publications:
                pub_items.append(FeedReconciler._pub_to_item(pub, base_url))
            
            if pub_items:
                sec_id = feed.metadata.identifier or f"pubs_{logical_id}"
                next_url = FeedReconciler._find_next(feed.links, base_url)
                
                # If there's a next page or many items, use a GRID.
                # If it's the "Main Results" (top-level pubs usually are), use a GRID.
                is_paginated = bool(next_url) or (feed.metadata.numberOfItems or 0) > (feed.metadata.itemsPerPage or 50)
                layout = SectionLayout.GRID if is_paginated else SectionLayout.RIBBON

                sections.append(FeedSection(
                    title="Items",
                    section_id=sec_id,
                    items=pub_items,
                    total_items=feed.metadata.numberOfItems,
                    items_per_page=feed.metadata.itemsPerPage,
                    current_page=feed.metadata.currentPage or 1,
                    next_url=next_url,
                    layout=layout
                ))

        return FeedPage(
            title=page_title,
            sections=sections,
            facets=facets
        )

    @staticmethod
    def _pub_to_item(pub: Publication, base_url: str) -> FeedItem:
        cover_url = None
        if pub.images:
            cover_url = urllib.parse.urljoin(base_url, pub.images[0].href)
        return FeedItem(
            type=ItemType.BOOK,
            title=pub.metadata.title,
            cover_url=cover_url,
            raw_pub=pub,
            identifier=pub.identifier
        )

    @staticmethod
    def _find_acquisition_link(pub: Publication, base_url: str = "") -> Optional[str]:
        """Helper to find an acquisition link in a publication or its manifest."""
        for l in (pub.links or []):
            # Normalize rels to a list of lower-case strings
            rels = l.rel
            if isinstance(rels, str):
                rel_list = [rels.lower()]
            elif isinstance(rels, list):
                rel_list = [str(r).lower() for r in rels]
            else:
                rel_list = []
                
            # Aggressive check for acquisition rels
            is_acq = any("acquisition" in r for r in rel_list)
            
            # Type-based detection (CBZ, CBR, PDF, EPUB, etc.)
            l_type = (l.type or "").lower()
            l_href = (l.href or "").lower()
            is_comic = any(t in l_type for t in ["cbz", "cbr", "cb7", "pdf", "octet-stream"]) or \
                       any(l_href.endswith(ext) for ext in [".cbz", ".cbr", ".cb7", ".pdf"])
            
            # If it's explicitly an acquisition link, or looks like a comic file, take it
            if is_acq or is_comic:
                # Avoid links that are clearly not downloads (like search, self, etc. if mislabeled)
                if any(r in rel_list for r in ["self", "search", "alternate"]) and not is_acq:
                    continue
                return urllib.parse.urljoin(base_url, l.href)
        return None

    @staticmethod
    def _find_next(links: List[Link], base_url: str) -> Optional[str]:
        if not links: return None
        for l in links:
            rel = l.rel if isinstance(l.rel, list) else [l.rel]
            if "next" in rel:
                return urllib.parse.urljoin(base_url, l.href)
        return None
