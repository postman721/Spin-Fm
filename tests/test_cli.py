from spin_fm import __version__
from spin_fm.app import build_parser


def test_cli_collects_paths() -> None:
    args = build_parser().parse_args(["/tmp/a", "file:///tmp/b"])
    assert args.paths == ["/tmp/a", "file:///tmp/b"]
    assert __version__ == "2.6.21"


def test_application_main_invokes_window_setup_once(monkeypatch) -> None:
    import sys
    import types

    from spin_fm import app as app_module

    class Signal:
        def connect(self, callback) -> None:
            self.callback = callback

    class Timer:
        def __init__(self) -> None:
            self.timeout = Signal()

        def start(self, _milliseconds: int) -> None:
            return None

    class Application:
        def __init__(self, _arguments) -> None:
            self.quit = lambda: None

        def setApplicationName(self, _value) -> None:  # noqa: N802
            pass

        def setApplicationDisplayName(self, _value) -> None:  # noqa: N802
            pass

        def setApplicationVersion(self, _value) -> None:  # noqa: N802
            pass

        def setOrganizationName(self, _value) -> None:  # noqa: N802
            pass

        def setOrganizationDomain(self, _value) -> None:  # noqa: N802
            pass

        def setStyle(self, _value) -> None:  # noqa: N802
            pass

        def exec(self) -> int:
            return 0

    class GuiApplication:
        @staticmethod
        def setDesktopFileName(_value) -> None:  # noqa: N802
            pass

    class StyleFactory:
        @staticmethod
        def keys() -> list[str]:
            return ["Fusion"]

    class MessageBox:
        @staticmethod
        def critical(*_args) -> None:
            pass

    class MainWindow:
        def __init__(self, startup_paths) -> None:
            self.startup_paths = startup_paths
            self.shown = False

        def show(self) -> None:
            self.shown = True

        def show_status(self, *_args) -> None:
            pass

    qt_module = types.ModuleType("spin_fm.qt_compat")
    qt_module.QApplication = Application
    qt_module.QGuiApplication = GuiApplication
    qt_module.QMessageBox = MessageBox
    qt_module.QStyleFactory = StyleFactory
    qt_module.QTimer = Timer
    window_module = types.ModuleType("spin_fm.main_window")
    window_module.MainWindow = MainWindow
    monkeypatch.setitem(sys.modules, "spin_fm.qt_compat", qt_module)
    monkeypatch.setitem(sys.modules, "spin_fm.main_window", window_module)

    installed: list[MainWindow] = []
    previous_excepthook = sys.excepthook
    try:
        result = app_module.main(["/tmp"], window_setup=installed.append)
    finally:
        sys.excepthook = previous_excepthook

    assert result == 0
    assert len(installed) == 1
    assert installed[0].startup_paths == ["/tmp"]
    assert installed[0].shown
