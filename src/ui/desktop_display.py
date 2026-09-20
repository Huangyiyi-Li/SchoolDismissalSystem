"""Native monitor presentation; all QWidget and QScreen access stays on the UI thread."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import tempfile
from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton
from ..services.config_manager import LedScreenConfig, load_led_setup
from ..services.led_renderer import render_led_pages, render_club_led_pages
from ..services.led_preview import colorize_led_preview


def monitor_key(screen):
    serial = screen.serialNumber()
    return f'serial:{screen.manufacturer()}:{screen.model()}:{serial}' if serial else screen.name()


def resolve_monitor(key):
    if not key:
        return QGuiApplication.primaryScreen()
    return next((s for s in QGuiApplication.screens() if monitor_key(s) == key), None)


def monitor_pixels(screen):
    """Qt geometry is in logical pixels; render at the monitor's native density."""
    geometry = screen.geometry()
    ratio = screen.devicePixelRatio()
    return round(geometry.width() * ratio), round(geometry.height() * ratio)


def desktop_scale(width, height):
    return max(0.25, min(width / 640, height / 240))


def render_desktop_frames(values, classes_by_type, statuses, size):
    width, height = size
    common = dict(width=width, height=height,
                  show_title=values['led_show_title'], title_position=values['led_title_position'],
                  color_mode=values['led_color_mode'], pixel_scale=desktop_scale(width, height),
                  # Desktop output must size the grid from the native viewport.
                  # LED font overrides are deliberately ignored here; otherwise
                  # an old 8px LED setting produces a tiny table on a 1080p PC.
                  title_font_size=0,
                  header_font_size=0, cell_font_size=0)
    frames = []
    with tempfile.TemporaryDirectory(prefix='school-desktop-') as folder:
        for kind, classes in sorted(classes_by_type.items()):
            if kind == 1 and values['led_grade_filter_mode'] == 'selected':
                classes = [c for c in classes if c.get('grade_name') in values['led_visible_grades']]
            if not classes:
                continue
            if kind == 1:
                paths = render_led_pages(values['led_school_title'], classes, statuses, folder,
                                         grades_per_page=values['led_grades_per_page'],
                                         regions_per_page=values['led_layout_regions'], **common)
            else:
                paths = render_club_led_pages(values['led_school_title'], classes, statuses, folder,
                                              rows_per_group=values['led_club_rows_per_group'],
                                              groups_per_page=values['led_club_groups_per_page'], **common)
            for path in paths:
                image = colorize_led_preview(path, values['led_color_mode'])
                frames.append((image.width, image.height, image.tobytes()))
    return frames


class DesktopDisplayWindow(QWidget):
    dismissed = pyqtSignal()

    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview
        self.close_button = QPushButton("关闭展示", self)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QPushButton { color: white; background: rgba(20,20,20,190); "
            "border: 1px solid rgba(255,255,255,150); border-radius: 6px; "
            "padding: 8px 14px; font-size: 16px; } "
            "QPushButton:hover { background: rgba(160,30,30,230); }"
        )
        self.close_button.clicked.connect(self.close)
        self.close_button.raise_()
        self.setWindowTitle('放学信息展示 · Esc 退出')
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.frames = []
        self.index = 0
        self.message = '正在载入放学信息…'
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_page)

    def present(self, screen):
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self._position_close_button()

    def resizeEvent(self, event):
        self._position_close_button()
        super().resizeEvent(event)

    def _position_close_button(self):
        if hasattr(self, "close_button"):
            margin = 20
            size = self.close_button.sizeHint()
            self.close_button.setGeometry(
                max(0, self.width() - size.width() - margin), margin,
                size.width(), size.height(),
            )

    def set_frames(self, frames, seconds):
        self.frames = [QPixmap.fromImage(QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy())
                       for w, h, data in frames]
        self.index = self.index % len(self.frames) if self.frames else 0
        self.message = '当前时段暂无可展示班级，请检查班级同步及显示年级设置'
        self.timer.setInterval(round(float(seconds) * 1000))
        if len(self.frames) > 1:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def next_page(self):
        if self.frames:
            self.index = (self.index + 1) % len(self.frames)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self.frames:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            frame = self.frames[self.index]
            size = frame.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            x, y = (self.width() - size.width()) // 2, (self.height() - size.height()) // 2
            painter.drawPixmap(x, y, size.width(), size.height(), frame)
        else:
            painter.setPen(Qt.GlobalColor.yellow)
            painter.drawText(self.rect().adjusted(24, 24, -24, -24),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)

        if self.preview:
            painter.fillRect(0, self.height() - 32, self.width(), 32, Qt.GlobalColor.black)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(0, self.height() - 32, self.width(), 32, Qt.AlignmentFlag.AlignCenter,
                             '测试展示 · 非实时放学画面 · 按 Esc 返回设置')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        self.dismissed.emit()
        super().closeEvent(event)


