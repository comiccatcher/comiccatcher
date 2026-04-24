from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PyQt6.QtCore import QEvent, QModelIndex, QObject, QPoint, QRect, Qt, QItemSelectionModel
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QAbstractItemView, QAbstractScrollArea, QListView, QScrollBar, QWidget

from comiccatcher.logger import get_logger
from comiccatcher.ui.theme_manager import UIConstants

logger = get_logger("nav")


@dataclass(frozen=True)
class _Candidate:
    view: QListView
    index: QModelIndex
    rect: QRect

    @property
    def center(self) -> QPoint:
        return self.rect.center()


class KeyboardBrowserNavigator(QObject):
    """
    Browser-level keyboard navigation across multiple grids and ribbons.
    Strictly enforces physical viewport boundaries ("Walls").
    """

    def __init__(self, browser: QWidget):
        super().__init__(browser)
        self.browser = browser
        self._installed: set[int] = set()
        self._tracked_objects: list[QObject] = []
        self._current_view: Optional[QListView] = None
        self._cursor_active = False
        self.sync()

    @property
    def cursor_active(self) -> bool:
        return self._cursor_active

    def sync(self):
        for obj in self._tracked_objects:
            try:
                obj.removeEventFilter(self)
            except Exception:
                pass
        self._tracked_objects.clear()
        self._installed.clear()

        self._track(self.browser)
        if hasattr(self.browser, "get_keyboard_nav_focus_objects"):
            for obj in self.browser.get_keyboard_nav_focus_objects() or []:
                self._track(obj)
        
        views = self._iter_views()
        logger.debug(f"Navigator Sync: Tracking {len(views)} views")
        for view in views:
            self._track(view)
            self._track(view.viewport())
            self._track(view.horizontalScrollBar())
            self._track(view.verticalScrollBar())

        self._refresh_cursor_flags()

    def clear_cursor(self):
        if not self._cursor_active and not self._current_view:
            return
        self._cursor_active = False
        self._current_view = None
        self._refresh_cursor_flags()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        event_type = event.type()

        if event_type == QEvent.Type.KeyPress:
            view = self._view_for_object(obj)
            return self._handle_key_event(view, event)

        if self._cursor_active and event_type in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.Wheel,
        ):
            self.clear_cursor()

        return super().eventFilter(obj, event)

    def _track(self, obj: QObject):
        if not obj:
            return
        oid = id(obj)
        if oid not in self._installed:
            obj.installEventFilter(self)
            self._installed.add(oid)
            self._tracked_objects.append(obj)

    def _iter_views(self) -> Iterable[QListView]:
        if hasattr(self.browser, "get_keyboard_nav_views"):
            return self.browser.get_keyboard_nav_views() or []
        return []

    def _view_for_object(self, obj: QObject) -> Optional[QListView]:
        for view in self._iter_views():
            if obj is view or obj is view.viewport():
                return view
        return None

    def _handle_key_event(self, source_view: Optional[QListView], event) -> bool:
        key = event.key()
        modifiers = event.modifiers()
        
        # High-signal debug logging for every key received by the filter
        key_name = QKeySequence(key).toString()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        is_plain = modifiers == Qt.KeyboardModifier.NoModifier
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        logger.debug(f"Key: {key_name} (Ctrl: {is_ctrl}, Plain: {is_plain}, Shift: {is_shift})")

        source_view = source_view or self._preferred_view()
        is_shift_f10 = (
            key == Qt.Key.Key_F10
            and modifiers == Qt.KeyboardModifier.ShiftModifier
        )
        
        # 1. Capture View Shortcuts (P, G, T, Z, S, H, etc)
        if is_plain:
            if key == Qt.Key.Key_H:
                self.clear_cursor()
                if hasattr(self.browser, "toggle_help_popover"):
                    self.browser.toggle_help_popover()
                return True
            elif key == Qt.Key.Key_P:
                self.clear_cursor()
                if hasattr(self.browser, "cycle_display_mode"):
                    self.browser.cycle_display_mode()
                return True
            elif key == Qt.Key.Key_G:
                self.clear_cursor()
                if hasattr(self.browser, "cycle_group_by"):
                    self.browser.cycle_group_by()
                return True
            elif key == Qt.Key.Key_T:
                self.clear_cursor()
                if hasattr(self.browser, "toggle_labels"):
                    self.browser.toggle_labels(not getattr(self.browser, "show_labels", True))
                return True
            elif key == Qt.Key.Key_Z:
                self.clear_cursor()
                if hasattr(self.browser, "cycle_card_size"):
                    self.browser.cycle_card_size()
                return True
            elif key == Qt.Key.Key_S:
                self.clear_cursor()
                if hasattr(self.browser, "toggle_bulk_selection"):
                    self.browser.toggle_bulk_selection(not getattr(self.browser, "_bulk_selection_mode", False))
                return True
            elif key == Qt.Key.Key_D:
                if getattr(self.browser, "_bulk_selection_mode", False):
                    self.clear_cursor()
                    if hasattr(self.browser, "keyboard_trigger_bulk_action"):
                        self.browser.keyboard_trigger_bulk_action()
                        return True

            elif key == Qt.Key.Key_A:
                self.clear_cursor()
                if hasattr(self.browser, "add_feed"):
                    self.browser.add_feed()
                return True
            elif key == Qt.Key.Key_Backslash:
                self.clear_cursor()
                if hasattr(self.browser, "toggle_all_sections"):
                    self.browser.toggle_all_sections()
                return True
            elif key == Qt.Key.Key_BracketLeft:
                self.clear_cursor()
                if hasattr(self.browser, "toggle_active_section"):
                    self.browser.toggle_active_section(source_view)
                return True
            elif key == Qt.Key.Key_BracketRight:
                self.clear_cursor()
                if hasattr(self.browser, "follow_active_section_link"):
                    self.browser.follow_active_section_link(source_view)
                return True
            
            # Swallow Tab/Backtab to prevent focus from escaping our controlled views
            elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.clear_cursor()
                logger.debug(f"Swallowed {key_name} and cleared cursor")
                return True

        # 2. Keyboard Cursor Movement (Ctrl + Arrows)
        if is_ctrl and key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._move_cursor(key, source_view)
            return True

        # 3. Modal Exits (Escape)
        if key == Qt.Key.Key_Escape:
            # Priority 1: Keyboard Cursor
            if self._cursor_active:
                self.clear_cursor()
                return True

            # Priority 2: Bulk Selection Mode
            if getattr(self.browser, "_bulk_selection_mode", False):
                if hasattr(self.browser, "toggle_bulk_selection"):
                    self.browser.toggle_bulk_selection(False)
                    return True

        # 4. Active Cursor Operations
        if self._cursor_active:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current = self._get_current_candidate()
                if current and hasattr(self.browser, "keyboard_activate_index"):
                    self.browser.keyboard_activate_index(current.view, current.index)
                return True
            if key == Qt.Key.Key_Space:
                current = self._get_current_candidate()
                if current and hasattr(self.browser, "keyboard_toggle_bulk_item"):
                    self.browser.keyboard_toggle_bulk_item(current.view, current.index)
                return True
            if key == Qt.Key.Key_Menu or is_shift_f10:
                current = self._get_current_candidate()
                if current and hasattr(self.browser, "keyboard_context_menu_for_index"):
                    self.browser.keyboard_context_menu_for_index(current.view, current.index)
                return True
            
            # Any other movement or common key just clears the cursor if it's not handled
            if key not in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                # (Arrows/Scroll keys handled below)
                pass

        # 5. Scrolling Keys (Plain Up/Down/PgUp/PgDn/Home/End)
        if is_plain and key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End):
            self.clear_cursor()
            self._handle_scroll_key(key, source_view)
            return True
            
        # Swallow plain Left/Right to prevent native widget focus-jumping in ribbons
        if is_plain and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.clear_cursor()
            logger.debug(f"Swallowed {key_name} and cleared cursor")
            return True

        # 6. Block Native Behaviors
        # We explicitly block Tab and all Alpha keys to prevent focus escape and Alpha-search.
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            return True
            
        if is_plain and key >= Qt.Key.Key_A and key <= Qt.Key.Key_Z:
            self.clear_cursor()
            # Swallow all other plain letters to kill QListWidget type-ahead search
            return True

        return False

    def _handle_scroll_key(self, key: int, source_view: Optional[QListView]):
        scrollbar = None
        if hasattr(self.browser, "get_keyboard_nav_scrollbar"):
            scrollbar = self.browser.get_keyboard_nav_scrollbar()
        if not scrollbar:
            return

        if key == Qt.Key.Key_Home:
            scrollbar.setValue(scrollbar.minimum())
            return
        if key == Qt.Key.Key_End:
            scrollbar.setValue(scrollbar.maximum())
            return
        if key == Qt.Key.Key_PageUp:
            scrollbar.setValue(scrollbar.value() - scrollbar.pageStep())
            return
        if key == Qt.Key.Key_PageDown:
            scrollbar.setValue(scrollbar.value() + scrollbar.pageStep())
            return

        delta = -1 if key == Qt.Key.Key_Up else 1
        row_height = self._estimate_row_height(source_view)
        scrollbar.setValue(scrollbar.value() + (delta * row_height))

    def _estimate_row_height(self, preferred_view: Optional[QListView]) -> int:
        for view in self._iter_views():
            candidates = self._visible_candidates_for_view(view)
            if candidates:
                return max(24, candidates[0].rect.height() + 10)
        return 120

    def _move_cursor(self, key: int, source_view: Optional[QListView]):
        self._cursor_active = True
        current = self._get_current_candidate(source_view)
        if current is None:
            # We enable log_blocks here because failure to seed IS interesting debug info
            seed = self._seed_candidate(key, source_view, log_blocks=True)
            if seed:
                self._set_current(seed.view, seed.index)
            else:
                logger.debug("Move Failed: No seed candidate found (view empty or no items visible?)")
                self.clear_cursor()
            return

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            next_candidate = self._move_horizontal(current, key)
            if not next_candidate:
                logger.debug(f"Move Failed: Horizontal move {key} from '{current.index.data()}' blocked (edge of view?)")
        else:
            # We enable log_blocks here because vertical move candidates are often filtered by viewport
            next_candidate = self._move_vertical(current, key, log_blocks=True)
            if not next_candidate:
                logger.debug(f"Move Failed: Vertical move {key} from '{current.index.data()}' blocked (no candidates above/below?)")

        if next_candidate:
            self._set_current(next_candidate.view, next_candidate.index)
        else:
            self._refresh_cursor_flags()

    def _move_horizontal(self, current: _Candidate, key: int) -> Optional[_Candidate]:
        step = -1 if key == Qt.Key.Key_Left else 1
        if self._is_ribbon(current.view):
            row = current.index.row() + step
            model = current.view.model()
            if model and 0 <= row < model.rowCount():
                idx = model.index(row, 0)
                # For ribbons, we don't rely on visualRect for the search, 
                # as it might be empty for off-screen items.
                # We return a candidate with the index; _set_current will scrollTo it.
                rect = current.view.visualRect(idx)
                logger.debug(f"Ribbon H-Move: row {current.index.row()} -> {row}")
                return _Candidate(current.view, idx, rect)
            return None

        # For Grids, use coordinate-based search
        cy = current.center.y()
        candidates = []
        # When moving horizontally in a grid, we allow off-screen items 
        # so we can trigger a scroll.
        for candidate in self._all_candidates_for_view(current.view):
            if candidate.index == current.index: continue
            
            # Map candidate to browser space for more robust coordinate comparison
            # if we are moving between views, though horizontal is usually same-view
            dx = candidate.center.x() - current.center.x()
            if step < 0 and dx >= -4: continue
            if step > 0 and dx <= 4: continue
            dy = abs(candidate.center.y() - cy)
            candidates.append((dy, abs(dx), candidate))
        
        if not candidates:
            return None
            
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    def _move_vertical(self, current: _Candidate, key: int, log_blocks: bool = False) -> Optional[_Candidate]:
        step = -1 if key == Qt.Key.Key_Up else 1
        local_candidate = self._move_vertical_within_view(current, step, log_blocks=log_blocks)
        if local_candidate:
            return local_candidate

        ordered_views = self._ordered_visible_views()
        if not ordered_views:
            return None

        try:
            current_pos = ordered_views.index(current.view)
        except ValueError:
            current_pos = -1

        if current_pos == -1:
            return None

        search_range = range(current_pos + step, len(ordered_views), step) if step > 0 else range(current_pos - 1, -1, -1)
        
        # Map target_x (the column we are in) to browser space
        target_center_browser = current.view.viewport().mapTo(self.browser, current.center)

        for pos in search_range:
            view = ordered_views[pos]
            # When jumping between views, we look for ALL candidates, not just visible ones,
            # so we can trigger a scroll to the next section.
            candidates = self._all_candidates_for_view(view)
            if not candidates: continue
            
            # Sort by proximity to our current X, and then Y in BROWSER space
            def sort_key(c: _Candidate):
                c_center_browser = c.view.viewport().mapTo(self.browser, c.center)
                dx = abs(c_center_browser.x() - target_center_browser.x())
                dy = abs(c_center_browser.y() - target_center_browser.y())
                return (dx, dy, c.index.row())

            candidates.sort(key=sort_key)
            return candidates[0]

        return None

    def _all_candidates_for_view(self, view: QListView) -> list[_Candidate]:
        model = view.model()
        if not view.isVisible() or not model or model.rowCount() == 0: return []
        
        count = model.rowCount()
        out = []
        
        # We need a representative sample of candidates. 
        # For large grids, we prioritize the first 100 and last 100 items.
        # This ensures jumps TO this view (from above or below) find logical targets.
        rows_to_check = set()
        if count <= 200:
            rows_to_check.update(range(count))
        else:
            rows_to_check.update(range(100))
            rows_to_check.update(range(count - 100, count))
            
        for row in sorted(rows_to_check):
            idx = model.index(row, 0)
            rect = view.visualRect(idx)
            if not rect.isEmpty():
                out.append(_Candidate(view, idx, rect))
        return out

    def _move_vertical_within_view(self, current: _Candidate, step: int, log_blocks: bool = False) -> Optional[_Candidate]:
        if self._is_ribbon(current.view):
            return None

        # Try visible ones first for speed and precision
        candidates = []
        for candidate in self._visible_candidates_for_view(current.view, log_blocks=log_blocks):
            if candidate.index == current.index: continue
            dy = candidate.center.y() - current.center.y()
            if step < 0 and dy >= -4: continue
            if step > 0 and dy <= 4: continue
            dx = abs(candidate.center.x() - current.center.x())
            candidates.append((abs(dy), dx, candidate.index.row(), candidate))

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1], item[2]))
            return candidates[0][3]

        # No visible candidates? Try to scroll to the next row in the model
        model = current.view.model()
        if not model: return None
        
        # Determine stride (columns)
        stride = self._get_grid_stride(current.view)
        if stride <= 0: return None
        
        target_row = current.index.row() + (step * stride)
        if 0 <= target_row < model.rowCount():
            idx = model.index(target_row, 0)
            rect = current.view.visualRect(idx)
            # If rect is empty here, it might truly be hidden/collapsed
            if not rect.isEmpty():
                return _Candidate(current.view, idx, rect)
        
        return None

    def _get_grid_stride(self, view: QListView) -> int:
        model = view.model()
        if not model or model.rowCount() == 0: return 0
        
        y0 = view.visualRect(model.index(0, 0)).y()
        for i in range(1, min(model.rowCount(), 40)):
            if view.visualRect(model.index(i, 0)).y() > y0 + 10:
                return i
        return model.rowCount()

    def _seed_candidate(self, key: int, source_view: Optional[QListView], log_blocks: bool = False) -> Optional[_Candidate]:
        candidates = self._visible_candidates(log_blocks=log_blocks)
        if source_view:
            preferred = [c for c in candidates if c.view is source_view]
            if preferred: candidates = preferred
        if not candidates: return None

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            candidates.sort(key=lambda c: (c.center.y(), c.center.x()), reverse=True)
        else:
            candidates.sort(key=lambda c: (c.center.y(), c.center.x()))
        return candidates[0]

    def _get_current_candidate(self, source_view: Optional[QListView] = None) -> Optional[_Candidate]:
        """
        Returns the current cursor candidate if it exists AND is visible.
        If the item has been scrolled off-screen, returns None to force a re-seed.
        """
        def get_valid_candidate(view):
            if not view or not view.isVisible(): return None
            # Use our custom persistent cursor property instead of currentIndex()
            idx = view.property("keyboard_cursor_index")
            if not idx or not isinstance(idx, QModelIndex) or not idx.isValid():
                # Fallback only if we haven't set one yet
                idx = view.currentIndex()
            
            if not idx.isValid(): return None
            
            rect = view.visualRect(idx)
            if rect.isEmpty(): return None
            
            # If the item is physically off-screen from the main browser, 
            # we should return None so that it re-seeds to a visible item.
            # We add a generous grace margin here (100px) so that partially 
            # clipped items don't trigger a jumpy re-seed.
            viewport_rect = view.viewport().rect().adjusted(-100, -100, 100, 100)
            if not viewport_rect.contains(rect):
                return None
            
            return _Candidate(view, idx, rect)

        # 1. Try our tracked current view
        cand = get_valid_candidate(self._current_view)
        if cand: return cand

        # 2. Try the source view (usually the one with focus)
        cand = get_valid_candidate(source_view)
        if cand:
            self._current_view = source_view
            return cand
            
        return None

    def _set_current(self, view: QListView, index: QModelIndex):
        self._current_view = view
        
        # Log cursor move for debugging
        label = index.data(Qt.ItemDataRole.DisplayRole) or "Unknown"
        vtype = "Ribbon" if self._is_ribbon(view) else "Grid"
        logger.debug(f"Cursor moved to [{vtype}]: {label}")

        view.setFocus(Qt.FocusReason.ShortcutFocusReason)
        
        # 1. Main Browser Scrolling (e.g. jumping between ribbons/sections)
        # If the view itself is off-screen, we need to nudge the main scroll area.
        # CRITICAL: We do this BEFORE internal scrollTo, so that ScrolledFeedView 
        # can synchronize its clipped widget's scroll state correctly.
        if hasattr(self.browser, "get_keyboard_nav_scrollbar"):
            scrollbar = self.browser.get_keyboard_nav_scrollbar()
            if scrollbar:
                # 2a. Standard QScrollArea support
                from PyQt6.QtWidgets import QScrollArea
                scroll_area = scrollbar.parent()
                while scroll_area and not isinstance(scroll_area, QScrollArea):
                    scroll_area = scroll_area.parent()
                
                if isinstance(scroll_area, QScrollArea):
                    content_widget = scroll_area.widget()
                    if content_widget:
                        item_rect = view.visualRect(index)
                        top_left = view.viewport().mapTo(content_widget, item_rect.topLeft())
                        bottom_right = view.viewport().mapTo(content_widget, item_rect.bottomRight())
                        scroll_area.ensureVisible(top_left.x(), top_left.y(), 50, 50)
                        scroll_area.ensureVisible(bottom_right.x(), bottom_right.y(), 50, 50)
                
                # 2b. Generic Scrollbar Fallback (used by ScrolledFeedView)
                else:
                    # Map item rect to browser space to check visibility
                    # IMPORTANT: We use the rect BEFORE scrollTo for determining 
                    # how much we need to move the outer scrollbar.
                    item_rect_local = view.visualRect(index)
                    item_tl_browser = view.viewport().mapTo(self.browser, item_rect_local.topLeft())
                    item_br_browser = view.viewport().mapTo(self.browser, item_rect_local.bottomRight())
                    
                    # Vertical bounds check
                    margin = UIConstants.SCROLL_EDGE_MARGIN
                    view_top = margin + UIConstants.HEADER_HEIGHT
                    view_bot = self.browser.height() - margin - UIConstants.STATUS_HEIGHT
                    
                    if item_tl_browser.y() < view_top:
                        diff = view_top - item_tl_browser.y()
                        scrollbar.setValue(scrollbar.value() - diff)
                    elif item_br_browser.y() > view_bot:
                        diff = item_br_browser.y() - view_bot
                        scrollbar.setValue(scrollbar.value() + diff)
        
        # 2. Internal View Scrolling (e.g. within a large grid)
        from PyQt6.QtWidgets import QAbstractItemView
        view.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

        # IMPORTANT: We no longer use setCurrentIndex or selectionModel here.
        # This prevents interference with Bulk Selection mode.
        view.setProperty("keyboard_cursor_index", index)
        self._refresh_cursor_flags()

    def _refresh_cursor_flags(self):
        for view in self._iter_views():
            is_active = self._cursor_active and view is self._current_view
            
            # Update the 'active' flag property
            if view.property("keyboard_cursor_active") != is_active:
                view.setProperty("keyboard_cursor_active", is_active)
            
            # Ensure index property is valid if active, or cleared if not
            if not is_active:
                view.setProperty("keyboard_cursor_index", QModelIndex())
                
            view.viewport().update()

    def _iter_views(self) -> list[QListView]:
        result = []
        seen = set()
        if hasattr(self.browser, "get_keyboard_nav_views"):
            for view in self.browser.get_keyboard_nav_views() or []:
                if not isinstance(view, QListView): continue
                if id(view) in seen: continue
                seen.add(id(view))
                result.append(view)
        return result

    def _ordered_visible_views(self) -> list[QListView]:
        views = [view for view in self._iter_views() if view.isVisible()]
        # stationary coordinate sorting - use viewport as it's the actual container
        def sort_key(v: QListView):
            p = v.viewport().mapTo(self.browser, QPoint(0,0))
            return (p.y(), p.x())
        
        views.sort(key=sort_key)
        return views

    def _preferred_view(self) -> Optional[QListView]:
        if self._current_view and self._current_view.isVisible():
            return self._current_view
        views = self._ordered_visible_views()
        return views[0] if views else None

    def _visible_candidates(self, log_blocks: bool = False) -> list[_Candidate]:
        candidates = []
        for view in self._iter_views():
            candidates.extend(self._visible_candidates_for_view(view, log_blocks=log_blocks))
        return candidates

    def _is_fully_visible_in_view(self, view: QListView, rect: QRect, label: str = "Unknown", log_blocks: bool = False) -> bool:
        # Heuristic margin roughly matching section header height to prevent 'teleporting' 
        # when a grid is partially clipped by the top header.
        GRACE_MARGIN = 40
        viewport = view.viewport()
        if not viewport.rect().contains(rect): return False

        scrollbar = None
        if hasattr(self.browser, "get_keyboard_nav_scrollbar"):
            scrollbar = self.browser.get_keyboard_nav_scrollbar()
            
        if scrollbar:
            scroll_area = scrollbar.parent()
            if isinstance(scroll_area, QAbstractScrollArea):
                sv_viewport = scroll_area.viewport()
                if sv_viewport and sv_viewport is not viewport:
                    # Robust Browser-Relative Coordination
                    item_tl = viewport.mapTo(self.browser, rect.topLeft())
                    item_br = viewport.mapTo(self.browser, rect.bottomRight())
                    item_browser_rect = QRect(item_tl, item_br)
                    
                    sv_tl = sv_viewport.mapTo(self.browser, QPoint(0, 0))
                    sv_br = sv_viewport.mapTo(self.browser, QPoint(sv_viewport.width(), sv_viewport.height()))
                    sv_browser_rect = QRect(sv_tl, sv_br)
                    
                    # Allow clipping so we don't skip rows that are mostly visible.
                    is_contained = sv_browser_rect.adjusted(-1, -GRACE_MARGIN, 1, GRACE_MARGIN).contains(item_browser_rect)
                    if not is_contained and log_blocks:
                        logger.debug(f"Blocked '{label}': Item at browser {item_browser_rect} is outside physical viewport {sv_browser_rect}")
                    return is_contained

        # Final browser widget check with grace margin
        item_tl = viewport.mapTo(self.browser, rect.topLeft())
        item_br = viewport.mapTo(self.browser, rect.bottomRight())
        item_browser_rect = QRect(item_tl, item_br)
        is_visible = self.browser.rect().adjusted(-1, -GRACE_MARGIN, 1, GRACE_MARGIN).contains(item_browser_rect)
        if not is_visible and log_blocks:
            logger.debug(f"Blocked '{label}': Item {item_browser_rect} outside browser window {self.browser.rect()}")
        return is_visible

    def _visible_candidates_for_view(self, view: QListView, log_blocks: bool = False) -> list[_Candidate]:
        model = view.model()
        if not view.isVisible() or not model or model.rowCount() == 0: return []
        viewport = view.viewport()
        visible = viewport.rect()

        scrollbar = None
        if hasattr(self.browser, "get_keyboard_nav_scrollbar"):
            scrollbar = self.browser.get_keyboard_nav_scrollbar()
            
        if scrollbar:
            scroll_area = scrollbar.parent()
            if isinstance(scroll_area, QAbstractScrollArea):
                sv_viewport = scroll_area.viewport()
                if sv_viewport:
                    # Clip viewport by browser-relative coordination
                    v_tl = viewport.mapTo(self.browser, QPoint(0, 0))
                    v_browser_rect = QRect(v_tl, viewport.size())
                    
                    sv_tl = sv_viewport.mapTo(self.browser, QPoint(0, 0))
                    sv_br = sv_viewport.mapTo(self.browser, QPoint(sv_viewport.width(), sv_viewport.height()))
                    sv_browser_rect = QRect(sv_tl, sv_br)
                    
                    intersected_browser = v_browser_rect.intersected(sv_browser_rect)
                    if intersected_browser.isEmpty(): return []
                        
                    local_tl = viewport.mapFrom(self.browser, intersected_browser.topLeft())
                    visible = QRect(local_tl, intersected_browser.size())

        if self._is_ribbon(view):
            row_range = self._estimate_visible_ribbon_rows(view, visible)
        else:
            row_range = self._estimate_visible_grid_rows(view, visible)

        out = []
        for row in row_range:
            if 0 <= row < model.rowCount():
                idx = model.index(row, 0)
                rect = view.visualRect(idx)
                if not rect.isEmpty():
                    label = idx.data(Qt.ItemDataRole.DisplayRole) or "Unknown"
                    if self._is_fully_visible_in_view(view, rect, label, log_blocks=log_blocks):
                        out.append(_Candidate(view, idx, rect))
        return out

    def _estimate_visible_ribbon_rows(self, view: QListView, visible: QRect) -> range:
        model = view.model()
        y = max(4, visible.height() // 2) + visible.top()
        first = view.indexAt(QPoint(visible.left() + 4, y))
        last = view.indexAt(QPoint(visible.right() - 8, y))
        start = first.row() if first.isValid() else 0
        end = last.row() if last.isValid() else min(model.rowCount() - 1, start + 12)
        return range(start, end + 1)

    def _estimate_visible_grid_rows(self, view: QListView, visible: QRect) -> range:
        model = view.model()
        if not model or model.rowCount() == 0: return range(0,0)
        
        # 1. Detect Stride (Columns) and Item Height dynamically
        cols = 1
        item_h = view.iconSize().height() + (view.spacing() * 2)
        
        idx0 = model.index(0, 0)
        rect0 = view.visualRect(idx0)
        if not rect0.isEmpty():
            item_h = rect0.height() + view.spacing()
            y0 = rect0.y()
            # Look for where the row ends
            for i in range(1, min(model.rowCount(), 40)):
                if view.visualRect(model.index(i, 0)).y() > y0 + 10:
                    cols = i
                    break
            else:
                # If no y-jump found, all items might be on one row
                if model.rowCount() > 0:
                    cols = model.rowCount()
        
        if item_h <= 0:
            # Fallback to standard medium card height (no progress bar in grids)
            item_h = UIConstants.get_card_height(True, reserve_progress_space=False, card_size="medium")
        
        # 2. Map physical viewport boundaries to model rows
        # We look at the top-left and bottom-right of the physical visible rect.
        # If the view is scrolling itself, visible.top() is likely 0, but we need
        # the row at the physical top of the widget. indexAt() uses viewport coordinates.
        idx_top = view.indexAt(visible.topLeft() + QPoint(4, 4))
        idx_bot = view.indexAt(visible.bottomRight() - QPoint(4, 4))
        
        # Determine the physical Y offset of items in the model
        # If the view IS the scroll area, the viewport's top-left (0,0) corresponds 
        # to the model's Y = verticalScrollBar().value()
        model_y_offset = 0
        if not view.parent() or not isinstance(view.parent(), QAbstractScrollArea):
             # This view handles its own scrolling
             model_y_offset = view.verticalScrollBar().value()

        if idx_top.isValid():
            start_row = idx_top.row() // cols
        else:
            # Fallback using model-relative math
            start_row = max(0, (visible.top() + model_y_offset) // item_h)

        if idx_bot.isValid():
            end_row = idx_bot.row() // cols
        else:
            end_row = start_row + (visible.height() // item_h) + 1

        start_idx = max(0, int(start_row * cols))
        end_idx = min(model.rowCount() - 1, int((end_row + 1) * cols))
        
        logger.debug(f"View {id(view)} | Cols: {cols} | ItemH: {item_h} | ModelY: {model_y_offset} | Visible Rows: {start_row}-{end_row} | Range: {start_idx}-{end_idx}")
        return range(start_idx, end_idx + 1)

    def _is_ribbon(self, view: QListView) -> bool:
        if view.property("is_ribbon"): return True
        return (view.flow() == QListView.Flow.LeftToRight and not view.isWrapping() and view.viewMode() == QListView.ViewMode.IconMode)
