"""
Modern stylesheet for DAG Graph Editor.

Provides a polished, modern dark theme with glassmorphism effects.
"""

# Modern Dark Theme Stylesheet
DARK_THEME = """
/* Main Window */
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

/* Menu Bar */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
    padding: 4px;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #45475a;
}

QMenu {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #45475a;
}

/* Toolbar */
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 6px;
}

QToolBar::separator {
    background-color: #45475a;
    width: 1px;
    margin: 4px 8px;
}

QToolButton {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
    margin: 2px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #45475a;
}

QToolButton:pressed {
    background-color: #585b70;
}

/* Status Bar */
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
    padding: 4px;
}

/* Dock Widgets */
QDockWidget {
    color: #cdd6f4;
    titlebar-close-icon: url(none);
    titlebar-normal-icon: url(none);
}

QDockWidget::title {
    background-color: #1e1e2e;
    color: #cdd6f4;
    padding: 8px 12px;
    border-bottom: 1px solid #313244;
    font-weight: bold;
}

QDockWidget::close-button, QDockWidget::float-button {
    background-color: #313244;
    border-radius: 4px;
    padding: 4px;
}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {
    background-color: #45475a;
}

/* Scroll Bars */
QScrollBar:vertical {
    background-color: #181825;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #181825;
    height: 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 6px;
    min-width: 30px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #585b70;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 2px solid #89b4fa;
}

QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background-color: #1e1e2e;
    color: #6c7086;
}

/* Combo Box */
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    selection-background-color: #45475a;
}

/* Spin Box */
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #45475a;
    border-radius: 3px;
    width: 16px;
    margin: 2px;
}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #585b70;
}

/* Buttons */
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #b4befe;
}

QPushButton:pressed {
    background-color: #74c7ec;
}

QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}

/* Check Box */
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #45475a;
    background-color: #313244;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

QCheckBox::indicator:hover {
    border-color: #89b4fa;
}

/* Labels */
QLabel {
    color: #cdd6f4;
}

/* Form Layout */
QFormLayout {
    spacing: 12px;
}

/* Message Box */
QMessageBox {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

QMessageBox QPushButton {
    min-width: 80px;
    padding: 8px 16px;
}

/* Dialog */
QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

/* Tab Widget */
QTabWidget::pane {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 8px;
}

QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #45475a;
}

QTabBar::tab:hover {
    background-color: #45475a;
}

/* Tooltip */
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
}
"""

# Light Theme (optional - for switch)
LIGHT_THEME = """
QMainWindow {
    background-color: #eff1f5;
    color: #4c4f69;
}

QMenuBar, QToolBar, QStatusBar {
    background-color: #e6e9ef;
    color: #4c4f69;
    border-color: #ccd0da;
}

QToolButton {
    background-color: #dce0e8;
    color: #4c4f69;
}

QToolButton:hover {
    background-color: #ccd0da;
}

QDockWidget::title {
    background-color: #e6e9ef;
}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: #ffffff;
    color: #4c4f69;
    border-color: #ccd0da;
}

QPushButton {
    background-color: #1e66f5;
    color: #ffffff;
}

QPushButton:hover {
    background-color: #5c7bfa;
}
"""

# Node colors for better visual appearance
NODE_COLORS = {
    "default": "#89b4fa",       # Blue
    "selected": "#f5c2e7",      # Pink
    "critical": "#f38ba8",      # Red
    "success": "#a6e3a1",       # Green
    "warning": "#fab387",       # Orange
    "info": "#74c7ec",          # Cyan
}

# Gradient presets for nodes
NODE_GRADIENTS = {
    "blue": ("#89b4fa", "#74c7ec"),
    "green": ("#a6e3a1", "#94e2d5"),
    "purple": ("#cba6f7", "#f5c2e7"),
    "orange": ("#fab387", "#f9e2af"),
    "red": ("#f38ba8", "#eba0ac"),
}
