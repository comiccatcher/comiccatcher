import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar, QApplication, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QSize
from api.download_manager import DownloadManager, DownloadTask

class DownloadTaskWidget(QFrame):
    def __init__(self, task: DownloadTask, on_cancel, on_remove):
        super().__init__()
        self.task_id = task.book_id
        self.on_cancel = on_cancel
        self.on_remove = on_remove
        
        self.setObjectName("download_task")
        self.setStyleSheet("""
            QFrame#download_task {
                background-color: rgba(128, 128, 128, 20); 
                border: 1px solid rgba(128, 128, 128, 30);
                border-radius: 4px; 
                margin-bottom: 2px;
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(4)
        
        # Title and Close/Cancel Button
        header = QHBoxLayout()
        self.title_label = QLabel(task.title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12px; border: none;")
        self.title_label.setWordWrap(True)
        
        self.btn_action = QPushButton()
        self.btn_action.setFixedSize(20, 20)
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet("QPushButton { border: none; background: transparent; }")
        
        header.addWidget(self.title_label, 1)
        header.addWidget(self.btn_action)
        self.layout.addLayout(header)
        
        # Status and Progress
        status_row = QHBoxLayout()
        self.status_label = QLabel(task.status)
        self.status_label.setStyleSheet("font-size: 10px; border: none;")
        
        self.pct_label = QLabel("0%")
        self.pct_label.setStyleSheet("font-size: 10px; font-weight: bold; border: none;")
        
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_row.addWidget(self.pct_label)
        self.layout.addLayout(status_row)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        self.update_ui(task)

    def update_ui(self, task: DownloadTask):
        self.status_label.setText(task.status)
        self.progress_bar.setValue(int(task.progress * 100))
        self.pct_label.setText(f"{int(task.progress * 100)}%")
        
        if task.status == "Downloading" or task.status == "Pending":
            self.btn_action.setText("×") # Cancel
            self.btn_action.setToolTip("Cancel Download")
            try: self.btn_action.clicked.disconnect()
            except: pass
            self.btn_action.clicked.connect(lambda: self.on_cancel(task.book_id))
        else:
            self.btn_action.setText("×") # Remove from list
            self.btn_action.setToolTip("Remove from list")
            try: self.btn_action.clicked.disconnect()
            except: pass
            self.btn_action.clicked.connect(lambda: self.on_remove(task.book_id))
            
            if task.status == "Completed":
                self.progress_bar.setStyleSheet("""
                    QProgressBar { height: 4px; border: none; background-color: rgba(128,128,128,20); border-radius: 2px; }
                    QProgressBar::chunk { background-color: #4caf50; border-radius: 2px; }
                """)
            elif task.status == "Failed" or task.status == "Cancelled":
                self.progress_bar.setStyleSheet("""
                    QProgressBar { height: 4px; border: none; background-color: rgba(128,128,128,20); border-radius: 2px; }
                    QProgressBar::chunk { background-color: #f44336; border-radius: 2px; }
                """)

class DownloadsView(QWidget):
    refresh_needed = pyqtSignal()

    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self.dm = download_manager
        self.widgets = {} # book_id -> DownloadTaskWidget

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        
        self.header = QHBoxLayout()
        self.title = QLabel("Downloads")
        self.title.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.header.addWidget(self.title)
        self.header.addStretch()
        
        self.btn_clear = QPushButton("Clear Completed")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet("""
            QPushButton { background: transparent; font-size: 10px; border: 1px solid rgba(128, 128, 128, 50); padding: 2px 8px; border-radius: 4px; }
        """)
        self.btn_clear.clicked.connect(self._clear_finished)
        self.header.addWidget(self.btn_clear)
        self.layout.addLayout(self.header)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)
        
        self.empty_label = QLabel("No active downloads")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("empty_state_label")
        self.list_layout.addWidget(self.empty_label)

        self.refresh_needed.connect(self.do_refresh)
        if self.dm:
            self.dm.add_callback(self._on_dm_update)
            self.do_refresh()

    def _on_dm_update(self):
        self.refresh_needed.emit()

    def do_refresh(self):
        if not self.dm: return
        
        current_ids = set(self.dm.tasks.keys())
        
        # Remove widgets for deleted tasks
        for tid in list(self.widgets.keys()):
            if tid not in current_ids:
                w = self.widgets.pop(tid)
                self.list_layout.removeWidget(w)
                w.deleteLater()
                
        # Update or add widgets
        # We want newest on top, so we iterate reversed
        tasks_list = list(self.dm.tasks.values())
        tasks_list.sort(key=lambda t: t.book_id) # Consistent order for mapping
        
        for task in reversed(tasks_list):
            if task.book_id in self.widgets:
                self.widgets[task.book_id].update_ui(task)
            else:
                w = DownloadTaskWidget(task, self._cancel_task, self._remove_task)
                self.widgets[task.book_id] = w
                # Insert at top (after ensuring empty label is handled)
                self.list_layout.insertWidget(0, w)
        
        self.empty_label.setVisible(len(self.dm.tasks) == 0)

    def _cancel_task(self, book_id):
        if self.dm:
            self.dm.cancel_download(book_id)

    def _remove_task(self, book_id):
        if self.dm:
            self.dm.remove_task(book_id)

    def _clear_finished(self):
        if not self.dm: return
        to_remove = [tid for tid, task in self.dm.tasks.items() if task.status in ("Completed", "Failed", "Cancelled")]
        for tid in to_remove:
            self.dm.remove_task(tid)
