"""Reusable bounded background workers for non-UI work."""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from typing import Any

from .qt_compat import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

PROGRESS_MIN_INTERVAL_SECONDS = 0.05
MAX_ERROR_MESSAGE_CHARS = 16_384
MAX_TRACEBACK_CHARS = 65_536
THREAD_EXPIRY_TIMEOUT_MSEC = 5_000


def _bounded_text(value: Any, limit: int, *, keep_tail: bool = False) -> str:
    """Return text capped before it is copied into the Qt event queue."""

    text = str(value)
    if len(text) <= limit:
        return text
    marker = "\n… output truncated …\n"
    available = max(0, limit - len(marker))
    if available == 0:
        return marker[:limit]
    if keep_tail:
        return marker + text[-available:]
    return text[:available] + marker


class WorkerSignals(QObject):
    """Signals emitted by :class:`Worker` from a pool thread."""

    result = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(object)
    finished = pyqtSignal()
    completed = pyqtSignal(object)


class Worker(QRunnable):
    """Run one callable in a QThreadPool.

    When ``with_progress`` is true, the callable receives a keyword argument
    named ``progress_callback`` whose value is a rate-limited signal emitter.
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
        self._last_progress_emit = 0.0

        # Payload completion and QObject callback teardown are separate phases.
        # The payload marker is published before the private completion signal;
        # callback disconnection happens later on the TaskManager thread.
        self._disposed = False
        self._signals_disposed = False
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
                self.kwargs["progress_callback"] = self._emit_progress
            result = function(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - exercised via Qt runtime
            self.signals.error.emit(
                {
                    "type": type(exc).__name__,
                    "message": _bounded_text(exc, MAX_ERROR_MESSAGE_CHARS),
                    "traceback": _bounded_text(
                        traceback.format_exc(),
                        MAX_TRACEBACK_CHARS,
                        keep_tail=True,
                    ),
                }
            )
        else:
            self.signals.result.emit(result)
        finally:
            self.release_references()

            # Keep public callbacks connected through their emission. The
            # payload marker is then established before ``completed`` can make
            # TaskManager.active_count reach zero. ``finally`` also guarantees
            # cleanup notification if a Python signal callback unexpectedly
            # raises while ``finished`` is emitted.
            try:
                self.signals.finished.emit()
            finally:
                self._disposed = True
                self.signals.completed.emit(self)

    def _emit_progress(self, payload: Any) -> None:
        """Rate-limit queued UI progress without dropping the final update."""

        now = time.monotonic()
        terminal = False
        try:
            current, total, _label = payload
            terminal = int(total) > 0 and int(current) >= int(total)
        except (TypeError, ValueError):
            terminal = False

        if (
            self._last_progress_emit == 0.0
            or terminal
            or now - self._last_progress_emit >= PROGRESS_MIN_INTERVAL_SECONDS
        ):
            self._last_progress_emit = now
            self.signals.progress.emit(payload)

    def release_references(self) -> None:
        """Drop potentially large task inputs as soon as execution finishes."""

        self.function = None
        self.args = ()
        self.kwargs.clear()

    def dispose(self) -> None:
        """Release payloads and disconnect callbacks exactly once.

        ``_disposed`` can already be true because :meth:`run` publishes payload
        completion before notifying the manager. ``_signals_disposed`` is the
        separate idempotence guard for callback and QObject teardown.
        """

        self._disposed = True
        self.release_references()
        if self._signals_disposed:
            return

        self._signals_disposed = True
        for signal_name in (
            "result",
            "error",
            "progress",
            "finished",
            "completed",
        ):
            try:
                getattr(self.signals, signal_name).disconnect()
            except Exception:
                pass
        try:
            self.signals.deleteLater()
        except Exception:
            pass


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
            self.pool.setExpiryTimeout(THREAD_EXPIRY_TIMEOUT_MSEC)
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

        worker.signals.completed.connect(self._release_worker)
        try:
            self.pool.start(worker)
        except Exception:
            worker.dispose()
            self._workers.discard(worker)
            self.active_changed.emit(self.active_count)
            logger.exception("Unable to queue a background task")
            return None
        return worker

    @pyqtSlot(object)
    def _release_worker(self, worker: object) -> None:
        """Dispose a completed worker before publishing the idle state."""

        if not isinstance(worker, Worker):
            return

        # Initiate callback disconnection and QObject deletion before removing
        # the final retained worker. Every observer of active_count == 0 then
        # sees both disposal phases completed.
        worker.dispose()
        if worker not in self._workers:
            return
        self._workers.remove(worker)
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
            workers = tuple(self._workers)
            for worker in workers:
                worker.dispose()
            self._workers.clear()
            self.active_changed.emit(0)
        return completed
