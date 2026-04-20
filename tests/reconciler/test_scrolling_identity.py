#!/usr/bin/env python3
import json
import os
import sys
from rich.console import Console

# Add src to path for direct execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.models.opds import OPDSFeed

def main():
    console = Console()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    scrolling_dir = os.path.join(root, "tests", "reconciler", "fixtures", "raw", "scrolling")
    
    if not os.path.exists(scrolling_dir):
        console.print(f"[bold red]Error:[/bold red] Scrolling fixtures directory not found: {scrolling_dir}")
        sys.exit(1)
        
    console.print("[bold blue]Running Scrolling Identity Tests...[/bold blue]")

    # Case 1: Codex Publishers (The reported bug)
    console.print("\nTesting Case: [bold cyan]codex_publishers[/bold cyan]")
    
    pages = ["codex_p1.json", "codex_p2.json", "codex_p3.json"]
    section_ids = []
    
    for i, page_file in enumerate(pages):
        path = os.path.join(scrolling_dir, page_file)
        with open(path, "r") as f:
            raw_data = json.load(f)
            
        feed = OPDSFeed(**raw_data)
        # Simulate sequential URLs as provided in the bug report
        url = f"http://juke.local:9810/codex/opds/v2.0/r/0/{i+1}?topGroup=p"
        reconciled_page = FeedReconciler.reconcile(feed, url)
        
        main = reconciled_page.main_section
        if main:
            console.print(f"  Page {i+1}: Found Main Section '[bold green]{main.title}[/bold green]' with ID: [bold yellow]{main.section_id}[/bold yellow]")
            section_ids.append(main.section_id)
        else:
            console.print(f"  Page {i+1}: [bold red]FAILED[/bold red] - No main section identified.")
            section_ids.append(None)

    # Verification
    if len(set(section_ids)) == 1 and section_ids[0] is not None:
        console.print("\n[bold green]PASSED:[/bold green] Main section ID remains stable across all pages.")
    else:
        console.print("\n[bold red]FAILED:[/bold red] Main section identity is unstable or missing.")
        if None in section_ids:
            console.print("  - Reason: One or more pages failed to identify a main section.")
        if len(set([s for s in section_ids if s])) > 1:
            console.print("  - Reason: Section IDs drifted between pages (this breaks scrolling).")
        sys.exit(1)

if __name__ == "__main__":
    main()
