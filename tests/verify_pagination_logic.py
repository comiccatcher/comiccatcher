import json
import sys
import os

# Ensure paths are correct
sys.path.append(os.getcwd())

from models.opds import OPDSFeed
from api.feed_reconciler import FeedReconciler
from ui.components.feed_browser_model import FeedBrowserModel

def load_page(local_file, url):
    path = f"/home/tony/cc/test/feeds/crawls/codex/{local_file}"
    with open(path) as f:
        data = json.load(f)
        feed = OPDSFeed(**data)
    return FeedReconciler.reconcile(feed, url)

# URLs
url1 = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/1?topGroup=p"
url2 = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/2?orderBy=filename&orderReverse=True&topGroup=p"

# 1. Load Page 1
page1 = load_page("codex_opds_v2.0_p_0_1_16e2638808bc7ba2.json", url1)
main_section1 = page1.sections[0]
model = FeedBrowserModel(main_section1.items)
initial_count = model.rowCount()

print(f"Page 1 Title: {page1.title}")
print(f"Page 1 Section ID: {main_section1.section_id}")
print(f"Page 1 Item Count: {initial_count}")

# 2. Load Page 2
page2 = load_page("codex_opds_v2.0_p_0_2_8d630b67b57aeff0.json", url2)

# 3. Simulate FeedBrowser._fetch_next_page matching logic
new_section = None
for s in page2.sections:
    if s.section_id == main_section1.section_id:
        new_section = s
        break

if new_section:
    print(f"MATCH FOUND: {new_section.section_id}")
    print(f"New items to add: {len(new_section.items)}")
    model.add_items(new_section.items)
    print(f"Final Model Count: {model.rowCount()}")
else:
    print("CRITICAL FAILURE: No matching section found in Page 2!")
    for s in page2.sections:
        print(f"  Available Section ID in P2: {s.section_id}")
    sys.exit(1)

# Verification
actual = model.rowCount()
print(f"Verification: {actual} items in model (Initial: {initial_count}, Added: {len(new_section.items)})")

if actual > initial_count:
    print("SUCCESS: Items were successfully appended to the model.")
else:
    print("FAILURE: No items were added.")
    sys.exit(1)
