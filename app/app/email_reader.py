"""
Email monitor — supports both IMAP and POP3.

Protocol choice:
  protocol='imap'  → imaplib, persistent connection, folder selection supported
  protocol='pop3'  → poplib,  reconnects each poll, UIDL-based deduplication

On first connect, ALL existing messages are marked as seen (not processed).
Only messages that arrive AFTER start() is called are classified.
"""

import imaplib
import poplib
import email
import email.header
import threading
import time
from email.message import Message
from typing import Callable, Optional


class EmailMonitor:

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        folder: str = "INBOX",
        poll_interval: int = 60,
        use_ssl: bool = True,
        protocol: str = "imap",       # "imap" | "pop3"
        on_message: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ):
        self.host          = host
        self.port          = port
        self.username      = username
        self.password      = password
        self.folder        = folder
        self.poll_interval = poll_interval
        self.use_ssl       = use_ssl
        self.protocol      = protocol.lower()
        self.on_message    = on_message or (lambda m: None)
        self.on_error      = on_error  or (lambda e: None)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen_uids: set = set()
        self._initialized   = False

        self.connected           = False
        self.last_error: str     = ""
        self.messages_processed  = 0

    # Error formatting

    @staticmethod
    def _fmt_err(e: Exception) -> str:
        msg = str(e)
        if not msg or msg == "None":
            msg = type(e).__name__
        else:
            msg = f"{type(e).__name__}: {msg}"
        return msg

    # Header decoding

    def _decode_header(self, raw: str) -> str:
        parts = email.header.decode_header(raw or "")
        result = []
        for part, enc in parts:
            if isinstance(part, bytes):
                result.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                result.append(str(part))
        return "".join(result)

    def _get_body(self, msg: Message) -> str:
        """Extract plain-text or HTML body; prefer plain text."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct  = part.get_content_type()
                cd  = str(part.get("Content-Disposition", ""))
                if "attachment" in cd:
                    continue
                if ct == "text/plain":
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                elif ct == "text/html" and not body:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
        else:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors="replace")
        return body

    def _dispatch(self, uid: str, raw_bytes: bytes):
        """Parse raw RFC-822 bytes and call on_message."""
        msg = email.message_from_bytes(raw_bytes)
        self.on_message({
            "uid":    uid,
            "subject": self._decode_header(msg.get("Subject", "")),
            "sender":  self._decode_header(msg.get("From",    "")),
            "date":    msg.get("Date", ""),
            "body":    self._get_body(msg),
            "source":  "email",
        })
        self.messages_processed += 1

    # IMAP

    def _imap_connect(self):
        conn = (imaplib.IMAP4_SSL if self.use_ssl else imaplib.IMAP4)(self.host, self.port)
        conn.login(self.username, self.password)
        return conn

    def _imap_poll(self, conn):
        conn.select(self.folder, readonly=True)
        _, data = conn.search(None, "ALL")
        all_uids = set(data[0].split())

        if not self._initialized:
            self._seen_uids  = all_uids
            self._initialized = True
            return

        new_uids = all_uids - self._seen_uids
        self._seen_uids = all_uids

        for uid in sorted(new_uids):
            try:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                self._dispatch(uid.decode(), msg_data[0][1])
            except Exception as e:
                self.on_error(f"IMAP fetch error (uid {uid}): {self._fmt_err(e)}")

    def _imap_run(self):
        """IMAP main loop — persistent connection."""
        while not self._stop_event.is_set():
            try:
                conn = self._imap_connect()
                self.connected = True
                self.last_error = ""
                while not self._stop_event.is_set():
                    self._imap_poll(conn)
                    self._stop_event.wait(self.poll_interval)
                try:
                    conn.logout()
                except Exception:
                    pass
            except Exception as e:
                self.connected  = False
                self.last_error = self._fmt_err(e)
                self.on_error(f"IMAP error: {self.last_error}")
                if not self._stop_event.is_set():
                    self._stop_event.wait(30)

    # POP3

    def _pop3_connect(self):
        conn = (poplib.POP3_SSL if self.use_ssl else poplib.POP3)(self.host, self.port)
        conn.user(self.username)
        conn.pass_(self.password)
        return conn

    def _pop3_poll(self):
        """One POP3 session: connect → check new → quit."""
        conn = self._pop3_connect()
        try:
            # Use UIDL to get unique IDs
            try:
                _, uidl_lines, _ = conn.uidl()
            except poplib.error_proto:
                # Server doesn't support UIDL — fall back to count-based
                total, _ = conn.stat()
                if not self._initialized:
                    self._seen_uids  = set(range(1, total + 1))
                    self._initialized = True
                    return
                new_nums = set(range(1, total + 1)) - self._seen_uids
                self._seen_uids = set(range(1, total + 1))
                for num in sorted(new_nums):
                    try:
                        _, lines, _ = conn.retr(num)
                        self._dispatch(str(num), b"\r\n".join(lines))
                    except Exception as e:
                        self.on_error(f"POP3 fetch error (msg {num}): {self._fmt_err(e)}")
                return

            # UIDL succeeded — use string UIDs
            uid_map: dict[str, int] = {}
            for line in uidl_lines:
                parts = line.decode("utf-8", errors="replace").split()
                if len(parts) >= 2:
                    uid_map[parts[1]] = int(parts[0])

            all_uid_strs = set(uid_map)

            if not self._initialized:
                self._seen_uids   = all_uid_strs
                self._initialized = True
                return

            new_uid_strs = all_uid_strs - self._seen_uids
            self._seen_uids = all_uid_strs

            for uid_str in sorted(new_uid_strs, key=lambda u: uid_map.get(u, 0)):
                msg_num = uid_map[uid_str]
                try:
                    _, lines, _ = conn.retr(msg_num)
                    self._dispatch(uid_str, b"\r\n".join(lines))
                except Exception as e:
                    self.on_error(f"POP3 fetch error (uid {uid_str}): {self._fmt_err(e)}")
        finally:
            try:
                conn.quit()
            except Exception:
                pass

    def _pop3_run(self):
        """POP3 main loop — reconnects on every poll (POP3 is session-based)."""
        while not self._stop_event.is_set():
            try:
                self._pop3_poll()
                self.connected  = True
                self.last_error = ""
            except Exception as e:
                self.connected  = False
                self.last_error = self._fmt_err(e)
                self.on_error(f"POP3 error: {self.last_error}")
                if not self._stop_event.is_set():
                    self._stop_event.wait(30)
                continue
            self._stop_event.wait(self.poll_interval)

    # Public API

    def _run(self):
        if self.protocol == "pop3":
            self._pop3_run()
        else:
            self._imap_run()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._initialized = False
        self._seen_uids   = set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.connected = False

    # Batch fetch (for one-shot analysis)

    def fetch_messages(
        self,
        limit: int = 200,
        date_from: str = None,
        date_to: str = None,
    ) -> list[dict]:
        """Fetch messages within the given date range (ISO 'YYYY-MM-DD', inclusive).
        `limit` is a safety cap on the number of messages returned."""
        if self.protocol == "pop3":
            return self._pop3_fetch(limit, date_from, date_to)
        else:
            return self._imap_fetch(limit, date_from, date_to)

    def _imap_fetch(self, limit: int, date_from: str = None, date_to: str = None) -> list[dict]:
        from datetime import datetime, timedelta
        conn = self._imap_connect()
        try:
            conn.select(self.folder, readonly=True)
            criteria_parts = []
            if date_from:
                dt = datetime.strptime(date_from, "%Y-%m-%d")
                criteria_parts.append(f'SINCE {dt.strftime("%d-%b-%Y")}')
            if date_to:
                dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
                criteria_parts.append(f'BEFORE {dt.strftime("%d-%b-%Y")}')
            criteria = " ".join(criteria_parts) if criteria_parts else "ALL"
            _, data = conn.search(None, criteria)
            all_uids = data[0].split()
            to_fetch = all_uids[-limit:] if limit and limit < len(all_uids) else all_uids
            messages = []
            for uid in to_fetch:
                try:
                    _, msg_data = conn.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    messages.append({
                        "uid":     uid.decode(),
                        "subject": self._decode_header(msg.get("Subject", "")),
                        "sender":  self._decode_header(msg.get("From",    "")),
                        "date":    msg.get("Date", ""),
                        "body":    self._get_body(msg),
                        "source":  "email",
                    })
                except Exception:
                    pass
            return messages
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _pop3_fetch(self, limit: int, date_from: str = None, date_to: str = None) -> list[dict]:
        from datetime import datetime
        from email.utils import parsedate_to_datetime
        conn = self._pop3_connect()
        try:
            total, _ = conn.stat()
            if total == 0:
                return []
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
            dt_to   = datetime.strptime(date_to,   "%Y-%m-%d").date() if date_to   else None
            messages = []
            for num in range(total, 0, -1):
                try:
                    _, lines, _ = conn.retr(num)
                    raw = b"\r\n".join(lines)
                    msg = email.message_from_bytes(raw)
                    date_str = msg.get("Date", "")
                    try:
                        msg_date = parsedate_to_datetime(date_str).date()
                        if dt_to and msg_date > dt_to:
                            continue
                        if dt_from and msg_date < dt_from:
                            break   # messages ordered oldest→newest; stop here
                    except Exception:
                        pass        # unparseable date — include the message
                    messages.append({
                        "uid":     str(num),
                        "subject": self._decode_header(msg.get("Subject", "")),
                        "sender":  self._decode_header(msg.get("From",    "")),
                        "date":    date_str,
                        "body":    self._get_body(msg),
                        "source":  "email",
                    })
                    if limit and len(messages) >= limit:
                        break
                except Exception:
                    pass
            return list(reversed(messages))   # restore chronological order
        finally:
            try:
                conn.quit()
            except Exception:
                pass

    def test_connection(self) -> tuple[bool, str]:
        """Synchronous connection test (no background thread)."""
        try:
            if self.protocol == "pop3":
                conn = self._pop3_connect()
                total, size = conn.stat()
                conn.quit()
                return True, f"POP3 OK — {total} message(s) in mailbox ({size} bytes total)"
            else:
                conn = self._imap_connect()
                conn.select(self.folder, readonly=True)
                conn.logout()
                return True, f"IMAP OK — folder '{self.folder}' accessible"
        except Exception as e:
            return False, self._fmt_err(e)

    @property
    def status(self) -> dict:
        return {
            "connected":          self.connected,
            "running":            bool(self._thread and self._thread.is_alive()),
            "messages_processed": self.messages_processed,
            "last_error":         self.last_error,
            "protocol":           self.protocol.upper(),
            "host":               self.host,
            "username":           self.username,
            "folder":             self.folder if self.protocol == "imap" else "—",
            "poll_interval":      self.poll_interval,
        }
