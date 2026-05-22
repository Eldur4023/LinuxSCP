import ftplib
import paramiko
from PyQt6.QtCore import QThread, pyqtSignal

from linuxscp.ui.site_manager import SessionData


class ConnectWorker(QThread):
    """
    Runs the blocking connect() off the GUI thread for any protocol.

    Signals:
        connected(BaseSession)
        failed(str)
        key_passphrase_needed()   — SSH key requires passphrase
    """

    connected             = pyqtSignal(object)
    failed                = pyqtSignal(str)
    key_passphrase_needed = pyqtSignal()

    def __init__(self, data: SessionData, password: str = "",
                 key_passphrase: str = "", parent=None):
        super().__init__(parent)
        self._data          = data
        self._password      = password
        self._key_passphrase = key_passphrase

    def run(self):
        proto = self._data.protocol.upper()
        try:
            if proto in ("SFTP", "SCP"):
                session = self._connect_ssh()
            elif proto in ("FTP", "FTPS"):
                session = self._connect_ftp()
            else:
                self.failed.emit(f"Unsupported protocol: {proto}")
                return
        except Exception as e:
            self.failed.emit(str(e))
            return

        self.connected.emit(session)

    # ── SSH / SFTP ────────────────────────────────────────────────────────

    def _connect_ssh(self):
        from linuxscp.core.sftp_session import SFTPSession
        data = self._data

        session = SFTPSession(host=data.host, port=data.port, user=data.user)
        try:
            session.connect(
                password     = self._password or data.password,
                key_filename = data.key_file or "",
                timeout      = 15.0,
            )
        except paramiko.ssh_exception.PasswordRequiredException:
            # Encrypted key, no passphrase given — signal GUI to prompt
            if not self._key_passphrase:
                self.key_passphrase_needed.emit()
                return None   # worker exits; GUI re-launches with passphrase
            # Re-try with passphrase via pkey loading
            import paramiko as pm
            pkey = pm.RSAKey.from_private_key_file(
                data.key_file, password=self._key_passphrase)
            session._client = pm.SSHClient()
            session._client.load_system_host_keys()
            session._client.set_missing_host_key_policy(pm.AutoAddPolicy())
            session._client.connect(
                hostname  = data.host,
                port      = data.port,
                username  = data.user,
                pkey      = pkey,
                timeout   = 15.0,
            )
            session._sftp = session._client.open_sftp()
            try:
                session._home = session._sftp.normalize(".")
            except Exception:
                session._home = "/"
        except paramiko.AuthenticationException as e:
            raise RuntimeError(f"Authentication failed: {e}")
        except paramiko.SSHException as e:
            raise RuntimeError(f"SSH error: {e}")
        except OSError as e:
            raise RuntimeError(f"Connection error: {e}")
        return session

    # ── FTP / FTPS ────────────────────────────────────────────────────────

    def _connect_ftp(self):
        from linuxscp.core.ftp_session import FTPSession
        data = self._data

        session = FTPSession(
            host     = data.host,
            port     = data.port,
            user     = data.user,
            protocol = data.protocol.upper(),
        )
        try:
            session.connect(
                password = self._password or data.password,
                timeout  = 15.0,
            )
        except ftplib.error_perm as e:
            raise RuntimeError(f"FTP authentication failed: {e}")
        except ftplib.Error as e:
            raise RuntimeError(f"FTP error: {e}")
        except OSError as e:
            raise RuntimeError(f"Connection error: {e}")
        return session
