"""Audio-file detection and duration formatting helpers for Spin FM.

This module deliberately has no Qt imports, so format routing stays cheap and
can be tested even on build hosts without a graphical stack.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

# Common audio-only formats handled by Qt Multimedia backends on Linux. Actual
# decoding support depends on the installed Qt/FFmpeg or GStreamer backend.
SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".ac3",
        ".aif",
        ".aifc",
        ".aiff",
        ".alac",
        ".amr",
        ".ape",
        ".au",
        ".flac",
        ".m4a",
        ".m4b",
        ".mka",
        ".mp2",
        ".mp3",
        ".oga",
        ".ogg",
        ".opus",
        ".wav",
        ".wave",
        ".weba",
        ".wma",
    }
)


def is_supported_audio_file(path: str | os.PathLike[str]) -> bool:
    """Return whether *path* looks like an audio file Spin FM should play."""
    try:
        value = os.fspath(path).strip()
    except (AttributeError, TypeError, ValueError):
        return False
    if not value:
        return False

    if Path(value).suffix.casefold() in SUPPORTED_AUDIO_EXTENSIONS:
        return True

    media_type, _encoding = mimetypes.guess_type(value, strict=False)
    return bool(media_type and media_type.casefold().startswith("audio/"))


def format_milliseconds(value: int | float) -> str:
    """Format a non-negative millisecond duration as ``M:SS`` or ``H:MM:SS``."""
    try:
        total_seconds = max(0, int(value) // 1000)
    except (TypeError, ValueError, OverflowError):
        total_seconds = 0

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
