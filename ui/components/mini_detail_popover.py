from typing import Callable
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QGraphicsDropShadowEffect, QPushButton
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap, QColor
from ui.theme_manager import THEMES, UIConstants, ThemeManager
from ui.utils import format_artist_credits

class MiniDetailPopover(QFrame):
    """
    A stylish popover showing comic metadata summary.
    Themeable but pinned to "light" by default.
    """
    def __init__(self, parent=None, theme_name="light"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        s = UIConstants.scale
        self.setFixedWidth(s(460))
        self.setFixedHeight(s(340))
        
        theme = THEMES.get(theme_name, THEMES["light"])
        
        # Main container with theme background and rounded corners
        self.container = QFrame(self)
        self.container.setObjectName("popover_container")
        self.container.setStyleSheet(f"""
            QFrame#popover_container {{
                background-color: {theme['bg_header']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(12)}px;
            }}
            QWidget {{ 
                background-color: transparent; 
            }}
            QLabel {{ 
                color: {theme['text_main']}; 
            }}
            QLabel#meta_label {{ font-size: {s(12)}px; color: {theme['text_dim']}; }}
            QLabel#section_title {{ font-weight: bold; font-size: {s(16)}px; color: {theme['text_main']}; }}
            QLabel#section_subtitle {{ font-style: italic; font-size: {s(14)}px; color: {theme['text_dim']}; }}
            QScrollArea {{ 
                border: none; 
                background-color: transparent; 
            }}
            QScrollArea > QWidget > QWidget {{ 
                background-color: transparent; 
            }}
        """)
        
        # Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(s(15))
        shadow.setXOffset(0)
        shadow.setYOffset(s(4))
        shadow.setColor(QColor(0, 0, 0, 80))
        self.container.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(s(5), s(5), s(5), s(5))
        main_layout.addWidget(self.container)
        
        self.content_layout = QHBoxLayout(self.container)
        self.content_layout.setContentsMargins(s(12), s(12), s(12), s(12))
        self.content_layout.setSpacing(s(20))
        
        self.DEFAULT_WIDTH = s(460)
        self.NO_COVER_WIDTH = s(320)
        
        # Left: Cover
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(s(140), s(210))
        self.cover_label.setScaledContents(True)
        # Use theme colors for cover placeholder
        self.cover_label.setStyleSheet(f"border: 1px solid {theme['border']}; background: {theme['bg_main']}; border-radius: 4px;")
        self.content_layout.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignVCenter)
        
        # Right: Info
        self.info_area = QWidget()
        self.info_layout = QVBoxLayout(self.info_area)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(4)
        
        self.content_layout.addWidget(self.info_area, 1)
        self.theme = theme # Store for later use in populate
        
        # Bottom: Actions (Optional)
        self.actions_widget = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_widget)
        s = UIConstants.scale
        self.actions_layout.setContentsMargins(0, s(5), 0, 0)
        self.actions_layout.setSpacing(s(25))
        self.actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_layout.addWidget(self.actions_widget)
        self.actions_widget.hide()

    def set_show_cover(self, show: bool):
        self.cover_label.setVisible(show)
        if show:
            self.setFixedWidth(self.DEFAULT_WIDTH)
        else:
            self.setFixedWidth(self.NO_COVER_WIDTH)

    def add_action(self, icon_name: str, tooltip: str, on_click: Callable):
        self.actions_widget.show()
        # Ensure it's in the info_layout if it was hidden
        if self.info_layout.indexOf(self.actions_widget) == -1:
            self.info_layout.addWidget(self.actions_widget)
            
        s = UIConstants.scale
        btn = QPushButton()
        btn.setIcon(ThemeManager.get_icon(icon_name))
        btn.setToolTip(tooltip)
        btn.setFixedSize(s(32), s(32))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Simple styling for popover buttons
        btn.setStyleSheet(f"""
            QPushButton {{ 
                background-color: {self.theme['bg_item_hover']}; 
                border: 1px solid {self.theme['border']};
                border-radius: 4px;
            }}
            QPushButton:hover {{ 
                background-color: {self.theme['bg_item_selected']}; 
                border-color: {self.theme['accent']};
            }}
        """)
        
        btn.clicked.connect(lambda: [on_click(), self.hide()])
        self.actions_layout.addWidget(btn)

    def clear_actions(self):
        while self.actions_layout.count():
            item = self.actions_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.actions_widget.hide()

    def populate(self, cover: QPixmap = None, data: dict = {}, title: str = None, subtitle: str = None):
        """
        data expected keys:
          - credits: str (joined writers/artists)
          - publisher: str
          - published: str (Month Year)
          - summary: str
        """
        # 1. Temporarily remove actions_widget so we can clear everything else
        self.info_layout.removeWidget(self.actions_widget)
        
        # 2. Clear all other items in info_layout
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            
        # 3. Build Info Top-Down
        # Title & Subtitle (Optional)
        if title:
            t_label = QLabel(title)
            t_label.setObjectName("section_title")
            t_label.setWordWrap(True)
            self.info_layout.addWidget(t_label)
            
            if subtitle:
                s_label = QLabel(subtitle)
                s_label.setObjectName("section_subtitle")
                s_label.setWordWrap(True)
                self.info_layout.addWidget(s_label)
        
        # Pub Info (Just below titles)
        pub_parts = []
        if data.get("publisher"): pub_parts.append(data["publisher"])
        if data.get("published"): pub_parts.append(data["published"])
        
        if pub_parts:
            p_label = QLabel(" • ".join(pub_parts))
            # Smaller font than Detail View for popover
            s = UIConstants.scale
            p_label.setStyleSheet(f"font-size: {s(12)}px; color: {self.theme['text_dim']}; margin-top: {s(1)}px;")
            self.info_layout.addWidget(p_label)

        # Cover (Left label, handled outside info_layout)
        if cover and not cover.isNull():
            self.cover_label.setPixmap(cover)
        else:
            self.cover_label.setText("No Cover")
            
        # Divider
        self.info_layout.addSpacing(4)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {self.theme['border']}; min-height: 1px; max-height: 1px; border: none;")
        self.info_layout.addWidget(line)
        self.info_layout.addSpacing(4)

        # Credits
        if data.get("credits"):
            # Internal Artist Grouping for the Popover
            lines = data["credits"].split("\n")
            roles = {}
            for line in lines:
                if ":" in line:
                    role, names = line.split(":", 1)
                    roles[role.strip()] = names.strip()
            
            final_creds = format_artist_credits(roles)

            c_label = QLabel("\n".join(final_creds))
            c_label.setObjectName("meta_label")
            c_label.setWordWrap(True)
            self.info_layout.addWidget(c_label)
            
        # Summary (Truncated/Scrollable)
        summary_text = data.get("summary")
        if summary_text:
            summary_container = QWidget()
            summary_layout = QVBoxLayout(summary_container)
            summary_layout.setContentsMargins(0, 0, 0, 0)
            summary_layout.setSpacing(2)
            
            # Use a stack to swap between teaser and full scroll
            from PyQt6.QtWidgets import QStackedWidget
            stack = QStackedWidget()
            summary_layout.addWidget(stack)
            
            # Page 0: Teaser (Fills remaining height)
            teaser_label = QLabel(summary_text)
            teaser_label.setStyleSheet(f"font-size: 12px; line-height: 1.4; color: {self.theme['text_main']};")
            teaser_label.setWordWrap(True)
            teaser_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            stack.addWidget(teaser_label)
            
            # Calculate Available Height for Teaser
            from PyQt6.QtGui import QFontMetrics
            metrics = QFontMetrics(teaser_label.font())
            avail_w = (self.width() if self.width() > 0 else self.NO_COVER_WIDTH) - 40
            if self.cover_label.isVisible():
                avail_w -= 160
                
            rect = metrics.boundingRect(0, 0, avail_w, 1000, 
                                      Qt.TextFlag.TextWordWrap, summary_text)
            
            # Dynamic height: 120px with actions, 180px without
            TEASER_HEIGHT = 120 if not self.actions_widget.isHidden() else 180
            teaser_label.setFixedHeight(TEASER_HEIGHT)
            
            needs_more = rect.height() > TEASER_HEIGHT + 10
            
            # Page 1: Full Scroll Area
            scroll = QScrollArea()
            scroll.setFixedHeight(TEASER_HEIGHT)
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("background-color: transparent; border: none;")
            scroll.viewport().setStyleSheet("background-color: transparent;")
            full_label = QLabel(summary_text)
            full_label.setStyleSheet(f"font-size: 12px; line-height: 1.4; color: {self.theme['text_main']}; background-color: transparent;")
            full_label.setWordWrap(True)
            full_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(full_label)
            stack.addWidget(scroll)
            
            if needs_more:
                btn_more = QPushButton("More...")
                btn_more.setFlat(True)
                btn_more.setFixedWidth(60)
                btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_more.setStyleSheet(f"color: {self.theme['accent']}; font-size: 11px; font-weight: bold; text-align: left; padding: 0;")
                
                def toggle_summary():
                    if stack.currentIndex() == 0:
                        stack.setCurrentIndex(1)
                        btn_more.setText("Less")
                    else:
                        stack.setCurrentIndex(0)
                        btn_more.setText("More...")
                
                btn_more.clicked.connect(toggle_summary)
                summary_layout.addWidget(btn_more)
            else:
                teaser_label.setFixedHeight(min(TEASER_HEIGHT, rect.height() + 5))
                stack.setCurrentIndex(0)
            
            self.info_layout.addWidget(summary_container, 1)
        else:
            self.info_layout.addStretch()

        # 4. ALWAYS re-add Actions at the very bottom
        self.info_layout.addWidget(self.actions_widget)

    def show_at(self, pos: QPoint):
        # Adjust if would go off-screen
        self.move(pos)
        self.show()
