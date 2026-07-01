"""
robocopy_runner.py – Runs the system robocopy.exe via subprocess and parses
its real-time output to emit progress events compatible with the existing
CopyWorker signal interface.

Only used on Windows (robocopy is a Windows built-in since Vista).
On non-Windows platforms every method raises RuntimeError immediately.
"""

from __future__ import annotations

import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


IS_WINDOWS = platform.system() == "Windows"


# ── Option dataclass ──────────────────────────────────────────────────────────

@dataclass
class RobocopyOptions:
    """All configurable robocopy switches exposed in the UI."""

    # Copy behaviour
    mirror: bool = False          # /MIR  – mirror (delete extra files in dst)
    move_files: bool = False      # /MOV  – move (delete src after copy)
    copy_subdirs: bool = True     # /S    – include non-empty subdirs
    copy_empty_dirs: bool = False # /E    – include empty subdirs (supersedes /S)
    copy_flags: str = "DAT"       # /COPY:<flags> – D=data A=attrs T=timestamps

    # Retry
    retry_count: int = 1          # /R:<n>
    retry_wait: int = 3           # /W:<n> seconds between retries

    # Filtering
    exclude_files: str = ""       # /XF <patterns>
    exclude_dirs: str = ""        # /XD <patterns>
    exclude_older: bool = False   # /XO  – skip files older than dst
    exclude_newer: bool = False   # /XN  – skip files newer than dst

    # Performance
    threads: int = 8              # /MT:<n>  (1 = no /MT flag)

    # Logging
    log_file: str = ""            # /LOG:<path>
    no_progress: bool = False     # /NP  (we add this ourselves for parsing)

    # Extra raw flags the user can type freely
    extra_flags: str = ""

    def build_args(self, src: str, dst: str) -> list[str]:
        """Return the full robocopy argument list (without the 'robocopy' exe name)."""
        args: list[str] = [src, dst]

        if self.mirror:
            args.append("/MIR")
        elif self.move_files:
            args.append("/MOV")
        elif self.copy_empty_dirs:
            args.append("/E")
        elif self.copy_subdirs:
            args.append("/S")

        if self.copy_flags:
            args.append(f"/COPY:{self.copy_flags}")

        args += [f"/R:{self.retry_count}", f"/W:{self.retry_wait}"]

        if self.threads > 1:
            args.append(f"/MT:{self.threads}")

        if self.exclude_files.strip():
            args += ["/XF"] + self.exclude_files.split()

        if self.exclude_dirs.strip():
            args += ["/XD"] + self.exclude_dirs.split()

        if self.exclude_older:
            args.append("/XO")
        if self.exclude_newer:
            args.append("/XN")

        # Always add /NP so we can parse percentage lines reliably
        args.append("/NP")

        if self.log_file.strip():
            args += [f"/LOG:{self.log_file.strip()}"]

        if self.extra_flags.strip():
            args += self.extra_flags.split()

        return args


# ── Progress parser ───────────────────────────────────────────────────────────

# Robocopy prints lines like:
#   100%   New File          1234567 filename.ext
#    50%
_PCT_RE  = re.compile(r"^\s*(\d+)%")
# With /NP (no-progress) robocopy emits ONE line per file — no leading "100%":
#           New File          1234567 D:\path\file.ext
# We require leading whitespace so header words like "New File" in the
# summary table don't accidentally match.
_FILE_RE = re.compile(
    r"^\s+(?:New File|Newer|Older|Same|Extra File|Lonely)\s+(\d+)\s+(.+)$"
)
# Summary block line:  Files :       123       0       0     123       0       0
#                      total  copied  skipped  mismatch  failed  extras
_SUMM_RE = re.compile(r"^\s*Files\s*:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)")


@dataclass
class RobocopyProgress:
    total_files: int = 0
    copied_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    last_pct: int = 0          # percentage of the current file
    last_filename: str = ""
    finished: bool = False
    exit_code: int | None = None
    log_lines: list[str] = field(default_factory=list)


