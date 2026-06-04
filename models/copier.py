import shutil
import time
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class CopyResult:
    """Result of a single file copy."""
    success: bool
    filepath: Path
    size_bytes: int = 0
    duration_seconds: float = 0.0
    error_message: str | None = None
    cancelled: bool = False


class RoboCopier:
    """Handles file scanning and copying."""

    def __init__(self, workers: int = 8) -> None:
        self.workers = workers
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def copy_file(self, src: Path, dst: Path) -> CopyResult:
        if self._is_cancelled:
            return CopyResult(success=False, filepath=src, cancelled=True)

        size = src.stat().st_size
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            shutil.copy2(src, dst)
            elapsed = time.perf_counter() - t0
            return CopyResult(success=True, filepath=src, size_bytes=size, duration_seconds=elapsed)
        except Exception as e:
            return CopyResult(success=False, filepath=src, size_bytes=size, error_message=str(e))

    def get_folder_stats(self, src_path: Path) -> tuple[list[Path], int]:
        """Return list of files and total size in bytes."""
        files = []
        total_bytes = 0
        for f in src_path.rglob("*"):
            if f.is_file():
                files.append(f)
                total_bytes += f.stat().st_size
        return files, total_bytes
