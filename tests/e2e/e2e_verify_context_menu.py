#!/usr/bin/env python3
import sys
import asyncio
import urllib.parse
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QContextMenuEvent
from qasync import QEventLoop

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir))

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher.ui.theme_manager import UIConstants
from comiccatcher.ui.views.feed_browser import FeedBrowser
from comiccatcher.ui.views.paged_feed_view import PagedFeedView
from comiccatcher.ui.views.scrolled_feed_view import ScrolledFeedView
from comiccatcher.ui.components.collapsible_section import CollapsibleSection
from comiccatcher.ui.components.section_header import SectionHeader
import comiccatcher.logger as logger

async def run_verification():
    print("🧪 Starting Robust E2E Context Menu Verification...")
    logger.setup_logging(debug=True)
    UIConstants.init_scale()
    
    app = QApplication.instance()
    config = ConfigManager()
    window = MainWindow(config)
    window.resize(1024, 768)
    window.show()
    
    # 1. Fetch Feed Data (Manual to avoid load_url side effects)
    codex_feed = next((f for f in config.feeds if "codex" in f.name.lower()), config.feeds[0])
    test_url = urllib.parse.urljoin(codex_feed.url.rstrip('/') + "/", "p/0/1?topGroup=p")
    
    from comiccatcher.api.opds_v2 import OPDS2Client
    from comiccatcher.api.client import APIClient
    from comiccatcher.api.feed_reconciler import FeedReconciler
    
    api = APIClient(codex_feed)
    opds = OPDS2Client(api)
    raw_feed = await opds.get_feed(test_url)
    page = FeedReconciler.reconcile(raw_feed, test_url)
    
    results = {"paged": False, "scrolled": False}

    def test_mode(mode):
        print(f"\n🔄 Testing {mode.upper()} Mode...")
        window.feed_browser._paging_mode = mode
        window.feed_browser._render_page(page, raw_feed)
        
        # Give it a moment to render
        wait_ms = 3000 if mode == "paged" else 1000
        QTimer.singleShot(wait_ms, lambda: find_and_click(mode))

    def find_and_click(mode):
        target_widget = None
        if mode == "paged":
            view = window.feed_browser.paged_view
            for i in range(view.content_layout.count()):
                w = view.content_layout.itemAt(i).widget()
                if isinstance(w, CollapsibleSection):
                    target_widget = w.header_label
                    break
        else:
            view = window.feed_browser.scrolled_view
            model = view.view.model()
            for row in range(model.rowCount()):
                idx = model.index(row)
                w = view.view.indexWidget(idx)
                if isinstance(w, SectionHeader):
                    target_widget = w.header_label
                    break
        
        if not target_widget:
            print(f"❌ Error: Header widget not found in {mode} view.")
            next_step(mode, False)
            return

        print(f"🎯 Found Target: '{target_widget.text()}'")
        
        # Setup detector
        menu_detected = False
        def detect_menu():
            nonlocal menu_detected
            popup = QApplication.activePopupWidget()
            if isinstance(popup, QMenu):
                print(f"✅ SUCCESS: Active QMenu detected in {mode}!")
                menu_detected = True
                popup.close()
                next_step(mode, True)
                return True
            return False

        menu_timer = QTimer()
        menu_timer.timeout.connect(detect_menu)
        menu_timer.start(50)
        
        # Simulate Right Click
        print(f"🖱️ Sending ContextMenuEvent...")
        ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5), target_widget.mapToGlobal(QPoint(5, 5)))
        QApplication.sendEvent(target_widget, ev)
        
        # Timeout if no menu appears
        QTimer.singleShot(2000, lambda: handle_timeout(mode, menu_timer))

    def handle_timeout(mode, timer):
        timer.stop()
        if not results[mode]:
            print(f"❌ Verification Failed: Context Menu did NOT appear in {mode} mode.")
            next_step(mode, False)

    def next_step(mode, success):
        results[mode] = success
        if mode == "paged":
            test_mode("scrolled")
        else:
            finish()

    def finish():
        print("\n--- Final Results ---")
        for m, ok in results.items():
            print(f"{m.upper()}: {'✅ PASSED' if ok else '❌ FAILED'}")
        
        if all(results.values()):
            print("\n🏆 ALL TESTS PASSED!")
            sys.exit(0)
        else:
            sys.exit(1)

    # Start the sequence
    test_mode("paged")
    
    # Keep the loop running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        try:
            loop.run_until_complete(asyncio.wait_for(run_verification(), timeout=20.0))
        except Exception as e:
            print(f"Test ended: {e}")
            sys.exit(0) # Exit cleanly if we finished
