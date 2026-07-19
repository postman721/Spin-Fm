"""Lazy-loaded, seekable audio player used by Spin FM.

Qt Multimedia is imported only after a supported audio file is activated.  The
optional Wayland_OSD bridge is also best-effort: missing packages, stale sockets,
and daemon failures never prevent local or external playback.
"""

from __future__ import annotations

import os
from typing import Any

from .audio import format_milliseconds, is_supported_audio_file
from .config import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from .mpris import MPRISService
from .osd_integration import WaylandOSDBridge
from .qt_compat import (
    USING_PYQT6,
    QFrame,
    QHBoxLayout,
    QIcon,
    QLabel,
    QSettings,
    QSize,
    QSizePolicy,
    QSlider,
    QStyle,
    Qt,
    QtCore,
    QToolButton,
    QVBoxLayout,
    pyqtSignal,
)


class SeekSlider(QSlider):
    """Horizontal slider that also jumps when its groove is clicked."""

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        try:
            is_left_click = event.button() == Qt.LeftButton
        except Exception:
            is_left_click = False

        if is_left_click and self.isEnabled() and self.maximum() > self.minimum():
            try:
                x = float(event.position().x())
            except Exception:
                try:
                    x = float(event.x())
                except Exception:
                    x = -1.0

            width = max(1.0, float(self.width()))
            span = self.maximum() - self.minimum()
            current_x = (self.value() - self.minimum()) * width / span

            # Preserve normal handle dragging. A click elsewhere in the groove
            # becomes an immediate, exact seek and is handled through
            # valueChanged by AudioPlayerWidget.
            if x >= 0.0 and abs(x - current_x) > 13.0:
                ratio = max(0.0, min(1.0, x / width))
                self.setValue(self.minimum() + round(span * ratio))
                event.accept()
                return

        super().mousePressEvent(event)


