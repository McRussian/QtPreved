#!/usr/bin/env python3
"""Точка входа QtPreved."""
from __future__ import annotations

import signal
import sys

from evdev import InputDevice, ecodes, list_devices
from PyQt6.QtWidgets import QApplication, QMessageBox

from qtpreved import config as cfg
from qtpreved.daemon import KeyboardDaemon
from qtpreved.injector import UinputInjector
from qtpreved.kbd_map import load_default_layouts
from qtpreved.layout import KDELayoutManager
from qtpreved.tray import TrayIcon


def _find_keyboard() -> InputDevice | None:
    """Вернуть первое устройство с EV_KEY и буквенными клавишами."""
    for path in list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(ecodes.EV_KEY, [])
            if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                return dev
        except Exception:
            continue
    return None


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not QApplication.isSystemTrayAvailable():
        QMessageBox.critical(None, 'QtPreved', 'Системный трей недоступен.')
        sys.exit(1)

    device = _find_keyboard()
    if device is None:
        QMessageBox.critical(
            None, 'QtPreved',
            'Клавиатура не найдена в /dev/input.\n'
            'Убедитесь что пользователь в группе input:\n'
            '  sudo usermod -a -G input $USER',
        )
        sys.exit(1)

    conf = cfg.load()
    en, ru = load_default_layouts()
    layout_manager = KDELayoutManager()
    injector = UinputInjector()
    daemon = KeyboardDaemon(conf, injector, layout_manager, en, ru, device)

    tray = TrayIcon(conf, daemon)
    tray.show()

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    app.aboutToQuit.connect(daemon.stop)
    app.aboutToQuit.connect(injector.close)

    daemon.start()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
