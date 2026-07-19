"""Reusable bounded background workers for non-UI work."""

from __future__ import annotations

import logging
import traceback
import weakref
from collections.abc import Callable
from functools import partial
from typing import Any

from .qt_compat import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals emitted by :class:`Worker` from a pool thread."""

    result = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(object)
    finished = pyqtSignal()


class Worker(QRunnable):
    """Run one callable in a QThreadPool.

    When ``with_progress`` is true, the callable receives a keyword argument
    named ``progress_callback`` whose value is a thread-safe signal emitter.
    """

    def __init__(
        self,
        function: Callable[..., Any],
        *args: Any,
        with_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.function: Callable[..., Any] | None = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.with_progress = with_progress
        try:
            self.setAutoDelete(True)
        except Exception:
            pass

    @pyqtSlot()
    def run(self) -> None:
        try:
            function = self.function
            if function is None:
                raise RuntimeError("background task payload was already released")
            if self.with_progress:
                self.kwargs["progress_callback"] = self.signals.progress.emit
            result = function(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - exercised via Qt runtime
            self.signals.error.emit(
                {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        else:
            self.signals.result.emit(result)
        finally:
            self.release_references()
            self.signals.finished.emit()

    def release_references(self) -> None:
        """Drop potentially large task inputs as soon as execution finishes."""
        self.function = None
        self.args = ()
        self.kwargs.clear()


class TaskManager(QObject):
    """Own a small QThreadPool and retain workers until they finish.

    A bounded pool prevents bursts of device events or repeated refresh clicks
    from creating an unbounded number of native threads and signal objects.
    """

    active_changed = pyqtSignal(int)

    def __init__(
        self,
        parent: QObject | None = None,
        max_threads: int = 2,
        max_tasks: int | None = None,
    ) -> None:
        super().__init__(parent)
        thread_count = max(1, int(max_threads))
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(thread_count)
        try:
            self.pool.setExpiryTimeout(30_000)
        except Exception:
            pass
        self._workers: set[Worker] = set()
        self._accepting = True
        self._max_tasks = max(thread_count, int(max_tasks or thread_count * 4))

    @property
    def active_count(self) -> int:
        return len(self._workers)

    @property
    def is_busy(self) -> bool:
        return bool(self._workers)

    def submit(
        self,
        function: Callable[..., Any],
        *args: Any,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[dict[str, str]], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        with_progress: bool = False,
        **kwargs: Any,
    ) -> Worker | None:
        if not self._accepting or self.active_count >= self._max_tasks:
            return None

        worker = Worker(function, *args, with_progress=with_progress, **kwargs)
        self._workers.add(worker)
        self.active_changed.emit(self.active_count)

        if on_result is not None:
            worker.signals.result.connect(on_result)
        if on_error is not None:
            worker.signals.error.connect(on_error)
        else:
            worker.signals.error.connect(self._log_worker_error)
        if on_progress is not None:
            worker.signals.progress.connect(on_progress)
        if on_finished is not None:
            worker.signals.finished.connect(on_finished)

        worker_ref = weakref.ref(worker)
        worker.signals.finished.connect(partial(self._release_worker, worker_ref))
        try:
            self.pool.start(worker)
        except Exception:
            self._workers.discard(worker)
            worker.release_references()
            self.active_changed.emit(self.active_count)
            logger.exception("Unable to queue a background task")
            return None
        return worker

    def _release_worker(self, worker_ref: weakref.ReferenceType[Worker]) -> None:
        worker = worker_ref()
        if worker is not None:
            self._workers.discard(worker)
        self.active_changed.emit(self.active_count)

    @staticmethod
    def _log_worker_error(error: dict[str, str]) -> None:
        logger.error(
            "Background task failed: %s: %s\n%s",
            error.get("type", "Error"),
            error.get("message", ""),
            error.get("traceback", ""),
        )

    def shutdown(self, wait_msec: int = 0) -> bool:
        """Stop accepting new work and optionally wait for accepted jobs.

        Running jobs cannot be forcefully killed safely. Callers should prevent
        application shutdown while destructive file operations are active.
        """
        self._accepting = False
        if wait_msec <= 0:
            return not self.is_busy
        try:
            completed = bool(self.pool.waitForDone(wait_msec))
        except TypeError:
            self.pool.waitForDone()
            completed = True
        if completed and self._workers:
            self._workers.clear()
            self.active_changed.emit(0)
        return completed
