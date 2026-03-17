import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from api.download_manager import DownloadManager, DownloadTask

class DownloadTaskWidget(QFrame):
    def __init__(self, task: DownloadTask, on_delete):
        super().__init__()
        self.task = task
        self.on_delete = on_delete
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #222; border-radius: 8px; margin-bottom: 5px;")
        
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        self.title_label = QLabel(task.title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        self.btn_delete = QPushButton("X")
        self.btn_delete.setFixedSize(24, 24)
        self.btn_delete.clicked.connect(lambda: self.on_delete(task.book_id))
        
        header.addWidget(self.title_label, 1)
        header.addWidget(self.btn_delete)
        layout.addLayout(header)
        
        self.status_label = QLabel(f"Status: {task.status}")
        self.status_label.setStyleSheet("font-size: 11px; color: #aaa;")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(task.progress * 100))
        layout.addWidget(self.progress_bar)
        
        if task.error:
            self.error_label = QLabel(task.error)
            self.error_label.setStyleSheet("color: #f44336; font-size: 10px;")
            layout.addWidget(self.error_label)

    def update_task(self, task: DownloadTask):
        self.task = task
        self.status_label.setText(f"Status: {task.status}")
        self.progress_bar.setValue(int(task.progress * 100))
        if task.status == "Completed":
            self.status_label.setStyleSheet("font-size: 11px; color: #4caf50;")
        elif task.status == "Failed":
            self.status_label.setStyleSheet("font-size: 11px; color: #f44336;")

class DownloadsView(QWidget):
    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self.dm = download_manager
        self.task_widgets = {} # book_id -> widget

        self.layout = QVBoxLayout(self)
        
        self.title = QLabel("Active Downloads")
        self.title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.layout.addWidget(self.title)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)
        
        if self.dm:
            self.dm.set_callback(self.refresh_tasks)
            self.refresh_tasks()

    def refresh_tasks(self):
        # This callback might be coming from a background thread in DM
        # But qasync ensures tasks scheduled via asyncio.create_task run on main loop.
        # However, the DM callback is a simple function call. 
        # We'll use a signal or just be careful.
        
        # For simplicity in this port, we re-render
        for i in reversed(range(self.list_layout.count())):
            item = self.list_layout.itemAt(i)
            if item.widget(): item.widget().setParent(None)
            
        if not self.dm or not self.dm.tasks:
            self.list_layout.addWidget(QLabel("No active downloads."))
            return
            
        for task_id, task in reversed(list(self.dm.tasks.items())):
            widget = DownloadTaskWidget(task, self._delete_task)
            self.list_layout.addWidget(widget)

    def _delete_task(self, book_id):
        if self.dm:
            self.dm.remove_task(book_id)
            self.refresh_tasks()
