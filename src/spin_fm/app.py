"""Application bootstrap and command-line interface for Spin FM."""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Callable, Sequence
from typing import Any

from . import __version__
from .config import APP_ID, APP_NAME, ORGANIZATION_DOMAIN, ORGANIZATION_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spin-fm",
        description="A lightweight, tabbed Linux file manager.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH_OR_URI",
        help="files, folders, or file:// URIs to reveal/open",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=os.environ.get("SPIN_FM_LOG_LEVEL", "WARNING").upper(),
        help="logging verbosity (default: WARNING)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Spin FM {__version__}",
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    window_setup: Callable[[Any], Any] | None = None,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    configure_logging(args.log_level)

    try:
        from .qt_compat import (
            QApplication,
            QGuiApplication,
            QMessageBox,
            QStyleFactory,
            QTimer,
        )
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Keep Qt from parsing filesystem arguments as toolkit options.
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setOrganizationDomain(ORGANIZATION_DOMAIN)
    try:
        QGuiApplication.setDesktopFileName(APP_ID)
    except Exception:
        pass

    # Fusion plus the bundled QSS gives predictable metrics across Qt5/Qt6 and
    # desktop environments. Native styling can be requested explicitly.
    if os.environ.get("SPIN_FM_NATIVE_STYLE", "").lower() not in {"1", "true", "yes"}:
        try:
            if "Fusion" in QStyleFactory.keys():
                app.setStyle("Fusion")
        except Exception:
            pass

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger(__name__).critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        try:
            QMessageBox.critical(
                None,
                "Spin FM Error",
                "Spin FM encountered an unexpected error. Details were written "
                "to the application log.",
            )
        except Exception:
            pass

    sys.excepthook = handle_exception

    # Let Ctrl+C close a terminal-launched instance cleanly.
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGINT, lambda *_args: app.quit())
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(500)

    from .main_window import MainWindow

    window = MainWindow(startup_paths=args.paths)
    if window_setup is not None:
        try:
            window_setup(window)
        except Exception:
            logging.getLogger(__name__).exception(
                "Unable to initialize a Spin FM window extension"
            )
            try:
                window.show_status(
                    "An optional Spin FM integration could not be initialized",
                    8_000,
                )
            except Exception:
                pass
    window.show()
    return int(app.exec())
