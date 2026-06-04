import time
import shutil
from collections import deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import pyqtSignal, QThread

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

    def __init__(self, copier: RoboCopier, selected_paths: list[str], dst: str, move_mode: bool):
        super().__init__()
        self.copier = copier
        self.selected_paths = selected_paths
        self.dst = dst
        self.move_mode = move_mode

    def run(self) -> None:
        self.copier._is_cancelled = False

        dst_root = Path(self.dst)
        results: list[CopyResult] = []

        if not dst_root.exists():
            try:
                dst_root.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.log_message.emit(f"Error creating destination folder: {e}")
                self.finished_sig.emit([])
                return

        # ── scan mixed items queue ────────────────────────────────────────────
        self.log_message.emit("Scanning source files and target directories layout...")
        
        files_to_copy = []
        total_bytes = 0

        for path_str in self.selected_paths:
            if self.copier._is_cancelled:
                break
            p = Path(path_str)
            if p.is_file():
                files_to_copy.append((p, p.parent))
                total_bytes += p.stat().st_size
            elif p.is_dir():
                for item in p.rglob('*'):
                    if item.is_file():
                        files_to_copy.append((item, p.parent))
                        total_bytes += item.stat().st_size

        total_files = len(files_to_copy)
        self.log_message.emit(f"Found {total_files} files · {fmt_size(total_bytes)} total data size")
        self.scan_done.emit(total_files, total_bytes)

        if total_files == 0:
            self.log_message.emit("No valid data elements found inside staging selection.")
            self.finished_sig.emit([])
            return

        # ── copy execution loop ───────────────────────────────────────────────
        # Rolling 3-second speed window
        speed_window: deque[tuple[float, int]] = deque()
        WINDOW = 3.0

        copied_files = 0
        copied_bytes = 0
        start_time = time.perf_counter()
        last_stats_emit = start_time

        with ThreadPoolExecutor(max_workers=self.copier.workers) as pool:
            future_map = {}
            for f, base_parent in files_to_copy:
                if self.copier._is_cancelled:
                    break
                
                # Reconstruct relative folders matching source tree structure over target location
                dest_file = dst_root / f.relative_to(base_parent)
                
                # Inject copy method directly or wrapped for safety cleanup deletion rules
                future = pool.submit(self._execute_transfer, f, dest_file)
                future_map[future] = f

            for future in as_completed(future_map):
                if self.copier._is_cancelled:
                    break

                result = future.result()
                if result.cancelled:
                    continue

                results.append(result)
                copied_files += 1

                # Signal the completed file status update to buffering queue
                self.file_done.emit(
                    result.filepath.name,
                    getattr(result, 'size_bytes', 0),
                    result.success
                )

                if result.success:
                    file_size = getattr(result, 'size_bytes', 0)
                    copied_bytes += file_size
                    now = time.perf_counter()
                    speed_window.append((now, file_size))

                    # Prune old window entries
                    cutoff = now - WINDOW
                    while speed_window and speed_window[0][0] < cutoff:
                        speed_window.popleft()

                    # Emit stats throttled via internal ticks
                    if now - last_stats_emit >= self.STATS_INTERVAL:
                        last_stats_emit = now
                        window_bytes = sum(b for _, b in speed_window)
                        window_dur   = now - speed_window[0][0] + 0.001
                        speed_bps    = window_bytes / window_dur
                        remaining    = max(0, total_bytes - copied_bytes)
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
            self.log_message.emit("⚠  Transfer sequence aborted by user")
        self.log_message.emit(
            f"✓ {ok} processed  ✗ {fail} failed   "
            f"{fmt_size(copied_bytes)} in {fmt_time(elapsed)}   "
            f"avg {fmt_size(int(avg_speed))}/s"
        )
        self.log_message.emit("─" * 40)
        self.finished_sig.emit(results)

    def _execute_transfer(self, src: Path, dst: Path) -> CopyResult:
        """Internal worker method to copy files and process optional safe erasure rules."""
        if self.copier._is_cancelled:
            return CopyResult(success=False, filepath=src, error_message="Cancelled", cancelled=True)
        
        try:
            size = src.stat().st_size
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            
            # SAFE CUT ACTION: Delete the source file only after checking copy returns success
            if self.move_mode:
                src.unlink()
                
            res = CopyResult(success=True, filepath=src)
            res.size_bytes = size  # dynamically attach size attributes
            return res
        except Exception as e:
            res = CopyResult(success=False, filepath=src, error_message=str(e))
            res.size_bytes = 0
            return res

