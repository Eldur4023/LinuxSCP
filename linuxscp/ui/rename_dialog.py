from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)
from PyQt6.QtCore import Qt


class RenameDialog(QDialog):
    """F2 Rename — simple inline dialog."""

    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename")
        self.setFixedWidth(360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("New name:"))
        self._name = QLineEdit(current_name)
        self._name.selectAll()
        layout.addWidget(self._name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Rename")
        ok.setDefault(True)
        ok.setFixedWidth(80)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setFixedWidth(80)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

        self._name.setFocus()

    @property
    def new_name(self) -> str:
        return self._name.text().strip()


class MkdirDialog(QDialog):
    """F7 Create Directory."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Directory")
        self.setFixedWidth(360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("Directory name:"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("new_directory")
        layout.addWidget(self._name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Create")
        ok.setDefault(True)
        ok.setFixedWidth(80)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setFixedWidth(80)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

        self._name.setFocus()

    @property
    def dir_name(self) -> str:
        return self._name.text().strip()
