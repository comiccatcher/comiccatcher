#!/usr/bin/env python3
import asyncio
import argparse
import sys
import json
import urllib.parse
import math
import re
import httpx
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.syntax import Syntax

# Add src to path for direct execution
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from comiccatcher.api.client import APIClient
from comiccatcher.api.opds_v2 import OPDS2Client
from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.models.feed import FeedProfile
from comiccatcher.models.feed_page import SectionLayout, ItemType
from comiccatcher.ui.reader_logic import parse_reading_order, resolve_href

async def main():
    parser = argparse.ArgumentParser(description="Debug OPDS feed or Publication Manifest reconciliation.")
    parser.add_argument("url", help="Feed or Manifest URL")
    parser.add_argument("-u", "--username", help="Authentication username")
    parser.add_argument("-p", "--password", help="Authentication password")
    parser.add_argument("-t", "--token", help="Bearer token")
    parser.add_argument("--raw", action="store_true", help="Dump raw JSON response")
    parser.add_argument("--json", action="store_true", help="Dump reconciled FeedPage as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all links and detailed item metadata")
    parser.add_argument("-m", "--manifest", action="store_true", help="Interpret as a Publication Manifest (WebPub/Divina)")
    
    args = parser.parse_args()
    
    console = Console()
    
    # Create a minimal profile for the client
    profile = FeedProfile(
        id="debug",
        name="Debug",
        url=args.url,
        username=args.username,
        password=args.password,
        bearer_token=args.token
    )
    
    async with APIClient(profile) as api:
        try:
            console.print(f"[bold blue]Fetching content from:[/bold blue] {args.url}")
            
            try:
                resp = await api.get(args.url)
                resp.raise_for_status()
            except httpx.ConnectError:
                console.print(f"\n[bold red]Error: Connection failed.[/bold red] The server at [cyan]{args.url}[/cyan] is unreachable or not responding.")
                return
            except httpx.TimeoutException:
                console.print(f"\n[bold red]Error: Request timed out.[/bold red] The server took too long to respond.")
                return
            except httpx.HTTPStatusError as e:
                console.print(f"\n[bold red]HTTP Error {e.response.status_code}:[/bold red] {e.response.reason_phrase}")
                if e.response.status_code == 401:
                    console.print("[yellow]Hint: This feed requires authentication. Try providing --username and --password.[/yellow]")
                return
            except httpx.RequestError as e:
                console.print(f"\n[bold red]Network Error:[/bold red] {str(e)}")
                return
            
            content_type = resp.headers.get("Content-Type", "")
            console.print(f"Content-Type: [cyan]{content_type}[/cyan]")

            if "json" not in content_type.lower():
                console.print(f"[bold yellow]Warning: Response is not JSON.[/bold yellow]")
                if "application/octet-stream" in content_type.lower() or "application/x-cbz" in content_type.lower() or "application/zip" in content_type.lower():
                    console.print("[bold red]This appears to be a binary archive file, not a manifest or feed.[/bold red]")
                else:
                    console.print(f"Sample content: {resp.content[:100]!r}")
                return

            raw_data = resp.json()
            
            if args.raw:
                console.print(f"\n[bold magenta]--- Raw Response ---[/bold magenta]")
                syntax = Syntax(json.dumps(raw_data, indent=2), "json", theme="monokai", line_numbers=True)
                console.print(syntax)

            # --- AUTO-DETECTION HEURISTIC ---
            is_manifest = args.manifest
            reason = "manual flag"

            if not is_manifest:
                # 1. Check Content-Type
                if "webpub" in content_type.lower() or "divina" in content_type.lower():
                    is_manifest = True
                    reason = f"Content-Type: {content_type}"
                
                # 2. Check conformsTo in metadata
                if not is_manifest:
                    metadata = raw_data.get("metadata", {})
                    conforms_to = metadata.get("conformsTo")
                    if conforms_to:
                        # Could be a string or a list
                        conforms_list = [conforms_to] if isinstance(conforms_to, str) else conforms_to
                        for uri in conforms_list:
                            if "webpub-manifest" in uri or "divina" in uri:
                                is_manifest = True
                                reason = f"conformsTo: {uri}"
                                break
                
                # 3. Check Structure (fallback)
                if not is_manifest:
                    if "readingOrder" in raw_data or "spine" in raw_data:
                        is_manifest = True
                        reason = "structural keys (readingOrder/spine)"

            if is_manifest:
                console.print(f"[bold green]Auto-detected Publication Manifest[/bold green] (via {reason})")
                handle_manifest(raw_data, args.url, console, args.verbose)
            else:
                if args.manifest: # Should not happen due to 'is_manifest = args.manifest' above
                     handle_manifest(raw_data, args.url, console, args.verbose)
                else:
                     handle_feed(raw_data, args.url, console, args)

        except Exception as e:
            console.print(f"[bold red]Error during processing:[/bold red] {e}")
            import traceback
            traceback.print_exc()

