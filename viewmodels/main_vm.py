"""
ViewModel – bridges CopyWorker / RobocopyWorker (background thread) and the View.

Copy-engine modes
─────────────────
  "python"   – built-in chunked copy via models.copier.RoboCopier  (original)
  "robocopy" – subprocess robocopy.exe via models.robocopy_runner.RobocopyRunner

Performance design (python mode)
──────────────────────────────────
The worker emits signals into thread-safe queues.
A 100 ms QTimer on the main thread drains those queues and
updates the UI in one batch — at most 10 repaints/second
regardless of how many files complete per second.

Large-file fix (python mode)
──────────────────────────────
copier.copy_file() now accepts a progress_cb that fires after every
256 KB chunk.  The worker emits a ``bytes_tick`` signal from that
callback so stats/ETA keep updating even when only one huge file is
being copied.
"""

import time
from collections import deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from models.copier import RoboCopier, CopyResult
from models.robocopy_runner import RobocopyRunner, RobocopyOptions


# ── formatting helpers ────────────────────────────────────────────────────────

def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ── Python-mode worker thread ─────────────────────────────────────────────────

class CopyWorker(QThread):
    """
    Runs file copying on a background thread.
    All signals go to thread-safe queues; the main thread drains them
    via a QTimer — never directly updating widgets from here.
    """

    # Emitted once when scanning is done (total_files, total_bytes)
    scan_done    = pyqtSignal(int, int)
    # Emitted per completed file (name, size_bytes, success)
    file_done    = pyqtSignal(str, int, bool)
    # Emitted after every chunk inside a large file (bytes_just_written)
    bytes_tick   = pyqtSignal(int)
    # Periodic stats (copied_files, total_files, copied_bytes, total_bytes, speed_bps, eta_sec)
    stats_tick   = pyqtSignal(int, int, int, int, float, float)
    # Simple log lines
    log_message  = pyqtSignal(str)
    # Final list of results
    finished_sig = pyqtSignal(list)

    # How often (seconds) to emit a stats_tick while copying
    STATS_INTERVAL = 0.1

    def __init__(self, copier: RoboCopier, src: str, dst: str):
        super().__init__()
        self.copier = copier
        self.src = src
        self.dst = dst

    def run(self) -> None:
        self.copier._is_cancelled = False

        src_path = Path(self.src)
        dst_path = Path(self.dst) / src_path.name

        if not src_path.exists():
            self.log_message.emit(f"Error: Source '{self.src}' does not exist.")
            self.finished_sig.emit([])
            return

        # ── scan ──────────────────────────────────────────────────────────────
        self.log_message.emit("Scanning source folder…")
        files, total_bytes = self.copier.get_folder_stats(src_path)
        total_files = len(files)
        self.log_message.emit(f"Found {total_files} files · {fmt_size(total_bytes)} total")
        self.scan_done.emit(total_files, total_bytes)

        if total_files == 0:
            self.log_message.emit("Nothing to copy.")
            self.finished_sig.emit([])
            return

        # ── copy ──────────────────────────────────────────────────────────────
        # Rolling 3-second speed window
        speed_window: deque[tuple[float, int]] = deque()
        WINDOW = 3.0

        copied_files = 0
        copied_bytes = 0
        results: list[CopyResult] = []
        start_time = time.perf_counter()
        last_stats_emit = start_time

        def _emit_stats():
            """Recalculate and emit stats_tick. Called from progress_cb and after each file."""
            nonlocal last_stats_emit
            now = time.perf_counter()
            if now - last_stats_emit < self.STATS_INTERVAL:
                return
            last_stats_emit = now

            # Prune old window entries
            cutoff = now - WINDOW
            while speed_window and speed_window[0][0] < cutoff:
                speed_window.popleft()

            if speed_window:
                window_bytes = sum(b for _, b in speed_window)
                window_dur   = now - speed_window[0][0] + 0.001
                speed_bps    = window_bytes / window_dur
            else:
                speed_bps = 0.0

            remaining = max(total_bytes - copied_bytes, 0)
            eta = remaining / speed_bps if speed_bps > 0 else 0.0
            self.stats_tick.emit(
                copied_files, total_files,
                copied_bytes, total_bytes,
                speed_bps, eta,
            )

        def _make_progress_cb():
            """
            Returns a closure that the copier calls after each 256 KB chunk.
            Adds to the rolling speed window and emits a stats_tick if enough
            time has passed — this is the key fix for large-file UI freezes.
            """
            def progress_cb(chunk_bytes: int):
                nonlocal copied_bytes
                now = time.perf_counter()
                copied_bytes += chunk_bytes
                speed_window.append((now, chunk_bytes))
                # Signal raw bytes so the VM can re-emit to View
                self.bytes_tick.emit(chunk_bytes)
                _emit_stats()
            return progress_cb

        with ThreadPoolExecutor(max_workers=self.copier.workers) as pool:
            future_map = {
                pool.submit(
                    self.copier.copy_file,
                    f,
                    dst_path / f.relative_to(src_path),
                    _make_progress_cb(),
                ): f
                for f in files
                if not self.copier._is_cancelled
            }

            for future in as_completed(future_map):
                if self.copier._is_cancelled:
                    break

                result = future.result()
                if result.cancelled:
                    continue

                results.append(result)
                copied_files += 1

                # NOTE: copied_bytes already includes this file's bytes via
                # the progress_cb, so we must NOT add size_bytes here again.
                _emit_stats()

                # Signal the completed file (cheap: name + int + bool)
                self.file_done.emit(
                    result.filepath.name,
                    result.size_bytes,
                    result.success,
                )

        # ── summary ───────────────────────────────────────────────────────────
        elapsed   = max(time.perf_counter() - start_time, 0.001)
        avg_speed = copied_bytes / elapsed
        ok        = sum(1 for r in results if r.success)
        fail      = len(results) - ok

        self.log_message.emit("─" * 40)
        if self.copier._is_cancelled:
            self.log_message.emit("⚠  Transfer cancelled by user")
        self.log_message.emit(
            f"✓ {ok} copied   ✗ {fail} failed   "
            f"{fmt_size(copied_bytes)} in {fmt_time(elapsed)}   "
            f"avg {fmt_size(int(avg_speed))}/s"
        )
        self.log_message.emit("─" * 40)
        self.finished_sig.emit(results)


