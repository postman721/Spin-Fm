#!/usr/bin/env python3
# theme_manager.py
import sys
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True
import os
from PyQt5.QtWidgets import QApplication

class ThemeManager:
    def __init__(self, theme_dir):
        self.theme_dir = theme_dir

    def load_and_apply_theme(self, theme_name):
        """Load a CSS file from theme_dir and apply it to the QApplication."""
        theme_path = os.path.join(self.theme_dir, theme_name + ".css")
        if os.path.exists(theme_path):
            with open(theme_path, "r") as f:
                style = f.read()
                QApplication.instance().setStyleSheet(style)
            print(f"[ThemeManager] Theme '{theme_name}' applied from {theme_path}.")
        else:
            print(f"[ThemeManager] Theme file {theme_path} not found.")

    def get_available_themes(self):
        """Return a list of available theme names (without extension)."""
        if os.path.exists(self.theme_dir):
            return [os.path.splitext(f)[0] for f in os.listdir(self.theme_dir) if f.endswith(".css")]
        return []

    def empty_trash(self):
        """Call the empty_trash function from empty_trash.py."""
        from empty_trash import empty_trash as do_empty_trash
        try:
            do_empty_trash()
        except Exception as e:
            print(f"Failed to empty trash: {e}")
