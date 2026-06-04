"""
ViewModel – bridges CopyWorker (background thread) and the View.

Performance design
──────────────────
The worker emits signals into thread-safe queues.
A 100 ms QTimer on the main thread drains those queues and
updates the UI in one batch — at most 10 repaints/second
regardless of how many files complete per second.
"""

import time
from collections import deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from models.copier import RoboCopier, CopyResult


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


# ── worker thread ─────────────────────────────────────────────────────────────

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

        with ThreadPoolExecutor(max_workers=self.copier.workers) as pool:
            future_map = {
                pool.submit(self.copier.copy_file, f, dst_path / f.relative_to(src_path)): f
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

                # Signal the completed file (cheap: name + int + bool)
                self.file_done.emit(
                    result.filepath.name,
                    result.size_bytes,
                    result.success,
                )

                if result.success:
                    copied_bytes += result.size_bytes
                    now = time.perf_counter()
                    speed_window.append((now, result.size_bytes))

                    # Prune old window entries
                    cutoff = now - WINDOW
                    while speed_window and speed_window[0][0] < cutoff:
                        speed_window.popleft()

                    # Emit stats at most every STATS_INTERVAL seconds
                    if now - last_stats_emit >= self.STATS_INTERVAL:
                        last_stats_emit = now
                        window_bytes = sum(b for _, b in speed_window)
                        window_dur   = now - speed_window[0][0] + 0.001
                        speed_bps    = window_bytes / window_dur
                        remaining    = total_bytes - copied_bytes
                        eta          = remaining / speed_bps if speed_bps > 0 else 0
                        self.stats_tick.emit(
                            copied_files, total_files,
                            copied_bytes, total_bytes,
                            speed_bps, eta,
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


# ── view-model ────────────────────────────────────────────────────────────────

class MainViewModel(QObject):
    """
    Receives raw signals from the worker, buffers them,
    and re-emits coarse-grained UI signals on a 100 ms timer.
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
        self._worker: CopyWorker | None = None

        # Pending file events waiting to be flushed to the View
        self._pending_files: list[tuple[str, str, str]] = []

        # 100 ms flush timer (only runs while copying)
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_MS)
        self._flush_timer.timeout.connect(self._flush)

        # Cache the last stats so we can re-emit on flush
        self._last_stats: tuple | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def start_copy(self, src: str, dst: str, workers: int) -> None:
        if not src or not dst:
            self.log_updated.emit("Error: Source and Destination must be set.")
            return

        self.copier.workers = workers
        self._pending_files.clear()
        self._last_stats = None
        self.ui_busy.emit(True)

        self._worker = CopyWorker(self.copier, src, dst)
        self._worker.log_message.connect(self.log_updated)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.stats_tick.connect(self._on_stats_tick)
        self._worker.finished_sig.connect(self._on_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

        self._flush_timer.start()

    def cancel_copy(self) -> None:
        if self._worker and self._worker.isRunning():
            self.log_updated.emit("Cancellation requested…")
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
