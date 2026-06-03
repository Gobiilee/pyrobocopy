import sys
from PyQt6.QtWidgets import QApplication
from viewmodels import MainViewModel
from views.main_window import MainWindow

def main():
    # 1. Initialize the Qt Application
    app = QApplication(sys.argv)
    
    # 2. Instantiate the ViewModel (which instantiates the Model internally)
    view_model = MainViewModel()
    
    # 3. Instantiate the View and pass it the ViewModel
    window = MainWindow(view_model)
    window.show()
    
    # 4. Run the application loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()