# ── Robocopy-mode worker thread ───────────────────────────────────────────────

class RobocopyWorker(QThread):
    """
    Wraps RobocopyRunner in a QThread and re-emits the same signals
    as CopyWorker so MainViewModel can handle both identically.
    """

    scan_done    = pyqtSignal(int, int)
    file_done    = pyqtSignal(str, int, bool)
    bytes_tick   = pyqtSignal(int)
    stats_tick   = pyqtSignal(int, int, int, int, float, float)
    log_message  = pyqtSignal(str)
    finished_sig = pyqtSignal(list)   # emits empty list (no CopyResult objects)

    def __init__(self, runner: RobocopyRunner, src: str, dst: str):
        super().__init__()
        self.runner = runner
        self.src    = src
        self.dst    = dst

    def run(self) -> None:
        self.runner._cancelled = False

        # Mirror Python-mode behaviour: copy src into dst/<src_name>/
        src_name = Path(self.src).name
        dst_path = str(Path(self.dst) / src_name)

        # Emit a synthetic scan_done so the UI shows *something* immediately.
        # We don't have a total in advance with robocopy, so we use 0/0.
        self.scan_done.emit(0, 0)

        def _log(line: str):
            self.log_message.emit(line)

        def _file_done(name: str, size: int, ok: bool):
            self.file_done.emit(name, size, ok)

        def _stats(cf, tf, cb, tb, speed, eta):
            self.stats_tick.emit(cf, tf, cb, tb, speed, eta)

        def _finished(ok: bool, exit_code: int):
            status = "completed successfully" if ok else f"finished with errors (code {exit_code})"
            self.log_message.emit("─" * 40)
            self.log_message.emit(f"robocopy {status}  (exit {exit_code})")
            self.log_message.emit("─" * 40)

        try:
            exit_code = self.runner.run(
                self.src, dst_path,
                log_cb=_log,
                file_done_cb=_file_done,
                stats_cb=_stats,
                finished_cb=_finished,
            )
        except Exception as exc:
            self.log_message.emit(f"ERROR: {exc}")

        self.finished_sig.emit([])


