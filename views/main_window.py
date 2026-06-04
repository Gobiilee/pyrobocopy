"""
Main window – AnyDesk/RustDesk-style dark UI.

Performance design
──────────────────
- File list uses a plain QTextEdit (monospace, read-only) instead of
  per-file QWidget rows.  Appending text is O(1) vs O(n) layout work.
- Stats bar updates on the ViewModel's 100 ms flush timer, not per file.
- No QTimer.singleShot spam; auto-scroll happens only during flush.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QProgressBar,
    QTextEdit, QSpinBox, QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor

from viewmodels.main_vm import MainViewModel


# ── helpers ───────────────────────────────────────────────────────────────────

def _label(text: str, *, bold=False, size=9, color="#cccccc") -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setPointSize(size)
    f.setBold(bold)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color};")
    return lbl


# ── path card ─────────────────────────────────────────────────────────────────

class PathCard(QWidget):
    """Labeled folder picker card."""

    def __init__(self, title: str, placeholder: str, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(_label(title, bold=True, size=8, color="#888888"))

        row = QHBoxLayout()
        row.setSpacing(6)

        row.addWidget(QLabel("📁"))

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)
        self.path_input.setReadOnly(True)
        self.path_input.setStyleSheet("""
            QLineEdit {
                background: #1e1e1e;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 4px 8px;
                font-size: 9pt;
            }
        """)
        row.addWidget(self.path_input)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setFixedWidth(78)
        self.browse_btn.setStyleSheet("""
            QPushButton {
                background: #2d2d2d; border: 1px solid #4a4a4a;
                border-radius: 4px; color: #cccccc;
                padding: 4px 10px; font-size: 9pt;
            }
            QPushButton:hover   { background: #383838; }
            QPushButton:pressed { background: #252525; }
            QPushButton:disabled{ color: #555; }
        """)
        row.addWidget(self.browse_btn)
        layout.addLayout(row)

        self.setStyleSheet("""
            PathCard {
                background: #252525;
                border: 1px solid #333333;
                border-radius: 6px;
            }
        """)

    def text(self) -> str:
        return self.path_input.text()

    def set_enabled(self, enabled: bool):
        self.browse_btn.setEnabled(enabled)


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
        v.setContentsMargins(0, 0, 0, 0)
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


# ── main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, vm: MainViewModel) -> None:
        super().__init__()
        self.vm = vm
        self.setWindowTitle("Py-RoboCopy")
        self.resize(740, 640)
        self.setStyleSheet(DARK)

        self._build_ui()
        self._connect_vm()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Source / destination cards
        path_row = QHBoxLayout()
        path_row.setSpacing(10)

        self.src_card = PathCard("SOURCE", "Choose source folder…")
        self.src_card.browse_btn.clicked.connect(
            lambda: self._pick_folder(self.src_card.path_input))

        arrow = _label("→", bold=True, size=16, color="#555555")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFixedWidth(28)

        self.dst_card = PathCard("DESTINATION", "Choose destination folder…")
        self.dst_card.browse_btn.clicked.connect(
            lambda: self._pick_folder(self.dst_card.path_input))

        path_row.addWidget(self.src_card, 1)
        path_row.addWidget(arrow)
        path_row.addWidget(self.dst_card, 1)
        layout.addLayout(path_row)

        # Stats bar
        self.stats_bar = StatsBar()
        self.stats_bar.setStyleSheet(
            "background:#252525; border:1px solid #333; border-radius:6px;")
        layout.addWidget(self.stats_bar)

        # File list — plain QTextEdit, much faster than per-row widgets
        layout.addWidget(_label("FILES", bold=True, size=8, color="#555555"))
        self.file_log = QTextEdit()
        self.file_log.setReadOnly(True)
        self.file_log.setFixedHeight(210)
        self.file_log.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #dddddd;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 8.5pt;
                padding: 4px;
            }
        """)
        layout.addWidget(self.file_log)

        # Log area
        layout.addWidget(_label("LOG", bold=True, size=8, color="#555555"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(90)
        self.log_area.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #aaaaaa;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 8pt;
                padding: 4px;
            }
        """)
        layout.addWidget(self.log_area)

        # Bottom row: threads + start/cancel
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        bottom.addWidget(_label("Threads:", color="#888888", size=9))

        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 64)
        self.thread_spin.setValue(16)
        self.thread_spin.setMinimumWidth(68)   # wide enough to show "16" clearly
        self.thread_spin.setFixedHeight(30)
        self.thread_spin.setStyleSheet("""
            QSpinBox {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 3px 8px;
                font-size: 10pt;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 18px;
                background: #333;
                border: none;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #444;
            }
        """)
        bottom.addWidget(self.thread_spin)
        bottom.addStretch()

        self.action_btn = QPushButton("▶  Start Transfer")
        self.action_btn.setFixedHeight(38)
        self.action_btn.setMinimumWidth(165)
        self._style_start()
        self.action_btn.clicked.connect(self._on_action)
        bottom.addWidget(self.action_btn)

        layout.addLayout(bottom)

    # ── connect ViewModel ─────────────────────────────────────────────────────

    def _connect_vm(self):
        self.vm.log_updated.connect(self._append_log)
        self.vm.file_batch.connect(self._on_file_batch)
        self.vm.stats_update.connect(self.stats_bar.update_stats)
        self.vm.ui_busy.connect(self._set_busy)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _pick_folder(self, line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            line_edit.setText(folder)

    def _append_log(self, msg: str):
        self.log_area.append(msg)
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_file_batch(self, rows: list):
        """
        Append all pending file rows in one shot.
        Rows are (name, size_str, status_str) tuples.
        Building one big HTML string and inserting once is far faster
        than appending line-by-line.
        """
        if not rows:
            return

        parts = []
        for name, size, status in rows:
            icon  = FILE_ICON.get(status, "·")
            color = FILE_COLOR.get(status, "#888888")
            # Escape any HTML-special chars in filenames
            safe_name = name.replace("&", "&amp;").replace("<", "&lt;")
            parts.append(
                f'<span style="color:{color}">{icon}</span>'
                f'&nbsp;{safe_name}'
                f'<span style="color:#555555"> &nbsp;{size}</span>'
            )

        # Append all rows at once — one layout pass
        cursor = self.file_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.file_log.setTextCursor(cursor)
        self.file_log.insertHtml("<br>".join(parts) + "<br>")

        # Scroll to bottom once
        sb = self.file_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_action(self):
        if self.action_btn.text().startswith("▶"):
            self._start()
        else:
            self._cancel()

    def _start(self):
        self.log_area.clear()
        self.file_log.clear()
        self.stats_bar.reset()
        self.vm.start_copy(
            src=self.src_card.text(),
            dst=self.dst_card.text(),
            workers=self.thread_spin.value(),
        )

    def _cancel(self):
        self.action_btn.setEnabled(False)
        self.vm.cancel_copy()

    def _set_busy(self, busy: bool):
        self.action_btn.setEnabled(True)
        self.src_card.set_enabled(not busy)
        self.dst_card.set_enabled(not busy)
        self.thread_spin.setEnabled(not busy)
        if busy:
            self._style_cancel()
        else:
            self._style_start()

    # ── button styles ─────────────────────────────────────────────────────────

    def _style_start(self):
        self.action_btn.setText("▶  Start Transfer")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background: #1a73e8; border: none; border-radius: 6px;
                color: white; font-size: 10pt; font-weight: bold; padding: 0 18px;
            }
            QPushButton:hover    { background: #1565c0; }
            QPushButton:pressed  { background: #0d47a1; }
            QPushButton:disabled { background: #333; color: #555; }
        """)

    def _style_cancel(self):
        self.action_btn.setText("■  Cancel")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background: #c62828; border: none; border-radius: 6px;
                color: white; font-size: 10pt; font-weight: bold; padding: 0 18px;
            }
            QPushButton:hover    { background: #b71c1c; }
            QPushButton:pressed  { background: #7f0000; }
            QPushButton:disabled { background: #333; color: #555; }
        """)
