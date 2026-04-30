# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from typing import Set, Tuple, Optional, Callable, List
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QListView, QWidget, QPushButton, QApplication
from comiccatcher.models.feed_page import FeedItem
from comiccatcher.ui.components.help_popover import BrowserHelpPopover

class HelpPopoverMixin:
    """
    Standardized help popover logic for all views.
    Provides methods to build and toggle the 'H' help screen.
    """
    def init_help_popover(self):
        self.help_popover = BrowserHelpPopover(self)

    def toggle_help_popover(self):
        if not hasattr(self, 'help_popover'):
            self.init_help_popover()

        if self.help_popover.isVisible():
            self.help_popover.hide()
            return
        
        self.help_popover.rebuild(
            self.get_help_popover_title(),
            self.get_help_popover_sections(),
        )
        
        # Center relative to the main window's global coordinates
        win = self.window()
        target_rect = win.frameGeometry() if win else self.rect()
        self.help_popover.show_at_center(target_rect)

    def get_help_popover_title(self) -> str:
        return "Controls"

    def get_help_popover_sections(self) -> List[Tuple[str, List[Tuple[str, str]]]]:
        return self.get_common_help_sections()

    def get_common_help_sections(self) -> List[Tuple[str, List[Tuple[str, str]]]]:
        """Returns shortcuts that are applicable globally across most views."""
        sections = [
            ("GLOBAL NAVIGATION", [
                ("Ctrl + F", "Jump to Feeds list"),
                ("Ctrl + L", "Jump to Library"),
                ("Ctrl + +/-", "Adjust UI scaling"),
                ("Ctrl + 0", "Reset UI scaling"),
                ("F11 / F", "Toggle fullscreen"),
                ("Esc", "Go back"),
                ("F5", "Refresh current view"),
                ("Ctrl + Q", "Quit application"),
            ]),
            ("HELP", [
                ("H / Ctrl + H", "Toggle this help popover"),
            ])
        ]
        return sections

    def get_keyboard_nav_focus_objects(self):
        return []

class SectionControlMixin:
    """
    Standardized keyboard controls for sections.
    Provides logic for toggle-all, toggle-active, and follow-link.
    """
    def toggle_all_sections(self):
        """Toggles the collapsed state of all sections based on the state of the first one."""
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        # Only find sections that are currently visible to the user
        sections = [s for s in self.findChildren(CollapsibleSection) if s.isVisible()]
        if not sections: return
        
        # Decide next state based on the first visible section
        next_state = not sections[0]._is_collapsed
        for section in sections:
            section.set_collapsed(next_state)

    def toggle_active_section(self, active_view: QWidget):
        """Finds the section (CollapsibleSection or SectionHeader) owning the active_view and toggles it."""
        if not active_view: return
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        from comiccatcher.ui.components.section_header import SectionHeader
        
        # Walk up from the view to find its section container
        parent = active_view.parent()
        while parent:
            if isinstance(parent, (CollapsibleSection, SectionHeader)):
                parent.toggle()
                return
            parent = parent.parent()

    def follow_active_section_link(self, active_view: QWidget):
        """Finds the section owning the active_view and clicks its action button (e.g., See All)."""
        if not active_view: return
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        from comiccatcher.ui.components.section_header import SectionHeader
        
        parent = active_view.parent()
        while parent:
            if isinstance(parent, (CollapsibleSection, SectionHeader)):
                if hasattr(parent, "action_widget") and isinstance(parent.action_widget, QPushButton):
                    if parent.action_widget.isEnabled():
                        parent.action_widget.click()
                return
            parent = parent.parent()

