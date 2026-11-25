from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qtpreved.config import Config
from qtpreved.logs import LOG_PATH

_AUTOSTART_PATH = Path.home() / '.config' / 'autostart' / 'qtpreved.desktop'


def _set_autostart(enabled: bool) -> None:
    if enabled:
        _AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
        exe = sys.executable
        script = Path(sys.argv[0]).resolve()
        _AUTOSTART_PATH.write_text(
            '[Desktop Entry]\n'
            'Type=Application\n'
            'Name=QtPreved\n'
            f'Exec={exe} {script}\n'
            'X-KDE-autostart-phase=1\n',
            encoding='utf-8',
        )
    else:
        _AUTOSTART_PATH.unlink(missing_ok=True)


class _ListEditor(QWidget):
    """Редактор списка строк с кнопками Добавить/Удалить."""

    def __init__(self, items: list[str], prompt: str = '', parent=None) -> None:
        super().__init__(parent)
        self._prompt = prompt
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._list.addItems(items)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        add_btn = QPushButton('Добавить')
        del_btn = QPushButton('Удалить')
        add_btn.clicked.connect(self._add)
        del_btn.clicked.connect(self._remove)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch()
        layout.addLayout(row)

    def _add(self) -> None:
        text, ok = QInputDialog.getText(self, 'Добавить', self._prompt)
        if ok and text.strip():
            self._list.addItem(text.strip())

    def _remove(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def values(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle('Настройки QtPreved')
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)
        tabs.addTab(self._tab_hotkeys(), 'Горячие клавиши')
        tabs.addTab(self._tab_detection(), 'Автопереключение')
        tabs.addTab(self._tab_exclusions(), 'Исключения')
        tabs.addTab(self._tab_general(), 'Общие')

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # --- Tabs ---

    def _tab_hotkeys(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        c = self._config
        self._hk_word = QLineEdit(c.hotkey_switch_word)
        self._hk_sel = QLineEdit(c.hotkey_switch_selection)
        self._hk_undo = QLineEdit(c.hotkey_undo)
        self._hk_win = QLineEdit(c.hotkey_toggle_window)
        form.addRow('Переключить слово:', self._hk_word)
        form.addRow('Переключить выделение:', self._hk_sel)
        form.addRow('Отменить переключение:', self._hk_undo)
        form.addRow('Вкл/выкл для окна:', self._hk_win)
        hint = QLabel('Формат: Pause, Ctrl+Pause, Shift+Pause, Alt+Pause')
        hint.setStyleSheet('color: gray; font-size: 11px;')
        form.addRow('', hint)
        return w

    def _tab_detection(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        c = self._config
        self._auto_switch = QCheckBox()
        self._auto_switch.setChecked(c.auto_switch)
        self._min_len = QSpinBox()
        self._min_len.setRange(1, 20)
        self._min_len.setValue(c.min_word_length)
        self._skip_upper = QCheckBox()
        self._skip_upper.setChecked(c.skip_uppercase)
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 3.0)
        self._threshold.setSingleStep(0.05)
        self._threshold.setDecimals(2)
        self._threshold.setValue(c.detection_margin)
        self._min_alt = QDoubleSpinBox()
        self._min_alt.setRange(-15.0, 0.0)
        self._min_alt.setSingleStep(0.5)
        self._min_alt.setDecimals(1)
        self._min_alt.setValue(c.min_alt_logprob)
        form.addRow('Автопереключение:', self._auto_switch)
        form.addRow('Минимальная длина слова:', self._min_len)
        form.addRow('Игнорировать CAPS:', self._skip_upper)
        form.addRow('Порог детектора:', self._threshold)
        form.addRow('Мин. оценка альт. раскладки:', self._min_alt)
        return w

    def _tab_exclusions(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel('Исключённые слова:'))
        self._exc_words = _ListEditor(list(self._config.excluded_words), 'Слово')
        layout.addWidget(self._exc_words)
        layout.addWidget(QLabel('Исключённые приложения:'))
        self._exc_apps = _ListEditor(list(self._config.excluded_apps), 'Имя приложения')
        layout.addWidget(self._exc_apps)
        return w

    def _tab_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        c = self._config
        self._undo_depth = QSpinBox()
        self._undo_depth.setRange(1, 100)
        self._undo_depth.setValue(c.undo_stack_depth)
        self._autostart = QCheckBox()
        self._autostart.setChecked(c.autostart)
        self._debug_log = QCheckBox()
        self._debug_log.setChecked(c.debug_log)
        form.addRow('Глубина undo:', self._undo_depth)
        form.addRow('Автозапуск:', self._autostart)
        form.addRow('Подробный лог:', self._debug_log)
        hint = QLabel(f'Файл: {LOG_PATH}\nЗаписывает все нажатия клавиш — включайте только для отладки.')
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hint.setStyleSheet('color: gray; font-size: 11px;')
        form.addRow('', hint)
        return w

    # --- Apply ---

    def _apply(self) -> None:
        c = self._config
        c.hotkey_switch_word = self._hk_word.text().strip()
        c.hotkey_switch_selection = self._hk_sel.text().strip()
        c.hotkey_undo = self._hk_undo.text().strip()
        c.hotkey_toggle_window = self._hk_win.text().strip()
        c.auto_switch = self._auto_switch.isChecked()
        c.min_word_length = self._min_len.value()
        c.skip_uppercase = self._skip_upper.isChecked()
        c.detection_margin = self._threshold.value()
        c.min_alt_logprob = self._min_alt.value()
        c.excluded_words = self._exc_words.values()
        c.excluded_apps = self._exc_apps.values()
        c.undo_stack_depth = self._undo_depth.value()
        c.debug_log = self._debug_log.isChecked()
        autostart_changed = c.autostart != self._autostart.isChecked()
        c.autostart = self._autostart.isChecked()
        if autostart_changed:
            _set_autostart(c.autostart)
        self.accept()
