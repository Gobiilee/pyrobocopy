"""
main.py  –  Application entry point.

Boot sequence
─────────────
1. Show SplashScreen immediately (before any heavy imports)
2. Splash animates its progress bar (~1.5 s)
3. When bar hits 100 %, build the ViewModel + MainWindow
4. Splash fades out, main window appears
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui     import QIcon
from splash          import SplashScreen, _asset


def _launch_main(splash: SplashScreen):
    """Called by the splash timer when the loading bar finishes."""
    splash.set_status("Starting application…")

    # Heavy imports happen here — after the splash is already visible
    from viewmodels.main_vm  import MainViewModel
    from views.main_window   import MainWindow

    vm     = MainViewModel()
    window = MainWindow(vm)

    # Set window icon (title bar + taskbar)
    window.setWindowIcon(QIcon(_asset("icon.ico")))

    splash.finish(window)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Py-RoboCopy")

    # Set app-wide icon (affects taskbar group on Windows)
    app.setWindowIcon(QIcon(_asset("icon.ico")))

    splash = SplashScreen()
    splash.show()
    app.processEvents()   # paint the splash before anything else runs

    splash.start(done_callback=lambda: _launch_main(splash))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