class ViewportHelper:
    """
    Shared utilities for viewport visibility detection and resource fetching.
    Consolidates logic used by FeedBrowser, FeedDetailView, and others.
    """

    @staticmethod
    def get_visible_range(view: QListView, buffer: int = 0) -> Tuple[int, int]:
        """
        Calculates the range of visible row indices (first, last) in a QListView.
        Robust against margins and gutters by checking multiple probe points
        and adding a small safety buffer.
        """
        from comiccatcher.ui.theme_manager import UIConstants
        if not view or not view.isVisible():
            return 0, -1
            
        vp = view.viewport()
        if not vp:
            return 0, -1
            
        rect = vp.rect()
        w = rect.width()
        h = rect.height()
        
        # 1. Detect First Visible Item
        # Check top-left and top-center
        fi = view.indexAt(QPoint(UIConstants.VIEWPORT_MARGIN, UIConstants.VIEWPORT_MARGIN))
        if not fi.isValid():
            fi = view.indexAt(QPoint(w // 2, UIConstants.VIEWPORT_MARGIN))
            
        # 2. Detect Last Visible Item
        # Check bottom-right, bottom-center, and bottom-left
        li = view.indexAt(QPoint(w - UIConstants.VIEWPORT_MARGIN, h - UIConstants.VIEWPORT_MARGIN))
        if not li.isValid():
            li = view.indexAt(QPoint(w // 2, h - UIConstants.VIEWPORT_MARGIN))
        if not li.isValid():
            li = view.indexAt(QPoint(UIConstants.VIEWPORT_MARGIN, h - UIConstants.VIEWPORT_MARGIN))
        
        model = view.model()
        row_count = model.rowCount() if model else 0
        if row_count == 0:
            return 0, -1

        first = fi.row() if fi.isValid() else 0
        
        if li.isValid():
            last = li.row()
        else:
            # Fallback estimation: use viewport height and scroll position
            # We assume a standard card height if we can't detect one
            from comiccatcher.ui.theme_manager import UIConstants
            # Use unscaled BASE_CARD_HEIGHT as a safe minimum if scaling isn't init'd
            card_h = UIConstants.get_card_height(True) or 300 
            
            inner_scroll = view.verticalScrollBar().value()
            # Estimate row based on scroll
            first_est = max(0, (inner_scroll // card_h) * 2) # conservative 2 cols
            visible_rows = (h // card_h) + 2 # +2 rows for safety
            last = min(row_count - 1, first_est + (visible_rows * 10)) # very safe 10 cols

        # 3. Add safety buffer (usually 1 row) to prevent cancellation flickering
        # We assume 2-10 columns, so +10 is a safe "one row" buffer
        first = max(0, first - 5)
        last = min(row_count - 1, last + 10)
            
        if buffer > 0:
            first = max(0, first - buffer)
            last = min(row_count - 1, last + buffer)
            
        return first, last

    @staticmethod
    def get_visible_urls(view: QListView) -> Set[str]:
        """Returns a set of all cover URLs currently visible in the view's viewport."""
        urls = set()
        if not view or not view.isVisible():
            return urls
            
        model = view.model()
        if not model:
            return urls
            
        first, last = ViewportHelper.get_visible_range(view)
        if last < 0:
            return urls
            
        for row in range(first, last + 1):
            item = model.get_item(row)
            if isinstance(item, FeedItem) and item.cover_url:
                urls.add(item.cover_url)
        return urls

    @staticmethod
    async def fetch_cover_async(
        url: str, 
        image_manager, 
        pending_set: Set[str], 
        on_done_callback: Optional[Callable] = None,
        max_dim: int = 400,
        timeout: Optional[float] = None
    ):
        """
        Asynchronously fetches a cover thumbnail via ImageManager.
        Manages a 'pending_set' to prevent redundant concurrent requests.
        """
        if not url or url in pending_set:
            return
            
        pending_set.add(url)
        try:
            await image_manager.get_image_b64(url, max_dim=max_dim, timeout=timeout)
        except Exception:
            # Failures are logged by ImageManager
            pass
        finally:
            pending_set.discard(url)
            
        if on_done_callback:
            on_done_callback()

    @staticmethod
    def position_popover(popover, view, index_or_item):
        """
        Calculates and applies the optimal bubble position for a popover anchored to a list item.
        Handles screen boundary detection and arrow side selection.
        Supports both QListView (index) and QListWidget (item).
        """
        from PyQt6.QtWidgets import QApplication, QListWidget
        from PyQt6.QtCore import QPoint
        
        if not view:
            return
            
        # 1. Get item global rect
        if isinstance(view, QListWidget):
            item_rect = view.visualItemRect(index_or_item)
        else:
            item_rect = view.visualRect(index_or_item)
            
        global_item_topleft = view.viewport().mapToGlobal(item_rect.topLeft())

        # 2. Default: Show to the right of the card, centered vertically
        pop_x = global_item_topleft.x() + item_rect.width()
        pop_y = global_item_topleft.y() + item_rect.height() // 2
        arrow_side = "left"

        # 3. Screen boundary check
        screen = QApplication.primaryScreen().availableGeometry()
        if pop_x + popover.width() > screen.right():
            # Show to the left instead
            pop_x = global_item_topleft.x()
            arrow_side = "right"

        popover.show_at(QPoint(pop_x, pop_y), arrow_side=arrow_side)

    @staticmethod
    def enrich_popover_for_item(popover, item, last_loaded_url: Optional[str] = None):
        """
        Standardizes the metadata population for a MiniDetailPopover from a FeedItem.
        Ensures consistent presentation (no thumbnail) and field formatting.
        Also updates action button states (like Download) if last_loaded_url is provided.
        """
        if not item or not item.raw_pub:
            return

        from comiccatcher.ui.components.mini_detail_popover import format_opds_publication
        data = format_opds_publication(item.raw_pub)

        # Identify if this is a non-streamable OPDS 1.2 item
        is_opds12 = False
        if item.raw_pub.metadata and item.raw_pub.metadata.conformsTo:
            cf = item.raw_pub.metadata.conformsTo
            if isinstance(cf, str) and cf == "opds1_2": is_opds12 = True
            elif isinstance(cf, list) and "opds1_2" in cf: is_opds12 = True
            
        if is_opds12 and not item.raw_pub.is_divina:
            note = "\n\n(Note: Page streaming not available for this item.)"
            if data.get("summary"):
                data["summary"] += note
            else:
                data["summary"] = note

        # Standards: No thumbnail in mini-details, use title/subtitle from formatted data
        popover.set_show_cover(False)
        popover.populate(
            data=data,
            title=data.get("title"),
            subtitle=data.get("subtitle")
        )

        # Update action button states (e.g. Download)
        if last_loaded_url:
            from comiccatcher.api.feed_reconciler import FeedReconciler
            download_url, _ = FeedReconciler._find_acquisition_link(item.raw_pub, last_loaded_url)
            
            # Find the download button in popover to update it
            from PyQt6.QtWidgets import QPushButton
            for i in range(popover.actions_layout.count()):
                btn = popover.actions_layout.itemAt(i).widget()
                if isinstance(btn, QPushButton) and btn.property("icon_name") == "download":
                    btn.setEnabled(download_url is not None)
                    break

    @staticmethod
    def trigger_manifest_enrichment(popover, item, opds_client, last_loaded_url: Optional[str], active_load_id_getter: Callable[[], str]):
        """
        Detects if an item has a JSON manifest and triggers an async enrichment fetch.
        Updates the popover metadata once fetched, ensuring loading states are managed.
        """
        from urllib.parse import urljoin
        import uuid
        
        pub = item.raw_pub
        manifest_url = None
        for link in (pub.links or []):
            if link.type in ["application/webpub+json", "application/divina+json", "application/opds-publication+json"]:
                manifest_url = link.href
                break

        if manifest_url and last_loaded_url:
            load_id = str(uuid.uuid4())
            # We assume the caller manages the 'active' load ID to prevent race conditions
            # on the shared popover widget.
            full_url = urljoin(last_loaded_url, manifest_url)
            popover.set_loading(True)
            
            async def _do_enrich():
                try:
                    full_pub = await opds_client.get_publication(full_url)
                    
                    # Verify we are still looking at the same request
                    try:
                        if load_id != active_load_id_getter() or not popover:
                            return
                    except (RuntimeError, AttributeError):
                        return 

                    # Stop loading indicator
                    try:
                        popover.set_loading(False)
                    except (RuntimeError, AttributeError):
                        pass

                    # Merge logic (preserving descriptions/bytes if better in original)
                    if not full_pub.images and pub.images: full_pub.images = pub.images
                    if full_pub.metadata and pub.metadata:
                        if not full_pub.metadata.description and pub.metadata.description: 
                            full_pub.metadata.description = pub.metadata.description
                        if not full_pub.metadata.numberOfBytes and pub.metadata.numberOfBytes:
                            full_pub.metadata.numberOfBytes = pub.metadata.numberOfBytes
                    
                    # Update item with enriched data
                    item.raw_pub = full_pub
                    
                    # Refresh Popover UI (with button state update)
                    ViewportHelper.enrich_popover_for_item(popover, item, last_loaded_url)
                    
                except Exception as e:
                    from comiccatcher.logger import get_logger
                    get_logger("ui.view_helpers").debug(f"Manifest enrichment failed for {full_url}: {e}")
                    try:
                        popover.set_loading(False)
                    except (RuntimeError, AttributeError):
                        pass
            
            asyncio.create_task(_do_enrich())
            return load_id
        else:
            popover.set_loading(False)
            return None
