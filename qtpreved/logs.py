"""Подробный лог для отладки.

Включается настройкой debug_log (Настройки → Общие → Подробный лог) и применяется
сразу, без перезапуска. Пишется в файл с ротацией (1 МБ × 3), чтобы не разрастался.
Лог содержит все нажатые клавиши — включать только на время отладки.

Переменная окружения QTPREVED_DEBUG=1 дополнительно выводит лог в консоль.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state') / 'qtpreved' / 'qtpreved.log'
LOG_FORMAT = '%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

_ROOT = 'qtpreved'
_FILE_HANDLER = 'qtpreved-file'
_CONSOLE_HANDLER = 'qtpreved-console'


def _logger() -> logging.Logger:
    return logging.getLogger(_ROOT)


def _handlers(name: str) -> list[logging.Handler]:
    return [h for h in _logger().handlers if h.get_name() == name]


def _update_level() -> None:
    # Есть куда писать — пишем всё; нет — только предупреждения и ошибки (в stderr)
    _logger().setLevel(logging.DEBUG if _logger().handlers else logging.WARNING)


def _formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)


def apply_logging(enabled: bool, path: Path = LOG_PATH) -> None:
    """Включить или выключить подробный лог в файл. Повторный вызов с тем же значением ничего не меняет."""
    existing = _handlers(_FILE_HANDLER)
    if enabled and not existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding='utf-8',
        )
        handler.set_name(_FILE_HANDLER)
        handler.setFormatter(_formatter())
        _logger().addHandler(handler)
        _update_level()
        _logger().info('подробный лог включён: %s', path)
    elif not enabled and existing:
        _logger().info('подробный лог выключен')
        for handler in existing:
            _logger().removeHandler(handler)
            handler.close()
        _update_level()


def enable_console() -> None:
    """Дублировать лог в консоль (stderr) — для запуска из терминала."""
    if not _handlers(_CONSOLE_HANDLER):
        handler = logging.StreamHandler()
        handler.set_name(_CONSOLE_HANDLER)
        handler.setFormatter(_formatter())
        _logger().addHandler(handler)
        _update_level()


def is_file_logging() -> bool:
    return bool(_handlers(_FILE_HANDLER))
