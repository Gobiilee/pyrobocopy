import sys
import shutil
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLabel, 
                             QProgressBar, QTextEdit, QSpinBox, QLineEdit)
from PyQt6.QtCore import QThread, pyqtSignal

# ---------------------------------------------------------
# 1. STANDALONE WORKER FUNCTIONS
# ---------------------------------------------------------
def copy_file(src, dst):
    """Worker function to copy a single file."""
    try:
        shutil.copy2(src, dst) 
        return True, src
    except Exception as e:
        return False, f"{src} -> Error: {e}"

def get_folder_stats(src_path):
    """Scans the folder to return a list of files and total size in bytes."""
    files = []
    total_size_bytes = 0
    for f in src_path.rglob('*'):
        if f.is_file():
            files.append(f)
            total_size_bytes += f.stat().st_size 
    return files, total_size_bytes


# ---------------------------------------------------------
# 2. THE BACKGROUND THREAD (QThread)
# ---------------------------------------------------------
class CopyWorker(QThread):
    # Signals to communicate with the Main GUI safely
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self, src_dir, dest_dir, workers):
        super().__init__()
        self.src_dir = src_dir
        self.dest_dir = dest_dir
        self.workers = workers

    def run(self):
        """This runs in the background so the UI doesn't freeze."""
        src_path = Path(self.src_dir)
        dst_path = Path(self.dest_dir) / src_path.name 

        if not src_path.exists():
            self.log_signal.emit(f"Error: The source folder '{self.src_dir}' does not exist.")
            self.finished_signal.emit()
            return

        self.log_signal.emit("Scanning directory, calculating size, and mapping structure...")
        
        files, total_size_bytes = get_folder_stats(src_path)
        total_files = len(files)
        total_size_mb = total_size_bytes / (1024 * 1024)
        
        self.log_signal.emit(f"Total files found: {total_files}")
        self.log_signal.emit(f"Total size to copy: {total_size_mb:.2f} MB\n")

        dst_path.mkdir(parents=True, exist_ok=True)
        
        # --- 1. DIRECTORY CREATION ---
        directories = [d for d in src_path.rglob('*') if d.is_dir()]
        total_dirs = len(directories)
        
        if total_dirs > 0:
            for i, d in enumerate(directories, 1):
                rel_path = d.relative_to(src_path)
                (dst_path / rel_path).mkdir(parents=True, exist_ok=True)
            self.log_signal.emit("Folder structure created.")

        # --- 2. FILE COPYING ---
        if total_files == 0:
            self.log_signal.emit("No files to copy.")
            self.finished_signal.emit()
            return

        self.log_signal.emit(f"Starting parallel copy using {self.workers} threads...")
        success_count = 0
        start_time = time.perf_counter()

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = []
            for f in files:
                dest_file = dst_path / f.relative_to(src_path)
                futures.append(executor.submit(copy_file, f, dest_file))

            for future in as_completed(futures):
                success, result = future.result()
                if success:
                    success_count += 1
                    # Calculate percentage and emit to GUI progress bar
                    percent = int((success_count / total_files) * 100)
                    self.progress_signal.emit(percent)
                else:
                    self.log_signal.emit(f"Failed: {result}")

        end_time = time.perf_counter()
        duration_seconds = max(end_time - start_time, 0.001) 
        speed_mb_per_second = total_size_mb / duration_seconds

        # --- SUMMARY ---
        self.log_signal.emit("\n" + "="*30)
        self.log_signal.emit("       COPY SUMMARY")
        self.log_signal.emit("="*30)
        self.log_signal.emit(f"Files Copied : {success_count} / {total_files}")
        self.log_signal.emit(f"Total Data   : {total_size_mb:.2f} MB")
        self.log_signal.emit(f"Time Taken   : {duration_seconds:.2f} seconds")
        self.log_signal.emit(f"Avg Speed    : {speed_mb_per_second:.2f} MB/s")
        self.log_signal.emit("="*30)
        
        self.finished_signal.emit()


# ---------------------------------------------------------
# 3. THE MAIN GUI APPLICATION
# ---------------------------------------------------------
class RoboCopyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoboCopy GUI")
        self.resize(600, 450)

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Source Selection
        src_layout = QHBoxLayout()
        self.src_input = QLineEdit()
        self.src_input.setPlaceholderText("Select Source Folder...")
        src_btn = QPushButton("Browse")
        src_btn.clicked.connect(self.browse_src)
        src_layout.addWidget(QLabel("Source:"))
        src_layout.addWidget(self.src_input)
        src_layout.addWidget(src_btn)
        layout.addLayout(src_layout)

        # Destination Selection
        dst_layout = QHBoxLayout()
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("Select Destination Folder...")
        dst_btn = QPushButton("Browse")
        dst_btn.clicked.connect(self.browse_dst)
        dst_layout.addWidget(QLabel("Destination:"))
        dst_layout.addWidget(self.dst_input)
        dst_layout.addWidget(dst_btn)
        layout.addLayout(dst_layout)

        # Workers / Threads Selection
        worker_layout = QHBoxLayout()
        self.worker_spinbox = QSpinBox()
        self.worker_spinbox.setRange(1, 64)
        self.worker_spinbox.setValue(8)
        worker_layout.addWidget(QLabel("Number of Threads:"))
        worker_layout.addWidget(self.worker_spinbox)
        worker_layout.addStretch()
        layout.addLayout(worker_layout)

        # Log Output Area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(QLabel("Process Log:"))
        layout.addWidget(self.log_area)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Start Button
        self.start_btn = QPushButton("Start Copying")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.start_copy)
        layout.addWidget(self.start_btn)

    def browse_src(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Directory")
        if folder:
            self.src_input.setText(folder)

    def browse_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Directory")
        if folder:
            self.dst_input.setText(folder)

    def append_log(self, text):
        """Adds text to the log window."""
        self.log_area.append(text)

    def update_progress(self, value):
        """Updates the progress bar."""
        self.progress_bar.setValue(value)

    def start_copy(self):
        src = self.src_input.text()
        dst = self.dst_input.text()
        workers = self.worker_spinbox.value()

        if not src or not dst:
            self.append_log("<b>Error: Please select both source and destination folders.</b>")
            return

        # Disable button to prevent multiple clicks
        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_area.clear()
        
        # Set up the background thread
        self.worker_thread = CopyWorker(src, dst, workers)
        self.worker_thread.log_signal.connect(self.append_log)
        self.worker_thread.progress_signal.connect(self.update_progress)
        self.worker_thread.finished_signal.connect(self.copy_finished)
        
        # Start the background task
        self.worker_thread.start()

    def copy_finished(self):
        """Called when the QThread completes."""
        self.start_btn.setEnabled(True)
        self.append_log("<b>Process Complete.</b>")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RoboCopyApp()
    window.show()
    sys.exit(app.exec())