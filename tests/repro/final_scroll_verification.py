#!/usr/bin/env python3
import asyncio
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication
from comiccatcher.ui.theme_manager import UIConstants

async def drive(window):
    print("🚀 Final Verification Driver Started!")
    await asyncio.sleep(5) # Wait for initial feed load
    
    browser = window.feed_browser
    show_labels = window.config_manager.get_show_labels()
    # Feed cards (Scrolled/PagedFeedView) DO NOT reserve progress space
    expected_step = UIConstants.get_card_height(show_labels, reserve_progress_space=False) + UIConstants.GRID_GUTTER
    print(f"[*] Expected Row Step: {expected_step}px (Labels: {show_labels})")

    async def run_test():
        view = browser.stack.currentWidget()
        view_name = type(view).__name__
        print(f"\n[*] Active View: {view_name}")
        
        if view_name == "LoadingOverlay":
            print("⚠️ Still loading...")
            return False

        # Robust Scrollbar/Viewport discovery
        sb = None
        target = None
        if hasattr(view, "_impl"): # Scrolled
            sb = view._impl.verticalScrollBar()
            target = view._impl.viewport()
        elif hasattr(view, "scroll_area"): # Paged
            sb = view.scroll_area.verticalScrollBar()
            target = view.scroll_area.viewport()
        elif hasattr(view, "list_widget"): # Library
            sb = view.list_widget.verticalScrollBar()
            target = view.list_widget.viewport()
            
        if not sb or not target:
            print(f"❌ Failed to find scrollbar/viewport for {view_name}")
            return False

        if sb.maximum() == 0:
            print(f"⚠️ No scroll range (0-0). Feed might be small.")
            return False

        start = sb.value()
        print(f"    Initial Scroll: {start}")
        
        # Simulating the Key
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        view.eventFilter(target, event)
        
        await asyncio.sleep(0.5)
        delta = sb.value() - start
        print(f"    Actual Delta: {delta}px")
        
        if delta == expected_step:
            print(f"✅ SUCCESS: {view_name} scrolled exactly one row.")
        else:
            print(f"❌ FAILED: {view_name} delta {delta} != {expected_step}")
        return True

    # Test current view
    await run_test()

    # Toggle mode and test again
    print("\n[*] Toggling view mode...")
    current_view = browser.stack.currentWidget()
    if type(current_view).__name__ == "ScrolledFeedView":
        browser._on_paging_mode_changed("paged")
    else:
        browser._on_paging_mode_changed("scrolled")
        
    await asyncio.sleep(3)
    await run_test()

    print("\n🏁 Verification Complete!")
    await asyncio.sleep(1)
    QApplication.instance().quit()
