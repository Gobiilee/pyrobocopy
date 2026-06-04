"""
ViewModel – bridges CopyWorker (background thread) and the View.

Performance design
──────────────────
The worker emits signals into thread-safe queues.
A 100 ms QTimer on the main thread drains those queues and
updates the UI in one batch — at most 10 repaints/second
regardless of how many files complete per second.
"""

from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from models.copier import RoboCopier
from viewmodels.copy_woker import CopyWorker, fmt_size, fmt_time

# ── view-model ────────────────────────────────────────────────────────────────

class MainViewModel(QObject):
    """
    Receives raw signals from the worker, buffers them,
    and re-emits coarse-grained UI signals on a 100 ms timer.
    """

    # ── outgoing signals (View listens to these) ──────────────────────────────
    log_updated       = pyqtSignal(str)
    copy_finished     = pyqtSignal()
    ui_state_changed  = pyqtSignal(bool)
    selection_updated = pyqtSignal(object)
    
    # Batch of completed rows: list of (name, size_str, status_str)
    file_batch        = pyqtSignal(list)
    stats_update      = pyqtSignal(int, int, int, int, float, float)

    # ── flush interval ────────────────────────────────────────────────────────
    FLUSH_MS = 100   # drain queue and repaint at most 10×/s

    def __init__(self) -> None:
        super().__init__()
        self.copier  = RoboCopier()
        self._worker: CopyWorker | None = None
        self._selected_paths: list[str] = []

        # Pending file events waiting to be flushed to the View
        self._pending_files: list[tuple[str, str, str]] = []

        # 100 ms flush timer (only runs while copying)
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_MS)
        self._flush_timer.timeout.connect(self._flush)

        # Cache the last stats so we can re-emit on flush
        self._last_stats: tuple | None = None
    
    def add_paths(self, paths: list[str]) -> None:
        for p in paths:
            if p and p not in self._selected_paths:
                self._selected_paths.append(p)
        self.selection_updated.emit(self._selected_paths)

    def remove_path(self, path: str) -> None:
        if path in self._selected_paths:
            self._selected_paths.remove(path)
        self.selection_updated.emit(self._selected_paths)

    def clear_selection(self) -> None:
        self._selected_paths.clear()
        self.selection_updated.emit(self._selected_paths)

    # ── public ────────────────────────────────────────────────────────────────

    def start_copy(self, dst_dir: str, move_mode: bool) -> None:
        """v2 core processing activation routine."""
        if not self._selected_paths:
            self.log_updated.emit("Error: Source queue staging selection list is empty.")
            return
        if not dst_dir:
            self.log_updated.emit("Error: Destination folder target path must be defined.")
            return

        self.ui_state_changed.emit(True)
        self.copier._is_cancelled = False

        self._pending_files.clear()
        self._last_stats = (0, 0, 0, 0, 0.0, 0.0)

        # Initialize background worker engine with clean array states
        self._worker = CopyWorker(self.copier, self._selected_paths, dst_dir, move_mode)
        self._worker.log_message.connect(lambda msg: self.log_updated.emit(msg))
        self._worker.file_done.connect(self._on_file_done)
        self._worker.stats_tick.connect(self._on_stats_tick)
        self._worker.finished_sig.connect(self._on_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        
        self._worker.start()
        self._flush_timer.start()

    def cancel_copy(self) -> None:
        if self._worker and self._worker.isRunning():
            self.log_updated.emit("Cancellation requested, cleaning pipeline workers safely...")
            self.copier.cancel()

    # ── worker signal receivers (called via thread-safe Qt queued connection) ──

    def _on_file_done(self, name: str, size_bytes: int, success: bool) -> None:
        status = "done" if success else "failed"
        self._pending_files.append((name, fmt_size(size_bytes), status))

    def _on_stats_tick(self, cf, tf, cb, tb, speed, eta) -> None:
        self._last_stats = (cf, tf, cb, tb, speed, eta)

    def _on_finished(self, results: list) -> None:
        self._flush_timer.stop()
        self._flush()  # sweep lingering items out of buffers
        
        # ── DELETE FOLDER EMPTY WHEN TURN ON CUT MODE ─────────────────────
        is_move_mode = getattr(self._worker, 'move_mode', False) if self._worker else False

        if is_move_mode and not self.copier._is_cancelled and any(r.success for r in results):
            parent_dirs = set()
            
            for p_raw in self._selected_paths:
                p = Path(p_raw)
                
                if p.is_dir():
                    parent_dirs.add(p)
                    for child in p.rglob('*'):
                        if child.is_dir():
                            parent_dirs.add(child)
                elif p.is_file():
                    parent_dirs.add(p.parent)

            sorted_dirs = sorted(parent_dirs, key=lambda x: len(str(x)), reverse=True)

            for d in sorted_dirs:
                try:
                    if d.exists() and d.is_dir() and not any(d.iterdir()):
                        d.rmdir()
                except Exception as e:
                    self.log_updated.emit(f"Can not delete empty folder {d.name}: {e}")

        if not self.copier._is_cancelled and all(r.success for r in results):
            self.clear_selection()

        self.ui_state_changed.emit(False)
        self.copy_finished.emit()

    # ── flush (main thread, triggered by event loop timer) ───────────────────
    def _flush(self) -> None:
        if self._pending_files:
            self.file_batch.emit(list(self._pending_files))
            self._pending_files.clear()

        if self._last_stats:
            self.stats_update.emit(*self._last_stats)
            self._last_stats = None