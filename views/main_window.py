from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QLabel, QTextEdit, 
                             QSpinBox, QLineEdit)
from viewmodels import MainViewModel

class MainWindow(QMainWindow):
    def __init__(self, view_model: MainViewModel) -> None:
        super().__init__()
        self.vm = view_model
        
        self.setWindowTitle("MVVM Py-RoboCopy")
        self.resize(650, 500)
        
        self._setup_ui()
        self._bind_view_model()

    def _setup_ui(self) -> None:
        """Creates and arranges the UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Source Layout
        src_layout = QHBoxLayout()
        self.src_input = QLineEdit()
        self.src_btn = QPushButton("Browse Src")
        self.src_btn.clicked.connect(lambda: self._browse_folder(self.src_input))
        src_layout.addWidget(QLabel("Source:"))
        src_layout.addWidget(self.src_input)
        src_layout.addWidget(self.src_btn)
        layout.addLayout(src_layout)

        # Destination Layout
        dst_layout = QHBoxLayout()
        self.dst_input = QLineEdit()
        self.dst_btn = QPushButton("Browse Dst")
        self.dst_btn.clicked.connect(lambda: self._browse_folder(self.dst_input))
        dst_layout.addWidget(QLabel("Destination:"))
        dst_layout.addWidget(self.dst_input)
        dst_layout.addWidget(self.dst_btn)
        layout.addLayout(dst_layout)

        # Workers Layout
        worker_layout = QHBoxLayout()
        self.worker_spinbox = QSpinBox()
        self.worker_spinbox.setRange(1, 64)
        self.worker_spinbox.setValue(16)
        worker_layout.addWidget(QLabel("Threads:"))
        worker_layout.addWidget(self.worker_spinbox)
        worker_layout.addStretch()
        layout.addLayout(worker_layout)

        # Log Area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(QLabel("Logs:"))
        layout.addWidget(self.log_area)

        # Control Buttons
        btn_layout = QHBoxLayout()
        self.action_btn = QPushButton("Start Copy")
        self.action_btn.setMinimumHeight(35)
        
        btn_layout.addWidget(self.action_btn)
        layout.addLayout(btn_layout)

        # Connect UI interactions to ViewModel methods
        self.action_btn.clicked.connect(self._on_action_clicked)

    def _bind_view_model(self) -> None:
        """Subscribes to the signals emitted by the ViewModel."""
        self.vm.log_updated.connect(self.log_area.append)
        self.vm.ui_state_changed.connect(self._update_ui_states)

    def _browse_folder(self, line_edit: QLineEdit) -> None:
        """Helper to open a dialog and set the text box."""
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            line_edit.setText(folder)

    def _on_start_clicked(self) -> None:
        """Triggers the ViewModel to begin the operation."""
        self.log_area.clear()
        self.vm.start_copy(
            src=self.src_input.text(),
            dst=self.dst_input.text(),
            workers=self.worker_spinbox.value()
        )
        
    def _on_action_clicked(self) -> None:
        """Determines whether to Start or Cancel based on the current button text."""
        if self.action_btn.text() == "Start Copy":
            self._on_start_clicked()
        else:
            # Temporarily disable to prevent double clicks while waiting for threads to abort
            self.action_btn.setEnabled(False)
            self.log_area.append("<br><font color='orange'><b>Cancellation requested. Stopping safely...</b></font>")
            self.vm.cancel_copy()

    def _update_ui_states(self, is_busy: bool) -> None:
        """
        Toggles the single button state and input fields based on ViewModel signals.
        is_busy = True  -> App is copying, button should be 'Cancel'
        is_busy = False -> App is idle, button should be 'Start Copy'
        """
        # Re-enable the button safety lock
        self.action_btn.setEnabled(True)
        
        if is_busy:
            self.action_btn.setText("Cancel")
            # Optional: Add a visual cue like a red background for cancel
            self.action_btn.setStyleSheet("background-color: #f44336; color: white;")
        else:
            self.action_btn.setText("Start Copy")
            self.action_btn.setStyleSheet("") # Reset to default OS style
            
        # Keep your field locks so users don't change paths mid-copy
        self.src_input.setEnabled(not is_busy)
        self.src_btn.setEnabled(not is_busy)
        self.dst_input.setEnabled(not is_busy)
        self.dst_btn.setEnabled(not is_busy)
        self.worker_spinbox.setEnabled(not is_busy)