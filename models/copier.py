import shutil
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

@dataclass
class CopyResult:
    """Data structure to hold the result of a single file copy operation."""
    success: bool
    filepath: Path
    error_message: str | None = None
    cancelled: bool = False  # Added to track if the file was skipped due to cancel


class RoboCopier:
    def __init__(self, workers: int = 8) -> None:
        """Initializes the file copier model."""
        self.workers: int = workers
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        """Flags the current copy operation to abort."""
        self._is_cancelled = True

    def copy_file(self, src: Path, dst: Path) -> CopyResult:
        """
        Copies a single file, checking for cancellation before running.
        """
        # If cancelled before this thread picks up the task, abort early
        if self._is_cancelled:
            return CopyResult(success=False, filepath=src, error_message="Cancelled", cancelled=True)
            
        try:
            shutil.copy2(src, dst)
            return CopyResult(success=True, filepath=src)
        except Exception as e:
            return CopyResult(success=False, filepath=src, error_message=str(e))

    def execute_copy(self, src_dir: str, dest_dir: str) -> list[CopyResult]:
        """Executes a multi-threaded folder copy with robust cancellation."""
        self._is_cancelled = False
        src_path = Path(src_dir)
        dst_path = Path(dest_dir) / src_path.name
        results: list[CopyResult] = []

        if not src_path.exists():
            results.append(CopyResult(False, src_path, "Source directory does not exist."))
            return results

        # Create folder structure
        for d in src_path.rglob('*'):
            if d.is_dir():
                (dst_path / d.relative_to(src_path)).mkdir(parents=True, exist_ok=True)

        files = [f for f in src_path.rglob('*') if f.is_file()]

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_file = {}
            for f in files:
                # Do not submit new tasks if already cancelled
                if self._is_cancelled:
                    break
                dest_file = dst_path / f.relative_to(src_path)
                future = executor.submit(self.copy_file, f, dest_file)
                future_to_file[future] = f

            for future in as_completed(future_to_file):
                result = future.result()
                # Only add successful copies or non-cancelled failures to results
                if not result.cancelled:
                    results.append(result)

        return results