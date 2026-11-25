"""Подробный лог: включение/выключение на лету, запись в файл с ротацией, вывод в консоль."""
from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved import logs


class _LogsTestBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / 'sub' / 'qtpreved.log'
        self.logger = logging.getLogger('qtpreved')
        self._saved_handlers = list(self.logger.handlers)
        self._saved_level = self.logger.level

    def tearDown(self):
        logs.apply_logging(False, self.path)
        for handler in list(self.logger.handlers):
            if handler not in self._saved_handlers:
                self.logger.removeHandler(handler)
                handler.close()
        self.logger.setLevel(self._saved_level)
        self._tmp.cleanup()

    def read(self) -> str:
        return self.path.read_text(encoding='utf-8') if self.path.exists() else ''


class TestApplyLogging(_LogsTestBase):

    def test_enable_creates_file_and_dirs(self):
        logs.apply_logging(True, self.path)
        self.assertTrue(self.path.exists())
        self.assertTrue(logs.is_file_logging())

    def test_module_messages_written(self):
        logs.apply_logging(True, self.path)
        logging.getLogger('qtpreved.daemon').debug('проверка %s', 'отладки')
        self.assertIn('qtpreved.daemon: проверка отладки', self.read())

    def test_debug_level_when_enabled(self):
        logs.apply_logging(True, self.path)
        self.assertEqual(self.logger.level, logging.DEBUG)

    def test_disable_stops_writing(self):
        logs.apply_logging(True, self.path)
        logs.apply_logging(False, self.path)
        logging.getLogger('qtpreved.daemon').debug('после выключения')
        self.assertNotIn('после выключения', self.read())
        self.assertFalse(logs.is_file_logging())

    def test_disable_writes_marker(self):
        logs.apply_logging(True, self.path)
        logs.apply_logging(False, self.path)
        self.assertIn('подробный лог выключен', self.read())

    def test_enable_twice_single_handler(self):
        logs.apply_logging(True, self.path)
        logs.apply_logging(True, self.path)
        logging.getLogger('qtpreved.daemon').debug('одна запись')
        self.assertEqual(self.read().count('одна запись'), 1)

    def test_disable_when_not_enabled_is_noop(self):
        logs.apply_logging(False, self.path)
        self.assertFalse(self.path.exists())

    def test_warning_level_when_disabled(self):
        logs.apply_logging(True, self.path)
        logs.apply_logging(False, self.path)
        self.assertEqual(self.logger.level, logging.WARNING)

    def test_rotation_configured(self):
        logs.apply_logging(True, self.path)
        handler = next(h for h in self.logger.handlers if isinstance(h, RotatingFileHandler))
        self.assertEqual(handler.maxBytes, logs.LOG_MAX_BYTES)
        self.assertEqual(handler.backupCount, logs.LOG_BACKUP_COUNT)

    def test_reenable_appends(self):
        logs.apply_logging(True, self.path)
        logging.getLogger('qtpreved').info('первый запуск')
        logs.apply_logging(False, self.path)
        logs.apply_logging(True, self.path)
        logging.getLogger('qtpreved').info('второй запуск')
        text = self.read()
        self.assertIn('первый запуск', text)
        self.assertIn('второй запуск', text)


class TestConsole(_LogsTestBase):

    def test_console_handler_added_once(self):
        logs.enable_console()
        logs.enable_console()
        consoles = [h for h in self.logger.handlers if h.get_name() == 'qtpreved-console']
        self.assertEqual(len(consoles), 1)

    def test_console_keeps_debug_after_file_disabled(self):
        logs.enable_console()
        logs.apply_logging(True, self.path)
        logs.apply_logging(False, self.path)
        self.assertEqual(self.logger.level, logging.DEBUG)


if __name__ == '__main__':
    unittest.main()
