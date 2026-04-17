# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Optional
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPolygonF, QPen, QBrush
from comiccatcher.ui.theme_manager import UIConstants

class BubbleMixin:
    """
    A mixin that provides shared logic for painting word-balloon / bubble 
    popovers with a configurable 'tail' (arrow).
    """
    def paint_bubble(self, painter: QPainter, widget_rect: QRectF, container_rect: QRectF, theme: dict, 
                     arrow_side: Optional[str] = None, arrow_pos: float = 0.5):
        """
        Paints the bubble silhouette, shadow, and border.
        - widget_rect: The total geometry of the widget (including margins for shadow/tail).
        - container_rect: The geometry of the inner content box.
        - theme: Current theme dictionary.
        - arrow_side: "left", "right", "top", "bottom" or None.
        - arrow_pos: 0.0 to 1.0 along the specified side.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        s = UIConstants.scale
        bg_color = QColor(theme['bg_header'])
        border_color = QColor(theme['accent'])
        pen_width = max(1, s(1.5))
        radius = s(12)
        
        # 1. Define the bubble path
        path = QPainterPath()
        path.addRoundedRect(container_rect, radius, radius)
        
        if arrow_side:
            arrow_w = s(15)    # tip length
            arrow_base = s(30) # base width
            
            tri = QPolygonF()
            if arrow_side == "right":
                y = container_rect.top() + container_rect.height() * arrow_pos
                y = max(container_rect.top() + radius + arrow_base/2, min(container_rect.bottom() - radius - arrow_base/2, y))
                tri.append(QPointF(container_rect.right(), y - arrow_base/2))
                tri.append(QPointF(container_rect.right() + arrow_w, y))
                tri.append(QPointF(container_rect.right(), y + arrow_base/2))
            elif arrow_side == "left":
                y = container_rect.top() + container_rect.height() * arrow_pos
                y = max(container_rect.top() + radius + arrow_base/2, min(container_rect.bottom() - radius - arrow_base/2, y))
                tri.append(QPointF(container_rect.left(), y - arrow_base/2))
                tri.append(QPointF(container_rect.left() - arrow_w, y))
                tri.append(QPointF(container_rect.left(), y + arrow_base/2))
            elif arrow_side == "bottom":
                x = container_rect.left() + container_rect.width() * arrow_pos
                x = max(container_rect.left() + radius + arrow_base/2, min(container_rect.right() - radius - arrow_base/2, x))
                tri.append(QPointF(x - arrow_base/2, container_rect.bottom()))
                tri.append(QPointF(x, container_rect.bottom() + arrow_w))
                tri.append(QPointF(x + arrow_base/2, container_rect.bottom()))
            elif arrow_side == "top":
                x = container_rect.left() + container_rect.width() * arrow_pos
                x = max(container_rect.left() + radius + arrow_base/2, min(container_rect.right() - radius - arrow_base/2, x))
                tri.append(QPointF(x - arrow_base/2, container_rect.top()))
                tri.append(QPointF(x, container_rect.top() - arrow_w))
                tri.append(QPointF(x + arrow_base/2, container_rect.top()))
            
            path.addPolygon(tri)
            path = path.simplified()
            
        # 2. Draw Shadow (Simple feathered path approach)
        painter.save()
        painter.translate(s(2), s(2))
        for i in range(5, 0, -1):
            alpha = 40 // i
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawPath(path)
        painter.restore()
        
        # 3. Draw Fill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawPath(path)
        
        # 4. Draw Border
        pen = QPen(border_color)
        pen.setWidthF(pen_width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
