"""
smb_browser.py  –  SMB/Network share browsing and downloading.

smbprotocol is an optional dependency. If it is not installed the
NetworkTab will show a clear install instruction instead of crashing.
"""

from __future__ import annotations
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable
from collections import deque

# Optional import — app still launches without it
try:
    import smbclient
    SMB_AVAILABLE = True
except ImportError:
    SMB_AVAILABLE = False


@dataclass
class SMBEntry:
    """Represents a file or folder on the SMB share."""
    name:       str
    path:       str          # full UNC path  \\server\share\sub\file
    is_dir:     bool
    size_bytes: int = 0
    children:   list["SMBEntry"] = field(default_factory=list)


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class SMBBrowser:
    """Connect to an SMB share and list / download its contents."""

    def __init__(self) -> None:
        self._is_cancelled = False

    # ── connection ────────────────────────────────────────────────────────────

    def connect(self, server: str, username: str,
                password: str, share: str) -> list[SMBEntry]:
        """
        Register credentials and list top-level contents of the share.
        Raises RuntimeError on failure.
        """
        if not SMB_AVAILABLE:
            raise RuntimeError(
                "smbprotocol is not installed.\n"
                "Run:  pip install smbprotocol"
            )
        smbclient.register_session(server, username=username, password=password)
        return self._list_dir(f"\\\\{server}\\{share}")

    def _list_dir(self, unc_path: str) -> list[SMBEntry]:
        entries: list[SMBEntry] = []
        try:
            for entry in smbclient.scandir(unc_path):
                is_dir = entry.is_dir()
                stat   = entry.stat()
                entries.append(SMBEntry(
                    name       = entry.name,
                    path       = f"{unc_path}\\{entry.name}",
                    is_dir     = is_dir,
                    size_bytes = stat.st_size if not is_dir else 0,
                ))
        except Exception as e:
            raise RuntimeError(f"Cannot list '{unc_path}': {e}") from e
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return entries

    def expand_dir(self, unc_path: str) -> list[SMBEntry]:
        return self._list_dir(unc_path)

    # ── download ──────────────────────────────────────────────────────────────

    def cancel(self) -> None:
        self._is_cancelled = True

    def download_selected(
        self,
        selected_paths: list[str],
        destination:    str,
        on_log:         Callable[[str], None],
        on_file_done:   Callable[[str, int, bool], None],
        on_stats:       Callable[[int, int, int, int, float, float], None],
        on_finished:    Callable[[int, int], None],
    ) -> None:
        self._is_cancelled = False

        # file_list  – (unc_path, size_bytes) for every file to copy
        # empty_dirs – unc_paths of directories that contained no files at all
        file_list:  list[tuple[str, int]] = []
        empty_dirs: list[str]             = []

        on_log("Scanning selected items…")
        for unc in selected_paths:
            if self._is_cancelled:
                break
            self._collect_files(unc, file_list, empty_dirs, on_log)

        total_files = len(file_list)
        total_bytes = sum(sz for _, sz in file_list)
        on_log(
            f"Found {total_files} file(s) · {_fmt_size(total_bytes)} total"
            + (f" · {len(empty_dirs)} empty folder(s)" if empty_dirs else "")
        )

        if self._is_cancelled:
            on_finished(0, 0)
            return

        # ── create empty directories first ────────────────────────────────────
        for unc_dir in empty_dirs:
            parts     = unc_dir.lstrip("\\").split("\\")
            rel_parts = parts[2:] if len(parts) > 2 else parts[-1:]
            local_dir = Path(destination).joinpath(*rel_parts)
            try:
                local_dir.mkdir(parents=True, exist_ok=True)
                on_log(f"  📁 Created empty folder: {local_dir}")
            except Exception as exc:
                on_log(f"  ⚠ Could not create folder '{local_dir}': {exc}")

        if total_files == 0:
            on_finished(0, 0)
            return

        # ── copy files ────────────────────────────────────────────────────────
        copied_files = 0
        copied_bytes = 0
        failed_files = 0
        speed_window: deque[tuple[float, int]] = deque()
        WINDOW     = 3.0
        start_time = time.perf_counter()
        last_stats = start_time

        for unc_path, size in file_list:
            if self._is_cancelled:
                break

            parts      = unc_path.lstrip("\\").split("\\")
            rel_parts  = parts[2:] if len(parts) > 2 else parts[-1:]
            local_path = Path(destination).joinpath(*rel_parts)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            success = False
            try:
                with smbclient.open_file(unc_path, mode="rb") as src_f:
                    with open(local_path, "wb") as dst_f:
                        while True:
                            chunk = src_f.read(1024 * 1024)
                            if not chunk:
                                break
                            dst_f.write(chunk)
                success = True
                copied_files += 1
                copied_bytes += size
            except Exception as exc:
                failed_files += 1
                on_log(f"  ✗ Failed: {unc_path} — {exc}")

            on_file_done(parts[-1], size, success)

            now = time.perf_counter()
            speed_window.append((now, size if success else 0))
            cutoff = now - WINDOW
            while speed_window and speed_window[0][0] < cutoff:
                speed_window.popleft()

            if now - last_stats >= 0.1:
                last_stats   = now
                window_bytes = sum(b for _, b in speed_window)
                window_dur   = now - speed_window[0][0] + 0.001
                speed_bps    = window_bytes / window_dur
                remaining    = total_bytes - copied_bytes
                eta          = remaining / speed_bps if speed_bps > 0 else 0
                on_stats(copied_files, total_files,
                         copied_bytes, total_bytes, speed_bps, eta)

        on_log("─" * 40)
        if self._is_cancelled:
            on_log("⚠  Download cancelled by user")
        on_log(
            f"✓ {copied_files} downloaded   ✗ {failed_files} failed   "
            f"{_fmt_size(copied_bytes)}"
        )
        on_log("─" * 40)
        on_finished(copied_files, failed_files)

    def _collect_files(
        self,
        unc_path:  str,
        out:       list[tuple[str, int]],
        empty_dirs: list[str],
        on_log:    Callable[[str], None],
    ) -> None:
        """
        Recursively collect all files under *unc_path* into *out*.
        Directories that turn out to contain no files (at any depth) are
        recorded in *empty_dirs* so the caller can still create them on disk.
        """
        try:
            import stat as stat_mod
            st = smbclient.stat(unc_path)
            if stat_mod.S_ISDIR(st.st_mode):
                children = list(smbclient.scandir(unc_path))
                if not children:
                    # Genuinely empty directory — record it directly.
                    empty_dirs.append(unc_path)
                else:
                    files_before = len(out)
                    for entry in children:
                        self._collect_files(
                            f"{unc_path}\\{entry.name}", out, empty_dirs, on_log
                        )
                    # If recursing into all children produced no files, this
                    # directory only contained other empty directories (which
                    # were already added). Nothing extra to do here.
            else:
                out.append((unc_path, st.st_size))
        except Exception as exc:
            on_log(f"  ⚠ Skipping '{unc_path}': {exc}")