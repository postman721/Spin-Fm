from __future__ import annotations

import pytest

from spin_fm.audio import format_milliseconds, is_supported_audio_file


@pytest.mark.parametrize(
    "path",
    [
        "song.mp3",
        "SONG.OGG",
        "voice.opus",
        "album.flac",
        "recording.wav",
        "podcast.m4a",
    ],
)
def test_common_audio_formats_are_detected(path: str) -> None:
    assert is_supported_audio_file(path)


@pytest.mark.parametrize("path", ["", "notes.txt", "movie.mp4", "archive.tar.gz"])
def test_non_audio_paths_are_not_detected(path: str) -> None:
    assert not is_supported_audio_file(path)


def test_duration_formatting() -> None:
    assert format_milliseconds(0) == "0:00"
    assert format_milliseconds(65_432) == "1:05"
    assert format_milliseconds(3_661_000) == "1:01:01"
    assert format_milliseconds(-100) == "0:00"
