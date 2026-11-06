"""Small native widgets used by the settings workspace.

Task order: choose a screen, choose its display range, then adjust layout or device.
The form scrolls inside a tab; context, preview and save actions stay in place.
"""
from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QToolButton, QLineEdit, QCheckBox, QGroupBox,
    QStackedWidget, QScrollArea, QFrame, QSizePolicy)


class WrappingLabel(QLabel):
    """Keep dynamic form hints tall enough after changing device or viewport."""
    def _fit_height(self):
        if self.wordWrap() and self.width() > 0:
            height = self.heightForWidth(self.width())
            if height >= 0 and self.minimumHeight() != height:
                self.setMinimumHeight(height)

    def setText(self, text):
        super().setText(text)
        self._fit_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()


def hint(text):
    label = WrappingLabel(text)
    label.setWordWrap(True)
    label.setProperty('role', 'hint')
    return label


def section(title, description=''):
    group = QGroupBox(title)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(18, 26, 18, 16)
    layout.setSpacing(14)
    if description:
        layout.addWidget(hint(description))
    return group, layout


def scroll_page(content):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


class Disclosure(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setProperty('role', 'disclosure')
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content.hide()
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, checked):
        self.content.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def isExpanded(self):
        return self.toggle.isChecked()


class ClassGrid(QGroupBox):
    """Keep the class choices compact as the editor/preview divider moves."""
    def __init__(self, grade):
        super().__init__(grade)
        self.checks = []
        self.columns = 2

    def reflow(self):
        grid = self.layout()
        for check in self.checks:
            grid.removeWidget(check)
        self.columns = max(2, min(4, (self.width() + 8) // 100))
        all_check = grid.itemAtPosition(0, 0).widget()
        grid.removeWidget(all_check)
        grid.addWidget(all_check, 0, 0, 1, self.columns)
        visible = [check for check in self.checks if not check.isHidden()]
        for index, check in enumerate(visible):
            grid.addWidget(check, index // self.columns + 1, index % self.columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout() and max(2, min(4, (self.width() + 8) // 100)) != self.columns:
            self.reflow()


class ClassSelector(QWidget):
    """One grade at a time, with search and explicitly scoped bulk selection."""
    def __init__(self, dialog, catalog, saved):
        super().__init__()
        self.dialog = dialog
        self.current_grade = None
        self._loading = False
        self.grade_buttons = {}
        self.grade_counts = {}
        self.names = {}
        by_grade = {grade: {} for grade in dialog.led_grade_checks}
        for item in catalog:
            grade = str(item.get('grade_name') or '').strip()
            cid = str(item.get('class_id') or '').strip()
            if grade and cid:
                by_grade.setdefault(grade, {})[cid] = str(item.get('class_show_name') or item.get('class_name') or cid)
        for grade, ids in saved.items():
            for cid in ids:
                by_grade.setdefault(grade, {}).setdefault(cid, f'班级 {cid}（已失效）')
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        title = QLabel('选择这块屏幕显示的班级')
        title.setProperty('role', 'sectionTitle')
        root.addWidget(title)
        root.addWidget(hint('先选择年级，再勾选班级。仅影响当前屏幕，语音播报和平台通知照常。'))
        root.addWidget(dialog.led_all_grades_check)
        columns = QHBoxLayout()
        columns.setSpacing(16)
        root.addLayout(columns)
        grade_pane = QWidget()
        grade_pane.setObjectName('gradePane')
        grade_pane.setFixedWidth(142)
        grades = QVBoxLayout(grade_pane)
        grades.setContentsMargins(8, 8, 8, 8)
        grades.setSpacing(4)
        columns.addWidget(grade_pane, alignment=Qt.AlignmentFlag.AlignTop)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        dialog.led_class_groups = {}
        dialog.led_all_classes_checks = {}
        dialog.led_class_checks = {}
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索当前年级的班级')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('搜索当前年级的班级')
        # Search and batch tools sit above the grade's current page, not per class.
        details = QVBoxLayout()
        details.addWidget(self.search)
        tools = QHBoxLayout()
        self.select_all_button = QPushButton('全选班级')
        self.clear_button = QPushButton('清空班级')
        for button in (self.select_all_button, self.clear_button):
            button.setProperty('role', 'link')
            tools.addWidget(button)
        tools.addStretch()
        details.addLayout(tools)
        details.addWidget(self.stack)
        columns.addLayout(details, 1)
        self.empty_search = hint('没有匹配的班级，请更换关键词。')
        details.addWidget(self.empty_search)
        self.empty_search.hide()
        self.disabled_hint = hint('该年级未在此屏展示，勾选左侧年级后生效。')
        details.addWidget(self.disabled_hint)
        self.disabled_hint.hide()
        self.selection_hint = hint('至少选择一个班级，或在左侧取消勾选该年级。')
        self.selection_hint.setStyleSheet('color:#aa3443;')
        details.addWidget(self.selection_hint)
        self.selection_hint.hide()
        for grade, classes in by_grade.items():
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            check = dialog.led_grade_checks.get(grade)
            if check:
                row_layout.addWidget(check, 1)
                check.toggled.connect(lambda checked, g=grade: self._grade_changed(g, checked))
            button = QToolButton()
            button.setText('›')
            button.setAccessibleName(f'选择{grade}的班级')
            button.clicked.connect(lambda _checked=False, g=grade: self.select_grade(g))
            row_layout.addWidget(button)
            grades.addWidget(row)
            count = hint('')
            grades.addWidget(count)
            self.grade_buttons[grade] = row
            self.grade_counts[grade] = count
            group = ClassGrid(grade)
            group.setProperty('role', 'classGroup')
            grid = QGridLayout(group)
            grid.setContentsMargins(0, 24, 0, 0)
            grid.setSpacing(6)
            all_check = QCheckBox('包含全部班级（含以后新增）')
            all_check.setChecked(True)
            grid.addWidget(all_check, 0, 0, 1, 2)
            dialog.led_class_groups[grade] = group
            dialog.led_all_classes_checks[grade] = all_check
            dialog.led_class_checks[grade] = {}
            for index, (cid, name) in enumerate(classes.items()):
                check = QCheckBox(name)
                check.setProperty('role', 'classChoice')
                check.setToolTip(name)
                check.setChecked(True)
                check.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                dialog.led_class_checks[grade][cid] = check
                self.names[(grade, cid)] = name
                group.checks.append(check)
                grid.addWidget(check, index // 2 + 1, index % 2)
                check.toggled.connect(lambda checked, g=grade: self._class_changed(g, checked))
            if not classes:
                grid.addWidget(hint('暂无班级数据，请同步学校数据后重新打开设置。'), 1, 0, 1, 2)
            grid.setRowStretch(grid.rowCount(), 1)
            all_check.toggled.connect(lambda checked, g=grade: self._all_changed(g, checked))
            self.stack.addWidget(group)
        grades.addStretch()
        if not by_grade:
            root.addWidget(hint('暂无年级数据，请先同步学校数据。'))
            self.search.hide()
            self.select_all_button.hide()
            self.clear_button.hide()
            grade_pane.hide()
        self.search.textChanged.connect(self._filter)
        self.select_all_button.clicked.connect(lambda: self._bulk(True))
        self.clear_button.clicked.connect(lambda: self._bulk(False))
        if by_grade:
            self.select_grade(next(iter(by_grade)))

    def select_grade(self, grade):
        if grade not in self.dialog.led_class_groups:
            return
        self.current_grade = grade
        self.stack.setCurrentWidget(self.dialog.led_class_groups[grade])
        self.search.clear()
        self.update_grade_state()
        self._filter()

    def _grade_changed(self, grade, checked):
        if not checked and self.dialog.led_all_grades_check.isChecked():
            with QSignalBlocker(self.dialog.led_all_grades_check):
                self.dialog.led_all_grades_check.setChecked(False)
        self.select_grade(grade)

    def update_grade_state(self):
        for grade, row in self.grade_buttons.items():
            row.setProperty('active', grade == self.current_grade)
            row.style().unpolish(row)
            row.style().polish(row)
            selected = sum(c.isChecked() for c in self.dialog.led_class_checks[grade].values())
            total = len(self.dialog.led_class_checks[grade])
            all_classes = self.dialog.led_all_classes_checks[grade].isChecked()
            self.grade_counts[grade].setText('全部班级' if all_classes else f'已选 {selected} / {total} 班')
        if self.current_grade:
            active = (self.dialog.led_all_grades_check.isChecked() or
                      self.dialog.led_grade_checks[self.current_grade].isChecked())
            self.stack.setEnabled(active)
            self.search.setEnabled(active)
            self.select_all_button.setEnabled(active)
            self.clear_button.setEnabled(active)
            self.disabled_hint.setVisible(not active)
            has_classes = any(c.isChecked() for c in self.dialog.led_class_checks[self.current_grade].values())
            all_classes = self.dialog.led_all_classes_checks[self.current_grade].isChecked()
            self.selection_hint.setVisible(active and not has_classes and not all_classes)

    def _changed(self):
        self.update_grade_state()
        if hasattr(self.dialog, 'preview_generate_btn'):
            self.dialog.mark_led_preview_stale()

    def _class_changed(self, grade, checked):
        if self._loading:
            return
        if not checked:
            with QSignalBlocker(self.dialog.led_all_classes_checks[grade]):
                self.dialog.led_all_classes_checks[grade].setChecked(False)
        self._changed()

    def _all_changed(self, grade, checked):
        if self._loading:
            return
        if checked:
            self._loading = True
            for check in self.dialog.led_class_checks[grade].values():
                check.setChecked(True)
            self._loading = False
        self._changed()

    def _filter(self, *_args):
        query = self.search.text().strip().casefold()
        found = 0
        for cid, check in self.dialog.led_class_checks.get(self.current_grade, {}).items():
            match = query in self.names[(self.current_grade, cid)].casefold()
            check.setVisible(match)
            found += int(match)
        self.empty_search.setVisible(bool(query) and not found)
        if self.current_grade:
            self.dialog.led_class_groups[self.current_grade].reflow()
        self.select_all_button.setText('选中搜索结果' if query else '全选班级')
        self.clear_button.setText('清空搜索结果' if query else '清空班级')
        active = self.stack.isEnabled()
        self.select_all_button.setEnabled(active and bool(found))
        self.clear_button.setEnabled(active and bool(found))

    def _bulk(self, checked):
        if not self.current_grade:
            return
        query = self.search.text().strip().casefold()
        self._loading = True
        self.dialog.led_all_classes_checks[self.current_grade].setChecked(False)
        for cid, check in self.dialog.led_class_checks[self.current_grade].items():
            if query in self.names[(self.current_grade, cid)].casefold():
                check.setChecked(checked)
        self._loading = False
        self._changed()

    def load_selection(self, selections):
        self._loading = True
        for grade, all_check in self.dialog.led_all_classes_checks.items():
            all_check.setChecked(grade not in selections)
            for cid, check in self.dialog.led_class_checks[grade].items():
                check.setChecked(grade not in selections or cid in selections[grade])
        self._loading = False
        self.update_grade_state()
