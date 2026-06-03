import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QObject, pyqtSignal, QThread
from models.copier import RoboCopier, CopyResult

class CopyWorker(QThread):
    """
    A background thread to run the blocking copy process.
    Prevents the main UI from freezing.
    """
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list)
    progress_signal = pyqtSignal(str)

    def __init__(self, copier: RoboCopier, src: str, dst: str):
        super().__init__()
        self.copier = copier
        self.src = src
        self.dst = dst

    def run(self) -> None:
        self.log_signal.emit(f"Starting copy from {self.src} to {self.dst}...")
        
        self.copier._is_cancelled = False
        src_path = Path(self.src)
        dst_path = Path(self.dst) / src_path.name
        results: list[CopyResult] = []

        if not src_path.exists():
            results.append(CopyResult(False, src_path, "Source directory does not exist."))
            self.finished_signal.emit(results)
            return

        self.log_signal.emit("Scanning directory, calculating size, and mapping structure...")
        
        files, total_size_bytes = self.copier.get_folder_stats(src_path)
        total_files = len(files)
        total_size_mb = total_size_bytes / (1024 * 1024)
        
        self.log_signal.emit(f"Total files found: {total_files}")
        self.log_signal.emit(f"Total size to copy: {total_size_mb:.2f} MB\n")
        
        if total_files == 0:
            self.log_signal.emit("No files found to copy.")
            self.finished_signal.emit(results)
            return

        success_count = 0
        processed_count = 0
        start_time = time.perf_counter()
        # Push the ThreadPoolExecutor into the Worker instead of leaving it in the Model 
        # helps control stop/cancel and emit signal real-time more smoothly
        with ThreadPoolExecutor(max_workers=self.copier.workers) as executor:
            future_to_file = {}
            for f in files:
                if self.copier._is_cancelled:
                    break
                dest_file = dst_path / f.relative_to(src_path)
                future = executor.submit(self.copier.copy_file, f, dest_file)
                future_to_file[future] = f

            processed_count = 0
            for future in as_completed(future_to_file):
                if self.copier._is_cancelled:
                    break
                
                result = future.result()
                processed_count += 1
                
                if not result.cancelled:
                    results.append(result)
                    # Send signal to UI
                    status = "Success" if result.success else "Failed"
                    percent = int((processed_count / total_files) * 100)
                    self.progress_signal.emit(f"[{processed_count}/{total_files}] Copied: {result.filepath.name} -> {status} - {percent}%")
        
        end_time = time.perf_counter()
        duration_seconds = max(end_time - start_time, 0.001) 
        speed_mb_per_second = total_size_mb / duration_seconds
        # --- SUMMARY ---
        self.log_signal.emit("\n" + "="*30)
        self.log_signal.emit("       COPY SUMMARY")
        self.log_signal.emit("="*30)
        self.log_signal.emit(f"Files Copied : {success_count} / {total_files}")
        self.log_signal.emit(f"Total Data   : {total_size_mb:.2f} MB")
        self.log_signal.emit(f"Time Taken   : {duration_seconds:.2f} seconds")
        if not self.copier._is_cancelled:
            self.log_signal.emit(f"Avg Speed    : {speed_mb_per_second:.2f} MB/s")
        self.log_signal.emit("="*30)

        self.finished_signal.emit(results)


class MainViewModel(QObject):
    """
    Transforms Model data into UI-friendly signals and handles user commands.
    """
    # Signals that the View will listen to
    log_updated = pyqtSignal(str)
    copy_finished = pyqtSignal()
    ui_state_changed = pyqtSignal(bool)  # True if busy, False if idle

    def __init__(self) -> None:
        super().__init__()
        self.copier = RoboCopier()
        self._worker: CopyWorker | None = None

    def start_copy(self, src: str, dst: str, workers: int) -> None:
        """Called by the View to begin the process."""
        if not src or not dst:
            self.log_updated.emit("Error: Source and Destination must be provided.")
            return

        self.ui_state_changed.emit(True)  # Tell UI to disable 'Start' button
        self.copier.workers = workers
        
        self._worker = CopyWorker(self.copier, src, dst)
        self._worker.log_signal.connect(self.log_updated.emit)
        self._worker.progress_signal.connect(self.log_updated.emit) # Log real-time
        self._worker.finished_signal.connect(self._on_copy_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def cancel_copy(self) -> None:
        """Called by the View when the user hits 'Cancel'."""
        if self._worker and self._worker.isRunning():
            self.log_updated.emit("Cancellation requested. Waiting for active files to finish...")
            self.copier.cancel()

    def _on_copy_finished(self, results: list[CopyResult]) -> None:
        """Processes the results from the background thread."""
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        
        self.log_updated.emit("=" * 30)
        if self.copier._is_cancelled:
            self.log_updated.emit("Process CANCELLED by user.")
        self.log_updated.emit(f"Process Complete. Copied: {success_count}, Failed: {fail_count}")
        
        # Log failures if any occurred
        if fail_count > 0:
            self.log_updated.emit("\nErrors encountered:")
            for r in results:
                if not r.success:
                    self.log_updated.emit(f"- {r.filepath.name}: {r.error_message}")
        
        self.ui_state_changed.emit(False)  # Tell UI to re-enable buttons
        self.copy_finished.emit()