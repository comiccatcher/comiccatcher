import sys
from enum import Enum
from PyQt6.QtWidgets import QApplication, QListView, QStyledItemDelegate, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QSize, QAbstractListModel, QModelIndex, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont

class ItemType(Enum):
    HEADER = 1
    CARD = 2

class MockItem:
    def __init__(self, type, title, section_id=None):
        self.type = type
        self.title = title
        self.section_id = section_id

class VirtualDashboardModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._all_items = [] 
        self._logical_items = [] 
        self._collapsed_sections = set()
        
        # Build 10 sections with 2000 items each to prove bypass of 32k limit
        for s in range(10):
            sid = f"sec_{s}"
            self._all_items.append(MockItem(ItemType.HEADER, f"Section {s + 1} (2000 Items - Click to Toggle)", sid))
            for i in range(2000):
                self._all_items.append(MockItem(ItemType.CARD, f"Item {s}.{i}", sid))
        
        self._rebuild_map()

    def _rebuild_map(self):
        self.beginResetModel()
        self._logical_items = []
        for item in self._all_items:
            if item.type == ItemType.HEADER:
                self._logical_items.append(item)
            elif item.section_id not in self._collapsed_sections:
                self._logical_items.append(item)
        self.endResetModel()

    def toggle_section(self, section_id):
        if section_id in self._collapsed_sections:
            self._collapsed_sections.discard(section_id)
        else:
            self._collapsed_sections.add(section_id)
        self._rebuild_map()

    def rowCount(self, parent=QModelIndex()):
        return len(self._logical_items)

    def data(self, index, role):
        if not index.isValid(): return None
        item = self._logical_items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.title
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

class VirtualDashboardDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.card_w = 150
        self.card_h = 200
        self.header_h = 50

    def sizeHint(self, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        # Force full width for headers to create a "row break"
        vp_width = self.view.viewport().width()
        
        if item.type == ItemType.HEADER:
            return QSize(vp_width - 20, self.header_h)
        return QSize(self.card_w, self.card_h)

    def paint(self, painter, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if item.type == ItemType.HEADER:
            self._draw_header(painter, option, item)
        else:
            self._draw_card(painter, option, item)
        
        painter.restore()

    def _draw_header(self, painter, option, item):
        rect = option.rect
        painter.fillRect(rect, QColor("#f8f9fa"))
        painter.setPen(QColor("#dee2e6"))
        painter.drawRect(rect)
        
        is_collapsed = item.section_id in self.view.model()._collapsed_sections
        chevron = "▶" if is_collapsed else "▼"
        
        painter.setPen(QColor("#007bff"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(rect.adjusted(15, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{chevron}  {item.title}")

    def _draw_card(self, painter, option, item):
        rect = option.rect.adjusted(5, 5, -5, -5)
        painter.setPen(QColor("#e9ecef"))
        painter.setBrush(QColor("white"))
        painter.drawRoundedRect(rect, 10, 10)
        
        painter.setPen(QColor("#495057"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, item.title)

class ProtoView(QListView):
    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSpacing(10)
        
        self.model_obj = VirtualDashboardModel()
        self.setModel(self.model_obj)
        self.delegate = VirtualDashboardDelegate(self)
        self.setItemDelegate(self.delegate)
        
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        if item.type == ItemType.HEADER:
            self.model_obj.toggle_section(item.section_id)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    view = ProtoView()
    view.setWindowTitle("Virtualized Dashboard Prototype (20k+ Items)")
    view.resize(1000, 800)
    view.show()
    sys.exit(app.exec())