# ── view-model ────────────────────────────────────────────────────────────────

class MainViewModel(QObject):
    """
    Receives raw signals from the worker, buffers them,
    and re-emits coarse-grained UI signals on a 100 ms timer.

    Supports two copy engines:
      • "python"   – built-in Python copy  (CopyWorker)
      • "robocopy" – subprocess robocopy   (RobocopyWorker)
    """

    # ── outgoing signals (View listens to these) ──────────────────────────────
    log_updated   = pyqtSignal(str)
    # Batch of completed rows: list of (name, size_str, status_str)
    file_batch    = pyqtSignal(list)
    stats_update  = pyqtSignal(int, int, int, int, float, float)
    copy_finished = pyqtSignal()
    ui_busy       = pyqtSignal(bool)

    # ── flush interval ────────────────────────────────────────────────────────
    FLUSH_MS = 100   # drain queue and repaint at most 10×/s

    def __init__(self) -> None:
        super().__init__()
        self.copier  = RoboCopier()
        self.runner  = RobocopyRunner()          # robocopy engine
        self._worker: CopyWorker | RobocopyWorker | None = None

        # Current engine: "python" or "robocopy"
        self.engine: str = "python"

        # Pending file events waiting to be flushed to the View
        self._pending_files: list[tuple[str, str, str]] = []

        # 100 ms flush timer (only runs while copying)
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_MS)
        self._flush_timer.timeout.connect(self._flush)

        # Cache the last stats so we can re-emit on flush
        self._last_stats: tuple | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def set_engine(self, engine: str) -> None:
        """Switch copy engine. Call before start_copy(). engine ∈ {'python','robocopy'}"""
        assert engine in ("python", "robocopy"), f"Unknown engine: {engine!r}"
        self.engine = engine

    def set_robocopy_options(self, options: RobocopyOptions) -> None:
        self.runner.options = options

    def start_copy(self, src: str, dst: str, workers: int) -> None:
        if not src or not dst:
            self.log_updated.emit("Error: Source and Destination must be set.")
            return

        self._pending_files.clear()
        self._last_stats = None
        self.ui_busy.emit(True)

        if self.engine == "robocopy":
            # Pass workers into the robocopy options thread count
            self.runner.options.threads = workers
            worker = RobocopyWorker(self.runner, src, dst)
        else:
            self.copier.workers = workers
            worker = CopyWorker(self.copier, src, dst)

        self._worker = worker
        worker.log_message.connect(self.log_updated)
        worker.file_done.connect(self._on_file_done)
        worker.stats_tick.connect(self._on_stats_tick)
        worker.finished_sig.connect(self._on_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

        self._flush_timer.start()

    def cancel_copy(self) -> None:
        if self._worker and self._worker.isRunning():
            self.log_updated.emit("Cancellation requested…")
            if isinstance(self._worker, RobocopyWorker):
                self.runner.cancel()
            else:
                self.copier.cancel()

    # ── worker signal receivers (can be called from any thread via Qt queued) ─

    def _on_file_done(self, name: str, size_bytes: int, success: bool) -> None:
        status = "done" if success else "failed"
        self._pending_files.append((name, fmt_size(size_bytes), status))

    def _on_stats_tick(self, cf, tf, cb, tb, speed, eta) -> None:
        # Just cache; _flush will emit to the View
        self._last_stats = (cf, tf, cb, tb, speed, eta)

    def _on_finished(self, results: list) -> None:
        self._flush_timer.stop()
        self._flush()          # drain anything still pending
        self.ui_busy.emit(False)
        self.copy_finished.emit()

    # ── flush (main thread, called by timer) ──────────────────────────────────

    def _flush(self) -> None:
        if self._pending_files:
            self.file_batch.emit(list(self._pending_files))
            self._pending_files.clear()

        if self._last_stats:
            self.stats_update.emit(*self._last_stats)
            self._last_stats = None
