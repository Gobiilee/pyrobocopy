import shutil
from pathlib import Path
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
        if self._is_cancelled:
            return CopyResult(success=False, filepath=src, error_message="Cancelled", cancelled=True)
            
        try:
            # Make sure have folder name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return CopyResult(success=True, filepath=src)
        except Exception as e:
            return CopyResult(success=False, filepath=src, error_message=str(e))

    def get_folder_stats(self, src_path):
        """Scans the folder to return a list of files and total size in bytes."""
        files = []
        total_size_bytes = 0
        for f in src_path.rglob('*'):
            if f.is_file():
                files.append(f)
                total_size_bytes += f.stat().st_size 
        return files, total_size_bytes
