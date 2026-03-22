
import sys
import asyncio
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

from config import ConfigManager
from ui.app_layout import MainWindow

async def run_perf_test():
    print("Initializing Performance Test...")
    config = ConfigManager()
    
    # Target Start Pages for Codex, Komga, Stump
    targets = [
        {"name": "Codex", "url": "https://anville.duckdns.org:2700/codex/opds/v2.0/"},
        {"name": "Stump", "url": "https://anville.duckdns.org:2702/opds/v2.0/catalog"},
        {"name": "Komga", "url": "https://anville.duckdns.org:2700/komga/opds/v2/catalog"},
    ]
    
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    
    browser = window.feed_browser
    results = []

    async def wait_for_settle(timeout=5):
        print(" Settling...", end="", flush=True)
        start = time.time()
        while time.time() - start < timeout:
            if browser.updatesEnabled() and browser.dash_layout.count() > 0:
                print(" Done.")
                await asyncio.sleep(0.5)
                return True
            # Special case for Codex might not use dash_layout if it promoted
            if browser.updatesEnabled() and browser.main_layout.count() > 0:
                 print(" Done (Main).")
                 await asyncio.sleep(0.5)
                 return True
            await asyncio.sleep(0.2)
        print(" Settle Timeout.")
        return False

    async def measure_page(name):
        print(f"Measuring: {name}")
        page = browser._last_page
        if not page:
            print("  No page data.")
            return
            
        num_sections = len(page.sections)
        total_items = sum(len(s.items) for s in page.sections)
        num_list_views = len(browser._section_views)
        
        # Measure Collapse All
        start = time.perf_counter()
        browser.collapse_all()
        collapse_time = time.perf_counter() - start
        
        # Measure Expand All
        start = time.perf_counter()
        browser.expand_all()
        # Wait for height re-calc timer (50ms)
        await asyncio.sleep(0.2)
        expand_time = time.perf_counter() - start
        
        results.append({
            "name": name,
            "sections": num_sections,
            "items": total_items,
            "collapse_s": collapse_time,
            "expand_s": expand_time,
            "list_views": num_list_views
        })
        print(f"  Sec: {num_sections}, Items: {total_items}, Views: {num_list_views}")
        print(f"  Coll: {collapse_time:.4f}s, Exp: {expand_time:.4f}s")

    for target in targets:
        print(f"\nTesting: {target['name']} ({target['url']})")
        await browser.load_url(target['url'])
        if await wait_for_settle():
            await measure_page(target['name'])
        else:
            print(f"  Failed to load {target['name']}")

    # Final Report
    print("\n" + "="*90)
    print("START PAGE PERFORMANCE COMPARISON")
    print("="*90)
    header = f"{'Source':<15} | {'Sec':<3} | {'Items':<5} | {'Views':<5} | {'Coll(s)':<8} | {'Exp(s)':<8}"
    print(header)
    print("-" * 90)
    for r in results:
        print(f"{r['name']:<15} | {r['sections']:<3} | {r['items']:<5} | {r['list_views']:<5} | {r['collapse_s']:<8.4f} | {r['expand_s']:<8.4f}")
    
    app.quit()

if __name__ == "__main__":
    loop = QEventLoop(QApplication(sys.argv))
    asyncio.set_event_loop(loop)
    with loop:
        try:
            loop.run_until_complete(run_perf_test())
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
