# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Dict, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QFormLayout, QFrame
)
from PyQt6.QtCore import Qt
from comiccatcher.models.opds_auth import AuthDocument, AuthFlow
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class DynamicAuthDialog(QDialog):
    def __init__(self, parent, auth_doc: AuthDocument):
        super().__init__(parent)
        self.auth_doc = auth_doc
        self.credentials: Dict[str, str] = {}
        
        s = UIConstants.scale
        self.setWindowTitle(auth_doc.title or "Authentication Required")
        self.setFixedWidth(s(400))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(25), s(25), s(25), s(25))
        layout.setSpacing(s(15))
        
        # Header
        if auth_doc.title:
            title_label = QLabel(auth_doc.title)
            title_label.setStyleSheet(f"font-size: {s(18)}px; font-weight: bold;")
            layout.addWidget(title_label)
            
        if auth_doc.description:
            desc_label = QLabel(auth_doc.description)
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
            
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # Form
        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(s(10))
        self.inputs: Dict[str, QLineEdit] = {}
        
        # Find the best flow (Basic Auth is most standard for direct login)
        self.selected_flow = self._select_best_flow(auth_doc)
        if self.selected_flow and self.selected_flow.labels:
            for key, label_text in self.selected_flow.labels.items():
                input_field = QLineEdit()
                if "password" in key.lower() or "pin" in key.lower():
                    input_field.setEchoMode(QLineEdit.EchoMode.Password)
                self.inputs[key] = input_field
                self.form_layout.addRow(f"{label_text}:", input_field)
        else:
            # Fallback for flows without explicit labels
            self.inputs["username"] = QLineEdit()
            self.form_layout.addRow("Username:", self.inputs["username"])
            self.inputs["password"] = QLineEdit()
            self.inputs["password"].setEchoMode(QLineEdit.EchoMode.Password)
            self.form_layout.addRow("Password:", self.inputs["password"])
            
        layout.addLayout(self.form_layout)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondary_button")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_login = QPushButton("Login")
        self.btn_login.setObjectName("primary_button")
        self.btn_login.setDefault(True) # Ensure Return key triggers Login
        self.btn_login.clicked.connect(self.on_login)
        
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_login)
        layout.addLayout(btn_row)
        
        self.reapply_theme()

    def _select_best_flow(self, auth_doc: AuthDocument) -> Optional[AuthFlow]:
        # Priority: Basic Auth, then anything else
        for flow in auth_doc.authentication:
            if flow.type == "http://opds-spec.org/auth/basic":
                return flow
        if auth_doc.authentication:
            return auth_doc.authentication[0]
        return None

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.setStyleSheet(f"color: {theme['text_main']};")

    def on_login(self):
        self.credentials = {k: v.text() for k, v in self.inputs.items()}
        # We don't perform the POST here to keep the UI responsive and logic clean.
        # The calling view will take these credentials and exchange them for a token.
        self.accept()

    def get_token_request_details(self) -> tuple[Optional[str], Dict[str, str]]:
        """Returns (url, payload) for the token exchange POST request."""
        if not self.selected_flow:
            return None, {}
            
        # Find the authentication endpoint link
        auth_url = None
        for link in self.selected_flow.links:
            if link.rel in ["authenticate", "http://opds-spec.org/auth/document"]:
                auth_url = link.href
                break
        
        if not auth_url:
            # Check root links as fallback
            for link in self.auth_doc.links:
                if link.rel in ["authenticate", "http://opds-spec.org/auth/document"]:
                    auth_url = link.href
                    break
                    
        return auth_url, self.credentials
