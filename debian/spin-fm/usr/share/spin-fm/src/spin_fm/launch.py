"""Safe, non-blocking desktop application launch helpers."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Iterable


def resolve_command(command_text: str) -> list[str]:
    """Parse a user-supplied command without invoking a shell.

    The executable is resolved through ``PATH`` when the command starts with a
    bare program name. Absolute paths and explicit relative paths are left for
    ``subprocess`` to validate so the resulting error remains precise.
    """
    text = str(command_text or "").strip()
    if not text:
        raise ValueError("No program specified.")

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise ValueError(f"Invalid command: {exc}") from exc

    if not tokens:
        raise ValueError("No program specified.")

    executable = tokens[0]
    if not os.path.isabs(executable) and os.sep not in executable:
        resolved = shutil.which(executable)
        if not resolved:
            raise FileNotFoundError(f"Program not found in PATH: {executable}")
        tokens[0] = resolved
    return tokens


def launch_paths(command_text: str, paths: Iterable[str]) -> subprocess.Popen[bytes]:
    """Launch *command_text* with local paths appended as separate arguments."""
    arguments = resolve_command(command_text)
    file_paths = [str(path) for path in paths]
    if not file_paths:
        raise ValueError("No files were selected.")
    return subprocess.Popen(
        arguments + file_paths,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def launch_default(path: str) -> subprocess.Popen[bytes]:
    """Open a local path with the desktop's default handler."""
    executable = shutil.which("xdg-open")
    if not executable:
        raise FileNotFoundError("xdg-open was not found in PATH.")
    return subprocess.Popen(
        [executable, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
