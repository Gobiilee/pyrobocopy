"""
build.py  –  Build RoboCopy into a standalone .exe

Usage
-----
    python build.py

Output
------
    dist/RoboCopy.exe   (Windows, single file, no console window)

Requirements
------------
    pip install pyinstaller
"""

import subprocess
import sys
from pathlib import Path

APP_NAME  = "RoboCopy"
ENTRY     = "main.py"
ICON      = "assets/icon.ico"   # used for the .exe file icon

# Optional Qt modules we don't use — excluding them silences the
# "Library not found" warnings and shrinks the output binary.
EXCLUDE_MODULES = [
    "PyQt6.Qt3DAnimation", "PyQt6.Qt3DCore", "PyQt6.Qt3DExtras",
    "PyQt6.Qt3DInput",     "PyQt6.Qt3DLogic", "PyQt6.Qt3DRender",
    "PyQt6.QtQml",         "PyQt6.QtQuick",   "PyQt6.QtQuick3D",
    "PyQt6.QtQuickControls2", "PyQt6.QtQuickWidgets",
    "PyQt6.QtWebEngineCore",  "PyQt6.QtWebEngineQuick",
    "PyQt6.QtWebEngineWidgets","PyQt6.QtWebView",
    "PyQt6.QtSql",
    "PyQt6.QtMultimedia",  "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtBluetooth",   "PyQt6.QtNfc",     "PyQt6.QtPositioning",
    "PyQt6.QtRemoteObjects","PyQt6.QtScxml",   "PyQt6.QtSensors",
    "PyQt6.QtSerialPort",  "PyQt6.QtStateMachine", "PyQt6.QtTextToSpeech",
    "tkinter", "unittest", "xmlrpc", "pydoc", "doctest",
]


def main():
    here = Path(__file__).parent

    icon_path = here / ICON
    if not icon_path.exists():
        print(f"Warning: icon not found at {icon_path}")

    cmd = [
        sys.executable, "-m", "PyInstaller",

        "--onefile",           # single .exe
        "--windowed",          # no console window

        f"--name={APP_NAME}",
        f"--distpath={here / 'dist'}",
        f"--workpath={here / 'build'}",
        f"--specpath={here / 'build'}",
        f"--paths={here}",

        # Bundle the assets folder (icon + splash image) into the exe
        f"--add-data={here / 'assets'};assets",

        # .exe file icon
        f"--icon={icon_path}",

        # Hidden imports PyInstaller sometimes misses with PyQt6
        "--hidden-import=PyQt6.sip",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--collect-all=PyQt6",
    ]

    for mod in EXCLUDE_MODULES:
        cmd += ["--exclude-module", mod]

    cmd.append(str(here / ENTRY))

    print("Running PyInstaller…")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        exe = here / "dist" / f"{APP_NAME}.exe"
        print(f"\n✓ Build succeeded: {exe}")
    else:
        print("\n✗ Build failed. Check the output above.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
