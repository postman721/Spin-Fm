"""Optional MPRIS 2 service for the embedded Spin FM audio player.

Wayland_OSD delegates media commands to ``playerctl``.  Direct OSD socket
messages can show a popup, but only an MPRIS service makes Spin FM discoverable
as an active desktop media player.  This module uses the Qt D-Bus binding that
ships with PyQt and intentionally treats every registration or transport failure
as a non-fatal feature disablement.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .audio import is_supported_audio_file
from .config import APP_ID, APP_NAME
from .qt_compat import (
    QApplication,
    QObject,
    QtCore,
    USING_PYQT6,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

logger = logging.getLogger(__name__)

SERVICE_PREFIX = "org.mpris.MediaPlayer2.spin_fm"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_INTERFACE = "org.mpris.MediaPlayer2"
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
NO_TRACK_PATH = "/org/mpris/MediaPlayer2/TrackList/NoTrack"

SUPPORTED_MIME_TYPES = (
    "audio/aac",
    "audio/flac",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/opus",
    "audio/wav",
    "audio/webm",
    "audio/x-aiff",
    "audio/x-ms-wma",
)

try:
    if USING_PYQT6:
        from PyQt6 import QtDBus  # type: ignore[import-not-found]
    else:
        from PyQt5 import QtDBus  # type: ignore[import-not-found]
except Exception:  # QtDBus is optional at runtime.
    QtDBus = None  # type: ignore[assignment]


def clamp_volume(value: object) -> float:
    """Return a finite MPRIS volume in the inclusive 0.0..1.0 range."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return max(0.0, min(1.0, number))


def track_id_for_path(path: str | os.PathLike[str] | None) -> str:
    """Create a stable D-Bus object path for a local track."""
    if not path:
        return NO_TRACK_PATH
    try:
        absolute = os.path.abspath(os.path.expanduser(os.fspath(path)))
    except (TypeError, ValueError):
        return NO_TRACK_PATH
    digest = hashlib.sha256(absolute.encode("utf-8", "surrogatepass")).hexdigest()[:24]
    return f"/net/techtimejourney/SpinFM/track/{digest}"


def metadata_for_track(path: str, duration_ms: int = 0) -> dict[str, object]:
    """Return the toolkit-neutral portion of an MPRIS metadata map."""
    if not path:
        return {}
    try:
        absolute = os.path.abspath(os.path.expanduser(os.fspath(path)))
    except (TypeError, ValueError):
        return {}

    metadata: dict[str, object] = {
        "mpris:trackid": track_id_for_path(absolute),
        "xesam:title": os.path.basename(absolute) or APP_NAME,
    }
    try:
        metadata["xesam:url"] = Path(absolute).as_uri()
    except (OSError, ValueError):
        pass
    try:
        duration = max(0, int(duration_ms))
    except (TypeError, ValueError, OverflowError):
        duration = 0
    if duration:
        metadata["mpris:length"] = duration * 1_000
    return metadata


def local_path_from_uri(uri: object) -> str | None:
    """Convert a local path or ``file://`` URI to an absolute path."""
    try:
        value = str(uri).strip()
    except Exception:
        return None
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme.casefold() != "file":
        return None
    if parsed.scheme.casefold() == "file":
        if parsed.netloc not in {"", "localhost"}:
            return None
        value = unquote(parsed.path)
    try:
        return os.path.abspath(os.path.expanduser(value))
    except (TypeError, ValueError):
        return None


def _qt_int64(value: int) -> object:
    """Return a QVariant explicitly typed as signed 64-bit when possible."""
    try:
        variant = QtCore.QVariant(int(value))
        if USING_PYQT6:
            enum_value = QtCore.QMetaType.Type.LongLong
            type_id = getattr(enum_value, "value", enum_value)
            variant.convert(QtCore.QMetaType(int(type_id)))
        else:
            long_long = getattr(QtCore.QVariant, "LongLong", QtCore.QMetaType.LongLong)
            variant.convert(long_long)
        return variant
    except Exception:
        return int(value)


