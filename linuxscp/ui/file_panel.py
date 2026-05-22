import os
import posixpath
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QLabel,
    QLineEdit, QAbstractItemView, QHeaderView, QSizePolicy,
    QPushButton, QMenu, QInputDialog, QApplication,
)
from PyQt6.QtCore import (
    Qt, QAbstractItemModel, QModelIndex, QVariant, pyqtSignal,
    QMimeData, QByteArray,
)
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QDrag

from linuxscp.core.base_session import BaseSession
from linuxscp.core.local_session import LocalSession
from linuxscp.core.local_fs import FileEntry
from linuxscp.core.preferences import get_prefs
from linuxscp.ui.styles import PANEL_STYLE

# Column indices
COL_NAME = 0
COL_EXT  = 1
COL_SIZE = 2
COL_DATE = 3
COL_ATTR = 4
COLUMNS  = ["Name", "Ext", "Size", "Changed", "Attr"]

# Colors matching WinSCP defaults
COLOR_DIR    = QColor("#0000AA")
COLOR_LINK   = QColor("#00AAAA")
COLOR_EXEC   = QColor("#006600")
COLOR_HIDDEN = QColor("#808080")
COLOR_PARENT = QColor("#000080")

FONT_BOLD = QFont()
FONT_BOLD.setBold(True)

_EXEC_EXTS = {"sh", "py", "pl", "rb", "run", "bin", "AppImage"}


class FileSystemModel(QAbstractItemModel):
    def __init__(self, session: BaseSession, parent=None):
        super().__init__(parent)
        self._session = session
        self._entries: list[FileEntry] = []
        self._path = ""

    def set_session(self, session: BaseSession):
        self._session = session
        self.beginResetModel()
        self._entries = []
        self._path = ""
        self.endResetModel()

    def load(self, path: str) -> str | None:
        self.beginResetModel()
        entries, error = self._session.list_directory(path)
        if not error:
            if not get_prefs().show_hidden_files:
                entries = [e for e in entries
                           if e.name == ".." or not e.name.startswith(".")]
            self._entries = entries
            try:
                if self._session.is_remote:
                    self._path = path
                else:
                    self._path = os.path.realpath(path)
            except Exception:
                self._path = path
        self.endResetModel()
        return error

    @property
    def current_path(self) -> str:
        return self._path

    def entry(self, index: QModelIndex) -> FileEntry | None:
        if index.isValid() and 0 <= index.row() < len(self._entries):
            return self._entries[index.row()]
        return None

    # ── QAbstractItemModel ─────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def index(self, row, col, parent=QModelIndex()) -> QModelIndex:
        if self.hasIndex(row, col, parent):
            return self.createIndex(row, col)
        return QModelIndex()

    def parent(self, index=QModelIndex()) -> QModelIndex:
        return QModelIndex()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return QVariant()

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()
        entry = self._entries[index.row()]
        col   = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(entry, col)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._color(entry)
        if role == Qt.ItemDataRole.FontRole and (entry.is_dir or entry.name == ".."):
            return FONT_BOLD
        if role == Qt.ItemDataRole.TextAlignmentRole and col == COL_SIZE:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return QVariant()

    def _display(self, e: FileEntry, col: int) -> str:
        if e.name == "..":
            return ".." if col == COL_NAME else ""
        match col:
            case 0: return e.name if e.is_dir else os.path.splitext(e.name)[0]
            case 1: return e.extension.upper() if not e.is_dir else ""
            case 2: return e.size_str
            case 3: return e.modified_str
            case 4: return e.permissions
        return ""

    def _color(self, e: FileEntry) -> QColor:
        if e.name == "..":
            return COLOR_PARENT
        if e.name.startswith("."):
            return COLOR_HIDDEN
        if e.is_link:
            return COLOR_LINK
        if e.is_dir:
            return COLOR_DIR
        if e.extension in _EXEC_EXTS:
            return COLOR_EXEC
        return QColor("#000000")


_MIME_TYPE = "application/x-linuxscp-files"


