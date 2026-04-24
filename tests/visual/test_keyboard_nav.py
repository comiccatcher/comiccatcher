import sys
import os
import argparse
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QListView, QScrollArea, QLabel, QFrame, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QAbstractListModel, QSize, QModelIndex, QRect, QPoint, QTimer
from PyQt6.QtGui import QColor, QPainter, QKeyEvent

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.ui.components.collapsible_section import CollapsibleSection
from comiccatcher.ui.components.keyboard_nav import KeyboardBrowserNavigator
from comiccatcher.ui.components.library_card_delegate import LibraryCardDelegate

class MockModel(QAbstractListModel):
    def __init__(self, count):
        super().__init__()
        self.count = count

    def rowCount(self, parent=QModelIndex()):
        return self.count

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return f"Item {index.row()}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Tooltip for Item {index.row()}"
        if role == Qt.ItemDataRole.DecorationRole:
            return ThemeManager.get_icon("book")
        # LibraryCardDelegate roles
        if role == Qt.ItemDataRole.UserRole: # PATH
            return None
        if role == Qt.ItemDataRole.UserRole + 1: # PROGRESS
            return (10, 100)
        if role == Qt.ItemDataRole.UserRole + 2: # LABELS
            return (f"Title {index.row()}", "Subtitle")
        return None

