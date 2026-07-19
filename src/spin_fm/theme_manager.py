"""Bundled application stylesheet discovery and caching."""

from __future__ import annotations

import logging
from pathlib import Path

from .qt_compat import QApplication

logger = logging.getLogger(__name__)


class ThemeManager:
    """Load bundled or developer-provided QSS themes."""

    def __init__(self, theme_dir: str | None = None) -> None:
        candidates = []
        if theme_dir:
            candidates.append(Path(theme_dir).expanduser())
        candidates.append(Path(__file__).resolve().parent / "themes")

        self.theme_dirs: list[Path] = []
        seen: set[Path] = set()
        for directory in candidates:
            resolved = directory.resolve(strict=False)
            if resolved not in seen:
                seen.add(resolved)
                self.theme_dirs.append(resolved)

        self._names: tuple[str, ...] | None = None
        self._stylesheet_cache: dict[Path, tuple[int, str]] = {}
        self.current_theme = ""

    def _theme_path(self, theme_name: str) -> Path | None:
        safe_name = Path(str(theme_name)).name
        if safe_name != str(theme_name) or not safe_name:
            return None
        filename = f"{safe_name}.css"
        for directory in self.theme_dirs:
            path = directory / filename
            if path.is_file():
                return path
        return None

    def _read_stylesheet(self, path: Path) -> str:
        stat = path.stat()
        cached = self._stylesheet_cache.get(path)
        if cached is not None and cached[0] == stat.st_mtime_ns:
            return cached[1]
        stylesheet = path.read_text(encoding="utf-8")
        self._stylesheet_cache[path] = (stat.st_mtime_ns, stylesheet)
        return stylesheet

    def load_and_apply_theme(self, theme_name: str) -> bool:
        path = self._theme_path(str(theme_name))
        if path is None:
            logger.warning("Theme %r was not found", theme_name)
            return False
        app = QApplication.instance()
        if app is None:
            logger.error("Cannot apply a theme before QApplication exists")
            return False
        try:
            app.setStyleSheet(self._read_stylesheet(path))
            app.setProperty("spinTheme", str(theme_name))
            self.current_theme = str(theme_name)
            return True
        except OSError:
            logger.exception("Unable to load theme %s", path)
            return False

    def get_available_themes(self, refresh: bool = False) -> list[str]:
        if self._names is not None and not refresh:
            return list(self._names)
        names: set[str] = set()
        for directory in self.theme_dirs:
            try:
                names.update(
                    path.stem
                    for path in directory.iterdir()
                    if path.suffix == ".css" and path.is_file()
                )
            except OSError:
                continue
        self._names = tuple(sorted(names))
        return list(self._names)
