from PyQt6.QtCore import QObject, pyqtSignal, QThread
from models.copier import RoboCopier, CopyResult

class CopyWorker(QThread):
    """
    A background thread to run the blocking copy process.
    Prevents the main UI from freezing.
    """
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list)

    def __init__(self, copier: RoboCopier, src: str, dst: str):
        super().__init__()
        self.copier = copier
        self.src = src
        self.dst = dst

    def run(self) -> None:
        """Executes when thread.start() is called."""
        self.log_signal.emit(f"Starting copy from {self.src} to {self.dst}...")
        
        # This is a blocking call to the Model's logic
        results = self.copier.execute_copy(self.src, self.dst)
        
        # Emit the final results back to the ViewModel
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
        self._worker.finished_signal.connect(self._on_copy_finished)
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
        self.log_updated.emit(f"Process Complete. Copied: {success_count}, Failed: {fail_count}")
        
        # Log failures if any occurred
        if fail_count > 0:
            self.log_updated.emit("\nErrors encountered:")
            for r in results:
                if not r.success:
                    self.log_updated.emit(f"- {r.filepath.name}: {r.error_message}")
        
        self.ui_state_changed.emit(False)  # Tell UI to re-enable buttons
        self.copy_finished.emit()