import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from src.ui.settings_dialog import SettingsDialog
from src.services.config_manager import ConfigManager


def test_settings_grouping_and_fixed_save():
    app = QApplication.instance() or QApplication([])
    class Config:
        def get(self, key, default=None):
            return ConfigManager.DEFAULT_CONFIG.get(key, default)
    dialog = SettingsDialog(Config())
    assert [dialog.navigation.item(i).text() for i in range(dialog.navigation.count())] == [
        '学校绑定', '读卡设备', '语音播报', 'LED 屏', '高级设置']
    dialog.show(); app.processEvents()
    assert dialog.school_id_edit.isVisible()
    assert not dialog.preview_scroll.isVisible()
    dialog.navigation.setCurrentRow(3); app.processEvents()
    assert dialog.preview_scroll.isVisible()
    assert dialog.save_btn.isVisible()
    dialog.reject()

def test_led_settings_do_not_need_horizontal_scrolling():
    from PyQt6.QtWidgets import QScrollArea
    app = QApplication.instance() or QApplication([])
    class Config:
        def get(self, key, default=None):
            return ConfigManager.DEFAULT_CONFIG.get(key, default)
    dialog = SettingsDialog(Config()); dialog.show()
    dialog.navigation.setCurrentRow(3); app.processEvents()
    assert all(s.horizontalScrollBar().maximum() == 0 for s in dialog.pages.currentWidget().findChildren(QScrollArea) if s is not dialog.preview_scroll)
    dialog.reject()

def test_saved_reader_settings_restart_and_cancel_cleans_capture(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.database import DatabaseManager
    from src.services.readers.reader_manager import ReaderManager
    from PyQt6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    class Config:
        values = dict(ConfigManager.DEFAULT_CONFIG, school_id='s1')
        def get(self, key, default=None): return self.values.get(key, default)
        def set(self, key, value): self.values[key] = value
        def save(self): pass
    config = Config(); db = DatabaseManager(str(tmp_path / 'db.sqlite'))
    manager = ReaderManager(config, db); manager.restart = Mock(return_value=True)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    dialog = SettingsDialog(config, SimpleNamespace(db=db, api=None), reader_manager=manager)
    dialog.reader_panel.uhf_enabled.setChecked(True)
    dialog.reader_panel.capture.setChecked(True)
    assert manager.capturing
    dialog.save_settings()
    assert config.get('readers')[1]['enabled']
    manager.restart.assert_called_once()
    assert not manager.capturing
