
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit,
)

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

