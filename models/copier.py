import shutil
import time
from pathlib import Path
from dataclasses import dataclass


@dataclass
class CopyResult:
    """Result of a single file copy operation."""
    success: bool
    filepath: Path
    size_bytes: int = 0
    duration_seconds: float = 0.0
    error_message: str | None = None
    cancelled: bool = False


class RoboCopier:
    """Handles deep asynchronous metadata scanning and multithreaded file copying."""

    def __init__(self, workers: int = 8) -> None:
        self.workers = workers
        self._is_cancelled = False

    def cancel(self) -> None:
        """Flags the running processing thread loop to terminate safely."""
        self._is_cancelled = True

    def copy_file(self, src: Path, dst: Path, move_mode: bool = False) -> CopyResult:
        """
        Executes file transfers with safety checks, performance tracking,
        and support for optional cut/move modes.
        """
        if self._is_cancelled:
            return CopyResult(success=False, filepath=src, error_message="Cancelled", cancelled=True)
            
        # Pre-calculate file stats for reporting metrics back to UI even on failures
        try:
            size = src.stat().st_size
        except Exception as e:
            return CopyResult(success=False, filepath=src, size_bytes=0, error_message=f"Access error: {e}")

        try:
            # Ensure the relative sub-folder tree maps out correctly to its destination target
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            t0 = time.perf_counter()
            shutil.copy2(src, dst)
            elapsed = time.perf_counter() - t0
            
            # If "Cut Mode" is selected, delete source only after successful copy sequence validation
            if move_mode:
                src.unlink()
                
            return CopyResult(
                success=True, 
                filepath=src, 
                size_bytes=size, 
                duration_seconds=elapsed
            )
        except Exception as e:
            return CopyResult(
                success=False, 
                filepath=src, 
                size_bytes=size, 
                error_message=str(e)
            )

    def get_item_stats(self, paths: list[Path]) -> tuple[list[tuple[Path, Path]], int]:
        """
        Scans mixed lists of dropped files and directories.
        Returns a flat list of (target_file_path, context_base_parent) mappings 
        along with the aggregated total byte calculation.
        """
        files_mapping: list[tuple[Path, Path]] = []
        total_size_bytes = 0
        
        for path in paths:
            if self._is_cancelled:
                break
            try:
                if path.is_file():
                    files_mapping.append((path, path.parent)) # Replicate relative to original file parent
                    total_size_bytes += path.stat().st_size
                elif path.is_dir():
                    # Recurse and flatten deep underlying target layouts
                    for f in path.rglob('*'):
                        if self._is_cancelled:
                            break
                        if f.is_file():
                            files_mapping.append((f, path.parent)) # Replicate relative to targeted base dir parent
                            total_size_bytes += f.stat().st_size
            except Exception:
                # Silently catch unreachable system nodes or locked access objects during pre-scanning
                continue
                
        return files_mapping, total_size_bytes