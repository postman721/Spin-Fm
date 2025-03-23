#!/usr/bin/env python3
import os, sys
from pathlib import Path
from PyQt5.QtGui import QIcon

# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True

class IconThemeManager:
    """
    Manages icon themes by scanning typical Linux icon directories and
    applying a chosen icon theme using QIcon.setThemeName.
    """
    def __init__(self):
        # Typical directories for icon themes.
        self.icon_paths = [
            "/usr/share/icons",
            os.path.expanduser("~/.icons"),
            "/usr/local/share/icons"
        ]
        # Set search paths so that QIcon can find the themes.
        QIcon.setThemeSearchPaths(self.icon_paths)

    def get_available_icon_themes(self):
        """
        Scans the typical icon directories for available icon themes.
        A valid theme is a directory containing an 'index.theme' file.
        :return: Sorted list of icon theme names.
        """
        themes = set()
        for path in self.icon_paths:
            p = Path(path)
            if p.exists() and p.is_dir():
                for item in p.iterdir():
                    if item.is_dir() and (item / "index.theme").exists():
                        themes.add(item.name)
        return sorted(list(themes))

    def load_and_apply_theme(self, theme_name: str):
        """
        Applies the icon theme by calling QIcon.setThemeName.
        :param theme_name: The name of the icon theme.
        """
        QIcon.setThemeName(theme_name)
