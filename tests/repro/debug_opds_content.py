#!/usr/bin/env python3
import asyncio
import argparse
import sys
import json
import urllib.parse
import os
import re
import httpx
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.syntax import Syntax

# Add src to path for direct execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from comiccatcher.api.client import APIClient
from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.models.feed import FeedProfile
from comiccatcher.models.feed_page import FeedPage, SectionLayout, ItemType

def rotate_text(s: str) -> str:
    """Applies ROT13 to letters and ROT5 to digits."""
    if not s: return s
    res = ""
    for c in s:
        if "A" <= c <= "Z":
            res += chr((ord(c) - ord("A") + 13) % 26 + ord("A"))
        elif "a" <= c <= "z":
            res += chr((ord(c) - ord("a") + 13) % 26 + ord("a"))
        elif "0" <= c <= "9":
            res += chr((ord(c) - ord("0") + 5) % 10 + ord("0"))
        else:
            res += c
    return res

def get_reconciliation_report(page: FeedPage, obfuscate: bool = False) -> dict:
    """Generates a high-level report of the reconciler's decisions for regression testing."""
    main = page.main_section
    
    # Calculate Scrolling Mode (matching ScrolledFeedView.render logic)
    scroll_mode = "Static Mode (no pagination)"
    has_groups = any(s.source_element and s.source_element.startswith("group[") for s in page.sections)
    has_root   = any(s.source_element in ("root:publications", "root:navigation") for s in page.sections)
    
    if main and main.total_items is None and page.next_url:
        scroll_mode = "Infinite Grid (appends items to main grid)"
    elif not main and page.next_url and has_groups and not has_root:
        scroll_mode = "Infinite Sections (appends new sections/headers)"
    elif main and main.total_items is not None:
        scroll_mode = "Virtualized Grid (pre-allocates rows for total count)"
    elif page.next_url:
        scroll_mode = "Static (Next URL ignored due to Dashboard heuristic)"

    def maybe_rot(t):
        return rotate_text(t) if obfuscate else t

    report = {
        "title": maybe_rot(page.title),
        "paginated": page.is_paginated,
        "page_info": {
            "current": page.current_page,
            "total_pages": page.total_pages,
            "items_per_page": page.feed_items_per_page,
            "total_items": main.total_items if main else None
        },
        "next_url": page.next_url,
        "offset_based": page.is_offset_based,
        "paging_base": page.pagination_base_number,
        "paging_template": page.pagination_template,
        "search_template": page.search_template,
        "main_section": maybe_rot(main.title) if main else None,
        "scroll_mode": scroll_mode,
        "sections": [
            {
                "title": maybe_rot(s.title),
                "count": len(s.items),
                "layout": "GRID" if s.layout == SectionLayout.GRID else "RIBBON",
                "is_main": s.is_main,
                "source": s.source_element
            }
            for s in page.sections
        ]
    }
    return report

def handle_feed(raw_data, url, console, args):
    from comiccatcher.models.opds import OPDSFeed
    feed = OPDSFeed(**raw_data)
    
    console.print(f"[bold green]Raw feed parsed successfully into OPDSFeed model.[/bold green]")
    
    page = FeedReconciler.reconcile(feed, url)
    report = get_reconciliation_report(page)

    if args.json:
        console.print(f"\n[bold yellow]--- Reconciled FeedPage (JSON) ---[/bold yellow]")
        if hasattr(page, "model_dump_json"):
            syntax = Syntax(page.model_dump_json(indent=2), "json", theme="monokai")
        else:
            syntax = Syntax(page.json(indent=2), "json", theme="monokai")
        console.print(syntax)
        return

    console.print(f"\n[bold yellow]--- Reconciled Feed Page ---[/bold yellow]")
    console.print(f"Title:        [bold white]{report['title']}[/bold white]")
    console.print(f"Paginated:    {'[green]Yes[/green]' if report['paginated'] else '[red]No[/red]'}")
    
    pi = report['page_info']
    console.print(f"Page Info:    [cyan]Current: {pi['current']}[/cyan] | [cyan]Total Pages: {pi['total_pages'] or 'N/A'}[/cyan] | [cyan]Items/Page: {pi['items_per_page'] or 'N/A'}[/cyan] | [cyan]Total Items: {pi['total_items'] if pi['total_items'] is not None else 'N/A'}[/cyan]")
    
    if report['next_url']:
        console.print(f"Next URL:     {report['next_url']}")

    console.print(f"Offset-based: {'[green]Yes[/green]' if report['offset_based'] else '[red]No[/red]'}")
    console.print(f"Paging Base:  [cyan]{report['paging_base']}[/cyan]")
    console.print(f"Paging Templ: [bold magenta]{report['paging_template'] or 'None'}[/bold magenta]")
    console.print(f"Search Templ: [bold green]{report['search_template'] or 'None'}[/bold green]")
    console.print(f"Main Section: {'[green]' + report['main_section'] + '[/green]' if report['main_section'] else '[red]None[/red]'}")
    console.print(f"Scroll Mode:  [bold yellow]{report['scroll_mode']}[/bold yellow]")
    
    if page.breadcrumbs:
        console.print(f"Breadcrumbs:  {' > '.join(b['title'] for b in page.breadcrumbs)}")
    
    main = page.main_section
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
    
    return page