class DesktopDisplayManager(QObject):
    rendered = pyqtSignal(object)

    def __init__(self, config, service, parent=None):
        super().__init__(parent)
        self.config, self.service = config, service
        self.windows, self.signatures, self.pending = {}, {}, {}
        self.suppressed, self.statuses = {}, {}
        self._closed = False
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='desktop-render')
        self.rendered.connect(self._apply_frames)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        QGuiApplication.instance().screenRemoved.connect(self._monitor_removed)

    def _monitor_removed(self, screen):
        # Qt can move a fullscreen window to the primary screen on unplug.
        # Hide first; tick reopens only windows whose saved monitor is available.
        for window in self.windows.values():
            window.hide()
        self.tick()

    def dismiss(self, sid):
        self.suppressed[sid] = self.service.display_snapshot()['session']
        self._remove(sid)

    def resume(self):
        self.suppressed.clear()
        self.tick()

    def _remove(self, sid):
        window = self.windows.pop(sid, None)
        self.signatures.pop(sid, None)
        if window:
            window.timer.stop()
            window.hide()
            window.deleteLater()

    def tick(self):
        if self._closed:
            return
        state = self.service.display_snapshot()
        screens, plans = load_led_setup(self.config)
        plans = {p['id']: p for p in plans}
        live = set()
        self.statuses = {}
        occupied = set()
        classes = None
        for device in screens:
            if device.get('settings', {}).get('led_output_type') != 'desktop':
                continue
            sid = device['id']
            cfg = LedScreenConfig(self.config, device, plans[device['plan_id']])
            monitor = resolve_monitor(cfg.get('led_monitor'))
            reason = ('未启用' if not device['enabled'] else
                      '显示器未连接' if monitor is None else
                      '等待放学时段' if not state['active'] else
                      '已退出 · 可在主界面恢复电脑展示' if self.suppressed.get(sid) == state['session'] else
                      '设置期间暂停展示' if QApplication.activeModalWidget() else '')
            if not reason and monitor_key(monitor) in occupied:
                reason = '该显示器已被另一块屏幕使用'
            self.statuses[sid] = reason or '电脑展示中'
            if reason:
                continue
            occupied.add(monitor_key(monitor))
            if classes is None:
                try:
                    classes = {kind: self.service.db.get_led_classes(self.config.get('school_id'), class_type=kind)
                               for kind in state['class_types']}
                except Exception as exc:
                    self.statuses[sid] = '读取班级失败：' + str(exc)
                    continue
            live.add(sid)
            size = monitor_pixels(monitor)
            signature = (repr(cfg.values), repr(classes), repr(state), size, self.config.get('school_id'))
            if sid not in self.windows:
                window = self.windows[sid] = DesktopDisplayWindow()
                window.dismissed.connect(lambda sid=sid: self.dismiss(sid))
            window = self.windows[sid]
            if not window.isVisible() or window.windowHandle().screen() != monitor or window.geometry() != monitor.geometry():
                window.present(monitor)
            if self.signatures.get(sid) == signature or sid in self.pending:
                continue
            self.signatures[sid] = signature
            future = self.executor.submit(render_desktop_frames, deepcopy(cfg.values), deepcopy(classes),
                                          dict(state['statuses']), size)
            self.pending[sid] = future
            def done(future, sid=sid, signature=signature, seconds=cfg.get('led_page_seconds')):
                try:
                    result = (sid, signature, seconds, future.result(), '')
                except Exception as exc:
                    result = (sid, signature, seconds, [], str(exc))
                if not self._closed:
                    self.rendered.emit(result)
            future.add_done_callback(done)
        for sid in set(self.windows) - live:
            self._remove(sid)

    def _apply_frames(self, result):
        sid, signature, seconds, frames, error = result
        self.pending.pop(sid, None)
        # Recheck schedule, device and dimensions after asynchronous rendering.
        self.tick()
        if sid not in self.windows or self.signatures.get(sid) != signature:
            return
        if error:
            self.windows[sid].message = '画面生成失败，请检查显示设置后重试'
            self.windows[sid].update()
            self.statuses[sid] = '画面生成失败：' + error
            self.signatures.pop(sid, None)
        else:
            self.windows[sid].set_frames(frames, seconds)

    def shutdown(self):
        self._closed = True
        self.timer.stop()
        for sid in list(self.windows):
            self._remove(sid)
        self.executor.shutdown(wait=True, cancel_futures=True)