class RobocopyRunner:
    """
    Wraps subprocess.Popen around robocopy.exe and provides a
    blocking ``run()`` method that calls callbacks as output arrives.
    """

    def __init__(self, options: RobocopyOptions | None = None) -> None:
        self.options = options or RobocopyOptions()
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def run(
        self,
        src: str,
        dst: str,
        *,
        log_cb: Callable[[str], None] | None = None,
        file_done_cb: Callable[[str, int, bool], None] | None = None,
        stats_cb: Callable[[int, int, int, int, float, float], None] | None = None,
        finished_cb: Callable[[bool, int], None] | None = None,
    ) -> int:
        """
        Start robocopy and stream its output.

        Callbacks mirror the MainViewModel's worker signals so the
        RobocopyWorker (QThread) can call the same downstream path.

        Returns the robocopy exit code (0-7 = success/warning, >=8 = error).
        """
        if not IS_WINDOWS:
            raise RuntimeError("robocopy is only available on Windows.")

        self._cancelled = False
        args = ["robocopy"] + self.options.build_args(src, dst)

        if log_cb:
            log_cb(f"Running: {' '.join(args)}")

        prog = RobocopyProgress()
        start_time = time.perf_counter()

        # Speed tracking — rolling 3-second window (mirrors Python-mode CopyWorker)
        from collections import deque
        speed_window: deque[tuple[float, int]] = deque()
        SPEED_WINDOW = 3.0
        copied_bytes_total: int = 0

        # Pre-create the destination folder so it exists even if robocopy
        # would otherwise only create it lazily (matches Python-mode behaviour).
        try:
            Path(dst).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            if log_cb:
                log_cb(f"WARNING: could not pre-create destination: {exc}")

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
        except FileNotFoundError:
            msg = "robocopy.exe not found – is this a Windows system?"
            if log_cb:
                log_cb(f"ERROR: {msg}")
            return 9

        for raw_line in self._proc.stdout:  # type: ignore[union-attr]
            if self._cancelled:
                self._proc.terminate()
                break

            line = raw_line.rstrip()
            if not line:
                continue

            prog.log_lines.append(line)

            # Parse percentage of current file (only present without /NP)
            m_pct = _PCT_RE.match(line)
            if m_pct:
                prog.last_pct = int(m_pct.group(1))
                # Don't forward raw percentage lines to the log
                continue

            # Parse completed-file line (with /NP, no leading 100%):
            #   "      New File          4746    D:\path\file.ext"
            m_file = _FILE_RE.match(line)
            if m_file:
                fsize = int(m_file.group(1))
                name  = Path(m_file.group(2).strip()).name
                prog.copied_files += 1
                prog.last_filename = name

                # Update byte-level speed window
                now = time.perf_counter()
                copied_bytes_total += fsize
                speed_window.append((now, fsize))
                cutoff = now - SPEED_WINDOW
                while speed_window and speed_window[0][0] < cutoff:
                    speed_window.popleft()

                # Compute speed and ETA from our own byte tracking
                if speed_window:
                    window_bytes = sum(b for _, b in speed_window)
                    window_dur   = max(now - speed_window[0][0], 0.001)
                    speed_bps    = window_bytes / window_dur
                else:
                    speed_bps = 0.0

                # Emit a clean log line matching Python-mode style
                if log_cb:
                    log_cb(f"[{prog.copied_files}] Copied: {name}")
                if file_done_cb:
                    file_done_cb(name, fsize, True)

                # Emit stats — use -1 as total sentinel while unknown (view shows "N / ?")
                if stats_cb:
                    tf = prog.total_files   # 0 while unknown, real value after summary
                    cf = prog.copied_files if tf == 0 else min(prog.copied_files, tf)
                    eta = 0.0
                    stats_cb(cf, tf, copied_bytes_total, copied_bytes_total, speed_bps, eta)
                continue

            # Don't parse "Files :" lines mid-stream — robocopy emits one per
            # subdirectory during the copy, which would corrupt total_files.
            # We parse the real final summary after proc.wait() instead.
            if _SUMM_RE.match(line):
                continue

            # Forward all other meaningful lines (headers, errors, dir names…)
            if log_cb:
                log_cb(line)

        self._proc.wait()
        exit_code = self._proc.returncode if not self._cancelled else -1
        prog.finished = True
        prog.exit_code = exit_code

        # Parse the LAST "Files :" line from the captured output — this is the
        # real grand-total summary (robocopy also emits per-directory lines
        # mid-run which we deliberately skipped above to avoid corrupting counts).
        for line in reversed(prog.log_lines):
            m = _SUMM_RE.match(line)
            if m:
                prog.total_files   = int(m.group(1))
                prog.copied_files  = int(m.group(2))
                prog.skipped_files = int(m.group(3))
                prog.failed_files  = int(m.group(5))
                break

        # Emit one final accurate stats tick
        if stats_cb and prog.total_files > 0:
            elapsed   = max(time.perf_counter() - start_time, 0.001)
            avg_speed = copied_bytes_total / elapsed
            cf = min(prog.copied_files, prog.total_files)
            stats_cb(cf, prog.total_files, copied_bytes_total, copied_bytes_total, avg_speed, 0.0)

        if finished_cb:
            # robocopy exit codes 0-7 are success/informational; >=8 are errors
            finished_cb(exit_code < 8, exit_code)

        return exit_code
