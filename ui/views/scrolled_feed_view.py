"""
ScrolledFeedView: section-level virtual scroll, no QScrollArea size-limit issues.

Architecture
------------
A QAbstractScrollArea (_impl) provides a properly-clipping viewport.  Each
FeedSection is a pair of real widgets (SectionHeader + content) that are children
of _impl.viewport() and repositioned on every scroll event.  No giant content
widget is created, so the 16 M-pixel QWidget limit cannot be hit.

Large GRID sections (up to 30 k items) use a QListView whose *widget* height
equals only the visible viewport slice; its internal verticalScrollBar is synced
to the outer scroll position, preserving full QListView item-level virtualization.

All page-fetching, debounced-scroll, and thumbnail-loading logic from the
original implementation is preserved unchanged.
"""

import asyncio
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QFrame, QListView, QWidget,
)

from api.feed_reconciler import FeedReconciler
from logger import get_logger
from models.feed_page import FeedItem, FeedPage, FeedSection, ItemType, SectionLayout
from ui.components.base_ribbon import BaseCardRibbon
from ui.components.feed_browser_model import FeedBrowserModel
from ui.components.feed_card_delegate import FeedCardDelegate
from ui.components.section_header import SectionHeader
from ui.theme_manager import UIConstants
from ui.views.base_feed_subview import BaseFeedSubView

logger = get_logger("ui.scrolled_feed_view")


@dataclass
class _SectionDesc:
    """Precomputed virtual geometry for one section."""
    section: FeedSection
    y: int = 0          # virtual top (cumulative sum of previous section heights)
    header_h: int = 0
    content_h: int = 0  # 0 when collapsed

    @property
    def total_h(self) -> int:
        """Total vertical footprint of this section, including bottom margins."""
        h = self.header_h + self.content_h
        # Mirror CollapsibleSection / QVBoxLayout behavior:
        # 1. Internal bottom margin of the section
        h += UIConstants.SECTION_MARGIN_BOTTOM
        # 2. Outer spacing between sections in the main layout
        h += UIConstants.SECTION_SPACING
        return h

    is_grid: bool = False   # set by render() based on _main_grid_sid, not section.layout


