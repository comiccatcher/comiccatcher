#!/usr/bin/env python3
import json
import os
import sys
import difflib
import urllib.parse
from rich.console import Console

# Add src to path for direct execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "repro")))

from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.models.opds import OPDSFeed
from debug_opds_content import get_reconciliation_report

def normalise_report(r):
    """Recursively replace any hostname with localhost in URLs."""
    if isinstance(r, dict):
        return {k: normalise_report(v) for k, v in r.items()}
    elif isinstance(r, list):
        return [normalise_report(x) for x in r]
    elif isinstance(r, str) and "://" in r:
        try:
            parts = urllib.parse.urlparse(r)
            return parts._replace(netloc="localhost").geturl()
        except:
            return r
    return r

def main():
    console = Console()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    raw_dir = os.path.join(root, "tests", "reconciler", "fixtures", "raw")
    exp_dir = os.path.join(root, "tests", "reconciler", "fixtures", "expected")
    
    if not os.path.exists(raw_dir):
        console.print(f"[bold red]Error:[/bold red] Raw directory not found: {raw_dir}")
        sys.exit(1)
        
    # Find all test cases (including subdirectories like scrolling/)
    test_cases = []
    for dirpath, _, filenames in os.walk(raw_dir):
        for f in filenames:
            if f.endswith(".json"):
                full_path = os.path.join(dirpath, f)
                rel_path = os.path.relpath(full_path, raw_dir)
                test_cases.append(rel_path[:-5]) # Strip .json
    
    if not test_cases:
        console.print("[yellow]No test cases found in tests/reconciler/fixtures/raw/[/yellow]")
        return

    failed = 0
    for case in sorted(test_cases):
        console.print(f"Testing case: [bold cyan]{case}[/bold cyan]...", end="")
        
        raw_path = os.path.join(raw_dir, f"{case}.json")
        exp_path = os.path.join(exp_dir, f"{case}.json")
        
        if not os.path.exists(exp_path):
            console.print(" [bold red]FAILED[/bold red] (Expected report file missing)")
            failed += 1
            continue
            
        with open(raw_path, "r") as f:
            raw_data = json.load(f)
            
        with open(exp_path, "r") as f:
            expected_report = json.load(f)
            
        # Reconcile using current logic
        try:
            feed = OPDSFeed(**raw_data)
            # Use a dummy base URL since we are testing from file
            page = FeedReconciler.reconcile(feed, "http://localhost/test")
            
            # Generate report for comparison
            should_obfuscate = ("stump" in case or "komga" in case)
            actual_report = get_reconciliation_report(page, obfuscate=should_obfuscate)
            
            # Normalise both for comparison (ensures hostname differences don't break tests)
            actual_report = normalise_report(actual_report)
            expected_report = normalise_report(expected_report)
                
            if actual_report == expected_report:
                console.print(" [bold green]PASSED[/bold green]")
            else:
                console.print(" [bold red]FAILED[/bold red] (Report mismatch)")
                
                exp_json = json.dumps(expected_report, indent=2)
                act_json = json.dumps(actual_report, indent=2)
                
                diff = difflib.unified_diff(
                    exp_json.splitlines(),
                    act_json.splitlines(),
                    fromfile="expected",
                    tofile="actual",
                    lineterm=""
                )
                for line in diff:
                    if line.startswith("+"): console.print(f"[green]{line}[/green]")
                    elif line.startswith("-"): console.print(f"[red]{line}[/red]")
                    else: console.print(line)
                failed += 1
                
        except Exception as e:
            console.print(f" [bold red]ERROR[/bold red] ({str(e)})")
            import traceback
            traceback.print_exc()
            failed += 1

    if failed == 0:
        console.print(f"\n[bold green]All {len(test_cases)} tests passed![/bold green]")
    else:
        console.print(f"\n[bold red]{failed} tests failed.[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
