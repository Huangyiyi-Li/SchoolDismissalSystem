from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DashboardView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        self.kicker_label = QLabel("DISMISSAL CONTROL CENTER")
        self.kicker_label.setObjectName("kickerLabel")
        title_block.addWidget(self.kicker_label)

        self.title_label = QLabel("校园放学守护看板")
        self.title_label.setObjectName("titleLabel")
        title_block.addWidget(self.title_label)

        self.subtitle_label = QLabel("低干扰值守模式，面向长期运行的 Windows 校园终端")
        self.subtitle_label.setObjectName("subtitleLabel")
        title_block.addWidget(self.subtitle_label)

        header_row.addLayout(title_block, 1)

        self.clock_chip = QLabel("--:--:--")
        self.clock_chip.setObjectName("clockChip")
        self.clock_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self.clock_chip)

        layout.addLayout(header_row)

        self.banner_frame = QFrame()
        self.banner_frame.setObjectName("bannerFrame")
        banner_layout = QHBoxLayout(self.banner_frame)
        banner_layout.setContentsMargins(16, 12, 16, 12)

        self.banner_label = QLabel("[正常] 系统状态: 初始化中")
        self.banner_label.setObjectName("bannerLabel")
        self.banner_label.setWordWrap(True)
        banner_layout.addWidget(self.banner_label)
        layout.addWidget(self.banner_frame)

        cards_row = QGridLayout()
        cards_row.setHorizontalSpacing(16)
        cards_row.setVerticalSpacing(16)

        self.runtime_card, self.runtime_label = self._create_stat_card(
            "运行状态",
            "运行状态: --",
            "广播、同步、监听综合状态",
        )
        cards_row.addWidget(self.runtime_card, 0, 0)

        self.devices_card, self.devices_label = self._create_stat_card(
            "在线设备",
            "在线设备: 0 台",
            "60 秒内有心跳的设备",
        )
        cards_row.addWidget(self.devices_card, 0, 1)

        self.window_card, self.window_label = self._create_stat_card(
            "播报时段",
            "默认: 16:30 - 18:30",
            "动态课表优先，静态时间兜底",
        )
        cards_row.addWidget(self.window_card, 0, 2)

        layout.addLayout(cards_row)

        logs_shell = QFrame()
        logs_shell.setObjectName("logsShell")
        logs_layout = QVBoxLayout(logs_shell)
        logs_layout.setContentsMargins(18, 18, 18, 18)
        logs_layout.setSpacing(14)

        logs_header = QHBoxLayout()
        logs_header.setSpacing(8)

        logs_title_block = QVBoxLayout()
        logs_title_block.setSpacing(2)

        logs_title = QLabel("实时日志")
        logs_title.setObjectName("sectionTitle")
        logs_title_block.addWidget(logs_title)

        logs_hint = QLabel("最近刷卡、播报、跳过和异常原因会优先显示在顶部")
        logs_hint.setObjectName("sectionHint")
        logs_title_block.addWidget(logs_hint)

        logs_header.addLayout(logs_title_block, 1)

        self.log_count_chip = QLabel("最近 0 条")
        self.log_count_chip.setObjectName("countChip")
        logs_header.addWidget(self.log_count_chip)

        logs_layout.addLayout(logs_header)

        self.log_table = QTableWidget()
        self.log_table.setObjectName("logTable")
        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels(["时间", "卡号", "班级", "动作", "详细原因"])
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.log_table.setColumnWidth(0, 110)
        self.log_table.setColumnWidth(1, 140)
        self.log_table.setColumnWidth(2, 180)
        self.log_table.setColumnWidth(3, 140)
        logs_layout.addWidget(self.log_table)

        layout.addWidget(logs_shell, 1)

    def _create_stat_card(self, title: str, value: str, hint: str):
        card = QFrame()
        card.setObjectName("statCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        value_label.setWordWrap(True)
        card_layout.addWidget(value_label)

        hint_label = QLabel(hint)
        hint_label.setObjectName("cardHint")
        hint_label.setWordWrap(True)
        card_layout.addWidget(hint_label)

        card_layout.addStretch(1)
        return card, value_label

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #08111f;
                color: #d8e4f4;
                font-family: "Segoe UI", "PingFang SC", sans-serif;
            }
            QLabel#kickerLabel {
                color: #7dd3fc;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#titleLabel {
                color: #f8fbff;
                font-size: 30px;
                font-weight: 700;
            }
            QLabel#subtitleLabel {
                color: #8ea3bd;
                font-size: 13px;
            }
            QLabel#clockChip {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #132238, stop:1 #0e1b2d);
                border: 1px solid #25405f;
                border-radius: 18px;
                color: #edf5ff;
                font-size: 18px;
                font-weight: 700;
                min-width: 128px;
                padding: 10px 18px;
            }
            QFrame#bannerFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #123250, stop:1 #10263e);
                border: 1px solid #2c577f;
                border-radius: 18px;
            }
            QLabel#bannerLabel {
                color: #f8fbff;
                font-size: 16px;
                font-weight: 700;
            }
            QFrame#statCard, QFrame#logsShell {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1829, stop:1 #101f34);
                border: 1px solid #1d3552;
                border-radius: 18px;
            }
            QLabel#cardTitle {
                color: #7dd3fc;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            QLabel#cardValue {
                color: #f8fbff;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#cardHint, QLabel#sectionHint {
                color: #8ea3bd;
                font-size: 12px;
            }
            QLabel#sectionTitle {
                color: #f8fbff;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#countChip {
                background: #13243a;
                border: 1px solid #284869;
                border-radius: 14px;
                color: #d8e4f4;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QTableWidget#logTable {
                background: #091321;
                alternate-background-color: #0d1829;
                border: 1px solid #1b3451;
                border-radius: 12px;
                gridline-color: #13253a;
                color: #d8e4f4;
                selection-background-color: #17314d;
            }
            QHeaderView::section {
                background: #11243a;
                color: #8ecdf1;
                border: none;
                padding: 10px 8px;
                font-size: 12px;
                font-weight: 700;
            }
            """
        )

    def set_clock_text(self, text: str):
        self.clock_chip.setText(text)

    def set_banner(self, text: str, should_pulse: bool):
        if should_pulse:
            frame_style = (
                "QFrame#bannerFrame {"
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                "stop:0 #46171d, stop:1 #35131c);"
                "border: 1px solid #a23b48;"
                "border-radius: 18px; }"
            )
            label_style = "QLabel#bannerLabel { color: #ffe6ea; font-size: 16px; font-weight: 700; }"
        else:
            frame_style = (
                "QFrame#bannerFrame {"
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                "stop:0 #123250, stop:1 #10263e);"
                "border: 1px solid #2c577f;"
                "border-radius: 18px; }"
            )
            label_style = "QLabel#bannerLabel { color: #f8fbff; font-size: 16px; font-weight: 700; }"
        self.banner_frame.setStyleSheet(frame_style)
        self.banner_label.setStyleSheet(label_style)
        self.banner_label.setText(text)

    def set_runtime_text(self, text: str):
        self.runtime_label.setText(text)

    def set_devices_text(self, text: str):
        self.devices_label.setText(text)

    def set_window_text(self, text: str):
        self.window_label.setText(text)

    def add_log_row(self, time_str: str, card_id: str, class_name: str, action: str, reason: str):
        self.log_table.insertRow(0)
        self.log_table.setItem(0, 0, QTableWidgetItem(time_str))
        self.log_table.setItem(0, 1, QTableWidgetItem(card_id))
        self.log_table.setItem(0, 2, QTableWidgetItem(class_name))

        action_item = QTableWidgetItem(action)
        lowered = action.lower()
        if "播报" in action:
            action_item.setForeground(QColor("#70e1a1"))
        elif "跳过" in action or "skip" in lowered:
            action_item.setForeground(QColor("#f8c36a"))
        elif "失败" in action or "error" in lowered:
            action_item.setForeground(QColor("#ff8e96"))
        self.log_table.setItem(0, 3, action_item)
        self.log_table.setItem(0, 4, QTableWidgetItem(reason))

        if self.log_table.rowCount() > 100:
            self.log_table.removeRow(100)

        self.log_count_chip.setText(f"最近 {self.log_table.rowCount()} 条")