if QtDBus is not None:

    class _RootAdaptorBase(QtDBus.QDBusAbstractAdaptor):
        """Implementation of ``org.mpris.MediaPlayer2``."""

        def __init__(self, service: "MPRISService") -> None:
            super().__init__(service)
            self._service = service

        @pyqtSlot()
        def Raise(self) -> None:  # noqa: N802 - MPRIS API
            self._service.request_raise()

        @pyqtSlot()
        def Quit(self) -> None:  # noqa: N802 - MPRIS API
            self._service.request_quit()

        @pyqtProperty(bool, constant=True)
        def CanQuit(self) -> bool:  # noqa: N802 - MPRIS API
            return True

        @pyqtProperty(bool)
        def Fullscreen(self) -> bool:  # noqa: N802 - MPRIS API
            return False

        @Fullscreen.setter
        def Fullscreen(self, _value: bool) -> None:  # noqa: N802 - MPRIS API
            return

        @pyqtProperty(bool, constant=True)
        def CanSetFullscreen(self) -> bool:  # noqa: N802 - MPRIS API
            return False

        @pyqtProperty(bool, constant=True)
        def CanRaise(self) -> bool:  # noqa: N802 - MPRIS API
            return True

        @pyqtProperty(bool, constant=True)
        def HasTrackList(self) -> bool:  # noqa: N802 - MPRIS API
            return False

        @pyqtProperty(str, constant=True)
        def Identity(self) -> str:  # noqa: N802 - MPRIS API
            return APP_NAME

        @pyqtProperty(str, constant=True)
        def DesktopEntry(self) -> str:  # noqa: N802 - MPRIS API
            return APP_ID

        @pyqtProperty("QStringList", constant=True)
        def SupportedUriSchemes(self) -> list[str]:  # noqa: N802 - MPRIS API
            return ["file"]

        @pyqtProperty("QStringList", constant=True)
        def SupportedMimeTypes(self) -> list[str]:  # noqa: N802 - MPRIS API
            return list(SUPPORTED_MIME_TYPES)


    class _PlayerAdaptorBase(QtDBus.QDBusAbstractAdaptor):
        """Implementation of ``org.mpris.MediaPlayer2.Player``."""

        Seeked = pyqtSignal("qlonglong")

        def __init__(self, service: "MPRISService") -> None:
            super().__init__(service)
            self._service = service

        @pyqtSlot()
        def Next(self) -> None:  # noqa: N802 - MPRIS API
            return

        @pyqtSlot()
        def Previous(self) -> None:  # noqa: N802 - MPRIS API
            return

        @pyqtSlot()
        def Pause(self) -> None:  # noqa: N802 - MPRIS API
            self._service.request_pause()

        @pyqtSlot()
        def PlayPause(self) -> None:  # noqa: N802 - MPRIS API
            self._service.request_play_pause()

        @pyqtSlot()
        def Stop(self) -> None:  # noqa: N802 - MPRIS API
            self._service.request_stop()

        @pyqtSlot()
        def Play(self) -> None:  # noqa: N802 - MPRIS API
            self._service.request_play()

        @pyqtSlot("qlonglong")
        def Seek(self, offset: int) -> None:  # noqa: N802 - MPRIS API
            self._service.request_seek(offset)

        @pyqtSlot("QDBusObjectPath", "qlonglong")
        def SetPosition(self, track_id: Any, position: int) -> None:  # noqa: N802
            self._service.request_set_position(track_id, position)

        @pyqtSlot(str)
        def OpenUri(self, uri: str) -> None:  # noqa: N802 - MPRIS API
            self._service.request_open_uri(uri)

        @pyqtProperty(str)
        def PlaybackStatus(self) -> str:  # noqa: N802 - MPRIS API
            return self._service.playback_status

        @pyqtProperty(str)
        def LoopStatus(self) -> str:  # noqa: N802 - MPRIS API
            return "None"

        @LoopStatus.setter
        def LoopStatus(self, _value: str) -> None:  # noqa: N802 - MPRIS API
            return

        @pyqtProperty(float)
        def Rate(self) -> float:  # noqa: N802 - MPRIS API
            return 1.0

        @Rate.setter
        def Rate(self, _value: float) -> None:  # noqa: N802 - MPRIS API
            return

        @pyqtProperty(bool)
        def Shuffle(self) -> bool:  # noqa: N802 - MPRIS API
            return False

        @Shuffle.setter
        def Shuffle(self, _value: bool) -> None:  # noqa: N802 - MPRIS API
            return

        @pyqtProperty("QVariantMap")
        def Metadata(self) -> dict[str, object]:  # noqa: N802 - MPRIS API
            return self._service.dbus_metadata()

        @pyqtProperty(float)
        def Volume(self) -> float:  # noqa: N802 - MPRIS API
            return self._service.volume

        @Volume.setter
        def Volume(self, value: float) -> None:  # noqa: N802 - MPRIS API
            self._service.request_volume(value)

        @pyqtProperty("qlonglong")
        def Position(self) -> int:  # noqa: N802 - MPRIS API
            return self._service.position_microseconds()

        @pyqtProperty(float, constant=True)
        def MinimumRate(self) -> float:  # noqa: N802 - MPRIS API
            return 1.0

        @pyqtProperty(float, constant=True)
        def MaximumRate(self) -> float:  # noqa: N802 - MPRIS API
            return 1.0

        @pyqtProperty(bool, constant=True)
        def CanGoNext(self) -> bool:  # noqa: N802 - MPRIS API
            return False

        @pyqtProperty(bool, constant=True)
        def CanGoPrevious(self) -> bool:  # noqa: N802 - MPRIS API
            return False

        @pyqtProperty(bool)
        def CanPlay(self) -> bool:  # noqa: N802 - MPRIS API
            return self._service.has_track

        @pyqtProperty(bool)
        def CanPause(self) -> bool:  # noqa: N802 - MPRIS API
            return self._service.has_track

        @pyqtProperty(bool)
        def CanSeek(self) -> bool:  # noqa: N802 - MPRIS API
            return self._service.seekable

        @pyqtProperty(bool, constant=True)
        def CanControl(self) -> bool:  # noqa: N802 - MPRIS API
            return True


    if USING_PYQT6:

        @QtCore.pyqtClassInfo("D-Bus Interface", ROOT_INTERFACE)
        class _RootAdaptor(_RootAdaptorBase):
            pass

        @QtCore.pyqtClassInfo("D-Bus Interface", PLAYER_INTERFACE)
        class _PlayerAdaptor(_PlayerAdaptorBase):
            pass

    else:

        class _RootAdaptor(_RootAdaptorBase):
            QtCore.Q_CLASSINFO("D-Bus Interface", ROOT_INTERFACE)

        class _PlayerAdaptor(_PlayerAdaptorBase):
            QtCore.Q_CLASSINFO("D-Bus Interface", PLAYER_INTERFACE)

