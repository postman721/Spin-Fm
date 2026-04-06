#!/usr/bin/env python3
"""Application stylesheet loader for Spin FM."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from qt_compat import QApplication

sys.dont_write_bytecode = True


class ThemeManager:
    """Load CSS themes from one or more local theme directories."""

    def __init__(self, theme_dir=None):
        module_dir = Path(__file__).resolve().parent
        candidate_dirs = []

        if theme_dir:
            candidate_dirs.append(Path(theme_dir).expanduser())

        # Support both the documented layout (themes/*.css) and a flat layout
        # where the CSS files live next to the Python sources.
        candidate_dirs.extend([
            module_dir / "themes",
            module_dir,
        ])

        seen = set()
        self.theme_dirs = []
        for directory in candidate_dirs:
            resolved = directory.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            self.theme_dirs.append(resolved)

    def _theme_path(self, theme_name: str):
        filename = f"{theme_name}.css"
        for directory in self.theme_dirs:
            path = directory / filename
            if path.exists():
                return path
        return None

    def load_and_apply_theme(self, theme_name):
        """Load a CSS file and apply it to QApplication.

        Returns True when a theme was found and applied, otherwise False.
        """
        theme_path = self._theme_path(theme_name)
        if theme_path is None:
            print(
                f"[ThemeManager] Theme '{theme_name}' not found. "
                f"Searched: {', '.join(str(path) for path in self.theme_dirs)}"
            )
            return False

        app = QApplication.instance()
        if app is None:
            print("[ThemeManager] QApplication instance not ready yet.")
            return False

        with open(theme_path, "r", encoding="utf-8") as handle:
            app.setStyleSheet(handle.read())
        print(f"[ThemeManager] Theme '{theme_name}' applied from {theme_path}.")
        return True

    def get_available_themes(self):
        """Return a sorted list of available theme names (without .css)."""
        names = set()
        for directory in self.theme_dirs:
            if not directory.exists():
                continue
            for filename in os.listdir(directory):
                if filename.endswith('.css'):
                    names.add(os.path.splitext(filename)[0])
        return sorted(names)
