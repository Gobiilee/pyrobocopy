# pyRoboCopy (MVVM Desktop Application)

A high-performance, multi-threaded folder synchronization and copying tool built with Python 3.10 and PyQt6. The application architecture strictly follows the **MVVM (Model-View-ViewModel)** design pattern to ensure clean separation of concerns, high maintainability, and reliable asynchronous execution.

## Features

- **Multi-threaded Core Engine:** Leverages a `ThreadPoolExecutor` to perform concurrent, non-blocking file I/O operations.
- **MVVM Architecture:** Separates business/copy logic (`Model`) from user interface layouts (`View`) using a stateful interface layer (`ViewModel`).
- **Responsive GUI:** Offloads long-running copy processes onto a dedicated background `QThread` to ensure the desktop window never freezes.
- **Graceful Cancellation:** Safely halts future file queues on-demand without killing ongoing active transfers or corrupting data.
- **Robust Error Handling:** Recovers automatically from locked or unreadable system files, providing a detailed breakdown summary of successful versus failed transfers.

---

## Project Structure

```text
py_robocopy/
│
├── main.py                 # Application entry point and dependency injection
├── requirements.txt        # Frozen third-party project dependencies
│
├── models/
│   ├── __init__.py         # Exposes the clean public API of the model layer
│   └── copier.py           # Core business logic, thread management, and file I/O
│
├── viewmodels/
│   ├── __init__.py         # Package initialization
│   └── main_vm.py          # State broker; translates background tasks to GUI updates
│
├── views/
│   ├── __init__.py         # Package initialization
│   └── main_window.py      # Declarative PyQt6 desktop window layout
│
└── tests/
    ├── __init__.py         # Enforces root module test discovery paths
    └── test_copier.py      # Automated unit tests covering edge-case scenarios

```

---

## Installation & Setup

### Prerequisites

* Python 3.10 or higher
* Windows OS (Optimized; compatible with cross-platform targets)

### 1. Environment Configuration

Clone or navigate to the project directory and create an isolated python virtual environment:

```powershell
# Create virtual environment
python -m venv venv_robocopy

# Activate the environment (Windows PowerShell)
.\venv_robocopy\Scripts\Activate.ps1

```

### 2. Dependency Resolution

Install the required third-party libraries using the provided requirements ledger:

```powershell
pip install -r requirements.txt

```

---

## Usage

### Running from Source

To execute the graphical user interface application directly using the Python interpreter:

```powershell
python main.py

```

### Running Automated Test Suites

Unit tests use `pytest` and automatically provision isolated temporary test environments on your machine to validate logic states safely:

```powershell
# Install test runner
pip install pytest

# Run automated tests
pytest

```

---

## Building a Portable Executable (`.exe`)

To compile the source files into a singular, independent executable that can run on any Windows system without a Python environment installed, utilize `pyinstaller`:

```powershell
pyinstaller --noconsole --onefile --name "pyRoboCopy" main.py

```
OR
```powershell
pyinstaller --noconfirm --onefile --windowed `
--name "pyRoboCopy" `
--icon="assets/logo.ico" `
--upx-dir="." `
--exclude-module PyQt6.QtWebEngineCore `
--exclude-module PyQt6.QtWebEngineWidgets `
--exclude-module PyQt6.QtPdf `
--exclude-module PyQt6.QtMultimedia `
--exclude-module PyQt6.Qt3DCore `
--exclude-module PyQt6.QtQuick `
--exclude-module PyQt6.QtNetwork `
--exclude-module PyQt6.QtSql `
--exclude-module PyQt6.QtXml `
main.py

```

After compilation finishes, locate the ready-to-run file in the newly generated directory:
`./dist/pyRoboCopy.exe`

---

## Automated Build & Release

This project uses GitHub Actions to automatically build and publish Windows executable releases.

### Release Workflow

Whenever a version tag is pushed to the repository, GitHub Actions will:

1. Create a clean Windows build environment.
2. Install Python dependencies.
3. Execute `build.py`.
4. Generate `pyRoboCopy.exe`.
5. Create a GitHub Release.
6. Upload the generated executable as a release asset.

### Creating a New Release

After committing your changes:

```powershell
git add .
git commit -m "Add new feature"
git push origin Gobi
```

Create a version tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The workflow will automatically:

* Build the executable.
* Create a GitHub Release named `v1.0.0`.
* Upload `pyRoboCopy.exe`.

### Versioning Convention

Recommended semantic versioning:

```text
v1.0.0
v1.0.1
v1.1.0
v2.0.0
```

Format:

```text
vMAJOR.MINOR.PATCH
```

Examples:

* `v1.0.0` – First public release
* `v1.0.1` – Bug fixes
* `v1.1.0` – New features
* `v2.0.0` – Breaking changes

### Viewing Releases

Published releases are available under:

https://github.com/<repository-owner>/pyrobocopy/releases

---

## Core Architecture Design & Logic Handlers

### File Locks & Open Windows Access

Windows platforms impose mandatory data locking mechanisms when external processes claim exclusive access to a file.

* If a target file is open exclusively elsewhere, the `Model` captures a `PermissionError`, safely documents the issue within a structured data wrapper (`CopyResult`), logs it gracefully, and continues iterating through the remainder of the pool.

### Abrupt Application Disconnection

Forcing the application window shut during active transfers can leave corrupt, incomplete data fragments at the destination. To prevent this, the architecture maintains a strict cooperative cancellation architecture. Activating **Cancel** trips a thread-safe atomic conditional check inside the running loop, clearing future tasks cleanly and awaiting active pool synchronization before exiting.

---

## License
![Build](https://github.com/Gobiilee/pyrobocopy/actions/workflows/build-release.yml/badge.svg)

![Python](https://img.shields.io/badge/Python-3.10-blue)

![License](https://img.shields.io/badge/License-MIT-green)

This project is open-source and available under the [MIT License](https://www.google.com/search?q=LICENSE).

