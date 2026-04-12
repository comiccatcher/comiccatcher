from typing import Callable, Optional
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QPushButton, QGridLayout, QApplication
)
from PyQt6.QtCore import Qt, QPoint, QSize, QUrl, QRectF, QPointF
from PyQt6.QtGui import (
    QPixmap, QColor, QFontMetrics, QIcon, QDesktopServices, 
    QPainter, QPainterPath, QPolygonF, QBrush, QPen
)
from comiccatcher.ui.theme_manager import THEMES, UIConstants, ThemeManager
from comiccatcher.ui.utils import format_artist_credits
from comiccatcher.ui.components.popover_mixin import BubbleMixin
from comiccatcher.ui.components.loading_spinner import LoadingSpinner
from comiccatcher.logger import get_logger

logger = get_logger("ui.mini_detail_popover")

class MiniDetailPopover(QFrame, BubbleMixin):
    """
    A stylish popover showing comic metadata summary.
    Dynamically responds to global theme changes.
    Features a word-balloon 'tail' (arrow) pointing to the source item.
    """
    def __init__(self, parent=None, theme_name: Optional[str] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        s = UIConstants.scale
        # Margins for arrow and shadow
        self._margin = s(20)
        self.setFixedWidth(s(460) + self._margin * 2)
        self.setFixedHeight(s(340) + self._margin * 2)
        
        self.arrow_side: Optional[str] = None # "left", "right", "top", "bottom"
        self.arrow_pos: float = 0.5 # 0.0 to 1.0 along the side
        
        # Main container (layout holder)
        self.container = QFrame(self)
        self.container.setObjectName("popover_container")
        # Translucent container, painting handled by paintEvent
        self.container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self._margin, self._margin, self._margin, self._margin)
        main_layout.addWidget(self.container)
        
        self.content_layout = QHBoxLayout(self.container)
        self.content_layout.setContentsMargins(s(12), s(12), s(12), s(8))
        self.content_layout.setSpacing(s(20))
        
        self._base_width = s(460)
        self.DEFAULT_WIDTH = self._base_width + self._margin * 2
        self.NO_COVER_WIDTH = s(320) + self._margin * 2
        
        # Left: Cover
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(s(140), s(210))
        self.cover_label.setScaledContents(False)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignTop)
        
        # Right: Info
        self.info_area = QWidget()
        self.info_layout = QVBoxLayout(self.info_area)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(s(4))
        
        self.content_layout.addWidget(self.info_area, 1)
        
        # Bottom: Actions (Optional)
        self.actions_widget = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_widget)
        self.actions_layout.setContentsMargins(0, s(5), 0, 0)
        self.actions_layout.setSpacing(s(25))
        self.actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_layout.addWidget(self.actions_widget)
        self.actions_widget.hide()
        
        # Loading Indicator (Indeterminate spinner)
        # Use absolute positioning so it doesn't push down other widgets
        self.spinner = LoadingSpinner(self.container, size=s(24))
        
        self.reapply_theme()

    def set_loading(self, loading: bool):
        """Toggles the loading spinner."""
        if loading:
            self.spinner.start()
            self._position_spinner()
        else:
            self.spinner.stop()

    def _position_spinner(self):
        """Manually position the spinner in the top-right of the container."""
        if hasattr(self, 'spinner') and hasattr(self, 'container'):
            s = UIConstants.scale
            padding = s(10)
            self.spinner.move(
                self.container.width() - self.spinner.width() - padding,
                padding
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_spinner()

    def reapply_theme(self):
        """Standardized method to update styles when theme changes."""
        self.theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        if hasattr(self, 'spinner'):
            self.spinner.set_color(QColor(self.theme['accent']))
        
        # Stylesheet for internal widgets only. Container background handled in paintEvent.
        self.container.setStyleSheet(f"""
            QWidget {{ background-color: transparent; }}
            QLabel {{ color: {self.theme['text_main']}; }}
            QLabel#meta_label {{ font-size: {s(12)}px; color: {self.theme['text_dim']}; }}
            QLabel#section_title {{ font-weight: bold; font-size: {s(16)}px; color: {self.theme['text_main']}; }}
            QLabel#section_subtitle {{ font-style: italic; font-size: {s(14)}px; color: {self.theme['text_dim']}; }}
            QScrollArea {{ border: none; background-color: transparent; }}
            QScrollBar:vertical {{
                width: {max(2, s(4))}px;
                background: transparent;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {self.theme['border']};
                border-radius: {max(1, s(2))}px;
                min-height: {s(20)}px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        
        self.cover_label.setStyleSheet(f"border: {max(1, s(1))}px solid {self.theme['border']}; background: {self.theme['bg_main']}; border-radius: {s(4)}px;")
        
        for i in range(self.actions_layout.count()):
            item = self.actions_layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), QPushButton):
                btn = item.widget()
                icon_name = btn.property("icon_name")
                if icon_name:
                    btn.setIcon(ThemeManager.get_icon(icon_name, "accent"))
        
        self.update() # Trigger repaint for the bubble

    def paintEvent(self, event):
        painter = QPainter(self)
        self.paint_bubble(
            painter, 
            QRectF(self.rect()), 
            QRectF(self.container.geometry()), 
            self.theme, 
            self.arrow_side,
            self.arrow_pos
        )

    def set_show_cover(self, show: bool):
        self.cover_label.setVisible(show)
        if show:
            self.setFixedWidth(self.DEFAULT_WIDTH)
        else:
            self.setFixedWidth(self.NO_COVER_WIDTH)

    def add_action(self, icon_name: str, tooltip: str, on_click: Callable) -> QPushButton:
        self.actions_widget.show()
        if self.info_layout.indexOf(self.actions_widget) == -1:
            self.info_layout.addWidget(self.actions_widget)
            
        s = UIConstants.scale
        btn = QPushButton()
        btn.setProperty("icon_name", icon_name)
        btn.setIcon(ThemeManager.get_icon(icon_name, "accent"))
        btn.setToolTip(tooltip)
        btn.setFixedSize(s(32), s(32))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setObjectName("secondary_button")
        btn.setStyleSheet("padding: 0px;")
        
        btn.clicked.connect(lambda: [on_click(), self.hide()])
        self.actions_layout.addWidget(btn)
        return btn

    def set_cover_pixmap(self, pixmap: QPixmap):
        """Sets the cover pixmap, scaling it to fit while preserving aspect ratio."""
        if not pixmap or pixmap.isNull():
            self.cover_label.clear()
            self.cover_label.setText("No Cover")
            return

        scaled = pixmap.scaled(
            self.cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.cover_label.setPixmap(scaled)

    def clear_actions(self):
        while self.actions_layout.count():
            item = self.actions_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.actions_widget.hide()

    def populate(self, cover: QPixmap = None, data: dict = {}, title: str = None, subtitle: str = None):
        s = UIConstants.scale
        # 1. Temporarily remove actions_widget
        self.info_layout.removeWidget(self.actions_widget)
        
        # 2. Clear all other items in info_layout robustly
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Inline clear layout to avoid adding extra methods
                l = item.layout()
                while l.count():
                    si = l.takeAt(0)
                    if si.widget(): si.widget().deleteLater()
                l.deleteLater()
        
        # 3. Build Header Section
        web_data = data.get("web")
        urls = [u.strip() for u in web_data.split(",") if u.strip()] if web_data else []
        has_web = len(urls) > 0
        
        pub_parts = []
        if data.get("publisher"): pub_parts.append(data["publisher"])
        if data.get("published"): pub_parts.append(data["published"])
        has_pub = len(pub_parts) > 0

        if title or subtitle or has_pub or has_web:
            header_widget = QWidget()
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(s(10))
            
            # Left: Text Stack
            text_stack = QVBoxLayout()
            text_stack.setContentsMargins(0, 0, 0, 0)
            text_stack.setSpacing(s(2))
            
            if title:
                t_label = QLabel(title)
                t_label.setObjectName("section_title")
                t_label.setWordWrap(True)
                text_stack.addWidget(t_label)
            
            if subtitle:
                s_label = QLabel(subtitle)
                s_label.setObjectName("section_subtitle")
                s_label.setWordWrap(True)
                text_stack.addWidget(s_label)
                
            if has_pub:
                p_label = QLabel(" • ".join(pub_parts))
                p_label.setStyleSheet(f"font-size: {s(12)}px; color: {self.theme['text_dim']}; margin-top: {s(1)}px;")
                text_stack.addWidget(p_label)
                
            header_layout.addLayout(text_stack, 1)
            
            # Right: Web Button
            if has_web:
                target_url = urls[0]
                logger.debug(f"MiniDetailPopover: Rendering web link button for: {target_url}")
                btn_web = QPushButton()
                btn_web.setObjectName("icon_button")
                btn_web.setIcon(ThemeManager.get_icon("globe", "accent"))
                btn_web.setToolTip(f"Open in browser: {target_url}")
                btn_web.setFixedSize(s(24), s(24))
                btn_web.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(target_url)))
                header_layout.addWidget(btn_web, 0, Qt.AlignmentFlag.AlignTop)
                
            self.info_layout.addWidget(header_widget)

        if cover and not cover.isNull():
            self.set_cover_pixmap(cover)
        else:
            self.cover_label.clear()
            self.cover_label.setText("No Cover")
            
        # Divider
        self.info_layout.addSpacing(4)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {self.theme['border']}; min-height: 1px; max-height: 1px; border: none;")
        self.info_layout.addWidget(line)
        self.info_layout.addSpacing(4)

        # Body Scroll Area (Unified for Credits and Summary)
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setStyleSheet("background: transparent; border: none;")
        
        body_container = QWidget()
        body_layout = QVBoxLayout(body_container)
        body_layout.setContentsMargins(0, 0, s(8), 0)
        body_layout.setSpacing(s(12))

        # Credits
        if data.get("credits"):
            credits_widget = QWidget()
            credits_grid = QGridLayout(credits_widget)
            credits_grid.setContentsMargins(0, 0, 0, 0)
            credits_grid.setSpacing(s(4))
            credits_grid.setColumnStretch(1, 1)
            
            # Parse into dict for format_artist_credits helper
            roles_dict = {}
            lines = data["credits"].split("\n")
            for line in lines:
                if ":" in line:
                    role, names = line.split(":", 1)
                    roles_dict[role.strip()] = names.strip()
            
            # Use helper to group roles (Artist/Penciller/etc) and filter
            final_creds = format_artist_credits(roles_dict)
            
            for row_idx, cred_line in enumerate(final_creds):
                if ":" in cred_line:
                    role, names = cred_line.split(":", 1)
                    r_label = QLabel(role.strip() + ":")
                    r_label.setObjectName("meta_label")
                    r_label.setStyleSheet(f"font-weight: bold; color: {self.theme['text_dim']};")
                    n_label = QLabel(names.strip())
                    n_label.setObjectName("meta_label")
                    n_label.setWordWrap(True)
                    credits_grid.addWidget(r_label, row_idx, 0, Qt.AlignmentFlag.AlignTop)
                    credits_grid.addWidget(n_label, row_idx, 1, Qt.AlignmentFlag.AlignTop)
            
            body_layout.addWidget(credits_widget)
            
        # Summary
        summary_text = data.get("summary")
        if summary_text:
            summary_label = QLabel(summary_text)
            summary_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; line-height: 1.4;")
            summary_label.setWordWrap(True)
            summary_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            body_layout.addWidget(summary_label)
        
        body_layout.addStretch()
        body_scroll.setWidget(body_container)
        self.info_layout.addWidget(body_scroll, 1)

        self.info_layout.addWidget(self.actions_widget)

    def show_at(self, pos: QPoint, arrow_side: Optional[str] = None, arrow_pos: float = 0.5):
        self.arrow_side = arrow_side
        self.arrow_pos = arrow_pos
        self.reapply_theme()
        
        # Adjust position based on arrow side to ensure tip is at 'pos'
        # The widget is (base_width + margin*2) wide. 
        # The bubble rect starts at 'margin'.
        s = UIConstants.scale
        tip_offset = s(15) # arrow_w
        
        final_pos = QPoint(pos)
        if arrow_side == "left":
            final_pos.setX(pos.x() + tip_offset)
            final_pos.setY(pos.y() - int(self.height() * arrow_pos))
        elif arrow_side == "right":
            final_pos.setX(pos.x() - self.width() - tip_offset)
            final_pos.setY(pos.y() - int(self.height() * arrow_pos))
        elif arrow_side == "top":
            final_pos.setX(pos.x() - int(self.width() * arrow_pos))
            final_pos.setY(pos.y() + tip_offset)
        elif arrow_side == "bottom":
            final_pos.setX(pos.x() - int(self.width() * arrow_pos))
            final_pos.setY(pos.y() - self.height() - tip_offset)
            
        self.move(final_pos)
        self.show()
