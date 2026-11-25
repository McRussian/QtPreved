"""Настройка подробного лога: галочка на вкладке «Общие», применяется после сохранения."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

from qtpreved.config import Config
from qtpreved.logs import LOG_PATH
from qtpreved.settings import SettingsDialog
from qtpreved.tray import TrayIcon

_app = None


def setUpModule():
    global _app
    _app = QApplication.instance() or QApplication(sys.argv[:1])


class TestSettingsDialogDebugLog(unittest.TestCase):

    def test_checkbox_reflects_config(self):
        dlg = SettingsDialog(Config(debug_log=True))
        self.assertTrue(dlg._debug_log.isChecked())

    def test_apply_saves_to_config(self):
        config = Config()
        dlg = SettingsDialog(config)
        dlg._debug_log.setChecked(True)
        dlg._apply()
        self.assertTrue(config.debug_log)

    def test_apply_can_disable(self):
        config = Config(debug_log=True)
        dlg = SettingsDialog(config)
        dlg._debug_log.setChecked(False)
        dlg._apply()
        self.assertFalse(config.debug_log)

    def test_hint_shows_path_and_warning(self):
        from PyQt6.QtWidgets import QLabel
        dlg = SettingsDialog(Config())
        texts = ' '.join(label.text() for label in dlg.findChildren(QLabel))
        self.assertIn(str(LOG_PATH), texts)
        self.assertIn('все нажатия', texts)


class TestTrayAppliesLogging(unittest.TestCase):
    """После сохранения настроек трей применяет лог сразу, без перезапуска."""

    def test_settings_accept_applies_logging(self):
        config = Config()
        tray = TrayIcon(config, MagicMock())

        def fake_exec(dlg):
            dlg._debug_log.setChecked(True)
            dlg._apply()
            return True

        with patch('qtpreved.settings.SettingsDialog.exec', fake_exec), \
                patch('qtpreved.tray.cfg.save') as save, \
                patch('qtpreved.tray.logs.apply_logging') as apply:
            tray._open_settings()
        save.assert_called_once_with(config)
        apply.assert_called_once_with(True)

    def test_settings_cancel_does_not_apply(self):
        tray = TrayIcon(Config(), MagicMock())
        with patch('qtpreved.settings.SettingsDialog.exec', return_value=False), \
                patch('qtpreved.tray.logs.apply_logging') as apply:
            tray._open_settings()
        apply.assert_not_called()

    def test_no_log_item_in_tray_menu(self):
        tray = TrayIcon(Config(), MagicMock())
        texts = [a.text() for a in tray.contextMenu().actions()]
        self.assertNotIn('Подробный лог', texts)

if __name__ == '__main__':
    unittest.main()
