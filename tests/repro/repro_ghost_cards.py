#!/usr/bin/env python3

import asyncio
import httpx
import os
import sys
from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.models.opds import OPDSFeed
from comiccatcher.models.feed_page import SectionLayout

async def observe():
    url = os.environ.get("CC_GHOST_URL")
    # Expected format: "username:password"
    auth_str = os.environ.get("CC_GHOST_AUTH")
    
    if not url:
        print("Error: CC_GHOST_URL environment variable is required.")
        sys.exit(1)
        
    auth = tuple(auth_str.split(":")) if auth_str else None
    
    async with httpx.AsyncClient(auth=auth) as client:
        # 1. Fetch Page 1
        print(f"Fetching Page 1: {url}")
        r = await client.get(url)
        feed = OPDSFeed(**r.json())
        page = FeedReconciler.reconcile(feed, url)
        
        main_sec = page.main_section
        if not main_sec:
            print("No main section found!")
            return
            
        total = main_sec.total_items
        ipp = main_sec.items_per_page or 40
        print(f"\nRECONCILIATION RESULT:")
        print(f"Main Section: {main_sec.title}")
        print(f"Total Items claimed: {total}")
        print(f"Items Per Page: {ipp}")
        
        # 2. Fetch the LAST Page
        # In a 1-indexed system with 3210 items and 40 IPP, page 81 is the last (80*40 = 3200)
        last_page_num = (total + ipp - 1) // ipp
        last_url = page.pagination_template.format(page=last_page_num)
        
        print(f"\nFetching Last Page ({last_page_num}): {last_url}")
        r_last = await client.get(last_url)
        feed_last = OPDSFeed(**r_last.json())
        page_last = FeedReconciler.reconcile(feed_last, last_url)
        
        # Find the matching section in the last page
        last_sec = next((s for s in page_last.sections if s.section_id == main_sec.section_id), None)
        
        if not last_sec:
            print("Could not find main section on last page!")
            return
            
        actual_last_count = len(last_sec.items)
        first_index_on_page = (last_page_num - 1) * ipp
        last_index_on_page = first_index_on_page + actual_last_count - 1
        
        print(f"\nLAST PAGE ANALYSIS:")
        print(f"Items on last page: {actual_last_count}")
        print(f"Calculated index of last item: {last_index_on_page}")
        print(f"Expected index of last item:   {total - 1}")
        
        gap = (total - 1) - last_index_on_page
        if gap > 0:
            print(f"\n[OBSERVATION CONFIRMED]")
            print(f"There are {gap} 'ghost' cards at the end of the list.")
            print(f"Indices {last_index_on_page + 1} to {total - 1} will never be populated.")
        else:
            print("\nNo ghost cards observed.")

if __name__ == "__main__":
    asyncio.run(observe())
