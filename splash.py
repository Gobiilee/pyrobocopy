"""
splash.py  –  Frameless splash screen shown while the main window loads.

Shows:
  - App icon (centered)
  - App name
  - Animated progress bar that fills over ~2 seconds
  - "Loading…" status text

The main window calls splash.finish(main_window) to dismiss it.
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget, QProgressBar
from PyQt6.QtCore    import Qt, QTimer, QSize
from PyQt6.QtGui     import (QPainter, QColor, QLinearGradient, QFont,
                              QPixmap, QPen, QBrush, QIcon)


# ── locate assets relative to this file (works both dev and PyInstaller) ──────

def _asset(name: str) -> str:
    """Return path to an asset, works in dev and inside a frozen .exe."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return str(base / "assets" / name)


# ── splash widget ─────────────────────────────────────────────────────────────

class SplashScreen(QWidget):
    """
    Custom frameless splash with icon, title, progress bar, status text.
    Call .start(callback) to begin the fake-load animation.
    Call .finish(main_window) to close after the app is ready.
    """

    W, H       = 480, 320
    BAR_H      = 8
    STEP_MS    = 30       # timer interval
    STEP_PCT   = 2        # % to advance per tick  → ~1.5 s to fill

    def __init__(self):
        super().__init__()

        # Frameless, always on top, no taskbar entry
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.W) // 2,
            (screen.height() - self.H) // 2,
        )

        # Load icon pixmap
        self._icon_px = QPixmap(_asset("splash.png")).scaled(
            120, 120,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self._progress = 0          # 0–100
        self._status   = "Loading…"
        self._timer    = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._done_cb  = None       # called when bar reaches 100

    # ── public API ────────────────────────────────────────────────────────────

    def start(self, done_callback=None):
        """Begin the loading animation. done_callback() called when bar hits 100."""
        self._done_cb = done_callback
        self._timer.start(self.STEP_MS)

    def set_status(self, text: str):
        self._status = text
        self.update()

    def finish(self, main_window=None):
        """Dismiss the splash and show the main window."""
        self._timer.stop()
        if main_window:
            main_window.show()
        self.close()

    # ── animation ─────────────────────────────────────────────────────────────

    def _tick(self):
        self._progress = min(self._progress + self.STEP_PCT, 100)
        self.update()
        if self._progress >= 100:
            self._timer.stop()
            if self._done_cb:
                self._done_cb()

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.W, self.H

        # ── rounded dark background ───────────────────────────────────────────
        p.setBrush(QColor("#1a1a1a"))
        p.setPen(QPen(QColor("#2a2a2a"), 1))
        p.drawRoundedRect(1, 1, W - 2, H - 2, 14, 14)

        # ── subtle top glow strip ─────────────────────────────────────────────
        glow = QLinearGradient(0, 0, W, 0)
        glow.setColorAt(0.0, QColor(0, 0, 0, 0))
        glow.setColorAt(0.5, QColor(26, 115, 232, 60))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(1, 1, W - 2, 4, 2, 2)

        # ── icon ──────────────────────────────────────────────────────────────
        ix = (W - self._icon_px.width())  // 2
        iy = 36
        p.drawPixmap(ix, iy, self._icon_px)

        # ── app name ──────────────────────────────────────────────────────────
        f = QFont("Segoe UI", 18, QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor("#e0e0e0"))
        p.drawText(0, iy + self._icon_px.height() + 16, W, 32,
                   Qt.AlignmentFlag.AlignHCenter, "pyRoboCopy")

        # ── tagline ───────────────────────────────────────────────────────────
        f2 = QFont("Segoe UI", 9)
        p.setFont(f2)
        p.setPen(QColor("#666666"))
        p.drawText(0, iy + self._icon_px.height() + 50, W, 20,
                   Qt.AlignmentFlag.AlignHCenter, "Fast parallel file transfer")

        # ── progress bar track ────────────────────────────────────────────────
        bar_y  = H - 52
        bar_x  = 40
        bar_w  = W - 80

        p.setBrush(QColor("#2a2a2a"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar_x, bar_y, bar_w, self.BAR_H, 4, 4)

        # ── progress bar fill (gradient) ──────────────────────────────────────
        fill_w = int(bar_w * self._progress / 100)
        if fill_w > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            grad.setColorAt(0.0, QColor("#1a73e8"))
            grad.setColorAt(1.0, QColor("#34a853"))
            p.setBrush(grad)
            p.drawRoundedRect(bar_x, bar_y, fill_w, self.BAR_H, 4, 4)

        # ── status text ───────────────────────────────────────────────────────
        f3 = QFont("Segoe UI", 8)
        p.setFont(f3)
        p.setPen(QColor("#555555"))
        p.drawText(0, bar_y + self.BAR_H + 8, W, 18,
                   Qt.AlignmentFlag.AlignHCenter, self._status)

        # ── version / copyright ───────────────────────────────────────────────
        p.setPen(QColor("#3a3a3a"))
        p.drawText(0, H - 18, W, 14,
                   Qt.AlignmentFlag.AlignHCenter, "v0.3.1")

        p.end()
