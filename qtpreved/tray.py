from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from qtpreved import config as cfg
from qtpreved.config import Config
from qtpreved.daemon import KeyboardDaemon

_COLORS = {
    'ru': ('#1565c0', '#ffffff'),
    'en': ('#2e7d32', '#ffffff'),
}


def _make_icon(layout_name: str) -> QIcon:
    bg, fg = _COLORS.get(layout_name, ('#555555', '#ffffff'))
    px = QPixmap(22, 22)
    px.fill(QColor(bg))
    p = QPainter(px)
    p.setFont(QFont('Sans', 8, QFont.Weight.Bold))
    p.setPen(QColor(fg))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, layout_name.upper())
    p.end()
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, conf: Config, daemon: KeyboardDaemon, parent=None) -> None:
        super().__init__(parent)
        self._config = conf
        self._daemon = daemon
        self._layout_action = None

        self._build_menu()
        self._apply_layout('en')
        daemon.layout_changed.connect(self._on_layout_changed)
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()
        self._layout_action = menu.addAction('EN')
        self._layout_action.setEnabled(False)
        menu.addSeparator()
        menu.addAction('Настройки…', self._open_settings)
        menu.addSeparator()
        menu.addAction('Выход', QApplication.instance().quit)
        self.setContextMenu(menu)

    def _apply_layout(self, layout_name: str) -> None:
        self.setIcon(_make_icon(layout_name))
        self.setToolTip(f'QtPreved [{layout_name.upper()}]')
        if self._layout_action is not None:
            self._layout_action.setText(layout_name.upper())

    def _on_layout_changed(self, layout_name: str) -> None:
        self._apply_layout(layout_name)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_settings()

    def _open_settings(self) -> None:
        from qtpreved.settings import SettingsDialog
        dlg = SettingsDialog(self._config)
        if dlg.exec():
            cfg.save(self._config)
            self._daemon.reload_hotkeys()