else:
    _RootAdaptor = None  # type: ignore[assignment,misc]
    _PlayerAdaptor = None  # type: ignore[assignment,misc]


class MPRISService(QObject):
    """Failure-isolated MPRIS facade owned by ``AudioPlayerWidget``."""

    availability_changed = pyqtSignal(bool, str)

    def __init__(self, player_widget: Any, parent: QObject | None = None) -> None:
        super().__init__(parent or player_widget)
        self._player_widget = player_widget
        self._connection: Any = None
        self._root_adaptor: Any = None
        self._player_adaptor: Any = None
        self._registered = False
        self._service_name = ""
        self._path = ""
        self._duration_ms = 0
        self._metadata: dict[str, object] = {}
        self._playback_status = "Stopped"
        self._seekable = False
        self._volume = 0.72

    @property
    def available(self) -> bool:
        return bool(self._registered and self._connection is not None)

    @property
    def service_name(self) -> str:
        return self._service_name

    @property
    def has_track(self) -> bool:
        return bool(self._path)

    @property
    def seekable(self) -> bool:
        return bool(self._seekable and self.has_track)

    @property
    def playback_status(self) -> str:
        return self._playback_status

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def track_id(self) -> str:
        return str(self._metadata.get("mpris:trackid", NO_TRACK_PATH))

    def _register(self) -> bool:
        if self.available:
            return True
        if QtDBus is None or _RootAdaptor is None or _PlayerAdaptor is None:
            return False

        connection: Any = None
        object_registered = False
        try:
            connection = QtDBus.QDBusConnection.sessionBus()
            if not connection.isConnected():
                return False

            root_adaptor = _RootAdaptor(self)
            player_adaptor = _PlayerAdaptor(self)
            options = getattr(QtDBus.QDBusConnection, "ExportAdaptors", None)
            if options is None:
                options = QtDBus.QDBusConnection.RegisterOption.ExportAdaptors
            object_registered = bool(connection.registerObject(OBJECT_PATH, self, options))
            if not object_registered:
                return False

            candidates = (
                SERVICE_PREFIX,
                f"{SERVICE_PREFIX}.instance{os.getpid()}",
            )
            service_name = next(
                (name for name in candidates if connection.registerService(name)), ""
            )
            if not service_name:
                connection.unregisterObject(OBJECT_PATH)
                return False

            self._connection = connection
            self._root_adaptor = root_adaptor
            self._player_adaptor = player_adaptor
            self._service_name = service_name
            self._registered = True
            self.availability_changed.emit(True, service_name)
            return True
        except Exception:
            if connection is not None and object_registered:
                try:
                    connection.unregisterObject(OBJECT_PATH)
                except Exception:
                    pass
            logger.debug("MPRIS registration is unavailable", exc_info=True)
            self._connection = None
            self._root_adaptor = None
            self._player_adaptor = None
            self._service_name = ""
            self._registered = False
            return False

    def dbus_metadata(self) -> dict[str, object]:
        """Return metadata with D-Bus-specific value types."""
        metadata = dict(self._metadata)
        if not metadata or QtDBus is None:
            return metadata
        try:
            metadata["mpris:trackid"] = QtDBus.QDBusObjectPath(self.track_id)
        except Exception:
            pass
        if "mpris:length" in metadata:
            metadata["mpris:length"] = _qt_int64(int(metadata["mpris:length"]))
        return metadata

    def set_track(self, path: str, duration_ms: int = 0) -> None:
        try:
            absolute = os.path.abspath(os.path.expanduser(os.fspath(path)))
        except (TypeError, ValueError):
            absolute = ""
        old_has_track = self.has_track
        self._path = absolute
        try:
            self._duration_ms = max(0, int(duration_ms))
        except (TypeError, ValueError, OverflowError):
            self._duration_ms = 0
        self._metadata = metadata_for_track(absolute, self._duration_ms)
        self._register()

        changes: dict[str, object] = {"Metadata": self.dbus_metadata()}
        if old_has_track != self.has_track:
            changes["CanPlay"] = self.has_track
            changes["CanPause"] = self.has_track
        self._emit_player_properties(changes)

    def clear_track(self) -> None:
        had_track = self.has_track
        self._path = ""
        self._duration_ms = 0
        self._metadata = {}
        self._seekable = False
        self._playback_status = "Stopped"
        changes: dict[str, object] = {
            "Metadata": {},
            "PlaybackStatus": "Stopped",
            "CanSeek": False,
        }
        if had_track:
            changes["CanPlay"] = False
            changes["CanPause"] = False
        self._emit_player_properties(changes)
        self._unregister()

    def set_duration(self, duration_ms: int) -> None:
        try:
            duration = max(0, int(duration_ms))
        except (TypeError, ValueError, OverflowError):
            duration = 0
        if duration == self._duration_ms:
            return
        self._duration_ms = duration
        if self._path:
            self._metadata = metadata_for_track(self._path, duration)
            self._emit_player_properties({"Metadata": self.dbus_metadata()})

    def set_playback_status(self, status: str, *, force: bool = False) -> None:
        normalized = str(status).title()
        if normalized not in {"Playing", "Paused", "Stopped"}:
            normalized = "Stopped"
        if not force and normalized == self._playback_status:
            return
        self._playback_status = normalized
        if self.has_track:
            self._register()
        self._emit_player_properties({"PlaybackStatus": normalized})

    def set_seekable(self, seekable: bool) -> None:
        value = bool(seekable and self.has_track)
        if value == self._seekable:
            return
        self._seekable = value
        self._emit_player_properties({"CanSeek": value})

    def set_volume(self, value: object) -> None:
        normalized = clamp_volume(value)
        if abs(normalized - self._volume) < 0.0005:
            return
        self._volume = normalized
        self._emit_player_properties({"Volume": normalized})

    def position_microseconds(self) -> int:
        try:
            return max(0, int(self._player_widget.current_position())) * 1_000
        except Exception:
            return 0

    def emit_seeked(self, position_ms: int) -> None:
        try:
            value = max(0, int(position_ms)) * 1_000
        except (TypeError, ValueError, OverflowError):
            return
        if self._player_adaptor is not None:
            try:
                self._player_adaptor.Seeked.emit(value)
            except Exception:
                logger.debug("Unable to emit the MPRIS Seeked signal", exc_info=True)

    def _emit_player_properties(self, changes: dict[str, object]) -> None:
        if not changes or not self.available or QtDBus is None:
            return
        try:
            # A QVariantMap already provides the one variant layer required by
            # the ``a{sv}`` PropertiesChanged signature. QDBusVariant here would
            # create a nested variant that some MPRIS consumers reject.
            wrapped = {
                str(name): QtCore.QVariant(value)
                for name, value in changes.items()
            }
            message = QtDBus.QDBusMessage.createSignal(
                OBJECT_PATH,
                PROPERTIES_INTERFACE,
                "PropertiesChanged",
            )
            message.setArguments([PLAYER_INTERFACE, wrapped, []])
            self._connection.send(message)
        except Exception:
            logger.debug("Unable to emit MPRIS property changes", exc_info=True)

    def request_play(self) -> None:
        self._safe_call("play")

    def request_pause(self) -> None:
        self._safe_call("pause")

    def request_play_pause(self) -> None:
        self._safe_call("toggle_playback")

    def request_stop(self) -> None:
        self._safe_call("stop")

    def request_seek(self, offset_microseconds: int) -> None:
        try:
            offset_ms = int(offset_microseconds) // 1_000
        except (TypeError, ValueError, OverflowError):
            return
        self._safe_call("seek_relative", offset_ms)

    def request_set_position(self, track_id: Any, position_microseconds: int) -> None:
        try:
            supplied = track_id.path() if hasattr(track_id, "path") else str(track_id)
        except Exception:
            return
        if supplied != self.track_id:
            return
        try:
            position_ms = max(0, int(position_microseconds) // 1_000)
        except (TypeError, ValueError, OverflowError):
            return
        self._safe_call("set_position", position_ms)

    def request_open_uri(self, uri: object) -> None:
        path = local_path_from_uri(uri)
        if path and is_supported_audio_file(path):
            self._safe_call("play_file", path)

    def request_volume(self, value: object) -> None:
        self._safe_call("set_volume_fraction", clamp_volume(value))

    def request_raise(self) -> None:
        try:
            window = self._player_widget.window()
            if window is None:
                return
            window.showNormal()
            window.show()
            window.raise_()
            window.activateWindow()
        except Exception:
            logger.debug("Unable to raise Spin FM through MPRIS", exc_info=True)

    def request_quit(self) -> None:
        try:
            window = self._player_widget.window()
            if window is not None:
                window.close()
                return
            application = QApplication.instance()
            if application is not None:
                application.quit()
        except Exception:
            logger.debug("Unable to close Spin FM through MPRIS", exc_info=True)

    def _safe_call(self, method_name: str, *args: object) -> None:
        try:
            method = getattr(self._player_widget, method_name, None)
            if callable(method):
                method(*args)
        except Exception:
            logger.debug("MPRIS callback %s failed", method_name, exc_info=True)

    def _unregister(self) -> None:
        connection = self._connection
        service_name = self._service_name
        was_available = self.available
        self._registered = False
        self._connection = None
        self._service_name = ""
        if connection is not None:
            try:
                connection.unregisterObject(OBJECT_PATH)
            except Exception:
                pass
            if service_name:
                try:
                    connection.unregisterService(service_name)
                except Exception:
                    pass
        self._root_adaptor = None
        self._player_adaptor = None
        if was_available:
            try:
                self.availability_changed.emit(False, "")
            except Exception:
                pass

    def shutdown(self) -> None:
        self._unregister()