class ProductionListView(QListView):
    """
    A QListView that behaves like the one in the app, including 
    auto-height adjustment to prevent internal scrolling in grids.
    """
    def __init__(self, mode="grid", card_size="medium", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.card_size = card_size
        self.show_labels = True
        
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setUniformItemSizes(True)
        self.setStyleSheet("background: transparent; border: none;")
        
        # Disable internal scrollbars for both grid and ribbon
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        if mode == "grid":
            self.setWrapping(True)
        else: # ribbon
            self.setWrapping(False)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.delegate = LibraryCardDelegate(self, show_labels=self.show_labels, card_size=self.card_size)
        self.setItemDelegate(self.delegate)
        self._update_metrics()

    def _update_metrics(self):
        w = UIConstants.get_card_width(self.card_size)
        h = UIConstants.get_card_height(self.show_labels, card_size=self.card_size)
        self.setIconSize(QSize(w, h))
        self.setGridSize(QSize(w + UIConstants.GRID_SPACING, h + UIConstants.GRID_SPACING))
        if self.mode == "grid":
            self._update_grid_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.mode == "grid":
            self._update_grid_height()

    def _update_grid_height(self):
        count = self.model().rowCount() if self.model() else 0
        if count == 0:
            return
            
        available_width = self.viewport().width()
        if available_width <= 0:
            available_width = self.width()
            
        if available_width <= 0:
            return

        item_w = UIConstants.get_card_width(self.card_size) + UIConstants.GRID_SPACING
        cols = max(1, available_width // item_w)
        rows_count = (count + cols - 1) // cols
        
        item_h = UIConstants.get_card_height(self.show_labels, card_size=self.card_size)
        target_h = rows_count * (item_h + UIConstants.GRID_SPACING) + UIConstants.GRID_SPACING
        
        if self.height() != target_h:
            self.setFixedHeight(target_h)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw the keyboard cursor if active
        if self.property("keyboard_cursor_active"):
            idx = self.currentIndex()
            if idx.isValid():
                rect = self.visualRect(idx)
                painter = QPainter(self.viewport())
                theme = ThemeManager.get_current_theme_colors()
                painter.setPen(QColor(theme['accent']))
                cursor_color = QColor(theme['accent'])
                cursor_color.setAlpha(80)
                painter.setBrush(cursor_color)
                painter.drawRect(rect.adjusted(2, 2, -2, -2))
                painter.end()

class ValidationHarness(QMainWindow):
    def __init__(self, auto_mode=False, card_size="medium"):
        super().__init__()
        self.auto_mode = auto_mode
        self.card_size = card_size
        self.setWindowTitle(f"Keyboard Nav - High Fidelity ({card_size.upper()} Cards)")
        
        # Larger window for manual inspection, small for auto reproduction
        if self.auto_mode:
            self.setFixedSize(1000, 400)
        else:
            self.resize(1100, 900)
        
        ThemeManager.apply_theme(QApplication.instance(), "dark")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none;")
        main_layout.addWidget(self.scroll_area)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(20)
        self.scroll_area.setWidget(self.content)

        # 1. Grid
        self.grid = ProductionListView("grid", card_size=card_size)
        self.grid.setModel(MockModel(120))
        self.content_layout.addWidget(CollapsibleSection(f"Library Grid ({card_size.upper()})", self.grid))

        # 2. Ribbon
        self.ribbon = ProductionListView("ribbon")
        self.ribbon.setModel(MockModel(50))
        # Ensure ribbon is tall enough to be clearly visible in 400px window
        self.ribbon.setFixedHeight(300)
        self.ribbon.setProperty("is_ribbon", True)
        self.content_layout.addWidget(CollapsibleSection("Recent Ribbons (Nested)", self.ribbon))

        self.nav = KeyboardBrowserNavigator(self)

    def get_keyboard_nav_views(self):
        return [self.grid, self.ribbon]

    def get_keyboard_nav_scrollbar(self):
        return self.scroll_area.verticalScrollBar()
    
    def keyboard_activate_index(self, view, index):
        pass

    def keyboard_toggle_bulk_item(self, view, index):
        pass

    def keyboard_context_menu_for_index(self, view, index):
        pass

    def toggle_bulk_selection(self, enabled):
        self._bulk_selection_mode = enabled

    def toggle_all_sections(self):
        pass

    def toggle_active_section(self, view):
        pass

    def follow_active_section_link(self, view):
        pass


    def simulate_key(self, key, modifiers=Qt.KeyboardModifier.NoModifier, target_view=None):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)
        # Manually trigger the global theft logic
        self.keyPressEvent(event)

    def keyPressEvent(self, event):
        # Steal all keys for the navigator
        # We pass the currently focused view if it's one of ours, otherwise default to grid
        view = self.grid
        if self.ribbon.hasFocus():
            view = self.ribbon
            
        if self.nav._handle_key_event(view, event):
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure focus is ready for immediate keyboard nav
        self.grid.setFocus(Qt.FocusReason.OtherFocusReason)
        # Seed the cursor automatically so the user sees it on first Ctrl+Arrow
        QTimer.singleShot(100, lambda: self.grid.setFocus())

    def run_validation(self):
        print("\n=== STARTING AUTOMATED KEYBOARD NAV VALIDATION ===\n")
        passed = True
        
        # --- REPRODUCTION: Upward Skipping Bug ---
        print("[TEST] REPRO: Testing Upward Navigation Skipping...")
        
        # 1. Scroll to the absolute bottom
        vbar = self.scroll_area.verticalScrollBar()
        vbar.setValue(vbar.maximum())
        QApplication.processEvents()
        import time
        time.sleep(0.1) # Wait for stabilization
        print(f"Scrolled to bottom: {vbar.value()}/{vbar.maximum()}")

        # 2. Seed focus in Ribbon
        print("Seeding focus in Ribbon...")
        self.ribbon.setFocus()
        self.simulate_key(Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier, target_view=self.ribbon)
        print(f"Ribbon row seeded: {self.ribbon.currentIndex().row()}")

        # 3. Navigate UP into the Grid
        print("Navigating UP from Ribbon into Grid...")
        self.simulate_key(Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier, target_view=self.ribbon)
        
        # Now we should be in the grid
        cand = self.nav._get_current_candidate()
        current_view = cand.view if cand else None
        current_row = cand.index.row() if cand else -1
        view_name = "GRID" if current_view is self.grid else "RIBBON" if current_view is self.ribbon else "NONE"
        print(f"Jumped to {view_name} at Row {current_row}")

        if current_view is self.grid:
            # Continue navigating UP and look for skips
            last_row = current_row
            skips_found = 0
            for i in range(5):
                self.simulate_key(Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier, target_view=self.grid)
                cand = self.nav._get_current_candidate()
                new_row = cand.index.row() if cand else last_row
                # A jump of more than 1 row (stride-wise) or backwards is a skip
                # (Actual rows are indices 0, 1, 2...)
                cols = 6 # approx
                diff = last_row - new_row
                print(f"Moved UP: {last_row} -> {new_row} (diff: {diff})")
                
                # In a grid of 6 cols, a normal Up jump should be exactly 6 indices
                if diff > 15: # Allow some leeway but 15+ is definitely a skip
                    print(f"WARNING: Potential SKIP detected! Jumped {diff} indices.")
                    skips_found += 1
                
                if new_row == last_row: # Wall hit
                    break
                last_row = new_row
            
            if skips_found > 0:
                print(f"FAILED: Found {skips_found} skips during upward navigation.")
                passed = False
            else:
                print("PASSED: No skips detected during initial upward test.")
        else:
            print("FAILED: Did not jump from Ribbon to Grid.")
            passed = False

        # --- ORIGINAL CHECKS ---
        print("\n[TEST] Running standard checks...")
        # (Reset for standard checks)
        vbar.setValue(0)
        QApplication.processEvents()
        self.grid.setFocus()
        self.nav.clear_cursor()

        # 4. Ribbon Panning Check
        print("[TEST] Verifying Ribbon Horizontal Panning...")
        # Ensure outer area is scrolled to maximum so ribbon is visible
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())
        QApplication.processEvents()
        
        self.ribbon.setFocus()
        hbar = self.ribbon.horizontalScrollBar()
        hbar.setValue(0)
        initial_h = hbar.value()
        
        # Explicitly seed the ribbon
        self.simulate_key(Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier, target_view=self.ribbon)
        cand = self.nav._get_current_candidate()
        initial_row = cand.index.row() if cand else -1
        
        for _ in range(30):
            self.simulate_key(Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier, target_view=self.ribbon)
            QApplication.processEvents()
            
        cand = self.nav._get_current_candidate()
        final_row = cand.index.row() if cand else -1
        if final_row <= initial_row:
             print(f"FAILED: Ribbon index did not move. row {initial_row} -> {final_row}")
             passed = False
        else:
             print(f"PASSED: Ribbon navigation confirmed. Row {final_row}, hbar {hbar.value()}")

        # 5. Auto-Clear Check
        print("[TEST] Verifying Auto-Clear on non-nav key...")
        self.simulate_key(Qt.Key.Key_A, target_view=self.grid)
        if self.nav.cursor_active:
            print("FAILED: Cursor remained active after pressing 'A'.")
            passed = False
        else:
            print("PASSED: Cursor cleared successfully.")

        print("\n=== VALIDATION SUMMARY ===")
        if passed:
            print("✅ ALL KEYBOARD NAVIGATION REQUIREMENTS MET.")
            sys.exit(0)
        else:
            print("❌ SOME VALIDATION CHECKS FAILED.")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keyboard Navigation Visual Test")
    parser.add_argument("--auto", action="store_true", help="Run automated validation")
    parser.add_argument("--size", "-s", choices=["small", "medium", "large"], default="medium", help="Set grid card size")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    UIConstants.init_scale()
    harness = ValidationHarness(auto_mode=args.auto, card_size=args.size)
    
    if args.auto:
        harness.show()
        QTimer.singleShot(500, harness.run_validation)
        sys.exit(app.exec())
    else:
        harness.show()
        print(f"Manual Mode Started with {args.size.upper()} cards. Use --auto for validation.")
        sys.exit(app.exec())
