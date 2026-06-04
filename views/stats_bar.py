
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar
)

from views.path_card import _label
# ── stats bar ─────────────────────────────────────────────────────────────────

class StatsBar(QWidget):
    """Speed · ETA · file count · progress bar — updated in batch."""

    def __init__(self):
        super().__init__()
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 8, 12, 8)
        main.setSpacing(6)

        nums = QHBoxLayout()
        nums.setSpacing(24)

        self.speed_lbl = self._make_stat("Speed",    "— B/s")
        self.eta_lbl   = self._make_stat("ETA",      "—")
        self.files_lbl = self._make_stat("Files",    "0 / 0")
        self.pct_lbl   = self._make_stat("Progress", "0 %")

        for w in (self.speed_lbl, self.eta_lbl, self.files_lbl, self.pct_lbl):
            nums.addWidget(w)
        nums.addStretch()
        main.addLayout(nums)

        self.bar = QProgressBar()
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a2a; border-radius: 4px; border: none;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:0, stop:0 #1a73e8, stop:1 #34a853);
            }
        """)
        main.addWidget(self.bar)

    @staticmethod
    def _make_stat(label: str, value: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(1)
        v.addWidget(_label(label, size=7, color="#666666"))
        val = _label(value, bold=True, size=10, color="#e0e0e0")
        val.setObjectName("val")
        v.addWidget(val)
        return w

    def _val(self, w: QWidget) -> QLabel:
        return w.findChild(QLabel, "val")

    def update_stats(self, cf: int, tf: int, cb: int, tb: int,
                     speed: float, eta: float):
        from viewmodels.main_vm import fmt_size, fmt_time
        pct = int(cb / tb * 100) if tb else 0
        self._val(self.speed_lbl).setText(f"{fmt_size(int(speed))}/s")
        self._val(self.eta_lbl).setText(fmt_time(eta))
        self._val(self.files_lbl).setText(f"{cf} / {tf}")
        self._val(self.pct_lbl).setText(f"{pct} %")
        self.bar.setValue(pct)

    def reset(self):
        self._val(self.speed_lbl).setText("— B/s")
        self._val(self.eta_lbl).setText("—")
        self._val(self.files_lbl).setText("0 / 0")
        self._val(self.pct_lbl).setText("0 %")
        self.bar.setValue(0)


# ── global dark stylesheet ────────────────────────────────────────────────────

DARK = """
QMainWindow, QWidget { background: #1a1a1a; color: #e0e0e0; }
QScrollBar:vertical   { background: #1a1a1a; width: 8px; margin: 0; }
QScrollBar::handle:vertical {
    background: #3a3a3a; border-radius: 4px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# Rich-text color map for file list entries
FILE_COLOR = {
    "done":   "#4caf50",
    "failed": "#f44336",
    "copying":"#f0c040",
}
FILE_ICON = {
    "done": "✓", "failed": "✗", "copying": "⟳",
}
