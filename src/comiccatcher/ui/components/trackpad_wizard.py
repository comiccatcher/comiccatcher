from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QPushButton, QProgressBar
from PyQt6.QtCore import Qt, QEvent, QTimer, QPropertyAnimation
from PyQt6.QtGui import QColor
import time

from ..theme_manager import ThemeManager, UIConstants

class EventCaptureFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        theme = ThemeManager.get_current_theme_colors()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme['card_bg']};
                border: {UIConstants.scale(2)}px dashed {theme['brand_primary']};
                border-radius: {UIConstants.scale(10)}px;
            }}
        """)
        self.setMinimumHeight(UIConstants.scale(200))
        self.setMinimumWidth(UIConstants.scale(400))

class TrackpadWizardDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Trackpad Setup Wizard")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setMinimumSize(UIConstants.scale(500), UIConstants.scale(450))

        # State tracking
        self.saw_momentum = False
        self.saw_end = False
        self.saw_update = False
        self.saw_no_phase = False
        self.is_done = False
        self.awaiting_feedback = False
        
        self.recorded_events = [] # (time, dx, dy, phase)
        
        # Debounce timer for mechanical wheels that don't send ScrollEnd
        self.eval_timer = QTimer(self)
        self.eval_timer.setSingleShot(True)
        self.eval_timer.timeout.connect(self._evaluate_and_apply)

        self._setup_ui()
        QTimer.singleShot(0, self.reapply_theme)
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(UIConstants.scale(20), UIConstants.scale(20), UIConstants.scale(20), UIConstants.scale(20))
        layout.setSpacing(UIConstants.scale(15))

        self.title_label = QLabel("Trackpad Calibration Wizard")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.instructions_label = QLabel("Please perform a quick <b>2-finger swipe</b> (left or right) inside the dashed box and lift your fingers.")
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.capture_frame = EventCaptureFrame(self)
        self.capture_frame.installEventFilter(self)
        
        self.capture_layout = QVBoxLayout(self.capture_frame)
        
        self.status_label = QLabel("Waiting for swipe...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.capture_layout.addWidget(self.status_label)
        
        self.meter_bar = QProgressBar()
        self.meter_bar.setTextVisible(False)
        self.meter_bar.setFixedHeight(UIConstants.scale(10))
        self.meter_bar.setRange(0, 100)
        self.meter_bar.setValue(0)
        self.capture_layout.addWidget(self.meter_bar)
        
        self.meter_anim = QPropertyAnimation(self.meter_bar, b"value")
        self.meter_anim.setDuration(200)
        self.meter_anim.setEndValue(0)

        layout.addWidget(self.title_label)
        layout.addWidget(self.instructions_label)
        layout.addWidget(self.capture_frame)
        
        self.try_again_btn = QPushButton("Try Again")
        self.try_again_btn.clicked.connect(self._reset_wizard)
        self.try_again_btn.hide()
        
        self.close_btn = QPushButton("Cancel")
        self.close_btn.clicked.connect(self.reject)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.try_again_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _reset_wizard(self):
        self.saw_momentum = False
        self.saw_end = False
        self.saw_update = False
        self.saw_no_phase = False
        self.is_done = False
        self.awaiting_feedback = False
        self.recorded_events.clear()
        
        self.status_label.setText("Waiting for swipe...")
        self.status_label.setStyleSheet("")
        self.instructions_label.setText("Please perform a quick <b>2-finger swipe</b> (left or right) inside the dashed box and lift your fingers.")
        
        self.close_btn.setText("Cancel")
        self.try_again_btn.hide()
            
        theme = ThemeManager.get_current_theme_colors()
        self.capture_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {theme['card_bg']};
                border: {UIConstants.scale(2)}px dashed {theme['brand_primary']};
                border-radius: {UIConstants.scale(10)}px;
            }}
        """)
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme['bg_main']};
            }}
            QLabel {{
                color: {theme['content_primary']};
                font-size: {UIConstants.scale(14)}px;
            }}
            QPushButton {{
                background-color: {theme['card_bg']};
                color: {theme['content_primary']};
                border: 1px solid {theme['card_border']};
                border-radius: {UIConstants.scale(4)}px;
                padding: {UIConstants.scale(6)}px {UIConstants.scale(16)}px;
            }}
            QPushButton:hover {{
                background-color: {theme['bg_item_hover']};
            }}
            QProgressBar {{
                border: 1px solid {theme['card_border']};
                border-radius: {UIConstants.scale(5)}px;
                background-color: {theme['bg_main']};
            }}
            QProgressBar::chunk {{
                background-color: {theme['status_success']};
                border-radius: {UIConstants.scale(4)}px;
            }}
        """)
        self.title_label.setStyleSheet(f"color: {theme['content_primary']}; font-size: {UIConstants.scale(18)}px; font-weight: bold;")
        
        if self.awaiting_feedback:
            self.status_label.setStyleSheet(f"color: {theme['brand_primary']}; font-size: {UIConstants.scale(16)}px; font-weight: bold;")
        elif self.is_done:
            self.status_label.setStyleSheet(f"color: {theme['status_success']}; font-size: {UIConstants.scale(14)}px;")

    def eventFilter(self, obj, event):
        if self.is_done or self.awaiting_feedback:
            return super().eventFilter(obj, event)
            
        if obj is self.capture_frame and event.type() == QEvent.Type.Wheel:
            phase = event.phase()
            
            dx = event.pixelDelta().x() if not event.pixelDelta().isNull() else event.angleDelta().x()
            dy = event.pixelDelta().y() if not event.pixelDelta().isNull() else event.angleDelta().y()
            self.recorded_events.append((time.time(), dx, dy, phase))
            
            self.meter_anim.stop()
            self.meter_bar.setValue(100)
            self.meter_anim.start()
            
            if phase == Qt.ScrollPhase.ScrollMomentum:
                self.saw_momentum = True
            elif phase == Qt.ScrollPhase.ScrollUpdate:
                self.saw_update = True
                self.status_label.setText("Recording swipe...")
            elif phase == Qt.ScrollPhase.ScrollEnd:
                self.saw_end = True
            elif phase == Qt.ScrollPhase.NoScrollPhase:
                self.saw_no_phase = True
                self.status_label.setText("Recording emulation...")
                
            # Restart eval timer. After 800ms of silence, we evaluate.
            self.eval_timer.start(800)
            
            # If we get a definitive ScrollEnd, we evaluate sooner
            if self.saw_end:
                self.eval_timer.start(100)
                
            return True # Consume event to prevent scrolling behind dialog
            
        return super().eventFilter(obj, event)

    def _evaluate_and_apply(self):
        if self.is_done or self.awaiting_feedback or not (self.saw_update or self.saw_no_phase):
            return
            
        if self.saw_end or self.saw_momentum:
            # We have clean data, no need to ask user
            self._finalize_settings(self.saw_momentum, self.saw_end, False)
            return
            
        # We have NO clear ending. Ask user to confirm fake momentum.
        self.awaiting_feedback = True
        
        self.status_label.setText("Did the green meter continue to bounce<br>after you lifted your fingers?")
        self.reapply_theme()
        
        self.btn_layout = QHBoxLayout()
        self.yes_btn = QPushButton("Yes (Fake Momentum)")
        self.yes_btn.clicked.connect(lambda: self._handle_feedback(True))
        
        self.no_btn = QPushButton("No (Stopped Instantly)")
        self.no_btn.clicked.connect(lambda: self._handle_feedback(False))
        
        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)
        self.capture_layout.addLayout(self.btn_layout)
        
        self.reapply_theme()

    def _handle_feedback(self, has_fake_momentum):
        # Hide the question buttons
        for i in reversed(range(self.btn_layout.count())): 
            self.btn_layout.itemAt(i).widget().setParent(None)
        
        # If they had fake momentum, they need basic emulation to kill the bounce.
        # If they didn't have fake momentum but lacked a scroll end, they are still basically a generic wheel.
        # We'll consider both cases as basic emulation to be safe with edge bounce.
        self._finalize_settings(False, False, True, has_fake_momentum)

    def _finalize_settings(self, saw_momentum, saw_end, basic_emulation, fake_momentum=False):
        self.is_done = True
        self.awaiting_feedback = False
        theme = ThemeManager.get_current_theme_colors()
        
        momentum_enabled = False
        
        if saw_momentum:
            msg = "<b>Native Momentum Detected!</b><br><br>Your trackpad provides native physics.<br><br>"
            momentum_enabled = False
        elif saw_end:
            msg = "<b>Clean Gesture Detected!</b><br><br>We will simulate missing momentum.<br><br>"
            momentum_enabled = True
        else:
            msg = "<b>Basic Emulation Detected!</b><br><br>Your driver acts like a basic mechanical wheel.<br><br>"
            msg += "<i>NOTE: Certain features will be disabled for 2-finger trackpad actions.</i><br><br>"
            momentum_enabled = not fake_momentum
            
        settings_applied = (
            "<b>Applied Settings:</b><br>"
            f"• 2D Panning Momentum: {'<b>ON</b>' if momentum_enabled else 'OFF'}<br>"
            f"• Basic Emulation Mode: {'<b>ON</b>' if basic_emulation else 'OFF'}"
        )
        msg += settings_applied
            
        if self.config_manager:
            self.config_manager.set_reader_trackpad_momentum(momentum_enabled)
            self.config_manager.set_reader_trackpad_basic_emulation(basic_emulation)
            
        self.reapply_theme()
        self.status_label.setText(msg)
        self.instructions_label.setText("Calibration complete. You may close this window.")
        self.try_again_btn.show()
        self.close_btn.setText("Close")
        
        self.capture_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {theme['card_bg']};
                border: {UIConstants.scale(2)}px solid {theme['status_success']};
                border-radius: {UIConstants.scale(10)}px;
            }}
        """)
