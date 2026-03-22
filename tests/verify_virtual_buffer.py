import json
import sys
import os

# Ensure paths are correct
sys.path.append(os.getcwd())

from models.opds import OPDSFeed
from api.feed_reconciler import FeedReconciler
from ui.components.feed_browser_model import FeedBrowserModel
from models.feed_page import ItemType

def test_virtual_buffer():
    print("--- TESTING VIRTUAL BUFFER (Zero-Jump) ---")
    
    # 1. Load a real Codex feed with many items
    path = "/home/tony/cc/test/feeds/crawls/codex/codex_opds_v2.0_p_0_1_16e2638808bc7ba2.json"
    url = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/1?topGroup=p"
    
    with open(path) as f:
        feed = OPDSFeed(**json.load(f))
    
    page = FeedReconciler.reconcile(feed, url)
    print(f"Feed reconciled. Total sections: {len(page.sections)}")
    
    # 2. Setup Model with Total Count (3193 items)
    total_items = page.sections[0].total_items # 3193
    model = FeedBrowserModel(total_count=total_items, items_per_page=100)
    
    print(f"Model initialized with rowCount: {model.rowCount()}")
    if model.rowCount() == 3193:
        print("SUCCESS: Pre-allocation verified.")
    else:
        print(f"FAILURE: rowCount is {model.rowCount()}, expected 3193.")
        sys.exit(1)

    # 3. Check for Flattened Header
    # Page 1 items are injected by the browser
    model.set_items_for_page(1, page.sections[0].items)
    
    first_item = model.get_item(0)
    print(f"Item 0 type: {first_item.type.name} - {first_item.title}")
    if first_item.type == ItemType.HEADER:
        print("SUCCESS: Flattened Header verified.")
    else:
        print("FAILURE: Item 0 is not a HEADER.")
        sys.exit(1)

    # 4. Test Sparse Signal
    requested_pages = []
    def on_page_requested(page_idx):
        requested_pages.append(page_idx)
        print(f"SIGNAL RECEIVED: Browser should fetch Page {page_idx}")

    model.page_request_needed.connect(on_page_requested)
    
    print("Accessing Row #550 (Page 6)...")
    # This should trigger the signal because Page 6 isn't loaded
    dummy = model.data(model.index(550))
    
    if 6 in requested_pages:
        print("SUCCESS: Sparse Page signal verified.")
    else:
        print(f"FAILURE: Page 6 was not requested. Pages requested: {requested_pages}")
        sys.exit(1)

    print("--- ALL VIRTUAL BUFFER TESTS PASSED ---")

if __name__ == "__main__":
    test_virtual_buffer()