class _ScrollImpl(QAbstractScrollArea):
    """Thin QAbstractScrollArea whose sole purpose is providing a clipping viewport."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        # Layout is driven by scrollbar's valueChanged; nothing to do here.
        pass


class ScrolledFeedView(BaseFeedSubView):
    """
    Virtual-scroll feed view for large, infinite-scroll feeds.

    Each FeedSection is a real pair of widgets (header + ribbon or grid) rather
    than rows inside a composite QListView.  The outer scroll is managed by a
    QAbstractScrollArea; only GRID section items are virtualized via QListView.
    """

    status_updated = pyqtSignal(str)
    busy_updated = pyqtSignal(bool)
    cover_request_needed = pyqtSignal(str)

    # ------------------------------------------------------------------ init --

    def __init__(self, opds_client, image_manager, collapsed_sections: Set[str], parent=None):
        super().__init__(image_manager, collapsed_sections, parent)
        self.opds_client = opds_client

        # Scrollable container — viewport() is a properly-clipping QWidget
        self._impl = _ScrollImpl(self)
        self._vp   = self._impl.viewport()
        self._vp.setMouseTracking(True)
        self._sb   = self._impl.verticalScrollBar()
        self._sb.setSingleStep(UIConstants.scale(20))
        self._sb.valueChanged.connect(self._on_scroll)

        # Virtual layout state
        self._scroll_offset: int = 0
        self._total_height:  int = 0
        self._descs: List[_SectionDesc] = []

        # Per-section widget pools (children of _vp)
        self._headers: Dict[str, SectionHeader]   = {}
        self._ribbons: Dict[str, BaseCardRibbon]  = {}
        self._grids:   Dict[str, QListView]        = {}
        self._models:  Dict[str, FeedBrowserModel] = {}

        # Page-fetching state
        self._current_context_id: float = 0
        self._pagination_template: Optional[str] = None
        self._is_offset_based: bool = False
        self._items_per_page:  int  = UIConstants.ITEMS_PER_PAGE
        self._active_sparse_tasks: Dict[str, asyncio.Task] = {}
        self._pending_page_requests: List[int] = []
        self._main_grid_sid: Optional[str] = None

        # Timers
        self._status_timer = QTimer()
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(UIConstants.STATUS_UPDATE_MS)
        self._status_timer.timeout.connect(self._do_update_status)

        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(UIConstants.SCROLL_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._update_status)

        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(UIConstants.RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._on_resize_settled)

    # ---------------------------------------------------------------- public --

    def render(self, page: FeedPage, template: Optional[str], is_offset: bool, ctx_id: float, target_offset: Optional[int] = None):
        self._current_context_id = ctx_id
        self._pagination_template = template
        self._is_offset_based     = is_offset
        self._cancel_tasks()
        self.busy_updated.emit(False)
        self._pending_page_requests.clear()

        # Identify the main (large / sparse) section
        main = None
        for s in page.sections:
            if (s.total_items or 0) > UIConstants.LARGE_SECTION_THRESHOLD or len(s.items) > UIConstants.LARGE_SECTION_THRESHOLD:
                main = s
                break
        if not main and page.sections:
            grids = [s for s in page.sections
                     if getattr(s, 'layout', None) == SectionLayout.GRID]
            main = max(grids, key=lambda s: len(s.items)) if grids else page.sections[-1]

        self._main_grid_sid  = main.section_id if main else None
        self._items_per_page = (main.items_per_page or 100) if main else 100

        self._clear_section_widgets()
        self._build_section_widgets(page.sections)
        self._recompute_positions()
        self._update_scrollbar()

        # Reset or restore scroll
        new_offset = target_offset if target_offset is not None else 0
        # Sanity check: if the new content is much shorter than the old offset, reset to 1
        if new_offset > self._total_height - self._vp.height():
            new_offset = 0

        self._sb.blockSignals(True)
        self._sb.setValue(new_offset)
        self._sb.blockSignals(False)
        self._scroll_offset = new_offset
        self._update_layout()

        # Seed first page of the main grid
        if main:
            m = self._models.get(self._main_grid_sid)
            if m:
                m.set_items_for_page(main.current_page, main.items)

        self._update_status()

    def set_show_labels(self, show: bool):
        self._show_labels = show
        for ribbon in self._ribbons.values():
            if hasattr(ribbon, 'show_labels'):
                ribbon.show_labels = show
            ribbon.viewport().update()
            ribbon.doItemsLayout()
        for view in self._grids.values():
            d = view.itemDelegate()
            if hasattr(d, 'show_labels'):
                d.show_labels = show
            view.viewport().update()
            view.doItemsLayout()
        self._recompute_positions()
        self._update_scrollbar()
        self._update_layout()

    def expand_all(self):
        for desc in self._descs:
            sid = desc.section.section_id
            self._collapsed_sections.discard(sid)
            hdr = self._headers.get(sid)
            if hdr:
                hdr.blockSignals(True)
                hdr.set_collapsed(False)
                hdr.blockSignals(False)
        self._recompute_positions()
        self._update_scrollbar()
        self._update_layout()

    def collapse_all(self):
        for desc in self._descs:
            sid = desc.section.section_id
            self._collapsed_sections.add(sid)
            hdr = self._headers.get(sid)
            if hdr:
                hdr.blockSignals(True)
                hdr.set_collapsed(True)
                hdr.blockSignals(False)
        self._recompute_positions()
        self._update_scrollbar()
        self._update_layout()

    # ---------------------------------------------------------- layout / scroll

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._impl.setGeometry(0, 0, self.width(), self.height())
        self._resize_timer.start()

    def _on_resize_settled(self):
        self._recompute_positions()
        self._update_scrollbar()
        self._update_layout()
        QTimer.singleShot(50, self._calibrate_grid_heights)
        self._update_status()

    def _on_scroll(self, value: int):
        self._scroll_offset = value
        self._update_layout()
        if not self._debounce_timer.isActive():
            self._debounce_timer.start()

    def _recompute_positions(self):
        vp_w     = max(1, self._vp.width())
        header_h = UIConstants.SECTION_HEADER_HEIGHT
        y = 0
        for desc in self._descs:
            desc.y        = y
            desc.header_h = header_h
            if desc.section.section_id in self._collapsed_sections:
                desc.content_h = 0
            elif desc.is_grid:
                cols, row_h, sp = self.get_grid_layout_info(vp_w)
                total = desc.section.total_items or len(desc.section.items)
                if total == 0:
                    desc.content_h = 0
                else:
                    # NOTE: Grid content doesn't need its own trailing gutter here
                    # because SECTION_MARGIN_BOTTOM handles it.
                    desc.content_h = math.ceil(total / cols) * row_h
            else:
                desc.content_h = self.get_ribbon_height()
            y += desc.total_h
        self._total_height = y

    def _update_scrollbar(self):
        vp_h = self._vp.height()
        self._sb.setRange(0, max(0, self._total_height - vp_h))
        self._sb.setPageStep(vp_h)

    def _update_layout(self):
        off  = self._scroll_offset
        vp_h = self._vp.height()
        vp_w = self._vp.width()

        for desc in self._descs:
            sid      = desc.section.section_id
            sec_top  = desc.y - off
            sec_bot  = sec_top + desc.total_h

            # Entirely out of viewport
            if sec_bot <= 0 or sec_top >= vp_h:
                for pool in (self._headers, self._ribbons, self._grids):
                    if sid in pool:
                        pool[sid].hide()
                continue

            # Header
            hdr = self._headers.get(sid)
            if hdr:
                hdr.setGeometry(0, sec_top, vp_w, desc.header_h)
                hdr.show()

            collapsed = sid in self._collapsed_sections
            if collapsed or desc.content_h == 0:
                for pool in (self._ribbons, self._grids):
                    if sid in pool:
                        pool[sid].hide()
                continue

            content_top = sec_top + desc.header_h

            if desc.is_grid:
                view = self._grids.get(sid)
                if view:
                    # Clip grid widget to the visible slice of the viewport
                    widget_top = max(0, content_top)
                    widget_bot = min(vp_h, sec_bot)
                    widget_h   = widget_bot - widget_top
                    if widget_h <= 0:
                        view.hide()
                        continue
                    view.setGeometry(0, widget_top, vp_w, widget_h)
                    view.show()
                    # Sync inner scroll: how far into the grid content are we?
                    inner = max(0, off - desc.y - desc.header_h)
                    sb = view.verticalScrollBar()
                    if sb.value() != inner:
                        sb.setValue(inner)
            else:
                ribbon = self._ribbons.get(sid)
                if ribbon:
                    ribbon.setGeometry(0, content_top, vp_w, desc.content_h)
                    ribbon.show()

    def _calibrate_grid_heights(self):
        """
        After the grid views have performed their first real layout, read the
        actual content heights from their scroll ranges and update if needed.
        Only applicable when content exceeds the visible slice (sb.maximum() > 0).
        """
        changed = False
        for desc in self._descs:
            if not desc.is_grid or desc.content_h == 0:
                continue
            view = self._grids.get(desc.section.section_id)
            if not view or not view.isVisible():
                continue
            view.doItemsLayout()
            sb     = view.verticalScrollBar()
            actual = sb.maximum() + view.viewport().height()
            # Only trust the calibrated value when content exceeds the viewport
            if sb.maximum() > 0 and actual != desc.content_h:
                desc.content_h = actual
                changed = True
        if changed:
            y = 0
            for desc in self._descs:
                desc.y  = y
                y      += desc.total_h
            self._total_height = y
            self._update_scrollbar()
            self._update_layout()

    # ---------------------------------------------------- widget construction --

    def _build_section_widgets(self, sections: List[FeedSection]):
        header_h = UIConstants.TOGGLE_BUTTON_SIZE + UIConstants.SECTION_HEADER_MARGIN_TOP

        # Locate parent FeedBrowser
        browser = self.parent()
        while browser and not hasattr(browser, 'create_action_button'):
            browser = browser.parent()
        
        on_ctx = getattr(browser, '_show_header_context_menu', None) if browser else None

        for sec in sections:
            sid     = sec.section_id
            is_grid = (sid == self._main_grid_sid)

            action_widget = None
            if getattr(sec, 'self_url', None) and browser:
                btn_all = browser.create_action_button(
                    "See All",
                    lambda _, u=sec.self_url, t=sec.title: self.navigate_requested.emit(u, t, False)
                )
                action_widget = btn_all

            hdr = SectionHeader(
                title=sec.title,
                action_widget=action_widget,
                is_collapsed=sid in self._collapsed_sections,
                on_context_menu=on_ctx,
                parent=self._vp,
            )
            hdr.toggled.connect(
                lambda is_col, _sid=sid: self._on_header_toggled(_sid, is_col))
            hdr.hide()
            self._headers[sid] = hdr

            if is_grid:
                self._grids[sid] = self._make_grid_view(sec)
            else:
                self._ribbons[sid] = self._make_ribbon(sec)

            self._descs.append(_SectionDesc(section=sec, header_h=header_h, is_grid=is_grid))

    def _make_grid_view(self, sec: FeedSection) -> QListView:
        s    = UIConstants.scale
        view = QListView(self._vp)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setUniformItemSizes(False)
        view.setSpacing(s(10))
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setContentsMargins(0, 0, 0, 0)
        view.viewport().setContentsMargins(0, 0, 0, 0)
        view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        view.setMouseTracking(True)
        # Outer scroll controls vertical movement; suppress the internal bar
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Intercept wheel events so they drive the outer scrollbar
        view.viewport().installEventFilter(self)

        model = FeedBrowserModel(items_per_page=sec.items_per_page or 100)
        # Single-section init: no HEADER composite row, just GRID_ITEM rows
        model.set_sections([sec], main_grid_section_id=sec.section_id)
        model.page_request_needed.connect(self._on_page_needed)
        model.cover_request_needed.connect(self.cover_request_needed.emit)

        delegate = FeedCardDelegate(view, self.image_manager, show_labels=self._show_labels)
        view.setModel(model)
        view.setItemDelegate(delegate)
        view.clicked.connect(lambda idx, m=model: self._on_grid_clicked(idx, m))
        view.hide()

        self._models[sec.section_id] = model
        return view

    def _make_ribbon(self, sec: FeedSection) -> BaseCardRibbon:
        ribbon = BaseCardRibbon(self._vp, show_labels=self._show_labels)
        rmodel = FeedBrowserModel(items_per_page=max(1, len(sec.items)))
        rmodel.set_items_for_page(1, sec.items)
        ribbon.setModel(rmodel)
        ribbon.setItemDelegate(
            FeedCardDelegate(ribbon, self.image_manager, self._show_labels))
        ribbon.clicked.connect(
            lambda idx, m=rmodel: self._on_ribbon_clicked(idx, m))
        ribbon.hide()
        return ribbon

    def _clear_section_widgets(self):
        for pool in (self._headers, self._ribbons, self._grids):
            for w in pool.values():
                w.deleteLater()
            pool.clear()
        self._models.clear()
        self._descs.clear()

    # ----------------------------------------------------------- event handling

    def eventFilter(self, source, event):
        """Forward vertical wheel events from grid viewports to the outer scrollbar."""
        for view in self._grids.values():
            if source is view.viewport():
                t = event.type()
                if t == QEvent.Type.Wheel:
                    dy = event.angleDelta().y()
                    if dy != 0:
                        step = UIConstants.scale(20)
                        self._sb.setValue(self._scroll_offset - (dy * step) // 120)
                        return True
                elif t == QEvent.Type.MouseMove:
                    index = view.indexAt(event.pos())
                    view.setCursor(
                        Qt.CursorShape.PointingHandCursor if index.isValid()
                        else Qt.CursorShape.ArrowCursor)
                break
        return super().eventFilter(source, event)

    def _on_header_toggled(self, sid: str, is_collapsed: bool):
        if is_collapsed:
            self._collapsed_sections.add(sid)
        else:
            self._collapsed_sections.discard(sid)
        self._recompute_positions()
        self._update_scrollbar()
        self._update_layout()

    def _on_grid_clicked(self, index, model: FeedBrowserModel):
        item = model.get_item(index.row())
        if item and item.type != ItemType.EMPTY:
            self.item_clicked.emit(item, self.gather_context_pubs(model))

    def _on_ribbon_clicked(self, index, model: FeedBrowserModel):
        item = model.get_item(index.row())
        if item:
            self.item_clicked.emit(item, self.gather_context_pubs(model))

    # -------------------------------------------------------- fetch / status --

    def _update_status(self):
        if not self._status_timer.isActive():
            self._status_timer.start()

    def _do_update_status(self):
        if not self.isVisible():
            return
            
        self._ensure_covers_for_grid()
        self._handle_fetching()
        
        model = self._models.get(self._main_grid_sid)
        view  = self._grids.get(self._main_grid_sid)
        if model and view and view.isVisible():
            total = model.rowCount()
            if total > 0:
                vp_w = view.viewport().width()
                vp_h = view.viewport().height()
                
                # 1. Try to find the first visible index using multiple points 
                # to avoid hitting margins/gutters
                fi = view.indexAt(QPoint(UIConstants.VIEWPORT_MARGIN, UIConstants.VIEWPORT_MARGIN))
                if not fi.isValid():
                    fi = view.indexAt(QPoint(UIConstants.VIEWPORT_MARGIN * 2, UIConstants.VIEWPORT_MARGIN * 2))
                
                cols, row_h, sp = self.get_grid_layout_info(vp_w)

                if fi.isValid():
                    first = fi.row()
                else:
                    # Fallback: estimate based on scroll position
                    inner = view.verticalScrollBar().value()
                    first = max(0, (inner // row_h) * cols)

                # 2. Try to find the last visible index
                li = view.indexAt(QPoint(vp_w - UIConstants.VIEWPORT_MARGIN, vp_h - UIConstants.VIEWPORT_MARGIN))
                if not li.isValid():
                    li = view.indexAt(QPoint(vp_w // 2, vp_h - UIConstants.GRID_GUTTER))
                
                if li.isValid():
                    last = li.row()
                else:
                    # Fallback: estimate based on viewport height
                    visible_rows = math.ceil(vp_h / row_h)
                    last = min(total - 1, first + (visible_rows * cols))
                
                ipp = self._items_per_page
                first_p = (first // ipp) + 1
                last_p = (last // ipp) + 1
                total_p = math.ceil(total / ipp)
                
                pending = len(self._pending_page_requests)
                active = len(self._active_sparse_tasks)
                
                status = f"Items {first + 1}–{last + 1} of {total} | Pages {first_p}–{last_p} of {total_p}"
                if pending > 0 or active > 0:
                    status += f" [Pending: {pending}, Active: {active}]"
                
                self.status_updated.emit(status)

    def _ensure_covers_for_grid(self):
        view  = self._grids.get(self._main_grid_sid)
        model = self._models.get(self._main_grid_sid)
        if not view or not model or not view.isVisible():
            return
        vp    = view.viewport()
        fi    = view.indexAt(QPoint(10, 10))
        li    = view.indexAt(QPoint(vp.width() - 10, vp.height() - 10))
        first = fi.row() if fi.isValid() else 0
        last  = (li.row() if li.isValid()
                 else min(model.rowCount() - 1, first + 50))
        for row in range(first, last + 1):
            item = model.get_item(row)
            if isinstance(item, FeedItem) and item.cover_url:
                self.cover_request_needed.emit(item.cover_url)

    def _handle_fetching(self):
        if not self._pagination_template:
            return
        view  = self._grids.get(self._main_grid_sid)
        model = self._models.get(self._main_grid_sid)
        if not view or not model or not view.isVisible():
            return
        vp    = view.viewport()
        fi    = view.indexAt(QPoint(10, 10))
        li    = view.indexAt(QPoint(vp.width() - 10, vp.height() - 10))
        first = fi.row() if fi.isValid() else 0
        last  = (li.row() if li.isValid()
                 else min(model.rowCount() - 1, first + 50))

        ipp     = self._items_per_page
        b       = UIConstants.SPARSE_FETCH_BUFFER
        first_p = first // ipp + 1
        last_p  = last  // ipp + 1
        visible = set(range(max(1, first_p - b), last_p + b + 1))

        to_cancel = [k for k in self._active_sparse_tasks
                     if int(k.split('_')[1]) not in visible]
        for k in to_cancel:
            self._active_sparse_tasks.pop(k).cancel()
        
        if to_cancel:
            self.busy_updated.emit(len(self._active_sparse_tasks) > 0)

        if self._pending_page_requests:
            to_fetch = [p for p in reversed(self._pending_page_requests)
                        if p in visible][:UIConstants.MAX_CONCURRENT_FETCHES]
            self._pending_page_requests.clear()
            for p in to_fetch:
                val = (p - 1) * ipp if self._is_offset_based else p
                url = self._pagination_template.replace("{page}", str(val))
                key = f"{self._current_context_id}_{p}"
                if key not in self._active_sparse_tasks:
                    task = asyncio.create_task(
                        self._fetch_page(p, url, self._current_context_id))
                    self._active_sparse_tasks[key] = task
                    self.busy_updated.emit(True)
                    task.add_done_callback(
                        lambda t, k=key: self._on_task_done(t, k))

    async def _fetch_page(self, page_idx: int, url: str, ctx_id: float):
        try:
            feed = await self.opds_client.get_feed(url)
            if ctx_id != self._current_context_id:
                return
            page = FeedReconciler.reconcile(feed, url)
            main = (max(page.sections, key=lambda s: len(s.items))
                    if page.sections else None)
            if main:
                model = self._models.get(self._main_grid_sid)
                if model:
                    model.set_items_for_page(page_idx, main.items)
        except Exception as e:
            logger.error(f"Fetch failed: {e}")

    def _on_task_done(self, task, key):
        self._active_sparse_tasks.pop(key, None)
        self.busy_updated.emit(len(self._active_sparse_tasks) > 0)
        self._update_status()

    def _on_page_needed(self, page_idx: int):
        if page_idx not in self._pending_page_requests:
            self._pending_page_requests.append(page_idx)
        self._update_status()
        self._debounce_timer.start()

    def _cancel_tasks(self):
        for t in self._active_sparse_tasks.values():
            t.cancel()
        self._active_sparse_tasks.clear()
