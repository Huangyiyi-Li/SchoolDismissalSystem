"""Restrained desktop settings theme, scoped to the settings dialog."""

SETTINGS_STYLE = """
QDialog#settingsDialog { background: #f4f6f9; }
QWidget { font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif; font-size: 13px; color: #263449; }
QLabel { background: transparent; }
QLabel[role="hint"] { color: #66758a; font-size: 12px; }
QLabel[role="sectionTitle"] { font-size: 16px; font-weight: 600; color: #1b2c44; }
QLabel#pageTitle { font-size: 21px; font-weight: 600; }
QLabel#appTitle { font-size: 17px; font-weight: 600; }
QWidget#settingsSidebar { background: #edf1f6; border-right: 1px solid #dce3ec; }
QListWidget#settingsNav { border: 0; background: transparent; outline: 0; }
QListWidget#settingsNav::item { padding: 13px 14px; margin: 3px 10px; border-radius: 6px; color: #57677d; }
QListWidget#settingsNav::item:selected { color: #215bd3; background: #dfe9fc; font-weight: 600; }
QListWidget#settingsNav::item:hover:!selected { background: #e5eaf2; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #cfd8e4; border-radius: 5px; padding: 7px 12px; min-height: 18px; }
QPushButton:hover, QToolButton:hover { border-color: #8aabdf; background: #f0f5fd; }
QPushButton:pressed, QToolButton:pressed { background: #e2ebfb; }
QPushButton:focus, QToolButton:focus { border: 1px solid #215bd3; }
QPushButton:disabled, QToolButton:disabled { color: #92a0b1; background: #f2f4f7; border-color: #e0e5ec; }
QPushButton[role="primary"] { background: #2864db; color: white; border-color: #2864db; font-weight: 600; padding: 8px 22px; }
QPushButton[role="primary"]:hover { background: #1d52c0; }
QPushButton[role="link"] { color: #315eaa; background: transparent; border: 0; padding: 4px 6px; }
QPushButton[role="danger"] { color: #aa3443; background: transparent; border-color: #e3c9ce; }
QToolButton[role="disclosure"] { border: 0; background: transparent; text-align: left; padding: 7px 0; font-weight: 600; }
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QComboBox { background: #ffffff; border: 1px solid #ccd6e3; border-radius: 5px; padding: 7px 9px; min-height: 18px; selection-background-color: #dbe7fb; selection-color: #173b80; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #2864db; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #8c99ab; background: #eef1f5; border-color: #e0e5ec; }
QLineEdit[readOnly="true"] { background: #eef1f5; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dfe9fc; color: #263449; }
QCheckBox { spacing: 7px; padding: 4px 0; }
QCheckBox:disabled { color: #7b889b; }
QCheckBox::indicator { width: 15px; height: 15px; }
QCheckBox[role="classChoice"] { border: 1px solid #d6dfea; border-radius: 5px; padding: 8px; background: white; min-height: 20px; }
QCheckBox[role="classChoice"]:checked { border-color: #91b3ee; background: #edf4ff; color: #214f9c; }
QGroupBox { background: #ffffff; border: 1px solid #dde4ed; border-radius: 7px; margin-top: 12px; padding-top: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 4px; color: #253953; }
QGroupBox[role="classGroup"] { background: transparent; border: 0; margin-top: 0; padding: 0; }
QGroupBox[role="classGroup"]::title { left: 0; font-size: 15px; }
QWidget#gradePane { background: #f0f3f8; border-radius: 6px; }
QWidget[active="true"] { background: #e0eafa; border-radius: 4px; }
QWidget#gradePane QToolButton { border: 0; background: transparent; padding: 2px 5px; font-size: 18px; color: #4872ac; }
QWidget#gradePane QLabel { padding-left: 22px; padding-bottom: 7px; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab { background: transparent; color: #69778a; padding: 12px 14px; border-bottom: 2px solid #dce3ed; }
QTabBar::tab:selected { color: #215bd3; border-bottom: 2px solid #2864db; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #eaf0f9; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 2px 0; }
QScrollBar::handle:vertical { background: #c6d0dd; border-radius: 4px; min-height: 36px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QListWidget#screenList { background: transparent; border: 0; outline: 0; }
QListWidget#screenList::item { border: 1px solid #d4dfea; border-radius: 6px; padding: 8px 12px; margin-right: 8px; background: white; }
QListWidget#screenList::item:selected { color: #215bd3; border-color: #81a8ec; background: #edf4ff; }
QFrame#settingsFooter { background: #ffffff; border-top: 1px solid #dce3ed; }
QFrame#previewPanel { background: #ffffff; border: 1px solid #dde4ed; border-radius: 7px; }
QSlider::groove:horizontal { height: 4px; background: #d9e1ec; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4380df; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: white; border: 1px solid #4380df; border-radius: 7px; }
"""
