import re

with open("comiccatcher/ui/views/feed_browser.py", "r") as f:
    text = f.read()

# 1. Line 320
text = text.replace("if view != self.grid_view:", "if not getattr(view, '_is_scrollable', False) and view.viewMode() == QListView.ViewMode.IconMode:")

# 2. Line 348
text = text.replace('self.grid_view.setStyleSheet(f"QListView {{ border: none; background-color: transparent; }}")', '')

# 3. Line 538
text = text.replace('self.stack.setCurrentWidget(self.grid_view)', 'self.stack.setCurrentWidget(self.hybrid_content)')

# 4. Line 539
text = text.replace('self.grid_view.verticalScrollBar().setValue(0)', 'if self._main_grid_view:\n                self._main_grid_view.verticalScrollBar().setValue(0)')

# 5. Line 616
text = text.replace('is_merged = (self.stack.currentWidget() == self.grid_view)', 'is_merged = (self.stack.currentWidget() == self.hybrid_content)')

# 6. Line 617
text = text.replace('vp_scroll = self.grid_view.viewport() if is_merged else self.dash_scroll.viewport()', 'vp_scroll = self._main_grid_view.viewport() if is_merged and self._main_grid_view else self.dash_scroll.viewport()')

# 7. Line 640
text = text.replace('first_row = (self.grid_view.verticalScrollBar().value() // item_h) * items_per_row', 'first_row = (self._main_grid_view.verticalScrollBar().value() // item_h) * items_per_row')

# 8. Line 641
text = text.replace('rows_visible = (self.grid_view.viewport().height() // item_h) + 1', 'rows_visible = (self._main_grid_view.viewport().height() // item_h) + 1')

# 9. Line 824
text = text.replace("offset = self._merged_main_offset if hasattr(self, '_merged_main_offset') and self.stack.currentWidget() == self.grid_view else 0", "offset = self._merged_main_offset if hasattr(self, '_merged_main_offset') and self.stack.currentWidget() == self.hybrid_content else 0")

# 10. Line 846
text = text.replace('self.grid_view.viewport().update()', '')

with open("comiccatcher/ui/views/feed_browser.py", "w") as f:
    f.write(text)
