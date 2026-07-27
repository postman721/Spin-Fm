"""Freedesktop icon-theme discovery with stable desktop defaults."""

from __future__ import annotations

import logging
import os

from .qt_compat import QIcon

logger = logging.getLogger(__name__)


class IconThemeManager:
    """Discover installed icon themes and apply one through Qt."""

    DEFAULT_THEME = "Adwaita"
    FALLBACK_THEME = "hicolor"
    PREFERRED_THEMES = (DEFAULT_THEME, "Breeze", "Papirus", FALLBACK_THEME)

    def __init__(self) -> None:
        self.icon_paths = self._build_icon_search_paths()
        self._available: tuple[str, ...] | None = None
        self.current_theme = ""
        try:
            QIcon.setThemeSearchPaths(self.icon_paths)
        except (RuntimeError, TypeError, ValueError):
            logger.debug("Unable to update Qt icon-theme search paths", exc_info=True)
        if hasattr(QIcon, "setFallbackThemeName"):
            try:
                QIcon.setFallbackThemeName(self.FALLBACK_THEME)
            except (RuntimeError, TypeError, ValueError):
                logger.debug("Unable to set the Qt fallback icon theme", exc_info=True)

    @staticmethod
    def _build_icon_search_paths() -> list[str]:
        paths: list[str] = []
        try:
            paths.extend(QIcon.themeSearchPaths())
        except (RuntimeError, TypeError):
            pass

        data_home = os.environ.get(
            "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
        )
        data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
        paths.extend((os.path.join(data_home, "icons"), os.path.expanduser("~/.icons")))
        paths.extend(os.path.join(value, "icons") for value in data_dirs.split(":"))

        unique: list[str] = []
        seen: set[str] = set()
        for value in paths:
            if not value:
                continue
            normalized = os.path.abspath(os.path.expanduser(value))
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    def get_available_icon_themes(self, refresh: bool = False) -> list[str]:
        if self._available is not None and not refresh:
            return list(self._available)

        themes: set[str] = set()
        for directory in self.icon_paths:
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False) and os.path.isfile(
                            os.path.join(entry.path, "index.theme")
                        ):
                            themes.add(entry.name)
            except OSError:
                continue
        self._available = tuple(sorted(themes, key=str.casefold))
        return list(self._available)

    @staticmethod
    def _installed_name(theme_name: str, available: list[str]) -> str:
        requested = str(theme_name or "").strip().casefold()
        if not requested:
            return ""
        return next((name for name in available if name.casefold() == requested), "")

    def resolve_theme(self, requested: str = "") -> str:
        """Resolve a saved choice, defaulting new installations to Adwaita."""
        available = self.get_available_icon_themes()
        requested_name = self._installed_name(requested, available)
        if requested_name:
            return requested_name
        if not available:
            return str(requested or "").strip() or self.DEFAULT_THEME

        for candidate in self.PREFERRED_THEMES:
            installed = self._installed_name(candidate, available)
            if installed:
                return installed

        inherited = self._installed_name(QIcon.themeName(), available)
        return inherited or available[0]

    def load_and_apply_theme(self, theme_name: str) -> bool:
        resolved = self.resolve_theme(theme_name)
        try:
            QIcon.setThemeName(resolved)
        except (RuntimeError, TypeError, ValueError):
            logger.exception("Unable to apply icon theme %s", resolved)
            return False

        applied = str(QIcon.themeName() or resolved)
        self.current_theme = applied
        return applied.casefold() == resolved.casefold()
