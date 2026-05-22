import os
import posixpath
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QMenu, QMessageBox, QLabel, QApplication,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence

from linuxscp.ui.file_panel import FilePanel
from linuxscp.ui.fkeys_bar import FKeysBar
from linuxscp.ui.site_manager import SiteManager, SessionData
from linuxscp.ui.password_dialog import PasswordDialog
from linuxscp.ui.copy_dialog import CopyDialog
from linuxscp.ui.rename_dialog import RenameDialog, MkdirDialog
from linuxscp.ui.transfer_queue import TransferQueuePanel
from linuxscp.ui.viewer import FileViewer
from linuxscp.ui.editor import FileEditor
from linuxscp.ui.sync_dialog import SyncDialog
from linuxscp.ui.terminal import TerminalPanel
from linuxscp.ui.preferences_dialog import PreferencesDialog
from linuxscp.ui.styles import MAIN_STYLE
from linuxscp.core.transfer import build_transfer_jobs, TransferWorker
from linuxscp.core.preferences import get_prefs

APP_TITLE = "LinuxSCP"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(900, 580)
        self.resize(1200, 720)
        self.setStyleSheet(MAIN_STYLE)

        self._left_panel:   FilePanel | None = None
        self._right_panel:  FilePanel | None = None
        self._active_panel: FilePanel | None = None
        self._connect_worker = None       # ConnectWorker — keep ref
        self._transfer_workers: list[TransferWorker] = []
        self._current_session = None      # active SFTPSession
        self._open_windows: list = []     # viewers / editors — keep refs
        self._pending_connect_data = None # SessionData during connect flow

        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        self._set_active_panel(self._left_panel)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._open_site_manager)

    # ── Menu bar ─────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        m_session = mb.addMenu("&Session")
        self._add_action(m_session, "&New Session…",  "Ctrl+N", self._open_site_manager)
        m_session.addSeparator()
        self._act_disconnect = self._add_action(m_session, "&Disconnect", "Ctrl+D", self._disconnect)
        self._act_disconnect.setEnabled(False)
        m_session.addSeparator()
        self._add_action(m_session, "E&xit", "Alt+F4", self.close)

        m_files = mb.addMenu("&Files")
        self._add_action(m_files, "&Properties",           "Alt+Return", lambda: self._fkey(9))
        self._add_action(m_files, "Change &Permissions…",  "",            lambda: None)
        m_files.addSeparator()
        self._add_action(m_files, "&Rename",   "F2", lambda: self._fkey(2))
        self._add_action(m_files, "&Copy…",    "F5", lambda: self._fkey(5))
        self._add_action(m_files, "&Move…",    "F6", lambda: self._fkey(6))
        self._add_action(m_files, "Create &Directory…", "F7", lambda: self._fkey(7))
        self._add_action(m_files, "&Delete",   "F8", lambda: self._fkey(8))

        m_cmd = mb.addMenu("&Commands")
        self._add_action(m_cmd, "&Open Terminal",              "Ctrl+T", self._open_terminal)
        self._add_action(m_cmd, "Synchronize &Directories…",   "",       self._synchronize)
        m_cmd.addSeparator()
        self._add_action(m_cmd, "&Compare Directories",        "",       self._synchronize)

        m_marks = mb.addMenu("&Marks")
        self._add_action(m_marks, "Select &All",      "Ctrl+A", self._select_all)
        self._add_action(m_marks, "Unselect All",     "Ctrl+U", self._unselect_all)
        self._add_action(m_marks, "Invert Selection", "Ctrl+I", self._invert_selection)

        m_opts = mb.addMenu("&Options")
        self._add_action(m_opts, "&Preferences…", "Ctrl+,", self._open_preferences)

        m_remote = mb.addMenu("&Remote")
        self._add_action(m_remote, "&Refresh",          "Ctrl+R", self._refresh)
        self._add_action(m_remote, "Open &Shell",       "",        lambda: None)
        m_remote.addSeparator()
        self._add_action(m_remote, "Execute &Command…", "",        lambda: None)

        m_help = mb.addMenu("&Help")
        self._add_action(m_help, "LinuxSCP &Help", "F1",  lambda: self._fkey(1))
        m_help.addSeparator()
        self._add_action(m_help, "&About LinuxSCP", "", self._about)

    # ── Toolbar ───────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        def tbtn(label, tip, slot, shortcut=""):
            act = QAction(label, self)
            act.setToolTip(tip)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            tb.addAction(act)
            return act

        tbtn("New Session",  "Open Site Manager (Ctrl+N)", self._open_site_manager, "Ctrl+N")
        self._tb_disconnect = tbtn("Disconnect", "Disconnect (Ctrl+D)", self._disconnect)
        self._tb_disconnect.setEnabled(False)
        self._tb_terminal = tbtn("⬛ Terminal", "Open SSH terminal (Ctrl+T)", self._open_terminal, "Ctrl+T")
        self._tb_terminal.setEnabled(False)
        tb.addSeparator()
        tbtn("Refresh",      "Refresh active panel (Ctrl+R)", self._refresh, "Ctrl+R")
        tbtn("Synchronize",  "Synchronize directories", self._synchronize)
        tb.addSeparator()
        tbtn("Copy",         "Copy (F5)",             lambda: self._fkey(5))
        tbtn("Move",         "Move (F6)",             lambda: self._fkey(6))
        tbtn("Mkdir",        "Create directory (F7)", lambda: self._fkey(7))
        tbtn("Delete",       "Delete (F8)",           lambda: self._fkey(8))
        tb.addSeparator()
        tbtn("Properties",   "File properties (Alt+Enter)", lambda: self._fkey(9))

    # ── Central widget ────────────────────────────────────────────────────

    def _build_central(self):
        central = QWidget()
        layout  = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        home = os.path.expanduser("~")
        self._left_panel  = FilePanel("Local",  start_path=home, parent=self)
        self._right_panel = FilePanel("Remote", start_path=home, parent=self)

        self._left_panel.focused.connect(lambda: self._set_active_panel(self._left_panel))
        self._right_panel.focused.connect(lambda: self._set_active_panel(self._right_panel))
        self._left_panel.path_changed.connect(lambda p: self._on_path_changed("left", p))
        self._right_panel.path_changed.connect(lambda p: self._on_path_changed("right", p))

        self._left_panel.files_dropped.connect(self._on_files_dropped)
        self._right_panel.files_dropped.connect(self._on_files_dropped)
        self._left_panel.entry_activated.connect(
            lambda e: self._on_entry_activated(e, self._left_panel))
        self._right_panel.entry_activated.connect(
            lambda e: self._on_entry_activated(e, self._right_panel))

        splitter.addWidget(self._left_panel)
        splitter.addWidget(self._right_panel)
        splitter.setSizes([600, 600])

        layout.addWidget(splitter, stretch=1)

        # F-keys bar
        self._fkeys = FKeysBar(self)
        self._fkeys.key_pressed.connect(self._fkey)
        layout.addWidget(self._fkeys)

        # Transfer queue (collapsible)
        self._queue_panel = TransferQueuePanel(self)
        self._queue_panel.setVisible(get_prefs().show_queue_panel)
        layout.addWidget(self._queue_panel)

        self.setCentralWidget(central)

    # ── Status bar ────────────────────────────────────────────────────────

    def _build_statusbar(self):
        sb = self.statusBar()
        self._status_main  = QLabel("Not connected")
        self._status_right = QLabel("")
        sb.addPermanentWidget(self._status_main,  1)
        sb.addPermanentWidget(QLabel(" | "),       0)
        sb.addPermanentWidget(self._status_right, 1)

    # ── Connection flow ───────────────────────────────────────────────────

    def _open_site_manager(self):
        dlg = SiteManager(self)
        dlg.connect_requested.connect(self._on_connect_requested)
        dlg.exec()

    def _on_connect_requested(self, data: SessionData):
        password = data.password
        if not password and not data.key_file:
            dlg = PasswordDialog(data.host, data.user, parent=self)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            password = dlg.password

        self._status_main.setText(f"Connecting to {data.user}@{data.host}:{data.port}…")
        QApplication.processEvents()

        self._pending_connect_data = data
        self._do_connect(data, password=password)

    def _do_connect(self, data: SessionData, password: str = "",
                    key_passphrase: str = ""):
        from linuxscp.core.connect_worker import ConnectWorker
        worker = ConnectWorker(data, password=password,
                               key_passphrase=key_passphrase, parent=self)
        worker.connected.connect(self._on_connected)
        worker.failed.connect(self._on_connect_failed)
        worker.key_passphrase_needed.connect(self._on_key_passphrase_needed)
        self._connect_worker = worker
        worker.start()

    def _on_key_passphrase_needed(self):
        from linuxscp.ui.password_dialog import PasswordDialog
        data = self._pending_connect_data
        dlg = PasswordDialog(data.host, data.user,
                             prompt="Key passphrase:", parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            self._status_main.setText("Not connected")
            return
        self._do_connect(data, key_passphrase=dlg.password)

    def _on_connected(self, session):
        self._current_session = session
        remote_dir = None
        # Use remote_dir from site manager if set
        self._right_panel.set_session(session, remote_dir)
        label = session.label
        self.setWindowTitle(f"{label} – {APP_TITLE}")
        self._status_main.setText(f"Connected to {label}")
        self._act_disconnect.setEnabled(True)
        self._tb_disconnect.setEnabled(True)
        self._tb_terminal.setEnabled(True)

    def _on_connect_failed(self, error: str):
        self._status_main.setText("Not connected")
        QMessageBox.critical(self, "Connection failed", error)

    def _disconnect(self):
        if self._current_session:
            self._current_session.disconnect()
            self._current_session = None

        from linuxscp.core.local_session import LocalSession
        self._right_panel.set_session(LocalSession())
        self._right_panel.set_title("Remote")

        self.setWindowTitle(APP_TITLE)
        self._status_main.setText("Not connected")
        self._status_right.setText("")
        self._act_disconnect.setEnabled(False)
        self._tb_disconnect.setEnabled(False)
        self._tb_terminal.setEnabled(False)

    # ── Panel management ──────────────────────────────────────────────────

    def _set_active_panel(self, panel: FilePanel):
        if self._active_panel is panel:
            return
        if self._active_panel:
            self._active_panel.set_active(False)
        self._active_panel = panel
        panel.set_active(True)

    def _active(self) -> FilePanel:
        return self._active_panel or self._left_panel

    def _opposite(self) -> FilePanel:
        return self._right_panel if self._active_panel is self._left_panel else self._left_panel

    def _on_path_changed(self, side: str, path: str):
        if side == "right":
            self._status_right.setText(path)

    # ── F-key dispatch ────────────────────────────────────────────────────

    def _fkey(self, n: int):
        {
            1:  self._help,
            2:  self._rename,
            3:  self._view,
            4:  self._edit,
            5:  self._copy,
            6:  self._move,
            7:  self._mkdir,
            8:  self._delete,
            9:  self._properties,
            10: self.close,
        }.get(n, lambda: None)()

    def _help(self):
        QMessageBox.information(self, "Help",
            "LinuxSCP — WinSCP-compatible SFTP client for Linux.\n\nHelp docs coming soon.")

    def _view(self):
        entries = self._active().selected_entries()
        entries = [e for e in entries if not e.is_dir and e.name != ".."]
        if not entries:
            return
        session = self._active()._model._session
        for entry in entries[:3]:    # cap at 3 simultaneous viewers
            viewer = FileViewer(entry.path, session, parent=self)
            viewer.show()
            self._open_windows.append(viewer)

    def _open_file(self, entry, session, panel: "FilePanel"):
        """
        Open a file with the appropriate tool:
        - Local: xdg-open (system default, e.g. VS Code)
        - Remote: download to temp → xdg-open → watch for saves → auto-upload
        - Fallback: built-in FileEditor if xdg-open is unavailable
        Respects use_external_editor preference for an explicit command override.
        """
        import subprocess, tempfile, shlex
        from PyQt6.QtCore import QFileSystemWatcher

        prefs = get_prefs()

        # ── Explicit external editor command ─────────────────────────────
        if prefs.use_external_editor and prefs.external_editor_cmd:
            if not session.is_remote:
                try:
                    cmd = prefs.external_editor_cmd.replace("%f", entry.path)
                    subprocess.Popen(shlex.split(cmd))
                except Exception as ex:
                    QMessageBox.warning(self, "Editor error", str(ex))
                return
            # Remote + explicit cmd: download then open with cmd + watcher
            self._open_remote_with_watcher(
                entry, session, panel,
                open_fn=lambda p: subprocess.Popen(
                    shlex.split(prefs.external_editor_cmd.replace("%f", p))))
            return

        # ── Local file: xdg-open ─────────────────────────────────────────
        if not session.is_remote:
            try:
                subprocess.Popen(["xdg-open", entry.path])
            except FileNotFoundError:
                # xdg-open not available — fall back to built-in editor
                editor = FileEditor(entry.path, session, parent=self)
                editor.show()
                self._open_windows.append(editor)
            return

        # ── Remote file: download → xdg-open → watch → auto-upload ──────
        self._open_remote_with_watcher(
            entry, session, panel,
            open_fn=lambda p: subprocess.Popen(["xdg-open", p]))

    def _open_remote_with_watcher(self, entry, session, panel: "FilePanel", open_fn):
        """Download remote file to temp, open it, watch for changes, auto-upload."""
        import tempfile
        from PyQt6.QtCore import QFileSystemWatcher

        ext  = os.path.splitext(entry.name)[1]
        tmp  = tempfile.NamedTemporaryFile(
            delete=False, suffix=ext,
            prefix=f"linuxscp_{entry.name[:16]}_")
        tmp_path = tmp.name
        tmp.close()

        self._status_main.setText(f"Downloading {entry.name}…")
        QApplication.processEvents()
        err = session.download(entry.path, tmp_path)
        if err:
            QMessageBox.critical(self, "Download failed", err)
            self._status_main.setText("Not connected" if not session.is_connected() else "")
            return

        self._status_main.setText(f"Opened {entry.name} — saves upload automatically")

        try:
            open_fn(tmp_path)
        except Exception as ex:
            # xdg-open failed — fall back to built-in editor
            editor = FileEditor(tmp_path, session, parent=self)
            remote_dir = panel.current_path()
            editor.file_saved.connect(lambda _: panel.navigate(remote_dir))
            editor.show()
            self._open_windows.append(editor)
            return

        # Watch for file changes and auto-upload
        watcher = QFileSystemWatcher([tmp_path], parent=self)
        remote_path = entry.path

        def _on_file_changed(path: str):
            if not os.path.exists(path):
                return
            err = session.upload(path, remote_path)
            if err:
                self._status_main.setText(f"Upload error: {err}")
            else:
                self._status_main.setText(f"Uploaded {entry.name}")
                panel.navigate(panel.current_path())
            # Re-add path — some editors replace the file (write+rename)
            if path not in watcher.files():
                watcher.addPath(path)

        watcher.fileChanged.connect(_on_file_changed)
        self._open_windows.append(watcher)

    def _on_entry_activated(self, entry, panel: "FilePanel"):
        """Double-click / Enter on a file."""
        session = panel._model._session
        self._open_file(entry, session, panel)

    def _edit(self):
        entries = self._active().selected_entries()
        entries = [e for e in entries if not e.is_dir and e.name != ".."]
        if not entries:
            return
        session      = self._active()._model._session
        active_panel = self._active()
        for entry in entries[:3]:
            self._open_file(entry, session, active_panel)

    # ── F2 Rename ────────────────────────────────────────────────────────

    def _rename(self):
        entries = self._active().selected_entries()
        if not entries:
            return
        entry = entries[0]
        dlg = RenameDialog(entry.name, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        new_name = dlg.new_name
        if not new_name or new_name == entry.name:
            return

        session = self._active()._model._session
        cur_dir = self._active().current_path()
        if session.is_remote:
            new_path = posixpath.join(cur_dir, new_name)
        else:
            new_path = os.path.join(cur_dir, new_name)

        err = session.rename(entry.path, new_path)
        if err:
            QMessageBox.critical(self, "Rename failed", err)
        else:
            self._active().navigate(cur_dir)

    # ── F5 Copy ──────────────────────────────────────────────────────────

    def _copy(self):
        entries = self._active().selected_entries()
        entries = [e for e in entries if e.name != ".."]
        if not entries:
            return

        src_session = self._active()._model._session
        dst_session = self._opposite()._model._session
        dst_dir     = self._opposite().current_path()

        dlg = CopyDialog("Copy", entries, dst_dir, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        dst_dir = dlg.destination
        jobs = build_transfer_jobs(entries, src_session, dst_session, dst_dir)
        if jobs:
            self._run_transfer(jobs, refresh_panel=self._opposite())

    # ── F6 Move ──────────────────────────────────────────────────────────

    def _move(self):
        entries = self._active().selected_entries()
        entries = [e for e in entries if e.name != ".."]
        if not entries:
            return

        src_session = self._active()._model._session
        dst_session = self._opposite()._model._session
        dst_dir     = self._opposite().current_path()

        dlg = CopyDialog("Move", entries, dst_dir, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        dst_dir = dlg.destination
        jobs    = build_transfer_jobs(entries, src_session, dst_session, dst_dir)
        if not jobs:
            return

        src_panel = self._active()
        src_dir   = src_panel.current_path()

        def on_all_done():
            # Delete sources after successful copy
            for job, entry in zip(jobs, entries):
                if job.status.name == "DONE":
                    src_session.delete(entry.path, entry.is_dir)
            src_panel.navigate(src_dir)

        self._run_transfer(jobs, refresh_panel=self._opposite(), on_done=on_all_done)

    # ── F7 Mkdir ─────────────────────────────────────────────────────────

    def _mkdir(self):
        dlg = MkdirDialog(parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name = dlg.dir_name
        if not name:
            return

        session = self._active()._model._session
        cur_dir = self._active().current_path()
        new_path = (posixpath.join(cur_dir, name) if session.is_remote
                    else os.path.join(cur_dir, name))

        err = session.mkdir(new_path)
        if err:
            QMessageBox.critical(self, "Create directory failed", err)
        else:
            self._active().navigate(cur_dir)

    # ── F8 Delete ────────────────────────────────────────────────────────

    def _delete(self):
        entries = self._active().selected_entries()
        entries = [e for e in entries if e.name != ".."]
        if not entries:
            return

        n     = len(entries)
        names = "\n".join(e.name for e in entries[:5])
        if n > 5:
            names += f"\n… and {n - 5} more"

        if get_prefs().confirm_delete and QMessageBox.question(
            self, "Delete",
            f"Delete the following {n} item(s)?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._active()._model._session
        cur_dir = self._active().current_path()
        errors  = []

        for entry in entries:
            err = session.delete(entry.path, entry.is_dir)
            if err:
                errors.append(f"{entry.name}: {err}")

        if errors:
            QMessageBox.critical(self, "Delete errors",
                                 "\n".join(errors[:10]))
        self._active().navigate(cur_dir)

    # ── F9 Properties ────────────────────────────────────────────────────

    def _properties(self):
        entries = self._active().selected_entries()
        if not entries:
            return
        e = entries[0]
        QMessageBox.information(self, f"Properties — {e.name}",
            f"Name:        {e.name}\n"
            f"Path:        {e.path}\n"
            f"Size:        {e.size_str}\n"
            f"Modified:    {e.modified_str}\n"
            f"Permissions: {e.permissions}\n"
            f"Owner:       {e.owner} / {e.group}"
        )

    # ── Transfer execution ────────────────────────────────────────────────

    def _run_transfer(self, jobs, refresh_panel: FilePanel = None,
                      on_done=None):
        self._queue_panel.add_jobs(jobs)
        worker = TransferWorker(jobs, parent=self)

        worker.job_started.connect(self._queue_panel.on_job_started)
        worker.job_progress.connect(self._queue_panel.on_job_progress)
        worker.job_done.connect(self._queue_panel.on_job_done)
        worker.job_failed.connect(self._queue_panel.on_job_failed)
        worker.all_done.connect(self._queue_panel.on_all_done)

        if refresh_panel:
            refresh_dir = refresh_panel.current_path()
            worker.all_done.connect(lambda: refresh_panel.navigate(refresh_dir))

        if on_done:
            worker.all_done.connect(on_done)

        # Clean up finished workers
        worker.finished.connect(lambda: self._transfer_workers.remove(worker)
                                if worker in self._transfer_workers else None)

        self._transfer_workers.append(worker)
        worker.start()

    # ── Other actions ─────────────────────────────────────────────────────

    def _refresh(self):
        self._active().navigate(self._active().current_path())

    def _select_all(self):
        self._active()._view.selectAll()

    def _unselect_all(self):
        self._active()._view.clearSelection()

    def _invert_selection(self):
        view  = self._active()._view
        model = self._active()._model
        sel   = view.selectionModel()
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            sel.select(idx, sel.SelectionFlag.Toggle | sel.SelectionFlag.Rows)

    def _synchronize(self):
        local_session  = self._left_panel._model._session
        remote_session = self._right_panel._model._session
        if not remote_session.is_remote:
            QMessageBox.information(self, "Synchronize",
                "Connect to a remote server first to synchronize directories.")
            return
        dlg = SyncDialog(
            local_session  = local_session,
            remote_session = remote_session,
            local_dir      = self._left_panel.current_path(),
            remote_dir     = self._right_panel.current_path(),
            parent         = self,
        )
        dlg.exec()

    # ── Terminal ──────────────────────────────────────────────────────────

    def _open_terminal(self):
        terminal = TerminalPanel()
        terminal.setWindowTitle("Terminal — LinuxSCP")
        terminal.resize(800, 480)
        terminal.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if self._current_session and self._current_session.is_connected():
            terminal.connect_ssh(self._current_session)
        else:
            terminal.connect_local(self._left_panel.current_path())
        terminal.show()
        self._open_windows.append(terminal)
        terminal.destroyed.connect(
            lambda: self._open_windows.remove(terminal)
            if terminal in self._open_windows else None)

    # ── Preferences ───────────────────────────────────────────────────────

    def _open_preferences(self):
        dlg = PreferencesDialog(parent=self)
        dlg.preferences_changed.connect(self._apply_preferences)
        dlg.exec()

    def _apply_preferences(self):
        prefs = get_prefs()
        # Refresh both panels (hidden-files filter may have changed)
        self._left_panel.navigate(self._left_panel.current_path())
        self._right_panel.navigate(self._right_panel.current_path())
        # Queue panel visibility
        self._queue_panel.setVisible(prefs.show_queue_panel)
        # Panel font
        if prefs.panel_font_family:
            from PyQt6.QtGui import QFont
            font = QFont(prefs.panel_font_family, prefs.panel_font_size)
            self._left_panel._view.setFont(font)
            self._right_panel._view.setFont(font)

    # ── Drag & drop handler ───────────────────────────────────────────────

    def _on_files_dropped(self, paths: list, dst_path: str):
        """Called when files are dropped onto a panel."""
        # Determine which panel is the source (the other one)
        if dst_path == self._left_panel.current_path():
            src_panel  = self._right_panel
            dst_panel  = self._left_panel
        else:
            src_panel  = self._left_panel
            dst_panel  = self._right_panel

        src_session = src_panel._model._session
        dst_session = dst_panel._model._session

        # Build FileEntry list from paths
        entries = [e for e in src_panel.selected_entries()
                   if e.path in paths and e.name != ".."]
        if not entries:
            # Fall back: use all selected entries whose paths match
            all_sel = src_panel.selected_entries()
            entries = [e for e in all_sel if e.name != ".."]
        if not entries:
            return

        dlg = CopyDialog("Copy", entries, dst_path, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        jobs = build_transfer_jobs(entries, src_session, dst_session, dlg.destination)
        if jobs:
            self._run_transfer(jobs, refresh_panel=dst_panel)

    def _about(self):
        QMessageBox.about(self, "About LinuxSCP",
            "<b>LinuxSCP</b><br>"
            "A WinSCP-compatible SFTP/SCP/FTP client for Linux.<br><br>"
            "Built with Python + PyQt6 + paramiko.<br>"
            "Phase 6 — Terminal, Preferences, Drag & Drop, Bookmarks")

    def _placeholder(self, feature: str):
        QMessageBox.information(self, "Not yet implemented",
            f"<b>{feature}</b><br><br>This feature will be available in a future phase.")

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _add_action(menu: QMenu, label: str, shortcut: str, slot) -> QAction:
        act = QAction(label, menu)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act
