# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import xml.etree.ElementTree as ET
import asyncio
import urllib.parse
import re
import copy
from typing import List, Dict, Any, Optional

from comiccatcher.models.opds import OPDSFeed, Publication, Metadata, Link, Contributor
from comiccatcher.api.client import APIClient
from comiccatcher.logger import get_logger

logger = get_logger("api.opds12")

# Namespace stripping helper
def _strip_ns(tag: str) -> str:
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag

def _get_text(elem: ET.Element, tag_name: str) -> Optional[str]:
    for child in elem:
        if _strip_ns(child.tag) == tag_name:
            return child.text
    return None

def _get_attrib(elem: ET.Element, attrib_name: str, ns_uri: Optional[str] = None) -> Optional[str]:
    if ns_uri:
        val = elem.get(f"{{{ns_uri}}}{attrib_name}")
        if val is not None:
            return val
    return elem.get(attrib_name)

def _clean_kavita_title(title: str) -> str:
    if not title: return ""
    # Kavita progress icons: ⭘ (Unread), ◔ (25%), ◑ (50%), ◕ (75%), ⬤ (Read)
    icons = ["⭘", "◔", "◑", "◐", "◕", "⬤"]
    for icon in icons:
        title = title.replace(icon, "")
    return title.strip()

async def parse_opds12(xml_text: str, api_client: APIClient, source_url: str) -> OPDSFeed:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse OPDS 1.2 XML: {e}")
    
    # Root level authors
    root_authors = []
    for child in root:
        if _strip_ns(child.tag) == "author":
            # Some servers (like Stump) put multiple names in one author tag
            for author_child in child:
                if _strip_ns(author_child.tag) == "name" and author_child.text:
                    root_authors.append(Contributor(name=author_child.text))

    metadata = Metadata()
    metadata.title = _clean_kavita_title(_get_text(root, "title"))
    metadata.subtitle = _get_text(root, "subtitle")
    metadata.identifier = _get_text(root, "id")
    metadata.author = root_authors if root_authors else None
    metadata.conformsTo = ["opds1_2"]
    
    links = []
    publications = []
    navigation = []
    facets_raw = {} # group_name -> list of links
    
    for child in root:
        tag = _strip_ns(child.tag)
        if tag == "totalResults":
            try: metadata.numberOfItems = int(child.text)
            except: pass
        elif tag == "itemsPerPage":
            try: metadata.itemsPerPage = int(child.text)
            except: pass
        elif tag == "startIndex":
            try: metadata.currentPage = (int(child.text) // (metadata.itemsPerPage or 1)) + 1
            except: pass
        elif tag in ["icon", "logo"]:
            href = child.text
            if href:
                # Handle Base64 encoded images missing the data: scheme
                if href.startswith("image/") or ";base64," in href:
                    if not href.startswith("data:"):
                        href = f"data:{href}"
                else:
                    href = urllib.parse.urljoin(source_url, href)
                links.append(Link(rel=tag, href=href))
        elif tag == "link":
            rel = child.get("rel")
            href = child.get("href")
            type_str = child.get("type")
            title = child.get("title")
            if rel and href:
                if href.startswith("data:") or href.startswith("image/") or ";base64," in href:
                    if not href.startswith("data:"):
                        href = f"data:{href}"
                else:
                    href = urllib.parse.urljoin(source_url, href)
                
                # Atom Threading Count (Ubooquity/Kavita folders)
                thr_count = _get_attrib(child, "count", "http://purl.org/syndication/thread/1.0")
                props = {"count": int(thr_count)} if thr_count else None

                if rel in ["next", "previous", "first", "last"]:
                    links.append(Link(rel=rel, href=href, type=type_str, properties=props))
                elif rel == "search" and type_str == "application/opensearchdescription+xml":
                    try:
                        logger.debug(f"Eagerly fetching OSDD: {href}")
                        resp = await api_client.get(href)
                        if resp.status_code == 200:
                            # Workaround for unescaped ampersands in search templates
                            fixed_text = resp.text.replace("&", "&amp;").replace("&amp;amp;", "&amp;")
                            osdd_root = ET.fromstring(fixed_text)
                            for os_child in osdd_root:
                                os_tag = _strip_ns(os_child.tag)
                                if os_tag == "Url":
                                    tmpl = os_child.get("template")
                                    if tmpl:
                                        tmpl = urllib.parse.urljoin(source_url, tmpl)
                                        links.append(Link(rel="search", href=tmpl, type="application/atom+xml", templated=True))
                                elif os_tag == "Image":
                                    img_href = os_child.text
                                    if img_href:
                                        img_href = urllib.parse.urljoin(source_url, img_href)
                                        links.append(Link(rel="icon", href=img_href, type=os_child.get("type")))
                    except Exception as e:
                        logger.warning(f"Failed to fetch OSDD {href}: {e}")
                elif "facet" in rel:
                    # OPDS 1.2 Facet logic
                    facet_group = _get_attrib(child, "facetGroup", "http://opds-spec.org/2010/catalog")
                    if not facet_group:
                        facet_group = _get_attrib(child, "facetGroup", "http://opds-spec.org/")
                    
                    if not facet_group:
                        facet_group = "Options"
                    
                    if facet_group not in facets_raw:
                        facets_raw[facet_group] = []
                    
                    is_active = _get_attrib(child, "activeFacet", "http://opds-spec.org/2010/catalog") == "true"
                    if not is_active:
                        is_active = _get_attrib(child, "activeFacet", "http://opds-spec.org/") == "true"
                    
                    facet_props = props or {}
                    if is_active: facet_props["active"] = True
                    facets_raw[facet_group].append(Link(rel=rel, href=href, type=type_str, title=title, properties=facet_props if facet_props else None))
                else:
                    links.append(Link(rel=rel, href=href, type=type_str, title=title, properties=props))
                    
        elif tag == "entry":
            entry_title = _clean_kavita_title(_get_text(child, "title"))
            entry_subtitle = _get_text(child, "subtitle")
            entry_id = _get_text(child, "id")
            if entry_id:
                entry_id = urllib.parse.urljoin(source_url, entry_id)

            entry_updated = _get_text(child, "updated")
            
            # Content handling (XHTML/HTML vs Text)
            entry_summary = None
            for e_child in child:
                tag = _strip_ns(e_child.tag)
                if tag in ["summary", "content"]:
                    content_type = e_child.get("type", "text")
                    if content_type == "xhtml":
                        # For XHTML, we want to serialize the inner content without namespace prefixes
                        # so that Qt's RichText engine can render it as standard HTML.
                        inner_xml = []
                        for node in e_child:
                            # We use method='html' to get cleaner output, but first we need to 
                            # strip the namespaces from the tags themselves.
                            def _strip_node_ns(n):
                                n.tag = _strip_ns(n.tag)
                                for child_node in n:
                                    _strip_node_ns(child_node)
                            
                            node_copy = copy.deepcopy(node)
                            _strip_node_ns(node_copy)
                            inner_xml.append(ET.tostring(node_copy, encoding='unicode', method='html'))
                        entry_summary = "".join(inner_xml).strip()
                        # If empty, fallback to text
                        if not entry_summary:
                            entry_summary = e_child.text
                    elif content_type == "html":
                        entry_summary = e_child.text
                    else:
                        entry_summary = e_child.text
                    
                    if entry_summary:
                        entry_summary = entry_summary.strip()
                        break

            entry_authors = []
            entry_subjects = []
            entry_language = None
            entry_rights = _get_text(child, "rights")
            
            # PSE Count element fallback (Ubooquity)
            entry_pse_count = _get_text(child, "count") # In pse namespace
            if not entry_pse_count:
                # Try with namespace
                for e_child in child:
                    if _strip_ns(e_child.tag) == "count" and "vaemendis" in e_child.tag:
                        entry_pse_count = e_child.text
                        break

            entry_authors = []
            entry_subjects = []
            entry_language = None
            entry_rights = _get_text(child, "rights")
            entry_publisher = None
            entry_issued = None

            for e_child in child:
                e_tag = _strip_ns(e_child.tag)
                if e_tag == "author":
                    # Some servers (like Stump) put multiple names in one author tag
                    for author_child in e_child:
                        if _strip_ns(author_child.tag) == "name" and author_child.text:
                            entry_authors.append(Contributor(name=author_child.text))
                elif e_tag == "category":
                    term = e_child.get("term")
                    label = e_child.get("label")
                    if label or term:
                        entry_subjects.append(label or term)
                elif e_tag == "language":
                    entry_language = e_child.text
                elif e_tag in ["publisher", "Publisher"]:
                    entry_publisher = e_child.text
                elif e_tag in ["issued", "date", "issuedDate"]:
                    entry_issued = e_child.text

            # Date fallback logic: published -> issued
            entry_date = _get_text(child, "published") or entry_issued

            entry_metadata = Metadata(
                title=entry_title,
                subtitle=entry_subtitle,
                identifier=entry_id,
                description=entry_summary,
                published=entry_date,
                author=entry_authors if entry_authors else None,
                subject=entry_subjects if entry_subjects else None,
                language=entry_language,
                publisher=entry_publisher,
                conformsTo=["opds1_2"]
            )
            
            # If rights exist, append to description
            if entry_rights and entry_metadata.description:
                entry_metadata.description += f" \n\nRights: {entry_rights}"
            
            entry_links = []
            images = []
            is_acquisition = False
            is_navigation = False
            
            reading_order = []
            has_self = False
            
            from comiccatcher.models.opds import BelongsTo, Collection
            entry_belongs_to = None

            for e_child in child:
                if _strip_ns(e_child.tag) == "link":
                    rel = e_child.get("rel", "")
                    href = e_child.get("href")
                    type_str = e_child.get("type", "")
                    title = e_child.get("title")
                    
                    if href:
                        href = urllib.parse.urljoin(source_url, href)
                        
                        # Workaround for Ubooquity bug: The server incorrectly labels HTML reader URLs 
                        # as image/jpeg. We normalize these to the actual binary pagereader endpoint.
                        if "/opds/comicreader/" in href:
                             if "image" in type_str.lower() or rel == "http://vaemendis.net/opds-pse/stream":
                                 href = href.replace("/opds/comicreader/", "/pagereader/")
                    
                    # Threading count for entries (folder size)
                    thr_count = _get_attrib(e_child, "count", "http://purl.org/syndication/thread/1.0")
                    link_props = {"count": int(thr_count)} if thr_count else None

                    if rel == "self":
                        has_self = True
                        entry_links.append(Link(rel=rel, href=href, type=type_str, title=title, properties=link_props))
                    elif rel.startswith("http://opds-spec.org/acquisition") or rel == "http://vaemendis.net/opds-pse/stream":
                        is_acquisition = True
                        entry_links.append(Link(rel=rel, href=href, type=type_str, title=title, properties=link_props))
                        
                        # PSE Page Streaming Extension support
                        # 1. Find the page count (check attribute, then fallback to entry-level tag)
                        pse_count_str = _get_attrib(e_child, "count", "http://vaemendis.net/opds-pse/ns")
                        if not pse_count_str:
                             # Try without the /ns suffix which some servers use
                             pse_count_str = _get_attrib(e_child, "count", "http://vaemendis.net/opds-pse")
                        
                        pse_count = pse_count_str or entry_pse_count
                        
                        if pse_count and "{pageNumber}" in href:
                            try:
                                count = int(pse_count)
                                for i in range(count):
                                    page_href = href.replace("{pageNumber}", str(i))
                                    # Handle optional width placeholders common in Ubooquity
                                    if "{maxWidth}" in page_href:
                                        page_href = page_href.replace("{maxWidth}", "1600")
                                    if "{width}" in page_href:
                                        page_href = page_href.replace("{width}", "1600")
                                        
                                    reading_order.append(Link(href=page_href, type=type_str))
                            except ValueError:
                                logger.warning(f"Invalid PSE count '{pse_count}' for {entry_title}")
                                pass
                                
                    elif "image" in rel or "thumbnail" in rel:
                        images.append(Link(rel=rel, href=href, type=type_str))
                    elif rel in ["start", "subsection", "http://opds-spec.org/sort", "http://opds-spec.org/facet"]:
                        is_navigation = True
                        entry_links.append(Link(rel=rel, href=href, type=type_str, title=title, properties=link_props))
                    elif rel == "http://vaemendis.net/opds-ps/shelf" or rel == "collection":
                        # Series backlink (Kavita)
                        series_name = title
                        if series_name and series_name.startswith("Series: "):
                            series_name = series_name.replace("Series: ", "")
                        
                        if series_name:
                            if not entry_belongs_to: entry_belongs_to = BelongsTo()
                            if not entry_belongs_to.series: entry_belongs_to.series = []
                            entry_belongs_to.series.append(Collection(name=series_name, links=[Link(rel="subsection", href=href, type=type_str)]))
                    else:
                        entry_links.append(Link(rel=rel, href=href, type=type_str, title=title, properties=link_props))

            # Ensure we have a self link for stable ID and navigation
            if not has_self:
                self_candidate = None
                # 1. Try alternate link
                for l in entry_links:
                    if l.rel == "alternate":
                        self_candidate = l.href
                        break
                # 2. Try ID if it looks like a URL
                if not self_candidate and entry_id and (entry_id.startswith("http") or "/" in entry_id):
                    self_candidate = entry_id
                
                if self_candidate:
                    entry_links.append(Link(rel="self", href=self_candidate, type="application/atom+xml;type=entry"))
            
            if is_acquisition or reading_order:
                pub = Publication(
                    metadata=entry_metadata,
                    links=entry_links,
                    images=images,
                    readingOrder=reading_order if reading_order else None,
                    belongsTo=entry_belongs_to
                )
                publications.append(pub)
            elif is_navigation or not entry_links:
                nav_href = ""
                nav_type = ""
                nav_title = entry_title
                for l in entry_links:
                    if l.rel in ["start", "subsection", "http://opds-spec.org/sort"]:
                        nav_href = l.href
                        nav_type = l.type
                        # Use count from link if available to enrich title
                        if l.properties and l.properties.get("count"):
                            nav_title = f"{entry_title} ({l.properties['count']})"
                        break
                if not nav_href and entry_links:
                    nav_href = entry_links[0].href
                    nav_type = entry_links[0].type
                
                if nav_href:
                    # HEURISTIC: Detect "fake" facets in navigation entries (common in Codex and others)
                    # These are navigation entries that act as sort/filter toggles.
                    is_fake_facet = False
                    facet_group = "Options"
                    
                    # 1. Prefix based detection (Codex style)
                    if entry_title.startswith("➠") or "Order By" in entry_title:
                        is_fake_facet = True
                        facet_group = "Order By"
                        entry_title = entry_title.replace("➠", "").strip()
                    elif entry_title.startswith("⇕") or "Order " in entry_title:
                        is_fake_facet = True
                        facet_group = "Direction"
                        entry_title = entry_title.replace("⇕", "").strip()
                    elif entry_title.startswith("⌗"):
                        is_fake_facet = True
                        facet_group = "Filter"
                        entry_title = entry_title.replace("⌗", "").strip()
                        
                    # 2. URL based detection
                    if not is_fake_facet:
                        source_path = urllib.parse.urlparse(source_url).path
                        nav_path = urllib.parse.urlparse(nav_href).path
                        
                        # Only promote if it's the SAME path (variation of current view)
                        if source_path == nav_path:
                            params = urllib.parse.parse_qs(urllib.parse.urlparse(nav_href).query)
                            if any(k in params for k in ["orderBy", "orderReverse", "filter", "facet"]):
                                is_fake_facet = True
                                if "orderBy" in params: facet_group = "Order By"
                                elif "orderReverse" in params: facet_group = "Direction"

                    if is_fake_facet:
                        if facet_group not in facets_raw:
                            facets_raw[facet_group] = []
                        
                        # Determine if active by comparing to source_url
                        is_active = False
                        source_params = urllib.parse.parse_qs(urllib.parse.urlparse(source_url).query)
                        nav_params = urllib.parse.parse_qs(urllib.parse.urlparse(nav_href).query)
                        
                        # Active if all nav params match source params
                        # (This is a simplified check)
                        match_count = 0
                        for k, v in nav_params.items():
                            if k in source_params and source_params[k] == v:
                                match_count += 1
                        if match_count == len(nav_params) and len(nav_params) > 0:
                            is_active = True
                            
                        props = {"active": True} if is_active else None
                        facets_raw[facet_group].append(Link(rel="facet", href=nav_href, type=nav_type, title=entry_title, properties=props))
                    elif entry_title.startswith("⌂") or entry_title.lower() == "start of catalog":
                        # Hide redundant "Home" entry
                        pass
                    else:
                        nav_props = {"identifier": entry_id}
                        if images:
                            # Capture folder thumbnail if available
                            nav_props["thumbnail"] = images[0].href
                        navigation.append(Link(rel="subsection", href=nav_href, type=nav_type, title=entry_title, properties=nav_props))

    deduped_nav = []
    seen_nav = set()
    for n in navigation:
        # Use identifier as primary deduplication key if available, fallback to (title, href)
        k = n.properties.get("identifier") if n.properties else None
        if not k:
            k = (n.title, n.href)
            
        if k not in seen_nav:
            seen_nav.add(k)
            deduped_nav.append(n)

    # Finalize Facets
    from comiccatcher.models.opds import Group
    facets = []
    for group_name, group_links in facets_raw.items():
        # Deduplicate links in group
        seen_links = set()
        deduped_group_links = []
        for l in group_links:
            k = (l.title, l.href)
            if k not in seen_links:
                seen_links.add(k)
                deduped_group_links.append(l)
        
        facets.append(Group(
            metadata=Metadata(title=group_name),
            links=deduped_group_links
        ))

    return OPDSFeed(
        metadata=metadata,
        links=links,
        publications=publications if publications else None,
        navigation=deduped_nav if deduped_nav else None,
        facets=facets if facets else None
    )