def format_contributors(contributors, include_links=True):
    if not contributors:
        return None
    
    def format_single(c):
        name = "Unknown"
        link = ""
        if isinstance(c, dict):
            name = c.get("name", "Unknown")
            if include_links:
                # Check for links in contributor object
                clinks = c.get("links", [])
                if clinks:
                    l_hrefs = [l.get("href") for l in clinks if l.get("href")]
                    if l_hrefs: link = f" [dim]({', '.join(l_hrefs)})[/dim]"
        elif hasattr(c, "name"):
            name = c.name
        else:
            name = str(c)
        return f"{name}{link}"

    if isinstance(contributors, list):
        return ", ".join([format_single(c) for c in contributors])
    return format_single(contributors)

def handle_manifest(data, url, console, verbose):
    console.print(f"\n[bold green]Detected: Publication Manifest (WebPub/Divina)[/bold green]")
    
    metadata = data.get("metadata", {})
    title = metadata.get("title", "Unknown Title")
    subtitle = metadata.get("subtitle")
    identifier = metadata.get("identifier", "No Identifier")
    publisher = format_contributors(metadata.get("publisher"), include_links=verbose)
    published = metadata.get("published")
    belongs_to = metadata.get("belongsTo")
    subjects = metadata.get("subject")
    summary = metadata.get("description")
    
    console.print(f"\n[bold yellow]--- Manifest Details ---[/bold yellow]")
    console.print(f"Title:        [bold white]{title}[/bold white]")
    if subtitle:
        console.print(f"Subtitle:     [dim]{subtitle}[/dim]")
    console.print(f"Identifier:   {identifier}")
    
    # Show Credits
    roles = ["author", "artist", "penciler", "penciller", "inker", "colorist", "letterer", "editor", "translator", "illustrator"]
    for role in roles:
        val = format_contributors(metadata.get(role), include_links=verbose)
        if val:
            console.print(f"{role.capitalize():13}: {val}")

    if publisher:
        console.print(f"Publisher:    {publisher}")
    if published:
        console.print(f"Published:    {published}")
        
    if subjects:
        genre_display = []
        subjects_list = subjects if isinstance(subjects, list) else [subjects]
        for s in subjects_list:
            if isinstance(s, dict):
                name = s.get("name") or s.get("label") or str(s)
                link = ""
                if verbose:
                    clinks = s.get("links", [])
                    l_hrefs = [l.get("href") for l in clinks if l.get("href")]
                    if l_hrefs: link = f" [dim]({', '.join(l_hrefs)})[/dim]"
                genre_display.append(f"{name}{link}")
            else:
                genre_display.append(str(s))
        console.print(f"Subject(s):   {', '.join(genre_display)}")

    if belongs_to:
        if "series" in belongs_to:
            s = belongs_to["series"]
            if isinstance(s, dict):
                name = s.get("name", "Unknown")
                pos = s.get("position")
                console.print(f"Series:       [bold magenta]{name}[/bold magenta]" + (f" (#{pos})" if pos else ""))
            else:
                console.print(f"Series:       {s}")
        if "collection" in belongs_to:
            c = belongs_to["collection"]
            name = c.get("name", "Unknown") if isinstance(c, dict) else str(c)
            console.print(f"Collection:   {name}")

    if summary:
        console.print(f"\n[bold yellow]Summary:[/bold yellow]")
        console.print(summary)

    reading_order = parse_reading_order(data)
    console.print(f"Page Count:   [bold cyan]{len(reading_order)}[/bold cyan]")
    
    # Links summary
    links = data.get("links", [])
    if links:
        console.print(f"\n[bold blue]--- Links ({len(links)}) ---[/bold blue]")
        for link in links:
            rel = link.get("rel", "none")
            href = link.get("href")
            l_type = link.get("type", "unknown")
            l_title = link.get("title", "")
            
            rel_str = f"[dim]{rel}:[/dim]"
            if rel == "self": rel_str = "[bold cyan]self:[/bold cyan]"
            
            display_line = f"  - {rel_str:15} {href} ({l_type})"
            if l_title: display_line += f" [italic]'{l_title}'[/italic]"
            console.print(display_line)

    # Display Reading Order Sample
    if reading_order:
        table = Table(title=f"\nReading Order (Sample of {min(5, len(reading_order))} pages)", box=None)
        table.add_column("Index", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Resolved URL", style="green")
        
        for i, item in enumerate(reading_order[:5]):
            full_url = resolve_href(url, item.get("href", ""))
            table.add_row(
                str(i + 1),
                item.get("type") or item.get("mediaType") or "unknown",
                full_url
            )
        console.print(table)
        if len(reading_order) > 5:
            console.print(f"  [dim]... and {len(reading_order) - 5} more items[/dim]")

    if verbose and "resources" in data:
        resources = data["resources"]
        console.print(f"\n[bold blue]Resources Found:[/bold blue] {len(resources)}")
        for res in resources[:10]:
            console.print(f" - {res.get('href')} ({res.get('type') or 'unknown'})")

def handle_feed(raw_data, url, console, args):
    from comiccatcher.models.opds import OPDSFeed
    feed = OPDSFeed(**raw_data)
    
    console.print(f"[bold green]Raw feed parsed successfully into OPDSFeed model.[/bold green]")
    
    page = FeedReconciler.reconcile(feed, url)
    
    if args.json:
        console.print(f"\n[bold yellow]--- Reconciled FeedPage (JSON) ---[/bold yellow]")
        if hasattr(page, "model_dump_json"):
            syntax = Syntax(page.model_dump_json(indent=2), "json", theme="monokai")
        else:
            syntax = Syntax(page.json(indent=2), "json", theme="monokai")
        console.print(syntax)
        return

    console.print(f"\n[bold yellow]--- Reconciled Feed Page ---[/bold yellow]")
    console.print(f"Title:        [bold white]{page.title}[/bold white]")
    console.print(f"Paginated:    {'[green]Yes[/green]' if page.is_paginated else '[red]No[/red]'}")
    
    # Pagination Details
    paging_links = {}
    for link in (feed.links or []):
        rel_list = [link.rel] if isinstance(link.rel, str) else (link.rel or [])
        for rel in rel_list:
            if rel in ["first", "previous", "next", "last"]:
                paging_links[rel] = urllib.parse.urljoin(url, link.href)
    
    m = feed.metadata
    if m:
        total_items = getattr(m, "numberOfItems", None)
        items_per_page = getattr(m, "itemsPerPage", None)
        
        console.print(f"Page Info:    [cyan]Current: {page.current_page}[/cyan] | [cyan]Total Pages: {page.total_pages or 'N/A'}[/cyan] | [cyan]Items/Page: {items_per_page or 'N/A'}[/cyan] | [cyan]Total Items: {total_items if total_items is not None else 'N/A'}[/cyan]")
    
    if paging_links:
        console.print("Paging Links:")
        for rel in ["first", "previous", "next", "last"]:
            if rel in paging_links:
                console.print(f"  - [bold cyan]{rel:8}[/bold cyan]: {paging_links[rel]}")

    console.print(f"Offset-based: {'[green]Yes[/green]' if page.is_offset_based else '[red]No[/red]'}")
    console.print(f"Paging Base:  [cyan]{page.pagination_base_number}[/cyan]")

    if page.first_page_url:
        console.print(f"First Page:   [dim cyan]{page.first_page_url}[/dim cyan]")

    if page.pagination_template:
        console.print(f"Paging Templ: [bold magenta]{page.pagination_template}[/bold magenta]")
    else:
        console.print(f"Paging Templ: [red]None (Fast Page Indexing Disabled)[/red]")

    if page.search_template:
        console.print(f"Search Templ: [bold green]{page.search_template}[/bold green]")
    else:
        console.print(f"Search Templ: [red]None (Server-side Search Unsupported)[/red]")

    main = page.main_section
    console.print(f"Main Section: {'[green]' + main.title + '[/green]' if main else '[red]None[/red]'}")
    
    # Calculate Scrolling Mode (matching ScrolledFeedView.render logic)
    scroll_mode = "Static Mode (no pagination)"
    style = "dim white"
    
    has_groups = any(s.source_element and s.source_element.startswith("group[") for s in page.sections)
    has_root   = any(s.source_element in ("root:publications", "root:navigation") for s in page.sections)
    
    if main and main.total_items is None and page.next_url:
        scroll_mode = "Infinite Grid (appends items to main grid)"
        style = "bold cyan"
    elif not main and page.next_url and has_groups and not has_root:
        scroll_mode = "Infinite Sections (appends new sections/headers)"
        style = "bold yellow"
    elif main and main.total_items is not None:
        scroll_mode = "Virtualized Grid (pre-allocates rows for total count)"
        style = "bold green"
    elif page.next_url:
        scroll_mode = "Static (Next URL ignored due to Dashboard heuristic)"
        style = "bold red"
        
    console.print(f"Scroll Mode:  [{style}]{scroll_mode}[/{style}]")
    
    if page.breadcrumbs:
        console.print(f"Breadcrumbs:  {' > '.join(b['title'] for b in page.breadcrumbs)}")
    
    for i, section in enumerate(page.sections):
        layout_name = "GRID" if section.layout == SectionLayout.GRID else "RIBBON"
        layout_style = "bold yellow" if section.layout == SectionLayout.GRID else "dim cyan"

        is_main = (main and section.section_id == main.section_id)
        main_info = " [bold green][MAIN][/bold green]" if is_main else ""
        source_info = f" [dim]({section.source_element})[/dim]" if section.source_element else ""
        table = Table(title=f"\nSection {i+1}: {section.title} (Layout: [{layout_style}]{layout_name}[/{layout_style}]){main_info}{source_info}", box=None)
        table.add_column("Type", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Identifier", style="green")
        table.add_column("Details", style="dim white")
        
        for item in section.items:
            type_str = item.type.name
            details = []
            if item.cover_url: details.append("🖼️")
            if item.download_url: details.append("⬇️")
            if item.subtitle: details.append(f"({item.subtitle})")
            if item.year: details.append(f"[yellow]{item.year}[/yellow]")
            
            if args.verbose:
                # Find navigation/self links
                links = []
                if item.raw_link:
                    links.append(f"[dim]href: {item.raw_link.href}[/dim]")
                if item.raw_pub:
                    for l in (item.raw_pub.links or []):
                        r = l.rel or "none"
                        links.append(f"[dim]{r}: {l.href}[/dim]")
                if item.download_url:
                    links.append(f"[green]acq: {item.download_url}[/green]")
                
                table.add_row(
                    type_str, 
                    item.title, 
                    str(item.identifier)[:40] + ("..." if len(str(item.identifier)) > 40 else ""),
                    " ".join(details) + "\n" + "\n".join(links)
                )
            else:
                table.add_row(
                    type_str, 
                    item.title, 
                    str(item.identifier)[:40] + ("..." if len(str(item.identifier)) > 40 else ""),
                    " ".join(details)
                )
        
        console.print(table)
        
        # Print section metadata if available
        meta = []
        if section.total_items is not None: meta.append(f"Total: {section.total_items}")
        if section.next_url: meta.append(f"Next: {section.next_url}")
        if args.verbose and section.self_url: meta.append(f"Self: {section.self_url}")
        if meta:
            console.print(f"   [dim cyan]{' | '.join(meta)}[/dim cyan]")
        
    if page.facets:
        console.print(f"\n[bold blue]Facets Found:[/bold blue] {len(page.facets)}")
        for f in page.facets:
            # Facets are groups
            title = getattr(f, "metadata", None)
            if title: title = getattr(title, "title", "Untitled Facet")
            else: title = "Untitled Facet"
            console.print(f" - {title}")

if __name__ == "__main__":
    asyncio.run(main())
