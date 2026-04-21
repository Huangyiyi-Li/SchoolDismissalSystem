from __future__ import annotations


def build_global_stylesheet() -> str:
    return """
    QDialog, QMessageBox, QInputDialog {
        background: #0d1829;
        color: #edf5ff;
        font-family: "Segoe UI", "PingFang SC", sans-serif;
    }
    QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {
        color: #edf5ff;
    }
    QDialog QLabel[muted="true"] {
        color: #9ab0c8;
    }
    QDialog QGroupBox {
        color: #8ecdf1;
        border: 1px solid #294765;
        border-radius: 14px;
        margin-top: 14px;
        padding-top: 12px;
        font-size: 13px;
        font-weight: 700;
    }
    QDialog QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 6px;
    }
    QDialog QLineEdit,
    QDialog QSpinBox,
    QDialog QDoubleSpinBox,
    QDialog QComboBox,
    QDialog QTimeEdit,
    QInputDialog QLineEdit {
        background: #091423;
        border: 1px solid #35506d;
        border-radius: 10px;
        color: #f8fbff;
        min-height: 34px;
        padding: 4px 10px;
        selection-background-color: #21486f;
    }
    QDialog QLineEdit:focus,
    QDialog QSpinBox:focus,
    QDialog QDoubleSpinBox:focus,
    QDialog QComboBox:focus,
    QDialog QTimeEdit:focus,
    QInputDialog QLineEdit:focus {
        border-color: #6ec7ff;
    }
    QDialog QPushButton,
    QMessageBox QPushButton,
    QInputDialog QPushButton {
        background: #14304d;
        border: 1px solid #335a82;
        border-radius: 10px;
        color: #edf5ff;
        font-size: 13px;
        font-weight: 600;
        min-height: 34px;
        min-width: 92px;
        padding: 6px 14px;
    }
    QDialog QPushButton:hover,
    QMessageBox QPushButton:hover,
    QInputDialog QPushButton:hover {
        background: #1b4168;
        border-color: #4c7aaa;
    }
    QDialog QPushButton:pressed,
    QMessageBox QPushButton:pressed,
    QInputDialog QPushButton:pressed {
        background: #10253b;
    }
    QDialog QTableWidget,
    QDialog QTabWidget::pane,
    QDialog QAbstractItemView {
        background: #091423;
        alternate-background-color: #0f1e31;
        border: 1px solid #1f3854;
        border-radius: 12px;
        color: #edf5ff;
        gridline-color: #17304a;
        selection-background-color: #173856;
        selection-color: #ffffff;
    }
    QDialog QHeaderView::section {
        background: #13253a;
        color: #9fdcff;
        border: none;
        border-bottom: 1px solid #27435f;
        padding: 8px;
        font-size: 12px;
        font-weight: 700;
    }
    QDialog QTabBar::tab {
        background: #102139;
        border: 1px solid #27435f;
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        color: #a8bfd8;
        min-width: 84px;
        padding: 8px 14px;
    }
    QDialog QTabBar::tab:selected {
        background: #15314f;
        color: #f8fbff;
    }
    QDialog QCheckBox {
        color: #edf5ff;
        spacing: 8px;
    }
    QDialog QCheckBox::indicator {
        width: 18px;
        height: 18px;
    }
    QDialog QCheckBox::indicator:unchecked {
        background: #091423;
        border: 1px solid #406182;
        border-radius: 4px;
    }
    QDialog QCheckBox::indicator:checked {
        background: #1d4ed8;
        border: 1px solid #60a5fa;
        border-radius: 4px;
    }
    """

