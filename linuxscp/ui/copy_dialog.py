from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt

from linuxscp.core.transfer import OverwriteMode


class CopyDialog(QDialog):
    """
    F5 Copy / F6 Move dialog — mirrors WinSCP's transfer dialog.
    """

    def __init__(self, action: str, entries: list, dst_path: str, parent=None):
        super().__init__(parent)
        n = len(entries)
        title = f"{action} {n} item(s)" if n > 1 else f"{action} '{entries[0].name}'" if entries else action
        self.setWindowTitle(title)
        self.setFixedWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Source summary
        if n == 1:
            src_label = QLabel(f"<b>{entries[0].name}</b>")
        else:
            names = ", ".join(e.name for e in entries[:3])
            if n > 3:
                names += f", … ({n - 3} more)"
            src_label = QLabel(f"<b>{n} items:</b> {names}")
        src_label.setTextFormat(Qt.TextFormat.RichText)
        src_label.setWordWrap(True)
        layout.addWidget(src_label)

        # Destination field
        layout.addWidget(QLabel(f"{action} to:"))
        self._dst = QLineEdit(dst_path)
        self._dst.setMinimumWidth(400)
        layout.addWidget(self._dst)

        # Options group
        grp = QGroupBox("Transfer options")
        grp_layout = QVBoxLayout(grp)

        self._chk_timestamps = QCheckBox("Preserve timestamps")
        self._chk_timestamps.setChecked(True)
        self._chk_permissions = QCheckBox("Preserve permissions")
        self._chk_permissions.setChecked(True)
        grp_layout.addWidget(self._chk_timestamps)
        grp_layout.addWidget(self._chk_permissions)

        # Overwrite mode
        ow_label = QLabel("If destination exists:")
        grp_layout.addWidget(ow_label)
        self._ow_group = QButtonGroup(self)
        for label, mode in (
            ("Overwrite",   OverwriteMode.OVERWRITE),
            ("Skip",        OverwriteMode.SKIP),
            ("Auto-rename", OverwriteMode.RENAME),
        ):
            rb = QRadioButton(label)
            rb.setProperty("mode", mode)
            if mode == OverwriteMode.OVERWRITE:
                rb.setChecked(True)
            self._ow_group.addButton(rb)
            grp_layout.addWidget(rb)

        layout.addWidget(grp)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton(action)
        ok.setDefault(True)
        ok.setFixedWidth(90)
        ok.setStyleSheet("font-weight: bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setFixedWidth(90)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    @property
    def destination(self) -> str:
        return self._dst.text().strip()

    @property
    def overwrite_mode(self) -> OverwriteMode:
        for btn in self._ow_group.buttons():
            if btn.isChecked():
                return btn.property("mode")
        return OverwriteMode.OVERWRITE

    @property
    def preserve_timestamps(self) -> bool:
        return self._chk_timestamps.isChecked()

    @property
    def preserve_permissions(self) -> bool:
        return self._chk_permissions.isChecked()
