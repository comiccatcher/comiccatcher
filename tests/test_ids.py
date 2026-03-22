import json
import sys
import os

# Ensure paths are correct
sys.path.append(os.getcwd())

from models.opds import OPDSFeed
from api.feed_reconciler import FeedReconciler

def get_sec_id(local_file, url):
    path = f"/home/tony/cc/test/feeds/crawls/codex/{local_file}"
    if not os.path.exists(path):
        return f"MISSING: {path}"
    with open(path) as f:
        data = json.load(f)
        feed = OPDSFeed(**data)
    page = FeedReconciler.reconcile(feed, url)
    return page.sections[0].section_id if page.sections else "NONE"

url1 = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/1?topGroup=p"
url2 = "https://anville.duckdns.org:2700/codex/opds/v2.0/p/0/2?topGroup=p"

id1 = get_sec_id("codex_opds_v2.0_p_0_1_16e2638808bc7ba2.json", url1)
id2 = get_sec_id("codex_opds_v2.0_p_0_2_8d630b67b57aeff0.json", url2)

print(f"Page 1 ID: {id1}")
print(f"Page 2 ID: {id2}")
print(f"Match: {id1 == id2}")
