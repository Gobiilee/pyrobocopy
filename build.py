"""
build.py  –  Build Py-RoboCopy into a standalone .exe

Usage
-----
    python build.py

Output
------
    dist/Py-RoboCopy.exe   (Windows, single file, no console window)

Requirements
------------
    pip install pyinstaller
"""

import subprocess
import sys
from pathlib import Path

APP_NAME   = "Py-RoboCopy"
ENTRY      = "main.py"
ICON       = None          # set to "assets/icon.ico" if you have one


def main():
    here = Path(__file__).parent

    cmd = [
        sys.executable, "-m", "PyInstaller",

        # single bundled .exe
        "--onefile",

        # no black console window on Windows
        "--windowed",

        # name of the output binary
        f"--name={APP_NAME}",

        # keep PyInstaller work files out of the source tree
        f"--distpath={here / 'dist'}",
        f"--workpath={here / 'build'}",
        f"--specpath={here / 'build'}",

        # make sure our packages are found
        f"--paths={here}",

        # hidden imports that PyInstaller sometimes misses with PyQt6
        "--hidden-import=PyQt6.sip",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--collect-all=PyQt6",
    ]

    if ICON and Path(ICON).exists():
        cmd.append(f"--icon={ICON}")

    cmd.append(str(here / ENTRY))

    print("Running PyInstaller…")
    print(" ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode == 0:
        exe = here / "dist" / f"{APP_NAME}.exe"
        print(f"\n✓ Build succeeded:  {exe}")
    else:
        print("\n✗ Build failed. Check the output above.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