def parse_reading_order(data):
    # Publication manifests use readingOrder or spine
    return data.get("readingOrder", data.get("spine", []))

def resolve_href(base_url, href):
    return urllib.parse.urljoin(base_url, href)

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

async def main():
    parser = argparse.ArgumentParser(description="Debug OPDS feed or Publication Manifest reconciliation")
    parser.add_argument("url", help="URL of the OPDS feed or Publication Manifest")
    parser.add_argument("-u", "--username", help="Authentication username")
    parser.add_argument("-p", "--password", help="Authentication password")
    parser.add_argument("-t", "--token", help="Bearer token")
    parser.add_argument("-k", "--api-key", help="API Key (X-API-Key)")
    parser.add_argument("--raw", action="store_true", help="Dump raw JSON response")
    parser.add_argument("--json", action="store_true", help="Dump reconciled FeedPage as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all links and detailed item metadata")
    parser.add_argument("-m", "--manifest", action="store_true", help="Interpret as a Publication Manifest (WebPub/Divina)")
    parser.add_argument("--save", help="Save raw JSON and reconciliation report JSON to tests/feeds/ using this ID")
    
    args = parser.parse_args()
    
    console = Console()
    
    # Determine auth_type
    auth_mode = "none"
    if args.api_key:
        auth_mode = "apikey"
    elif args.token:
        auth_mode = "bearer"
    elif args.username and args.password:
        auth_mode = "basic"

    # Create a minimal profile for the client
    profile = FeedProfile(
        id="debug",
        name="Debug",
        url=args.url,
        auth_type=auth_mode,
        username=args.username,
        password=args.password,
        bearer_token=args.token,
        api_key=args.api_key
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
                    console.print("[yellow]Hint: This feed requires authentication. Try providing --username/--password, --token, or --api-key.[/yellow]")
                return
            except httpx.RequestError as e:
                console.print(f"\n[bold red]Network Error:[/bold red] {str(e)}")
                return
            
            content_type = resp.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                console.print(f"\n[bold red]Error: Unexpected Content-Type:[/bold red] {content_type}")
                if resp.content:
                    console.print(f"Sample content: {resp.content[:100]!r}")
                return

            raw_data = resp.json()

            if args.save:
                # Always obfuscate for known servers when saving fixtures
                should_obfuscate = ("stump" in args.save or "komga" in args.save)

                if should_obfuscate:
                    # Obfuscate raw data before saving
                    if "metadata" in raw_data and "title" in raw_data["metadata"]:
                        raw_data["metadata"]["title"] = rotate_text(raw_data["metadata"]["title"])
                    for item in raw_data.get("navigation", []):
                        if "title" in item: item["title"] = rotate_text(item["title"])
                    for g in raw_data.get("groups", []):
                        if "metadata" in g and "title" in g["metadata"]:
                            g["metadata"]["title"] = rotate_text(g["metadata"]["title"])
                        for n in g.get("navigation", []):
                            if "title" in n: n["title"] = rotate_text(n["title"])
                        for p in g.get("publications", []):
                            if "metadata" in p and "title" in p["metadata"]:
                                p["metadata"]["title"] = rotate_text(p["metadata"]["title"])

                # Resolve project root (two levels up from tests/repro/)
                root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                raw_dir = os.path.join(root, "tests", "reconciler", "fixtures", "raw")
                exp_dir = os.path.join(root, "tests", "reconciler", "fixtures", "expected")
                os.makedirs(raw_dir, exist_ok=True)
                os.makedirs(exp_dir, exist_ok=True)
                
                raw_path = os.path.join(raw_dir, f"{args.save}.json")
                os.makedirs(os.path.dirname(raw_path), exist_ok=True)
                with open(raw_path, "w") as f:
                    json.dump(raw_data, f, indent=2)
                console.print(f"[bold green]Saved raw response (obfuscated={should_obfuscate}) to:[/bold green] {raw_path}")
            
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
                page = handle_feed(raw_data, args.url, console, args)
                if args.save and page:
                    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                    exp_path = os.path.join(root, "tests", "reconciler", "fixtures", "expected", f"{args.save}.json")
                    os.makedirs(os.path.dirname(exp_path), exist_ok=True)
                    
                    # Always obfuscate for known servers when saving fixtures
                    should_obfuscate = ("stump" in args.save or "komga" in args.save)
                    report = get_reconciliation_report(page, obfuscate=should_obfuscate)
                    
                    with open(exp_path, "w") as f:
                        json.dump(report, f, indent=2)
                    console.print(f"[bold green]Saved reconciliation report (obfuscated={should_obfuscate}) to:[/bold green] {exp_path}")

        except Exception as e:
            console.print(f"[bold red]Error during processing:[/bold red] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