class AudioPlayerWidget(QFrame):
    """A one-track player with robust seeking, volume, and OSD feedback."""

    status_message = pyqtSignal(str)
    open_externally_requested = pyqtSignal(str)

    SEEK_STEP_MS = 10_000
    OSD_RETRY_DELAYS_MS = (240, 520, 920)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("audioPlayer")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self._osd = WaylandOSDBridge()
        self._player: Any = None
        self._audio_output: Any = None
        self._media_player_class: Any = None
        self._media_content_class: Any = None
        self._current_path = ""
        self._track_name = ""
        self._duration = 0
        self._seeking = False
        self._updating_seek_slider = False
        self._muted = False
        self._last_nonzero_volume = 72
        self._backend_error = ""
        self._backend_unavailable = False
        # Track the state accepted by the backend instead of relying solely on
        # playbackState()/state(). Some multimedia backends report transitions
        # late (or not at all), which previously made Alt+P call play() again
        # while audio was already playing.
        self._playback_requested = False
        self._hide_after_animation = False
        self._suppress_state_notifications = False
        self._pending_osd_media: tuple[str, str, int, int] | None = None
        self._osd_media_retry_index = 0
        self._osd_volume_retry_index = 0
        self._pending_seek_heading = "Seeking"
        self._mpris = MPRISService(self, self)

        self._build_ui()
        self._build_animation()
        self._build_timers()
        self._set_stopped_ui()

    @property
    def current_path(self) -> str:
        return self._current_path

    @property
    def backend_error(self) -> str:
        return self._backend_error

    @property
    def osd_available(self) -> bool:
        try:
            refresh = getattr(self._osd, "refresh_availability", None)
            available = (
                bool(refresh()) if callable(refresh) else bool(self._osd.available)
            )
        except Exception:
            available = False

        badge = getattr(self, "osd_badge", None)
        if badge is not None:
            try:
                badge.setVisible(available)
            except Exception:
                pass
        return available

    # ------------------------------------------------------------------
    # User interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        layout.addLayout(top_row)

        self.music_label = QLabel("♫", self)
        self.music_label.setObjectName("audioGlyph")
        self.music_label.setAlignment(Qt.AlignCenter)
        self.music_label.setFixedSize(46, 46)
        self.music_label.setToolTip("Spin FM audio player")
        top_row.addWidget(self.music_label)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        top_row.addLayout(info_layout, 1)

        self.track_label = QLabel("No track loaded", self)
        self.track_label.setObjectName("audioTrackLabel")
        self.track_label.setMinimumWidth(180)
        self.track_label.setWordWrap(True)
        self.track_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info_layout.addWidget(self.track_label)

        self.path_label = QLabel("Double-click an audio file to play it", self)
        self.path_label.setObjectName("audioPathLabel")
        self.path_label.setWordWrap(True)
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info_layout.addWidget(self.path_label)

        badges = QHBoxLayout()
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(6)
        info_layout.addLayout(badges)

        self.state_label = QLabel("Ready", self)
        self.state_label.setObjectName("audioStateLabel")
        self.state_label.setToolTip("Playback state")
        badges.addWidget(self.state_label)

        self.mpris_badge = QLabel("MPRIS", self)
        self.mpris_badge.setObjectName("audioMprisBadge")
        self.mpris_badge.setVisible(self._mpris.available)
        self._update_mpris_badge(self._mpris.available, self._mpris.service_name)
        self._mpris.availability_changed.connect(self._update_mpris_badge)
        badges.addWidget(self.mpris_badge)

        self.osd_badge = QLabel("Wayland OSD", self)
        self.osd_badge.setObjectName("audioOsdBadge")
        self.osd_badge.setToolTip(
            "Optional Wayland_OSD integration detected; notifications are best-effort"
        )
        self.osd_badge.setVisible(self.osd_available)
        badges.addWidget(self.osd_badge)
        badges.addStretch(1)

        self.external_button = self._control_button(
            "document-open",
            QStyle.SP_DialogOpenButton,
            "Open in the default application",
            self._request_external_open,
        )
        top_row.addWidget(self.external_button)

        self.close_button = self._control_button(
            "window-close",
            QStyle.SP_DialogCloseButton,
            "Close player",
            self.close_player,
            object_name="audioCloseButton",
        )
        self.close_button.setIcon(QIcon())
        self.close_button.setText("×")
        top_row.addWidget(self.close_button)

        timeline = QHBoxLayout()
        timeline.setSpacing(8)
        layout.addLayout(timeline)

        self.position_label = QLabel("0:00", self)
        self.position_label.setObjectName("audioTimeLabel")
        self.position_label.setMinimumWidth(58)
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        timeline.addWidget(self.position_label)

        seek_back_fallback = getattr(
            QStyle, "SP_MediaSeekBackward", QStyle.SP_ArrowBack
        )
        self.rewind_button = self._control_button(
            "media-seek-backward",
            seek_back_fallback,
            "Rewind 10 seconds",
            self.rewind,
            fixed_size=40,
        )
        self.rewind_button.setIcon(QIcon())
        self.rewind_button.setText("−10")
        timeline.addWidget(self.rewind_button)

        self.seek_slider = SeekSlider(Qt.Horizontal, self)
        self.seek_slider.setObjectName("audioSeekSlider")
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setSingleStep(1_000)
        self.seek_slider.setPageStep(self.SEEK_STEP_MS)
        self.seek_slider.setTracking(True)
        self.seek_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.seek_slider.setToolTip(
            "Track position — click, drag, scroll, or use the arrow keys to seek"
        )
        self.seek_slider.setAccessibleName("Track position")
        self.seek_slider.sliderPressed.connect(self._seek_started)
        self.seek_slider.sliderMoved.connect(self._seek_preview)
        self.seek_slider.sliderReleased.connect(self._seek_finished)
        self.seek_slider.valueChanged.connect(self._seek_value_changed)
        timeline.addWidget(self.seek_slider, 1)

        seek_forward_fallback = getattr(
            QStyle, "SP_MediaSeekForward", QStyle.SP_ArrowForward
        )
        self.forward_button = self._control_button(
            "media-seek-forward",
            seek_forward_fallback,
            "Forward 10 seconds",
            self.fast_forward,
            fixed_size=40,
        )
        self.forward_button.setIcon(QIcon())
        self.forward_button.setText("+10")
        timeline.addWidget(self.forward_button)

        self.duration_label = QLabel("0:00", self)
        self.duration_label.setObjectName("audioTimeLabel")
        self.duration_label.setMinimumWidth(58)
        self.duration_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        timeline.addWidget(self.duration_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        layout.addLayout(controls)

        self.play_button = self._control_button(
            "media-playback-start",
            QStyle.SP_MediaPlay,
            "Play",
            self.toggle_playback,
            object_name="audioPrimaryButton",
            icon_size=22,
            fixed_size=40,
        )
        controls.addWidget(self.play_button)

        self.stop_button = self._control_button(
            "media-playback-stop",
            QStyle.SP_MediaStop,
            "Stop",
            self.stop,
        )
        controls.addWidget(self.stop_button)
        controls.addStretch(1)

        self.mute_button = self._control_button(
            "audio-volume-high",
            QStyle.SP_MediaVolume,
            "Mute",
            self.toggle_muted,
        )
        controls.addWidget(self.mute_button)

        self.volume_slider = QSlider(Qt.Horizontal, self)
        self.volume_slider.setObjectName("audioVolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setSingleStep(2)
        self.volume_slider.setPageStep(10)
        self.volume_slider.setMinimumWidth(120)
        self.volume_slider.setMaximumWidth(180)
        self.volume_slider.setToolTip("Player volume")
        self.volume_slider.setAccessibleName("Player volume")
        saved_volume = self._saved_volume()
        self._last_nonzero_volume = saved_volume if saved_volume > 0 else 72
        self.volume_slider.setValue(saved_volume)
        self.volume_slider.valueChanged.connect(self._volume_changed)
        controls.addWidget(self.volume_slider)

        self.volume_label = QLabel(f"{saved_volume}%", self)
        self.volume_label.setObjectName("audioVolumeLabel")
        self.volume_label.setMinimumWidth(48)
        self.volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls.addWidget(self.volume_label)
        self._mpris.set_volume(saved_volume / 100.0)

    def _update_mpris_badge(self, available: bool, service_name: str) -> None:
        """Reflect optional desktop-player registration without affecting audio."""
        badge = getattr(self, "mpris_badge", None)
        if badge is None:
            return
        badge.setVisible(bool(available))
        if available:
            badge.setToolTip(f"Desktop media player registered as {service_name}")
        else:
            badge.setToolTip("MPRIS is unavailable; local playback remains enabled")

    def _build_animation(self) -> None:
        self._animation = QtCore.QPropertyAnimation(self, b"maximumHeight", self)
        self._animation.setDuration(180)
        try:
            curve = (
                QtCore.QEasingCurve.Type.OutCubic
                if USING_PYQT6
                else QtCore.QEasingCurve.OutCubic
            )
            self._animation.setEasingCurve(curve)
        except Exception:
            pass
        self._animation.finished.connect(self._animation_finished)

    def _build_timers(self) -> None:
        self._osd_retry_timer = QtCore.QTimer(self)
        self._osd_retry_timer.setSingleShot(True)
        self._osd_retry_timer.timeout.connect(self._retry_osd_media)

        self._seek_osd_timer = QtCore.QTimer(self)
        self._seek_osd_timer.setSingleShot(True)
        self._seek_osd_timer.setInterval(120)
        self._seek_osd_timer.timeout.connect(self._send_pending_seek_osd)

        self._volume_osd_timer = QtCore.QTimer(self)
        self._volume_osd_timer.setSingleShot(True)
        self._volume_osd_timer.setInterval(110)
        self._volume_osd_timer.timeout.connect(self._notify_osd_volume)

        self._volume_osd_retry_timer = QtCore.QTimer(self)
        self._volume_osd_retry_timer.setSingleShot(True)
        self._volume_osd_retry_timer.timeout.connect(self._retry_osd_volume)

    def _control_button(
        self,
        theme_icon: str,
        fallback: Any,
        tooltip: str,
        slot,
        *,
        object_name: str = "audioControlButton",
        icon_size: int = 18,
        fixed_size: int = 32,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setAutoRaise(False)
        button.setIcon(self._theme_icon(theme_icon, fallback))
        button.setIconSize(QSize(icon_size, icon_size))
        button.setFixedSize(fixed_size, fixed_size)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        try:
            button.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass
        button.clicked.connect(slot)
        return button

    def _theme_icon(self, name: str, fallback: Any):
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
        return self.style().standardIcon(fallback)

    def refresh_icons(self) -> None:
        """Refresh player icons after the global icon theme changes."""
        self.stop_button.setIcon(
            self._theme_icon("media-playback-stop", QStyle.SP_MediaStop)
        )
        self.rewind_button.setIcon(QIcon())
        self.rewind_button.setText("−10")
        self.forward_button.setIcon(QIcon())
        self.forward_button.setText("+10")
        self.external_button.setIcon(
            self._theme_icon("document-open", QStyle.SP_DialogOpenButton)
        )
        self.close_button.setIcon(QIcon())
        self.close_button.setText("×")
        self._update_play_icon()
        self._update_volume_icon()

    # ------------------------------------------------------------------
    # Backend lifecycle
    # ------------------------------------------------------------------
    def _saved_volume(self) -> int:
        raw = self._settings.value("audio/volume", 72)
        try:
            return max(0, min(100, int(raw)))
        except (TypeError, ValueError):
            return 72

    def _ensure_backend(self) -> bool:
        if self._player is not None:
            return True
        if self._backend_unavailable:
            return False

        try:
            if USING_PYQT6:
                from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

                self._media_player_class = QMediaPlayer
                self._media_content_class = None
                self._player = QMediaPlayer(self)
                self._audio_output = QAudioOutput(self)
                self._player.setAudioOutput(self._audio_output)
            else:
                from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

                self._media_player_class = QMediaPlayer
                self._media_content_class = QMediaContent
                self._player = QMediaPlayer(self)
                self._audio_output = None
        except Exception as exc:
            self._backend_unavailable = True
            self._backend_error = (
                "Qt Multimedia is unavailable. Install the matching "
                "PyQt multimedia package"
            )
            if str(exc):
                self._backend_error += f" ({exc})"
            self._player = None
            self._audio_output = None
            return False

        self._player.positionChanged.connect(self._position_changed)
        self._player.durationChanged.connect(self._duration_changed)
        if USING_PYQT6:
            self._player.playbackStateChanged.connect(self._state_changed)
        else:
            self._player.stateChanged.connect(self._state_changed)

        seekable_changed = getattr(self._player, "seekableChanged", None)
        if seekable_changed is not None and hasattr(seekable_changed, "connect"):
            try:
                seekable_changed.connect(lambda *_args: self._refresh_seek_controls())
            except Exception:
                pass

        for signal_name in ("errorOccurred", "error"):
            signal = getattr(self._player, signal_name, None)
            if signal is not None and hasattr(signal, "connect"):
                try:
                    signal.connect(self._playback_error)
                    break
                except Exception:
                    continue

        self._apply_volume()
        return True

    def play_file(self, path: str | os.PathLike[str]) -> bool:
        """Load and immediately play *path*.

        ``False`` means the caller should use the desktop's default application.
        """
        try:
            absolute_path = os.path.abspath(os.path.expanduser(os.fspath(path)))
        except (TypeError, ValueError):
            self._backend_error = "Invalid audio path"
            return False

        if not is_supported_audio_file(absolute_path):
            self._backend_error = "Unsupported audio-file extension"
            return False
        if not os.path.isfile(absolute_path):
            self._backend_error = "Audio file no longer exists"
            return False
        if not self._ensure_backend():
            return False

        self._backend_error = ""
        if absolute_path == self._current_path and self._player is not None:
            try:
                if self._duration and self.current_position() >= self._duration - 50:
                    self._player.setPosition(0)
                    self._mpris.emit_seeked(0)
                self._show_animated()
                if not self._is_playing():
                    self._player.play()
                self._mpris.set_track(absolute_path, self._duration)
                self._commit_playback_request(True)
                return True
            except Exception:
                # Reload below if the current media object became stale.
                pass

        self._cancel_pending_osd_notifications()
        self._current_path = absolute_path
        self._track_name = os.path.basename(absolute_path)
        self.track_label.setToolTip(absolute_path)
        self.path_label.setToolTip(absolute_path)
        self._update_track_labels()
        self._reset_timeline()
        self._set_state_text("Loading…")
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.external_button.setEnabled(True)

        url = QtCore.QUrl.fromLocalFile(absolute_path)
        try:
            self._suppress_state_notifications = True
            self._player.stop()
            if USING_PYQT6:
                self._player.setSource(url)
            else:
                self._player.setMedia(self._media_content_class(url))
            self._player.play()
        except Exception as exc:
            self._backend_error = f"Unable to start audio playback: {exc}"
            self._cancel_pending_osd_notifications()
            self._release_backend()
            return False
        finally:
            self._suppress_state_notifications = False

        self._mpris.set_track(absolute_path, self._duration)
        self._show_animated()
        self._commit_playback_request(True)
        return True

    def play(self) -> bool:
        """Start or resume the loaded track through the shared control path."""
        if self._player is None or not self._current_path:
            return False
        if self._is_playing():
            self._mpris.set_playback_status("Playing", force=True)
            return True
        try:
            if self._duration and self.current_position() >= self._duration - 50:
                self._player.setPosition(0)
                self._mpris.emit_seeked(0)
            self._player.play()
        except Exception as exc:
            self.status_message.emit(f"Audio playback failed: {exc}")
            return False
        self._commit_playback_request(True)
        return True

    def pause(self) -> bool:
        """Pause the loaded track through the shared control path."""
        if self._player is None or not self._current_path:
            return False
        if not self._is_playing():
            self._mpris.set_playback_status("Paused", force=True)
            return True
        try:
            self._player.pause()
        except Exception as exc:
            self.status_message.emit(f"Audio playback failed: {exc}")
            return False
        self._commit_playback_request(False)
        return True

    def toggle_playback(self, _checked: bool = False) -> bool:
        """Toggle playback for the button, Alt+P, MPRIS, and Wayland_OSD."""
        return self.pause() if self._is_playing() else self.play()

    def _commit_playback_request(self, playing: bool) -> None:
        """Apply a backend-accepted play/pause request to UI and OSD state."""
        self._cancel_pending_osd_notifications()
        self._playback_requested = bool(playing)
        heading = "Playing" if self._playback_requested else "Paused"
        self._set_state_text(heading)
        self._update_play_icon(playing=self._playback_requested)
        self.status_message.emit(f"{heading} {self._track_name}")
        self._mpris.set_playback_status(heading, force=True)
        self._notify_osd_media(heading)

    def stop(self) -> None:
        if self._player is None:
            return
        self._cancel_pending_osd_notifications()
        try:
            self._player.stop()
            self._player.setPosition(0)
        except Exception:
            return
        self._playback_requested = False
        self._set_slider_value(0)
        self.position_label.setText("0:00")
        self._set_state_text("Stopped")
        self._update_play_icon(playing=False)
        self._mpris.set_playback_status("Stopped", force=True)
        self._mpris.emit_seeked(0)
        self._notify_osd_media("Stopped")

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------
    def toggle_muted(self, _checked: bool = False) -> None:
        if self._muted:
            self._muted = False
        elif self.volume_slider.value() == 0:
            self._muted = False
            self.volume_slider.setValue(self._last_nonzero_volume)
        else:
            self._muted = True
        self._apply_volume()
        self._update_volume_icon()
        self._update_volume_label()
        self._notify_osd_volume()

    def _volume_changed(self, value: int) -> None:
        if value > 0:
            self._last_nonzero_volume = int(value)
            if self._muted:
                self._muted = False
        self._settings.setValue("audio/volume", int(value))
        self._apply_volume()
        self._update_volume_icon()
        self._update_volume_label()
        if self.osd_available:
            self._volume_osd_timer.start()

    def _apply_volume(self) -> None:
        value = self.volume_slider.value()
        if self._player is not None:
            try:
                if USING_PYQT6:
                    self._audio_output.setMuted(self._muted)
                    self._audio_output.setVolume(value / 100.0)
                else:
                    self._player.setMuted(self._muted)
                    self._player.setVolume(value)
            except Exception:
                pass
        self._mpris.set_volume(0.0 if self._muted else value / 100.0)

    def set_volume_fraction(self, value: float) -> None:
        """Set player volume from an MPRIS-compatible 0.0..1.0 value."""
        try:
            percent = max(0, min(100, round(float(value) * 100)))
        except (TypeError, ValueError, OverflowError):
            return
        self._muted = False
        if self.volume_slider.value() != percent:
            self.volume_slider.setValue(percent)
        else:
            self._apply_volume()
            self._update_volume_icon()
            self._update_volume_label()

    def _update_volume_label(self) -> None:
        if self._muted:
            self.volume_label.setText("Muted")
        else:
            self.volume_label.setText(f"{self.volume_slider.value()}%")

    # ------------------------------------------------------------------
    # Playback state and icons
    # ------------------------------------------------------------------
    def _is_playing(self) -> bool:
        return bool(self._playback_requested)

    def _state_name(self, state: Any) -> str:
        """Normalize the state delivered by Qt without querying it again."""
        player_class = self._media_player_class
        if player_class is None:
            return "stopped"
        try:
            if USING_PYQT6:
                owner = player_class.PlaybackState
                if state == owner.PlayingState:
                    return "playing"
                if state == owner.PausedState:
                    return "paused"
            else:
                if state == player_class.PlayingState:
                    return "playing"
                if state == player_class.PausedState:
                    return "paused"
        except Exception:
            pass
        return "stopped"

    def _state_changed(self, state: Any) -> None:
        if self._suppress_state_notifications or not self._current_path:
            return

        state_name = self._state_name(state)
        if state_name == "playing":
            if not self._playback_requested:
                return
            label = "Playing"
        elif state_name == "paused":
            if self._playback_requested:
                return
            label = "Paused"
        elif self._duration and self.current_position() >= self._duration - 250:
            label = "Finished"
            self._playback_requested = False
        elif self._playback_requested:
            # Ignore the transient stopped state many backends expose between
            # setSource()/setMedia() and the accepted play request.
            return
        else:
            label = "Stopped"
            self._playback_requested = False
        self._update_play_icon(playing=self._playback_requested)
        self._set_state_text(label)
        if label in {"Finished", "Stopped"}:
            self._cancel_pending_osd_notifications()
        mpris_status = label if label in {"Playing", "Paused"} else "Stopped"
        self._mpris.set_playback_status(mpris_status)
        self._notify_osd_media(label)

    def _set_state_text(self, text: str) -> None:
        self.state_label.setText(text)
        self.state_label.setToolTip(f"Playback state: {text}")

    def _update_play_icon(self, *, playing: bool | None = None) -> None:
        is_playing = self._is_playing() if playing is None else bool(playing)
        if is_playing:
            name = "media-playback-pause"
            fallback = QStyle.SP_MediaPause
            action = "Pause"
        else:
            name = "media-playback-start"
            fallback = QStyle.SP_MediaPlay
            action = "Play"
        tooltip = f"{action} (Alt+P)"
        self.play_button.setIcon(self._theme_icon(name, fallback))
        self.play_button.setToolTip(tooltip)
        self.play_button.setAccessibleName(action)

    def _update_volume_icon(self) -> None:
        zero_volume = self.volume_slider.value() == 0
        if self._muted or zero_volume:
            name = "audio-volume-muted"
            fallback = QStyle.SP_MediaVolumeMuted
            tooltip = "Unmute" if self._muted else "Restore volume"
        else:
            name = "audio-volume-high"
            fallback = QStyle.SP_MediaVolume
            tooltip = "Mute"
        self.mute_button.setIcon(self._theme_icon(name, fallback))
        self.mute_button.setToolTip(tooltip)
        self.mute_button.setAccessibleName(tooltip)

    # ------------------------------------------------------------------
    # Seeking
    # ------------------------------------------------------------------
    def _duration_changed(self, duration: int) -> None:
        self._duration = max(0, int(duration))
        self.seek_slider.setRange(0, self._duration)
        self.duration_label.setText(format_milliseconds(self._duration))
        self._mpris.set_duration(self._duration)
        self._refresh_seek_controls()

    def _position_changed(self, position: int) -> None:
        value = max(0, int(position))
        if self._duration:
            value = min(value, self._duration)
        if not self._seeking:
            self._set_slider_value(value)
            self.position_label.setText(format_milliseconds(value))

    def _is_seekable(self) -> bool:
        if self._player is None or self._duration <= 0:
            return False
        try:
            return bool(self._player.isSeekable())
        except Exception:
            # Some older backends do not expose isSeekable reliably. A finite
            # duration is still a useful and compatible fallback.
            return self._duration > 0

    def _refresh_seek_controls(self) -> None:
        enabled = self._is_seekable()
        self.seek_slider.setEnabled(enabled)
        self.rewind_button.setEnabled(enabled)
        self.forward_button.setEnabled(enabled)
        if enabled:
            tooltip = "Rewind 10 seconds"
        elif self._duration > 0:
            tooltip = "This audio source does not support seeking"
        else:
            tooltip = "Seeking becomes available after the track loads"
        self.rewind_button.setToolTip(tooltip)
        self.forward_button.setToolTip("Forward 10 seconds" if enabled else tooltip)
        self._mpris.set_seekable(enabled)

    def _seek_started(self) -> None:
        self._seeking = True

    def _seek_preview(self, position: int) -> None:
        self.position_label.setText(format_milliseconds(position))

    def _seek_finished(self) -> None:
        self._seeking = False
        self._seek_to(self.seek_slider.value(), osd_heading="Seeking")

    def _seek_value_changed(self, position: int) -> None:
        if self._updating_seek_slider:
            return
        self.position_label.setText(format_milliseconds(position))
        if not self._seeking:
            self._seek_to(position, osd_heading="Seeking")

    def _seek_to(self, position: int, *, osd_heading: str = "Seeking") -> bool:
        if self._player is None or not self._is_seekable():
            return False
        target = max(0, min(int(position), self._duration))
        try:
            self._player.setPosition(target)
        except Exception:
            return False

        self._set_slider_value(target)
        self.position_label.setText(format_milliseconds(target))
        self._mpris.emit_seeked(target)
        self._schedule_seek_osd(osd_heading)
        return True

    def rewind(self) -> None:
        if self.seek_relative(-self.SEEK_STEP_MS, "Rewind 10 seconds"):
            self.status_message.emit("Rewound 10 seconds")

    def fast_forward(self) -> None:
        if self.seek_relative(self.SEEK_STEP_MS, "Forward 10 seconds"):
            self.status_message.emit("Forwarded 10 seconds")

    def seek_relative(self, delta_ms: int, heading: str = "Seeking") -> bool:
        """Seek relative to the current position for UI and MPRIS clients."""
        return self._seek_to(self.current_position() + delta_ms, osd_heading=heading)

    def set_position(self, position_ms: int) -> bool:
        """Seek to an absolute millisecond position for MPRIS clients."""
        return self._seek_to(position_ms, osd_heading="Seeking")

    def current_position(self) -> int:
        if self._player is not None:
            try:
                return max(0, int(self._player.position()))
            except Exception:
                pass
        return max(0, int(self.seek_slider.value()))

    def _set_slider_value(self, value: int) -> None:
        self._updating_seek_slider = True
        try:
            self.seek_slider.setValue(int(value))
        finally:
            self._updating_seek_slider = False

    def _reset_timeline(self) -> None:
        self._duration = 0
        self.seek_slider.setRange(0, 0)
        self._set_slider_value(0)
        self.position_label.setText("0:00")
        self.duration_label.setText("0:00")
        self._refresh_seek_controls()

    # ------------------------------------------------------------------
    # Optional Wayland_OSD integration
    # ------------------------------------------------------------------
    def _cancel_pending_osd_notifications(self) -> None:
        """Drop delayed OSD events that no longer describe current playback."""
        self._pending_osd_media = None
        self._pending_seek_heading = "Seeking"
        self._osd_media_retry_index = 0
        self._osd_volume_retry_index = 0
        for timer_name in (
            "_osd_retry_timer",
            "_seek_osd_timer",
            "_volume_osd_timer",
            "_volume_osd_retry_timer",
        ):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

    def _notify_osd_media(
        self,
        heading: str,
        *,
        track: str | None = None,
        position: int | None = None,
        duration: int | None = None,
        retry: bool = True,
    ) -> None:
        if not self.osd_available:
            return
        try:
            detail = self._track_name if track is None else track
            current = self.current_position() if position is None else int(position)
            total = self._duration if duration is None else int(duration)
            sent = self._osd.notify_media(
                heading,
                detail,
                position_ms=current,
                duration_ms=total,
            )
        except Exception:
            return
        if sent:
            self._pending_osd_media = None
            self._osd_retry_timer.stop()
            return
        if not retry:
            return
        self._pending_osd_media = (heading, detail, current, total)
        self._osd_media_retry_index = 0
        self._osd_retry_timer.setInterval(self.OSD_RETRY_DELAYS_MS[0])
        self._osd_retry_timer.start()

    def _retry_osd_media(self) -> None:
        pending = self._pending_osd_media
        if pending is None or not self.osd_available:
            self._pending_osd_media = None
            return
        heading, track, position, duration = pending
        try:
            sent = self._osd.notify_media(
                heading,
                track,
                position_ms=position,
                duration_ms=duration,
            )
        except Exception:
            self._pending_osd_media = None
            return
        if sent:
            self._pending_osd_media = None
            return

        next_index = self._osd_media_retry_index + 1
        if next_index >= len(self.OSD_RETRY_DELAYS_MS):
            self._pending_osd_media = None
            return
        self._osd_media_retry_index = next_index
        self._osd_retry_timer.setInterval(self.OSD_RETRY_DELAYS_MS[next_index])
        self._osd_retry_timer.start()

    def _schedule_seek_osd(self, heading: str) -> None:
        if not self.osd_available:
            return
        self._pending_seek_heading = heading
        self._seek_osd_timer.start()

    def _send_pending_seek_osd(self) -> None:
        self._notify_osd_media(self._pending_seek_heading)

    def _notify_osd_volume(self, *, retry: bool = True) -> None:
        if not self.osd_available:
            return
        try:
            sent = self._osd.notify_volume(
                self.volume_slider.value(), self._muted, self._track_name
            )
        except Exception:
            return
        if sent:
            self._volume_osd_retry_timer.stop()
            return
        if retry:
            self._osd_volume_retry_index = 0
            self._volume_osd_retry_timer.setInterval(self.OSD_RETRY_DELAYS_MS[0])
            self._volume_osd_retry_timer.start()

    def _retry_osd_volume(self) -> None:
        if not self.osd_available:
            return
        try:
            sent = self._osd.notify_volume(
                self.volume_slider.value(), self._muted, self._track_name
            )
        except Exception:
            return
        if sent:
            return

        next_index = self._osd_volume_retry_index + 1
        if next_index >= len(self.OSD_RETRY_DELAYS_MS):
            return
        self._osd_volume_retry_index = next_index
        self._volume_osd_retry_timer.setInterval(self.OSD_RETRY_DELAYS_MS[next_index])
        self._volume_osd_retry_timer.start()

    def notify_external_open(self, path: str | os.PathLike[str]) -> None:
        """Tell Wayland_OSD that playback is moving to the desktop player."""
        self._cancel_pending_osd_notifications()
        try:
            track = os.path.basename(os.fspath(path))
        except (TypeError, ValueError):
            track = "Audio file"
        self._notify_osd_media(
            "Opening externally",
            track=track,
            position=0,
            duration=0,
        )

    # ------------------------------------------------------------------
    # Errors, external open, panel lifecycle
    # ------------------------------------------------------------------
    def _playback_error(self, *_args: Any) -> None:
        message = "Unknown multimedia error"
        if self._player is not None:
            try:
                message = self._player.errorString() or message
            except Exception:
                pass
        self._backend_error = message
        self._playback_requested = False
        self._cancel_pending_osd_notifications()
        self._set_state_text("Playback error")
        self._mpris.set_playback_status("Stopped", force=True)
        self.status_message.emit(
            f"Could not play {self._track_name or 'audio file'}: {message}. "
            "Use the external-open button to try the desktop player."
        )
        self._notify_osd_media("Playback error")
        self._update_play_icon()

    def _request_external_open(self) -> None:
        if self._current_path:
            self.open_externally_requested.emit(self._current_path)

    def close_player(self) -> None:
        """Stop playback, release decoder resources, and hide the panel."""
        self._cancel_pending_osd_notifications()
        if self._current_path:
            self._notify_osd_media("Stopped")
        self._release_backend()
        self._hide_animated()

    def shutdown(self) -> None:
        self._animation.stop()
        self._cancel_pending_osd_notifications()
        self._release_backend()
        self._mpris.shutdown()

    def _show_animated(self) -> None:
        if self.isVisible() and self.maximumHeight() > 0:
            return
        self._animation.stop()
        self._hide_after_animation = False
        target = max(132, self.sizeHint().height())
        self.setMaximumHeight(0)
        self.show()
        self._animation.setStartValue(0)
        self._animation.setEndValue(target)
        self._animation.start()

    def _hide_animated(self) -> None:
        if self.isHidden():
            return
        self._animation.stop()
        self._hide_after_animation = True
        self._animation.setStartValue(max(0, self.height()))
        self._animation.setEndValue(0)
        self._animation.start()

    def _animation_finished(self) -> None:
        if self._hide_after_animation:
            self.hide()
            self._hide_after_animation = False
        self.setMaximumHeight(16_777_215)

    def _release_backend(self) -> None:
        player = self._player
        audio_output = self._audio_output
        media_content_class = self._media_content_class
        self._suppress_state_notifications = True

        if player is not None:
            try:
                player.stop()
            except Exception:
                pass
            try:
                if USING_PYQT6:
                    player.setSource(QtCore.QUrl())
                elif media_content_class is not None:
                    try:
                        empty_media = media_content_class()
                    except Exception:
                        empty_media = media_content_class(QtCore.QUrl())
                    player.setMedia(empty_media)
            except Exception:
                pass
            try:
                player.deleteLater()
            except Exception:
                pass

        if audio_output is not None:
            try:
                audio_output.deleteLater()
            except Exception:
                pass

        self._player = None
        self._audio_output = None
        self._media_player_class = None
        self._media_content_class = None
        self._playback_requested = False
        self._current_path = ""
        self._track_name = ""
        self._duration = 0
        self._mpris.clear_track()
        self.track_label.setToolTip("")
        self.path_label.setToolTip("")
        self._suppress_state_notifications = False
        self._set_stopped_ui()

    def _set_stopped_ui(self) -> None:
        self._playback_requested = False
        self.track_label.setText("No track loaded")
        self.path_label.setText("Double-click an audio file to play it")
        self._set_state_text("Ready")
        self._reset_timeline()
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.external_button.setEnabled(False)
        self._update_play_icon()
        self._update_volume_icon()
        self._update_volume_label()

    def _update_track_labels(self) -> None:
        if not self._track_name:
            self.track_label.setText("No track loaded")
            self.path_label.setText("Double-click an audio file to play it")
            return

        self.track_label.setText(self._track_name)
        self.path_label.setText(self._current_path)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._update_track_labels()
