import asyncio
import sys
import os
from pathlib import Path

# Ensure we use the workspace source
sys.path.insert(0, str(Path.cwd() / "comiccatcher/src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRect, QPoint
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher.ui.theme_manager import UIConstants

async def drive(window):
    print("\n--- Codex Navigation Repro ---")
    
    # 1. Select Codex
    codex = next((f for f in window.config_manager.feeds if "codex" in f.name.lower()), None)
    if not codex:
        print("Error: Codex feed not found in config.")
        QApplication.instance().quit()
        return
        
    print(f"Selecting feed: {codex.name}")
    window.on_feed_selected(codex)
    
    # 2. Wait for load
    browser = window.feed_browser
    for _ in range(20):
        await asyncio.sleep(0.5)
        if browser.stack.currentWidget() != browser.loading_view:
            break
            
    view = browser.stack.currentWidget()
    print(f"Active View: {type(view).__name__}")
    
    # 3. Inspect first row items
    import logging
    logging.getLogger("nav").setLevel(logging.DEBUG)
    
    # We need to see what the navigator thinks is in the first row
    nav = browser._keyboard_nav
    nav_views = view.get_keyboard_nav_views()
    if not nav_views:
        print("Error: No nav views found.")
        QApplication.instance().quit()
        return
        
    first_view = nav_views[0]
    is_ribbon = first_view.property("is_ribbon")
    print(f"View is_ribbon property: {is_ribbon}")
    print(f"View type: {type(first_view).__name__}")
    print(f"View geometry: {first_view.geometry()}")
    print(f"Viewport geometry: {first_view.viewport().geometry()}")

    print(f"View flow: {first_view.flow()}")
    print(f"View wrapping: {first_view.isWrapping()}")
    
    model = first_view.model()
    count = model.rowCount()
    print(f"First section has {count} items.")
    
    print("\nChecking Visibility via Navigator:")
    
    def debug_vis(view, idx):
        viewport = view.viewport()
        rect = view.visualRect(idx)
        item_tl = viewport.mapTo(window, rect.topLeft())
        item_br = viewport.mapTo(window, rect.bottomRight())
        item_browser_rect = QRect(item_tl, item_br)
        browser_rect = window.rect()
        is_vis = browser_rect.adjusted(-1, -15, 1, 15).contains(item_browser_rect)
        print(f"  Item {idx.row()}: browser_rect={item_browser_rect} | window_rect={browser_rect} | Visible={is_vis}")

    for i in range(count):
        debug_vis(first_view, model.index(i, 0))

    candidates = nav._visible_candidates_for_view(first_view)
    print(f"Navigator found {len(candidates)} visible candidates.")
    visible_titles = [nav._current_view.model().data(c.index, Qt.ItemDataRole.DisplayRole) if nav._current_view else first_view.model().data(c.index, Qt.ItemDataRole.DisplayRole) for c in candidates]
    print(f"Visible titles: {visible_titles}")

    for i in range(min(count, 10)):
        idx = model.index(i, 0)
        text = model.data(idx, Qt.ItemDataRole.DisplayRole)
        rect = first_view.visualRect(idx)
        print(f"[{i}] {text} | Rect: {rect}")

    # 4. Check Stride (Columns)
    stride = 1
    if count > 1:
        y0 = first_view.visualRect(model.index(0, 0)).y()
        for i in range(1, min(count, 30)):
            if first_view.visualRect(model.index(i, 0)).y() > y0 + 10:
                stride = i
                break
    
    print(f"Detected Stride (Columns): {stride}")
    
    if count >= 5:
        print(f"Item 5 (index 4) is: {model.data(model.index(4,0), Qt.ItemDataRole.DisplayRole)}")
        if stride < 5:
            print(f"!!! STRIDE ALERT: Stride is {stride}, so item 5 is on the NEXT row.")
        else:
            print(f"Stride is {stride}, item 5 should be reachable via Right arrow.")

    await asyncio.sleep(1)
    QApplication.instance().quit()
