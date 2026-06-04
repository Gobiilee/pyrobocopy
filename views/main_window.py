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
    QCheckBox, QListWidget, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTextEdit, QSpinBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor

from viewmodels.main_vm import MainViewModel
from views.path_card import PathCard, _label
from views.stats_bar import DARK, FILE_COLOR, FILE_ICON, StatsBar



# ── main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, vm: MainViewModel) -> None:
        super().__init__()
        self.vm = vm
        
        self.setWindowTitle("pyRoboCopy v2 (Network Optimized)")
        self.resize(760, 680)
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

        # ---- TOP: QUEUE SELECTION COMPONENT ----
        layout.addWidget(_label("SOURCE QUEUE (FILES & FOLDERS)", bold=True, size=8, color="#888888"))
        
        queue_layout = QHBoxLayout()
        queue_layout.setSpacing(10)
        
        self.src_queue_list = QListWidget()
        queue_layout.addWidget(self.src_queue_list, 1)
        
        # Queue Management Control Sidebar Buttons
        ctrl_sidebar = QVBoxLayout()
        ctrl_sidebar.setSpacing(6)
        ctrl_sidebar.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.add_file_btn = QPushButton("+ File")
        self.add_folder_btn = QPushButton("+ Folder")
        self.remove_item_btn = QPushButton("❌ Remove")
        
        btn_style = """
            QPushButton {
                background: #252525; border: 1px solid #3a3a3a;
                border-radius: 4px; color: #b5b5b5; padding: 6px; font-size: 8.5pt; font-weight: bold; width: 70px;
            }
            QPushButton:hover { background: #2d2d2d; color: #e0e0e0; }
            QPushButton:pressed { background: #1e1e1e; }
            QPushButton:disabled { color: #444; background: #181818; border-color: #252525; }
        """
        for btn in (self.add_file_btn, self.add_folder_btn, self.remove_item_btn):
            btn.setStyleSheet(btn_style)
            ctrl_sidebar.addWidget(btn)
            
        queue_layout.addLayout(ctrl_sidebar)
        layout.addLayout(queue_layout)

        # ---- MIDDLE: DESTINATION TARGET CARD ----
        self.dst_card = PathCard("DESTINATION (LOCAL OR LAN ETHERNET UNC PATH)", "Choose target destination folder or enter UNC path...")
        layout.addWidget(self.dst_card)

        # ---- STATS BAR REALTIME TRACKER ----
        self.stats_bar = StatsBar()
        self.stats_bar.setStyleSheet(
            "background:#252525; border:1px solid #333; border-radius:6px;")
        layout.addWidget(self.stats_bar)

        # ---- FILE PIPELINE FEED ----
        layout.addWidget(_label("FILES TRANSFER PIPELINE", bold=True, size=8, color="#555555"))
        self.file_log = QTextEdit()
        self.file_log.setReadOnly(True)
        self.file_log.setFixedHeight(160)
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

        # Mode configurations
        self.cut_mode_checkbox = QCheckBox("Cut Mode (Safe move via source erasure)")
        bottom.addWidget(self.cut_mode_checkbox)
        bottom.addStretch()

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
        bottom.addWidget(self.action_btn)

        layout.addLayout(bottom)

        # Connect internal action handlers
        self.add_file_btn.clicked.connect(self._pick_files_to_queue)
        self.add_folder_btn.clicked.connect(self._pick_folder_to_queue)
        self.remove_item_btn.clicked.connect(self._remove_selected_queue_item)
        self.dst_card.browse_btn.clicked.connect(self._pick_destination_folder)
        self.action_btn.clicked.connect(self._on_action)

    # ── connect ViewModel ─────────────────────────────────────────────────────

    def _connect_vm(self):
        self.vm.log_updated.connect(self._append_log)
        self.vm.file_batch.connect(self._on_file_batch)
        self.vm.stats_update.connect(self.stats_bar.update_stats)
        self.vm.ui_state_changed.connect(self._set_busy)
        
        # Bind ViewModel selection update mapping
        if hasattr(self.vm, 'selection_updated'):
            self.vm.selection_updated.connect(lambda paths: self._refresh_src_list_widget(paths))

    # ── slots ─────────────────────────────────────────────────────────────────

    def _pick_files_to_queue(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files to Queue")
        if files:
            self.vm.add_paths(files)

    def _pick_folder_to_queue(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Folder to Queue")
        if folder:
            self.vm.add_paths([folder])

    def _remove_selected_queue_item(self):
        current_item = self.src_queue_list.currentItem()
        if current_item:
            self.vm.remove_path(current_item.text())

    def _refresh_src_list_widget(self, paths: list):
        self.src_queue_list.clear()
        if paths:
            str_paths = [str(p) for p in paths]
            self.src_queue_list.addItems(str_paths)

    def _pick_destination_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Target")
        if folder:
            self.dst_card.path_input.setText(folder)

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
        
        # Calls the updated v2 start routine inside your viewmodel
        self.vm.start_copy(
            dst_dir=self.dst_card.text(),
            move_mode=self.cut_mode_checkbox.isChecked()
        )

    def _cancel(self):
        self.action_btn.setEnabled(False)
        self.vm.cancel_copy()

    def _set_busy(self, busy: bool):
        self.action_btn.setEnabled(True)
        
        # Lock staging mutations during processing cycles
        self.src_queue_list.setEnabled(not busy)
        self.add_file_btn.setEnabled(not busy)
        self.add_folder_btn.setEnabled(not busy)
        self.remove_item_btn.setEnabled(not busy)
        
        self.dst_card.set_enabled(not busy)
        self.thread_spin.setEnabled(not busy)
        self.cut_mode_checkbox.setEnabled(not busy)
        
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
