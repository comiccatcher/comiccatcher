# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import urllib.parse
import re
from typing import List, Optional, Dict, Any, Tuple
from comiccatcher.models.opds import OPDSFeed, Publication, Link, Group
from comiccatcher.models.feed_page import FeedPage, FeedSection, FeedItem, ItemType, SectionLayout
from comiccatcher.logger import get_logger

logger = get_logger("api.feed_reconciler")

# Threshold for choosing GRID layout over RIBBON for results sets
# MOVED TO UI LAYER

class FeedReconciler:
    """
    Transforms raw OPDS feeds into a unified structure.
    """
    
    @staticmethod
    def reconcile(feed: OPDSFeed, base_url: str) -> FeedPage:
        # Fallback title logic: metadata.title -> top-level title -> "Feed"
        page_title = "Feed"
        page_subtitle = None
        if feed.metadata:
            if feed.metadata.title:
                page_title = feed.metadata.title
            if feed.metadata.subtitle:
                page_subtitle = feed.metadata.subtitle
        elif hasattr(feed, 'title') and getattr(feed, 'title'):
            page_title = getattr(feed, 'title')
            
        sections = []
        facets = []
        
        # Robust identity and URL detection
        self_url = base_url
        first_page_url = None
        if feed.links:
            for l in feed.links:
                rels = [l.rel] if isinstance(l.rel, str) else (l.rel or [])
                target_url = urllib.parse.urljoin(base_url, l.href)
                if "self" in rels:
                    self_url = target_url
                if "first" in rels:
                    first_page_url = target_url
        
        # Determine stable logical ID for the entire feed
        logical_id = FeedReconciler._get_stable_id(feed, self_url, first_page_url)
        logger.debug(f"FeedReconciler: base_url={base_url} -> logical_id={logical_id}")

        # Check if the feed indicates pagination at the root level
        is_paginated = False
        if feed.links:
            for l in feed.links:
                rels = [l.rel] if isinstance(l.rel, str) else (l.rel or [])
                if any(r in ["next", "previous", "first", "last"] for r in rels):
                    is_paginated = True
                    break

        # Capture root-level pagination metadata for later assignment
        m = feed.metadata
        curr_page = (m.currentPage if m else None) or 1
        root_total = m.numberOfItems if m else None
        root_next = FeedReconciler._find_next(feed.links, base_url)
        root_ipp = m.itemsPerPage if m else None

        # Fallback: If no 'first' link, and we are on page 1, current is first.
        if not first_page_url and curr_page == 1:
            first_page_url = self_url

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
                rel_str = "".join(link.rel or []) if isinstance(link.rel, list) else (link.rel or "")
                if "start" in rel_str or (link.title and link.title.lower() == "start"):
                    continue
                nav_items.append(FeedItem(
                    type=ItemType.FOLDER,
                    title=link.title or "Untitled",
                    raw_link=link,
                    identifier=link.href
                ))
            
            if nav_items:
                sec_id = (m.identifier if m else None) or f"nav_{logical_id}"
                
                sections.append(FeedSection(
                    title="Browse",
                    section_id=sec_id,
                    items=nav_items,
                    total_items=len(nav_items),
                    items_per_page=len(nav_items),
                    current_page=1,
                    next_url=None, # Will be assigned to main_section later if applicable
                    source_element="root:navigation"
                ))

        # 2. Handle Groups
        if feed.groups:
            for i, group in enumerate(feed.groups):
                group_items = []
                if group.publications:
                    for pub in group.publications:
                        group_items.append(FeedReconciler._pub_to_item(pub, base_url))
                
                if group.navigation:
                    for link in group.navigation:
                        rel_str = "".join(link.rel or []) if isinstance(link.rel, list) else (link.rel or "")
                        if "facet" in rel_str or "http://opds-spec.org/facet" in rel_str:
                            continue
                        if has_top_start and ("start" in rel_str):
                            continue
                            
                        group_items.append(FeedItem(
                            type=ItemType.FOLDER,
                            title=link.title or "Untitled",
                            raw_link=link,
                            identifier=link.href
                        ))
                
                if group_items:
                    gm = group.metadata
                    
                    # Determine next link for paging
                    g_next = FeedReconciler._find_next(group.links, base_url)
                    
                    # total_items logic:
                    # Use the server's numberOfItems for this group if provided.
                    # Fallback to current item count if no total metadata exists.
                    g_total = (gm.numberOfItems if gm else None) or len(group_items)
                    
                    # Look for self link in group links for "See All" navigation
                    g_self = None
                    if group.links:
                        for l in group.links:
                            rels = [l.rel] if isinstance(l.rel, str) else (l.rel or [])
                            if "self" in rels:
                                g_self = urllib.parse.urljoin(base_url, l.href)
                                break
                    
                    sources = []
                    if group.publications: sources.append("publications")
                    if group.navigation: sources.append("navigation")
                    source_str = f"group[{i}]:{'+'.join(sources)}" if sources else f"group[{i}]"

                    sec_id = (gm.identifier if gm else None) or f"group_{(gm.title if gm else 'anon')}"

                    sections.append(FeedSection(
                        title=(gm.title if gm else None) or "Group",
                        section_id=sec_id,
                        items=group_items,
                        total_items=g_total,
                        items_per_page=gm.itemsPerPage if gm else None,
                        current_page=(gm.currentPage if gm else None) or 1,
                        next_url=g_next,
                        self_url=g_self,
                        source_element=source_str
                    ))

        # 3. Handle Top-level Publications
        if feed.publications:
            pub_items = []
            for pub in feed.publications:
                pub_items.append(FeedReconciler._pub_to_item(pub, base_url))
            
            if pub_items:
                sec_id = (m.identifier if m else None) or f"pubs_{logical_id}"

                sections.append(FeedSection(
                    title="Publications",
                    section_id=sec_id,
                    items=pub_items,
                    total_items=len(pub_items),
                    items_per_page=len(pub_items),
                    current_page=(m.currentPage if m else None) or 1,
                    next_url=None, # Will be assigned to main_section later if applicable
                    source_element="root:publications"
                ))

        # 4. Data Cleaning / Optimization
        # Prune redundant server-side nesting (e.g. Codex grouping items that duplicate section titles)
        for section in sections:
            if len(section.items) > 1:
                first = section.items[0]
                # If the first item is a folder/header and matches the section title, it's redundant
                if first.type in (ItemType.FOLDER, ItemType.FOLDER): # Using ItemType.FOLDER as proxy for grouping
                    clean_first = re.sub(r'[^a-z0-9]', '', first.title.lower())
                    clean_sec = re.sub(r'[^a-z0-9]', '', section.title.lower())
                    if clean_first == clean_sec:
                        logger.info(f"FeedReconciler: Pruned redundant grouping item '{first.title}' in section '{section.title}'")
                        section.items.pop(0)
                        if section.total_items: section.total_items -= 1

        # 4b. Pagination Sanity Check
        # Discard root itemsPerPage/numberOfItems if they don't match the actual content of any section.
        root_next_for_section = root_next
        if root_ipp is not None and root_next:
            match_found = False
            for s in sections:
                if len(s.items) == root_ipp:
                    match_found = True
                    break
            
            if not match_found:
                logger.debug(
                    f"FeedReconciler: Discarding discrepant root pagination metadata. "
                    f"itemsPerPage={root_ipp} but no section contains exactly {root_ipp} items (found sections with counts: {[len(s.items) for s in sections]})."
                )
                root_ipp = None
                root_total = None
                root_next_for_section = None

        # 4c. Determine Global Page
        # (Already defined above as part of root metadata capture)
        
        # 5. Determine Total Pages
        total_pages = None
        if root_total is not None and root_ipp:
            import math
            total_pages = math.ceil(root_total / root_ipp)

        # 6. Detect Pagination Template
        pagination_template = None
        is_offset_based = False
        pagination_base_number = 1
        
        next_link = FeedReconciler._find_next(feed.links, base_url)
        if next_link:
            match = re.search(r'/(?P<prefix>[a-z])/(?P<group>\d+)/(?P<page>\d+)', next_link)
            if match:
                pre, grp, p_val = match.groups()
                pagination_template = next_link.replace(f"/{pre}/{grp}/{p_val}", f"/{pre}/{grp}/{{page}}")
                # Heuristic: If we are on Page 1 (metadata), and the NEXT link says Page 1, then base is 0.
                if curr_page == 1 and int(p_val) == 1:
                    pagination_base_number = 0
            else:
                match = re.search(r'(?P<key>page|offset|start)=(?P<val>\d+)', next_link)
                if match:
                    key, val = match.groups()
                    is_offset_based = (key == 'offset' or key == 'start')
                    pagination_template = next_link.replace(f"{key}={val}", f"{key}={{page}}")
                    # If it's a page-based key and next is 1, then base is 0
                    if not is_offset_based and curr_page == 1 and int(val) == 1:
                        pagination_base_number = 0

        # 7. Detect Search Template
        search_template = None
        if feed.links:
            for link in feed.links:
                rel = link.rel
                rels = [rel] if isinstance(rel, str) else (rel or [])
                if "search" in rels:
                    # Resolve to absolute URL
                    search_template = urllib.parse.urljoin(base_url, link.href)
                    break

        # 8. Final Layout Assignment and Main Section Detection
        temp_page = FeedPage(
            title=page_title,
            subtitle=page_subtitle,
            current_page=curr_page,
            total_pages=total_pages,
            next_url=root_next,
            sections=sections,
            facets=facets,
            is_paginated=is_paginated,
            feed_items_per_page=root_ipp,
            pagination_template=pagination_template,
            pagination_base_number=pagination_base_number,
            first_page_url=first_page_url,
            search_template=search_template,
            is_offset_based=is_offset_based
        )
        
        # Determine logical main section and attach root pagination metadata to it
        main_sec = temp_page.main_section
        if main_sec:
            temp_page.main_section_id = main_sec.section_id
            main_sec.is_main = True
            
            # Transfer root metadata to the main section
            if root_total is not None:
                main_sec.total_items = root_total
            elif root_next_for_section is not None:
                # If we have a next link but no root_total, we don't know the full length
                main_sec.total_items = None
            
            if root_next_for_section:
                main_sec.next_url = root_next_for_section
            if root_ipp is not None:
                main_sec.items_per_page = root_ipp
        
        for section in sections:
            if section.is_main or section.source_element in ("root:publications", "root:navigation"):
                section.layout = SectionLayout.GRID
            else:
                section.layout = SectionLayout.RIBBON

        # 9. Server-provided Breadcrumbs
        breadcrumbs = []
        if feed.links:
            for link in feed.links:
                rel = link.rel
                rels = [rel] if isinstance(rel, str) else (rel or [])
                # "up" or "via" links indicate hierarchy in OPDS
                if "up" in rels or "via" in rels:
                    breadcrumbs.append({
                        "title": link.title or "Up",
                        "url": urllib.parse.urljoin(base_url, link.href)
                    })
        temp_page.breadcrumbs = breadcrumbs

        return temp_page

    @staticmethod
    def _pub_to_item(pub: Publication, base_url: str) -> FeedItem:
        cover_url = None
        if pub.images:
            cover_url = urllib.parse.urljoin(base_url, pub.images[0].href)

        download_url, download_format = FeedReconciler._find_acquisition_link(pub, base_url)

        # Metadata extraction for Subtitle (Volume/Issue), Series, Imprint and Year

        subtitle = None
        series_name = None
        imprint = None
        year = None
        m = pub.metadata
        
        if m:
            # 1. Imprint Extraction (m.imprint is now List[Contributor])
            if m.imprint and len(m.imprint) > 0:
                imprint = m.imprint[0].name

            # 2. Series/Position Extraction
            parts = []
            if m.belongsTo:
                # Komga/OPDS 2.0 Series info
                if m.belongsTo.series:
                    for s in m.belongsTo.series:
                        # Capture the series name
                        if not series_name:
                            series_name = s.name
                        
                        # Capture position
                        if s.position is not None:
                            # Standardize position as #N
                            pos_str = str(s.position)
                            if pos_str.endswith(".0"): pos_str = pos_str[:-2]
                            parts.append(f"#{pos_str}")
                
                # Readium/Collection info (fallback if series name missing)
                if m.belongsTo.collection:
                    for coll in m.belongsTo.collection:
                        if coll.name:
                            if not series_name:
                                series_name = coll.name
                            if not parts and coll.position:
                                parts.append(f"#{coll.position}")
            
            # Fallback to direct fields if available
            if not parts and m.numberOfPages:
                parts.append(f"{m.numberOfPages}p")
                
            if parts:
                subtitle = " ".join(parts)
            
            if hasattr(m, "published") and m.published:
                try:
                    # published is often a string/date
                    year = str(m.published)[:4]
                except:
                    pass

        # Heuristic for ItemType
        item_type = ItemType.BOOK
        if not download_url:
            has_nav = False
            for l in (pub.links or []):
                rels = [l.rel] if isinstance(l.rel, str) else (l.rel or [])
                if any(r in ["subsection", "collection", "alternate"] for r in rels):
                    if "opds+json" in (l.type or ""):
                        has_nav = True
                        break
            if has_nav:
                item_type = ItemType.FOLDER
            
        return FeedItem(
            type=item_type,
            title=m.title if m else "Unknown",
            subtitle=subtitle,
            series=series_name,
            imprint=imprint,
            year=year,
            cover_url=cover_url,
            download_url=download_url,
            download_format=download_format,
            raw_pub=pub,
            identifier=pub.identifier
        )

    @staticmethod
    def _find_acquisition_link(pub: Publication, base_url: str = "") -> Tuple[Optional[str], Optional[str]]:
        """
        Helper to find the best acquisition link based solely on MIME type.
        Returns (url, mime_type).
        """
        # MIME Type to Priority Mapping
        # Higher score = Better format
        MIME_PRIORITIES = {
            # CBZ
            "application/vnd.comicbook+zip": 100,
            "application/x-cbz": 100,
            "application/zip": 95,
            
            # CBR
            "application/vnd.comicbook-rar": 90,
            "application/x-cbr": 90,
            "application/x-rar": 85,
            "application/x-rar-compressed": 85,
            
            # CB7
            "application/x-cb7": 80,
            "application/x-7z-compressed": 80,
            
            # CBT
            "application/x-cbt": 75,
            "application/x-tar": 75,
            
            # PDF
            "application/pdf": 50,
            
            # Low Priority / Generic
            "application/octet-stream": 10
        }

        candidates = []
        
        # 1. Check standard links
        for l in (pub.links or []):
            rels = l.rel
            if isinstance(rels, str): rel_list = [rels.lower()]
            elif isinstance(rels, list): rel_list = [str(r).lower() for r in rels]
            else: rel_list = []
                
            # Strict relationship matching: Only direct acquisition or open-access.
            # We explicitly exclude 'borrow', 'buy', 'sample', etc.
            is_direct_acq = any(r in [
                "acquisition", 
                "http://opds-spec.org/acquisition",
                "http://opds-spec.org/acquisition/open-access"
            ] for r in rel_list)
            
            l_type = (l.type or "").lower().strip()
            priority = MIME_PRIORITIES.get(l_type, 0)
            
            # Button only activates if we have a direct acquisition relationship 
            # AND a format we actually support for reading.
            if is_direct_acq and priority > 0:
                candidates.append((priority, urllib.parse.urljoin(base_url, l.href), l_type))

        # 2. Check 'actions' (OPDS 2.0 indirect acquisition)
        if hasattr(pub, "actions") and pub.actions:
            for action in pub.actions:
                rel = (action.rel or "").lower()
                # Strict action relationship matching
                if rel in ["acquisition", "http://opds-spec.org/acquisition", "http://opds-spec.org/acquisition/open-access"]:
                    props = action.properties or {}
                    ia_list = props.get("indirectAcquisition")
                    if ia_list and isinstance(ia_list, list):
                        for ia in ia_list:
                            ia_type = str(ia.get("type", "")).lower().strip()
                            priority = MIME_PRIORITIES.get(ia_type, 0)
                            
                            # Check children (nested formats)
                            children = ia.get("child")
                            if children and isinstance(children, list):
                                for child in children:
                                    c_type = str(child.get("type", "")).lower().strip()
                                    child_priority = MIME_PRIORITIES.get(c_type, 0)
                                    priority = max(priority, child_priority)
                            
                            if priority > 0:
                                candidates.append((priority, urllib.parse.urljoin(base_url, action.href), ia_type))
        
        if not candidates:
            return None, None
            
        # Return the one with highest priority
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    @staticmethod
    def get_acquisition_note(pub: Publication) -> Optional[str]:
        """
        Returns a human-readable note explaining why download/read might be limited.
        Only shows format warnings if a supported format is NOT available.
        """
        reasons = []
        links = pub.links or []
        
        has_borrow = False
        has_buy = False
        all_acq_formats = set()
        supported_acq_formats = set()
        
        # 1. Scan standard links
        for l in links:
            rels = l.rel
            if isinstance(rels, str): rel_list = [rels.lower()]
            elif isinstance(rels, list): rel_list = [str(r).lower() for r in rels]
            else: rel_list = []
            
            rel_str = " ".join(rel_list)
            l_type = (l.type or "").lower().strip()
            
            if "borrow" in rel_str: has_borrow = True
            if "buy" in rel_str or "purchase" in rel_str: has_buy = True
            
            # Check if it is a direct download link
            is_direct_acq = any(r in ["acquisition", "http://opds-spec.org/acquisition", "http://opds-spec.org/acquisition/open-access"] for r in rel_list)
            
            if is_direct_acq:
                # Track what we found
                if "epub" in l_type: all_acq_formats.add("EPUB")
                elif "pdf" in l_type: supported_acq_formats.add("PDF")
                elif "cbz" in l_type: supported_acq_formats.add("CBZ")
                elif "cbr" in l_type: supported_acq_formats.add("CBR")
                elif "cb7" in l_type: supported_acq_formats.add("CB7")
                elif "cbt" in l_type: supported_acq_formats.add("CBT")

        # 2. Check actions
        if hasattr(pub, "actions") and pub.actions:
            for action in pub.actions:
                rel = (action.rel or "").lower()
                if "borrow" in rel: has_borrow = True
                if "buy" in rel: has_buy = True
                
                if rel in ["acquisition", "http://opds-spec.org/acquisition", "http://opds-spec.org/acquisition/open-access"]:
                    props = action.properties or {}
                    ia_list = props.get("indirectAcquisition")
                    if ia_list and isinstance(ia_list, list):
                        for ia in ia_list:
                            ia_type = str(ia.get("type", "")).lower().strip()
                            if "epub" in ia_type: all_acq_formats.add("EPUB")
                            elif "pdf" in ia_type: supported_acq_formats.add("PDF")
                            # ... (other formats)

        if has_borrow: reasons.append("Borrowing not supported by app")
        if has_buy: reasons.append("Purchasing not supported by app")
        
        # Format Warning: ONLY if no supported format was found among any direct acquisition links
        if not supported_acq_formats and all_acq_formats:
            fmt_str = ", ".join(sorted(list(all_acq_formats)))
            reasons.append(f"Format not supported by app: {fmt_str}")
            
        return " • ".join(reasons) if reasons else None

    @staticmethod
    def _find_next(links: List[Link], base_url: str) -> Optional[str]:
        if not links: return None
        for l in links:
            rel = l.rel if isinstance(l.rel, list) else [l.rel]
            if "next" in rel:
                return urllib.parse.urljoin(base_url, l.href)
        return None

    @staticmethod
    def _get_stable_id(feed: OPDSFeed, self_url: str, first_url: Optional[str]) -> str:
        """Determines a stable logical ID for a feed across different pages."""
        # 1. Highest Priority: Metadata Identifier
        if feed.metadata and feed.metadata.identifier:
            return feed.metadata.identifier
            
        # 2. Next Priority: Normalized 'first' page URL
        if first_url:
            return FeedReconciler._normalize_url(first_url)
            
        # 3. Fallback: Normalized current 'self' URL
        return FeedReconciler._normalize_url(self_url)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strips query parameters and pagination components from a URL to create a base ID."""
        if not url: return url
        
        # Strip query parameters (?page=2, etc)
        clean = url.split('?')[0].rstrip('/')
        
        # Strip Codex-style paging (/r/0/1, /s/0/2)
        clean = re.sub(r'/[a-z]/\d+/\d+$', '', clean)
        
        # Strip generic paging (/page/2, /offset/20)
        clean = re.sub(r'/(page|offset|start)/\d+$', '', clean)
        
        return clean
