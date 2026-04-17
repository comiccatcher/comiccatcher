# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from PyQt6.QtWidgets import QLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize, QPoint, QRect

class FlowLayout(QLayout):
    """A layout that wraps items to the next line when space is exhausted."""
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.items = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.items):
            return self.items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        margin = self.contentsMargins().left()
        size += QSize(2 * margin, 2 * margin)
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        
        line_data = [] # List of (item, x) for current line

        for item in self.items:
            wid = item.widget()
            space_x = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Horizontal)
            space_y = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Vertical)
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x > rect.right() and line_height > 0:
                # Commit current line with vertical centering
                if not test_only:
                    for li, lx in line_data:
                        # Center vertically within line_height
                        offset_y = (line_height - li.sizeHint().height()) // 2
                        li.setGeometry(QRect(QPoint(lx, y + offset_y), li.sizeHint()))
                
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
                line_data = []

            line_data.append((item, x))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        # Commit last line
        if not test_only:
            for li, lx in line_data:
                offset_y = (line_height - li.sizeHint().height()) // 2
                li.setGeometry(QRect(QPoint(lx, y + offset_y), li.sizeHint()))

        return y + line_height - rect.y()
