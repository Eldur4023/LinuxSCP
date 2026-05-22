from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QLabel, QLineEdit, QCheckBox, QComboBox,
    QSpinBox, QPushButton, QGroupBox, QRadioButton, QButtonGroup,
    QFileDialog, QDialogButtonBox, QFontComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from linuxscp.core.preferences import get_prefs, Preferences


class PreferencesDialog(QDialog):
    """
    Preferences dialog — mirrors WinSCP's Preferences window.
    Changes are applied live on OK/Apply.
    """

    preferences_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences – LinuxSCP")
        self.setMinimumSize(560, 420)
        self.setModal(True)

        self._prefs = get_prefs()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._build_general_tab()
        self._build_transfers_tab()
        self._build_editor_tab()
        self._build_interface_tab()

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Apply |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply_and_accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(btns)

        self._load_values()

    # ── Tab: General ──────────────────────────────────────────────────────

    def _build_general_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(10)
        form.setContentsMargins(14, 14, 14, 14)

        self._chk_confirm_del  = QCheckBox("Ask before deleting files")
        self._chk_confirm_ow   = QCheckBox("Ask before overwriting files")
        self._chk_show_hidden  = QCheckBox("Show hidden files (dotfiles)")
        self._chk_remember_dir = QCheckBox("Remember last local/remote directory")

        form.addRow(self._chk_confirm_del)
        form.addRow(self._chk_confirm_ow)
        form.addRow(self._chk_show_hidden)
        form.addRow(self._chk_remember_dir)

        form.addRow(QLabel(""))
        form.addRow(QLabel("<b>Double-click action:</b>"))
        self._dbl_group = QButtonGroup(self)
        for label, val in (("Open file / enter directory", "open"),
                           ("Select item (don't navigate)", "select")):
            rb = QRadioButton(label)
            rb.setProperty("val", val)
            self._dbl_group.addButton(rb)
            form.addRow(rb)

        self._tabs.addTab(tab, "General")

    # ── Tab: Transfers ────────────────────────────────────────────────────

    def _build_transfers_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(10)
        form.setContentsMargins(14, 14, 14, 14)

        self._chk_timestamps = QCheckBox("Preserve timestamps")
        self._chk_perms      = QCheckBox("Preserve permissions")
        form.addRow(self._chk_timestamps)
        form.addRow(self._chk_perms)

        self._combo_mode = QComboBox()
        self._combo_mode.addItems(["Auto-detect", "Binary", "Text"])
        form.addRow("Transfer mode:", self._combo_mode)

        self._spin_concurrent = QSpinBox()
        self._spin_concurrent.setRange(1, 8)
        self._spin_concurrent.setFixedWidth(60)
        form.addRow("Max concurrent transfers:", self._spin_concurrent)

        self._spin_retry = QSpinBox()
        self._spin_retry.setRange(0, 10)
        self._spin_retry.setFixedWidth(60)
        form.addRow("Retry count on failure:", self._spin_retry)

        self._tabs.addTab(tab, "Transfers")

    # ── Tab: Editor ───────────────────────────────────────────────────────

    def _build_editor_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(10)
        form.setContentsMargins(14, 14, 14, 14)

        self._chk_ext_editor = QCheckBox("Use external editor instead of built-in")
        form.addRow(self._chk_ext_editor)

        ext_row = QHBoxLayout()
        self._ext_editor_cmd = QLineEdit()
        self._ext_editor_cmd.setPlaceholderText("e.g. gedit %f  or  code %f")
        ext_row.addWidget(self._ext_editor_cmd)
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse_editor)
        ext_row.addWidget(btn_browse)
        form.addRow("Editor command:", ext_row)

        self._chk_ext_editor.toggled.connect(self._ext_editor_cmd.setEnabled)
        self._chk_ext_editor.toggled.connect(btn_browse.setEnabled)

        form.addRow(QLabel(""))
        form.addRow(QLabel("<b>Built-in editor font:</b>"))

        self._editor_font = QFontComboBox()
        self._editor_font.setFixedWidth(220)
        form.addRow("Font family:", self._editor_font)

        self._editor_font_size = QSpinBox()
        self._editor_font_size.setRange(7, 24)
        self._editor_font_size.setFixedWidth(60)
        form.addRow("Font size:", self._editor_font_size)

        self._tabs.addTab(tab, "Editor")

    # ── Tab: Interface ────────────────────────────────────────────────────

    def _build_interface_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(10)
        form.setContentsMargins(14, 14, 14, 14)

        self._combo_theme = QComboBox()
        self._combo_theme.addItems(["System default", "Light", "Dark"])
        form.addRow("Theme:", self._combo_theme)

        self._panel_font = QFontComboBox()
        self._panel_font.setFixedWidth(220)
        form.addRow("Panel font:", self._panel_font)

        self._panel_font_size = QSpinBox()
        self._panel_font_size.setRange(7, 18)
        self._panel_font_size.setFixedWidth(60)
        form.addRow("Panel font size:", self._panel_font_size)

        self._chk_queue = QCheckBox("Show transfer queue panel")
        form.addRow(self._chk_queue)

        self._tabs.addTab(tab, "Interface")

    # ── Load / Apply ──────────────────────────────────────────────────────

    def _load_values(self):
        p = self._prefs

        # General
        self._chk_confirm_del.setChecked(p.confirm_delete)
        self._chk_confirm_ow.setChecked(p.confirm_overwrite)
        self._chk_show_hidden.setChecked(p.show_hidden_files)
        self._chk_remember_dir.setChecked(p.remember_last_dir)
        for btn in self._dbl_group.buttons():
            if btn.property("val") == p.double_click_action:
                btn.setChecked(True)

        # Transfers
        self._chk_timestamps.setChecked(p.preserve_timestamps)
        self._chk_perms.setChecked(p.preserve_permissions)
        mode_map = {"auto": 0, "binary": 1, "text": 2}
        self._combo_mode.setCurrentIndex(mode_map.get(p.transfer_mode, 0))
        self._spin_concurrent.setValue(p.max_concurrent)
        self._spin_retry.setValue(p.retry_count)

        # Editor
        self._chk_ext_editor.setChecked(p.use_external_editor)
        self._ext_editor_cmd.setText(p.external_editor_cmd)
        self._ext_editor_cmd.setEnabled(p.use_external_editor)
        self._editor_font.setCurrentFont(QFont(p.editor_font_family))
        self._editor_font_size.setValue(p.editor_font_size)

        # Interface
        theme_map = {"system": 0, "light": 1, "dark": 2}
        self._combo_theme.setCurrentIndex(theme_map.get(p.theme, 0))
        if p.panel_font_family:
            self._panel_font.setCurrentFont(QFont(p.panel_font_family))
        self._panel_font_size.setValue(p.panel_font_size)
        self._chk_queue.setChecked(p.show_queue_panel)

    def _apply(self):
        p = self._prefs

        # General
        p.confirm_delete         = self._chk_confirm_del.isChecked()
        p.confirm_overwrite      = self._chk_confirm_ow.isChecked()
        p.show_hidden_files      = self._chk_show_hidden.isChecked()
        p.remember_last_dir      = self._chk_remember_dir.isChecked()
        for btn in self._dbl_group.buttons():
            if btn.isChecked():
                p.double_click_action = btn.property("val")

        # Transfers
        p.preserve_timestamps    = self._chk_timestamps.isChecked()
        p.preserve_permissions   = self._chk_perms.isChecked()
        mode_map = {0: "auto", 1: "binary", 2: "text"}
        p.transfer_mode          = mode_map.get(self._combo_mode.currentIndex(), "auto")
        p.max_concurrent         = self._spin_concurrent.value()
        p.retry_count            = self._spin_retry.value()

        # Editor
        p.use_external_editor    = self._chk_ext_editor.isChecked()
        p.external_editor_cmd    = self._ext_editor_cmd.text().strip()
        p.editor_font_family     = self._editor_font.currentFont().family()
        p.editor_font_size       = self._editor_font_size.value()

        # Interface
        theme_map = {0: "system", 1: "light", 2: "dark"}
        p.theme                  = theme_map.get(self._combo_theme.currentIndex(), "system")
        p.panel_font_family      = self._panel_font.currentFont().family()
        p.panel_font_size        = self._panel_font_size.value()
        p.show_queue_panel       = self._chk_queue.isChecked()

        p.save()
        self.preferences_changed.emit()

    def _apply_and_accept(self):
        self._apply()
        self.accept()

    def _browse_editor(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select editor executable", "/usr/bin")
        if path:
            self._ext_editor_cmd.setText(f"{path} %f")
