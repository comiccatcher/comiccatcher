#!/usr/bin/env python3
import asyncio
import sys
import os
import argparse

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from comiccatcher.api.client import APIClient
from comiccatcher.api.opds_v2 import OPDS2Client
from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.models.feed import FeedProfile
from comiccatcher.ui.theme_manager import UIConstants

async def test_url(url, token=None):
    print(f"🧪 Testing URL: {url}")
    if token:
        print(f"🔑 Using Bearer Token: {token[:10]}...")
    
    # Setup minimal environment
    UIConstants.LARGE_SECTION_THRESHOLD = 200 
    
    profile = FeedProfile(id="test", name="Test", url=url, bearer_token=token)
    api_client = APIClient(profile)
    opds_client = OPDS2Client(api_client)
    
    try:
        print("📡 Fetching feed...")
        feed = await opds_client.get_feed(url)
        
        print("🔄 Reconciling...")
        page = FeedReconciler.reconcile(feed, url)
        
        print(f"\n--- Result for '{page.title}' ---")
        print(f"Is Paginated: {page.is_paginated}")
        
        main = page.main_section
        print(f"Main Section: {main.title if main else 'None (All Ribbons)'}")
        
        print("\nSections:")
        for s in page.sections:
            is_main = (main and s.section_id == main.section_id)
            has_link = bool(s.self_url)
            has_next = bool(s.next_url)
            count = len(s.items)
            print(f"  - {s.title:25} | items={count:3} | main={str(is_main):5} | has_link={str(has_link):5} | has_next={str(has_next):5}")

        if page.is_paginated:
            if main is None:
                print("\n✅ Paginated: No main section detected (no items matched).")
            else:
                print(f"\nℹ️ Paginated: Section '{main.title}' promoted to Main Grid.")
        else:
            print("\n📄 List View: Not paginated.")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await api_client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test feed layout heuristics.")
    parser.add_argument("url", help="The OPDS 2.0 URL to test")
    parser.add_argument("-t", "--token", help="Bearer token for authentication", default=None)
    args = parser.parse_args()
    
    asyncio.run(test_url(args.url, args.token))