class _DragDropView(QTreeView):
    """QTreeView with drag-source and drop-target support for file entries."""

    files_dropped = pyqtSignal(list, str)  # (source_paths_json, dst_path)

    def __init__(self, panel: "FilePanel", parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def startDrag(self, supported_actions):
        entries = self._panel.selected_entries()
        if not entries:
            return
        paths = [e.path for e in entries if e.name != ".."]
        if not paths:
            return
        mime = QMimeData()
        mime.setData(_MIME_TYPE, QByteArray(json.dumps(paths).encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(_MIME_TYPE):
            event.ignore()
            return
        raw = bytes(event.mimeData().data(_MIME_TYPE)).decode()
        paths = json.loads(raw)
        self.files_dropped.emit(paths, self._panel.current_path())
        event.acceptProposedAction()


class FilePanel(QWidget):
    path_changed    = pyqtSignal(str)
    entry_activated = pyqtSignal(object)
    focused         = pyqtSignal()
    files_dropped   = pyqtSignal(list, str)   # forwarded from view

    def __init__(self, title: str = "Local", start_path: str = None,
                 session: BaseSession = None, parent=None):
        super().__init__(parent)
        self.setObjectName("FilePanel")
        self.setStyleSheet(PANEL_STYLE)
        self._active = False

        sess = session or LocalSession()

        # ── Title bar ───────────────────────────────────────────────────
        self._title_label = QLabel(title)
        self._title_label.setObjectName("PanelTitle")
        self._title_label.setProperty("active", "false")

        # ── Path bar ────────────────────────────────────────────────────
        self._path_bar = QLineEdit()
        self._path_bar.setObjectName("PathBar")
        self._path_bar.returnPressed.connect(self._on_path_entered)

        # ── File list ───────────────────────────────────────────────────
        self._model = FileSystemModel(sess)
        self._view  = _DragDropView(self)
        self._view.setObjectName("FileList")
        self._view.files_dropped.connect(self.files_dropped)
        self._view.setModel(self._model)
        self._view.setRootIsDecorated(False)
        self._view.setUniformRowHeights(True)
        self._view.setAlternatingRowColors(True)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._view.setAllColumnsShowFocus(True)
        self._view.setSortingEnabled(True)
        self._view.doubleClicked.connect(self._on_double_click)
        self._view.installEventFilter(self)

        hdr = self._view.header()
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_EXT,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_ATTR, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setMinimumSectionSize(20)

        # ── Status bar ──────────────────────────────────────────────────
        self._status = QLabel("")
        self._status.setStyleSheet("padding: 1px 4px; font-size: 8pt; color: #333;")
        self._status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # ── Layout ──────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title_label)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(2, 2, 2, 2)
        path_row.addWidget(self._path_bar)

        # Bookmark button
        self._bm_btn = QPushButton("★")
        self._bm_btn.setFixedSize(22, 22)
        self._bm_btn.setToolTip("Bookmarks")
        self._bm_btn.setStyleSheet(
            "QPushButton { border: 1px solid #ADADAD; background: #F0F0F0; font-size: 10pt; }"
            "QPushButton:hover { background: #CCE4F7; border-color: #0078D7; }"
        )
        self._bm_btn.clicked.connect(self._show_bookmarks)
        path_row.addWidget(self._bm_btn)

        layout.addLayout(path_row)

        layout.addWidget(self._view)
        layout.addWidget(self._status)

        self._view.selectionModel().selectionChanged.connect(self._update_status)

        start = start_path or sess.home_dir()
        self.navigate(start)

    # ── Public API ────────────────────────────────────────────────────

    def set_session(self, session: BaseSession, path: str = None):
        """Replace the active session (e.g. after SFTP connect)."""
        self._model.set_session(session)
        self.set_title(session.label)
        self.navigate(path or session.home_dir())

    def navigate(self, path: str):
        error = self._model.load(path)
        if error:
            self._status.setText(f"Error: {error}")
            return
        self._path_bar.setText(self._model.current_path)
        self._view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        if self._model.rowCount() > 0:
            self._view.setCurrentIndex(self._model.index(0, 0))
        self._update_status()
        self.path_changed.emit(self._model.current_path)

    def current_path(self) -> str:
        return self._model.current_path

    def selected_entries(self) -> list[FileEntry]:
        rows = {idx.row() for idx in self._view.selectedIndexes()}
        return [e for r in sorted(rows)
                if (e := self._model.entry(self._model.index(r, 0)))]

    def set_active(self, active: bool):
        self._active = active
        self._title_label.setProperty("active", "true" if active else "false")
        self._title_label.style().unpolish(self._title_label)
        self._title_label.style().polish(self._title_label)

    def set_title(self, title: str):
        self._title_label.setText(title)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_path_entered(self):
        self.navigate(self._path_bar.text().strip())

    def _on_double_click(self, index: QModelIndex):
        entry = self._model.entry(index)
        if entry and entry.is_dir:
            self.navigate(entry.path)
        elif entry:
            self.entry_activated.emit(entry)

    def _update_status(self):
        total    = self._model.rowCount()
        first    = self._model.entry(self._model.index(0, 0))
        has_parent = first and first.name == ".."
        count    = total - (1 if has_parent else 0)

        selected = self.selected_entries()
        sel_files = [e for e in selected if not e.is_dir and e.name != ".."]
        sel_bytes = sum(e.size for e in sel_files)

        if sel_files:
            self._status.setText(
                f"{len(sel_files)} of {count} file(s) selected  |  {_fmt_bytes(sel_bytes)}"
            )
        else:
            self._status.setText(f"{count} file(s)")

    # ── Event filter ──────────────────────────────────────────────────

    def eventFilter(self, source, event):
        if source is self._view and isinstance(event, QKeyEvent):
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._on_double_click(self._view.currentIndex())
                return True
            if key == Qt.Key.Key_Backspace:
                cur = self.current_path()
                parent = posixpath.dirname(cur) if self._model._session.is_remote else os.path.dirname(cur)
                if parent != cur:
                    self.navigate(parent)
                return True
        return super().eventFilter(source, event)

    def _show_bookmarks(self):
        from linuxscp.core.config_store import (
            load_bookmarks, add_bookmark, remove_bookmark,
        )
        session_label = self._model._session.label
        bookmarks = [b for b in load_bookmarks() if b.label == session_label]
        cur_path  = self.current_path()

        menu = QMenu(self)

        # Add / Remove current
        is_bookmarked = any(b.path == cur_path for b in bookmarks)
        if is_bookmarked:
            act_del = menu.addAction(f"✕  Remove '{cur_path.split('/')[-1] or cur_path}'")
            act_del.triggered.connect(
                lambda: remove_bookmark(cur_path, session_label))
        else:
            act_add = menu.addAction(f"★  Add '{cur_path.split('/')[-1] or cur_path}'")
            act_add.triggered.connect(
                lambda: add_bookmark(cur_path, session_label))

        if bookmarks:
            menu.addSeparator()
            for bm in bookmarks:
                label = f"  {bm.name}  ({bm.path})" if bm.name != bm.path else f"  {bm.path}"
                act = menu.addAction(label)
                path = bm.path
                act.triggered.connect(lambda _, p=path: self.navigate(p))

        menu.exec(self._bm_btn.mapToGlobal(self._bm_btn.rect().bottomLeft()))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.focused.emit()


def _fmt_bytes(n: int) -> str:
    for unit, th in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= th:
            return f"{n / th:.2f} {unit}"
    return f"{n} bytes"
