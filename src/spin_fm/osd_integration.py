"""Optional, failure-isolated integration with postman721/Wayland_OSD.

Wayland_OSD exposes a newline-delimited JSON protocol over a Unix-domain
socket. Spin FM uses it only in a Wayland session and only when the executable
or a live daemon socket is detected. Every public operation is best-effort: a
missing executable, an unavailable daemon, a stale socket, malformed settings,
or a launch failure never interrupts audio playback.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SOCKET_NAME = "wayland-volume-osd.sock"
DEFAULT_COMMAND = "wayland-volume-osd"
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
_FORCE_VALUES = {"force", "always"}
_VALID_THEMES = {"dark", "blue", "grey", "wood"}


class WaylandOSDBridge:
    """Send non-fatal media and volume notifications to Wayland_OSD.

    The bridge deliberately has no Qt dependency, so detection and protocol
    behavior can be tested on minimal build hosts. It never invokes a shell.
    Availability checks are throttled, which lets a daemon or executable appear
    after Spin FM starts without repeatedly probing the filesystem on every UI
    event.
    """

    def __init__(
        self,
        command: str | os.PathLike[str] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        socket_timeout: float = 0.08,
        refresh_interval: float = 4.0,
    ) -> None:
        # Start fully disabled. Detection is wrapped so unusual environment
        # mappings, broken PATH helpers, or filesystem errors cannot prevent the
        # audio widget from being constructed.
        self._environ: dict[str, str] = {}
        self._socket_timeout = 0.08
        self._refresh_interval = 4.0
        self._last_detection_at = 0.0
        self._last_payload: dict[str, Any] | None = None
        self._last_sent_at = 0.0
        self._last_start_attempt = 0.0
        self._requested_command: str | os.PathLike[str] | None = command
        self.last_error = ""
        self._enabled = False
        self._wayland_session = False
        self._socket_path = Path("/tmp") / SOCKET_NAME
        self.command: str | None = None
        self.theme = "dark"
        self.available = False

        try:
            self._environ = dict(os.environ if environ is None else environ)
            self._socket_timeout = max(0.01, min(0.35, float(socket_timeout)))
            self._refresh_interval = max(0.25, min(60.0, float(refresh_interval)))

            mode = str(self._environ.get("SPIN_FM_WAYLAND_OSD", "auto")).strip().lower()
            self._enabled = mode not in _FALSE_VALUES
            self._wayland_session = mode in _FORCE_VALUES or self._is_wayland_session()
            self._socket_path = self._runtime_dir() / SOCKET_NAME
            self._requested_command = command or self._environ.get(
                "SPIN_FM_WAYLAND_OSD_COMMAND", DEFAULT_COMMAND
            )
            self.theme = self._load_theme()
            self.refresh_availability(force=True)
        except Exception as exc:
            self.last_error = str(exc)
            self.available = False

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def connected(self) -> bool:
        """Return whether the expected path is currently a Unix socket."""
        return bool(self.available and self._socket_is_unix())

    def refresh_availability(self, *, force: bool = False) -> bool:
        """Refresh optional integration detection without raising exceptions.

        An installed executable is sufficient because Spin FM can ask it to
        start its daemon. Without an executable, the socket must both be a Unix
        socket and accept a protocol ping; a regular file or stale socket never
        enables the integration badge.
        """
        try:
            if not self._enabled or not self._wayland_session:
                self.available = False
                return False

            now = time.monotonic()
            if not force and now - self._last_detection_at < self._refresh_interval:
                return bool(self.available)
            self._last_detection_at = now

            self.command = self._resolve_command(self._requested_command)
            if self.command is not None:
                self.available = True
                return True

            if not self._socket_is_unix():
                self.available = False
                return False

            self.available = self._send_payload({"type": "ping"})
            if self.available:
                self.last_error = ""
            return bool(self.available)
        except Exception as exc:
            self.last_error = str(exc)
            self.available = False
            return False

    def notify_media(
        self,
        state: str,
        track: str = "",
        *,
        position_ms: int = 0,
        duration_ms: int = 0,
    ) -> bool:
        """Show media state and, when known, playback progress."""
        try:
            title = self._clean_text(state, fallback="Media")
            detail = self._clean_text(track, fallback="Spin FM")
            duration = max(0, int(duration_ms))
            position = max(0, int(position_ms))
            if duration > 0:
                level = round(min(position, duration) * 100 / duration)
            elif title.lower() in {"playing", "paused", "loading"}:
                level = 100
            else:
                level = 0

            return self._notify(
                {
                    "type": "show",
                    "mode": "media",
                    "title": title,
                    "detail": detail,
                    "level": max(0, min(100, int(level))),
                    "theme": self.theme,
                }
            )
        except Exception as exc:  # Integration must never affect playback.
            self.last_error = str(exc)
            return False

    def notify_volume(self, volume: int, muted: bool, track: str = "") -> bool:
        """Show Spin FM's player volume without changing system volume."""
        try:
            level = max(0, min(100, int(volume)))
            is_muted = bool(muted)
            return self._notify(
                {
                    "type": "show",
                    "mode": "volume",
                    "title": "Muted" if is_muted else f"Volume: {level}%",
                    "detail": self._clean_text(track, fallback="Spin FM"),
                    "level": 0 if is_muted else level,
                    "muted": is_muted,
                    "theme": self.theme,
                }
            )
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def ping(self) -> bool:
        """Check the daemon without raising an exception or starting it."""
        try:
            if not self.refresh_availability():
                return False
            return self._send_payload({"type": "ping"})
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def _notify(self, payload: dict[str, Any]) -> bool:
        if not self.refresh_availability():
            return False

        try:
            now = time.monotonic()
            if payload == self._last_payload and now - self._last_sent_at < 0.18:
                return True

            if self._send_payload(payload):
                self._last_payload = dict(payload)
                self._last_sent_at = now
                self.last_error = ""
                return True

            # Match Wayland_OSD's client behavior: when the program is installed
            # but its socket is unavailable, start the daemon non-blockingly and
            # let the Qt-side retry timer resend the payload. Launch attempts are
            # throttled so repeated slider events cannot spawn process storms.
            if self.command is None:
                self.available = False
            self._start_daemon_if_needed(now)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def _send_payload(self, payload: dict[str, Any]) -> bool:
        data = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._socket_timeout)
                client.connect(str(self._socket_path))
                client.sendall(data)
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return False

    def _socket_is_unix(self) -> bool:
        try:
            return stat.S_ISSOCK(self._socket_path.lstat().st_mode)
        except FileNotFoundError:
            return False
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return False

    def _start_daemon_if_needed(self, now: float | None = None) -> bool:
        if self.command is None:
            return False
        current = time.monotonic() if now is None else float(now)
        if self._last_start_attempt and current - self._last_start_attempt < 8.0:
            return False
        self._last_start_attempt = current

        try:
            subprocess.Popen(
                [self.command, "--theme", self.theme, "daemon"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return False

    def _is_wayland_session(self) -> bool:
        session_type = str(self._environ.get("XDG_SESSION_TYPE", "")).lower()
        return bool(self._environ.get("WAYLAND_DISPLAY") or session_type == "wayland")

    def _runtime_dir(self) -> Path:
        raw = self._environ.get("XDG_RUNTIME_DIR")
        if raw:
            try:
                return Path(raw)
            except (TypeError, ValueError, OSError):
                pass
        return Path("/tmp") / f"wayland-volume-osd-{os.getuid()}"

    def _resolve_command(self, command: str | os.PathLike[str] | None) -> str | None:
        if not command:
            return None
        try:
            raw = os.path.expanduser(os.fspath(command).strip())
        except (TypeError, ValueError):
            return None
        if not raw:
            return None

        try:
            if os.path.sep in raw:
                absolute = os.path.abspath(raw)
                if os.path.isfile(absolute) and os.access(absolute, os.X_OK):
                    return absolute
                return None
            search_path = self._environ.get("PATH")
            if search_path is None:
                return shutil.which(raw)
            return shutil.which(raw, path=str(search_path))
        except (OSError, TypeError, ValueError):
            return None

    def _load_theme(self) -> str:
        explicit = (
            str(self._environ.get("SPIN_FM_WAYLAND_OSD_THEME", "")).strip().lower()
        )
        if explicit in _VALID_THEMES:
            return explicit

        config_home = self._environ.get("XDG_CONFIG_HOME")
        home = self._environ.get("HOME")
        bases: list[Path] = []
        if config_home:
            bases.append(Path(config_home))
        if home:
            bases.append(Path(home) / ".config")
        else:
            try:
                bases.append(Path.home() / ".config")
            except RuntimeError:
                pass

        candidates: list[Path] = []
        for base in bases:
            candidates.extend(
                (
                    base / "volume-osd" / "osd.conf",
                    base / "wayland-volume-osd" / "config",
                    base / "osd.conf",
                )
            )

        for path in dict.fromkeys(candidates):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            for raw_line in lines:
                line = raw_line.split("#", 1)[0].strip()
                if "=" not in line:
                    continue
                key, value = (part.strip().lower() for part in line.split("=", 1))
                if key == "theme" and value in _VALID_THEMES:
                    return value
        return "dark"

    @staticmethod
    def _clean_text(value: Any, *, fallback: str) -> str:
        try:
            text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        except Exception:
            text = ""
        if not text:
            text = fallback
        return text[:240]
