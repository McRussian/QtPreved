from __future__ import annotations

import subprocess
import time

from evdev import UInput, ecodes

from qtpreved.kbd_map import Layout
from qtpreved.switcher import Injector

# Стоп-символы → (keycode, нужен_shift). Только US-раскладка: цифры/знаки одинаковы.
_STOP_CHAR_KEYS: dict[str, tuple[int, bool]] = {
    ' ':  (ecodes.KEY_SPACE,      False),
    '\t': (ecodes.KEY_TAB,        False),
    '\n': (ecodes.KEY_ENTER,      False),
    '\r': (ecodes.KEY_ENTER,      False),
    '.':  (ecodes.KEY_DOT,        False),
    ',':  (ecodes.KEY_COMMA,      False),
    '!':  (ecodes.KEY_1,          True),
    '?':  (ecodes.KEY_SLASH,      True),
    ';':  (ecodes.KEY_SEMICOLON,  False),
    ':':  (ecodes.KEY_SEMICOLON,  True),
    '-':  (ecodes.KEY_MINUS,      False),
    '(':  (ecodes.KEY_9,          True),
    ')':  (ecodes.KEY_0,          True),
    '[':  (ecodes.KEY_LEFTBRACE,  False),
    ']':  (ecodes.KEY_RIGHTBRACE, False),
    '{':  (ecodes.KEY_LEFTBRACE,  True),
    '}':  (ecodes.KEY_RIGHTBRACE, True),
    '"':  (ecodes.KEY_APOSTROPHE, True),
}


class UinputInjector(Injector):
    """Инжект нажатий через uinput и работа с буфером обмена через wl-clipboard.

    Принимает готовое UInput-устройство — реальное или мок для тестов.
    """

    def __init__(self, ui: UInput | None = None, paste_delay: float = 0.05) -> None:
        self._ui = ui if ui is not None else UInput()
        self._paste_delay = paste_delay

    def _press(self, keycode: int) -> None:
        self._ui.write(ecodes.EV_KEY, keycode, 1)
        self._ui.write(ecodes.EV_KEY, keycode, 0)
        self._ui.syn()

    def _press_shifted(self, keycode: int) -> None:
        self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
        self._ui.write(ecodes.EV_KEY, keycode, 1)
        self._ui.write(ecodes.EV_KEY, keycode, 0)
        self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
        self._ui.syn()

    def inject_backspaces(self, n: int) -> None:
        for _ in range(n):
            self._press(ecodes.KEY_BACKSPACE)

    def inject_text(self, text: str, layout: Layout) -> None:
        """Инжектировать текст посимвольно. Символы вне раскладки пропускаются."""
        char_map = layout._char_to_key
        for ch in text:
            if ch not in char_map:
                continue
            keycode, shifted = char_map[ch]
            if shifted:
                self._press_shifted(keycode)
            else:
                self._press(keycode)

    def get_selection(self) -> str | None:
        """Прочитать primary selection через wl-paste. None если пусто или ошибка."""
        try:
            result = subprocess.run(
                ['wl-paste', '--primary', '--no-newline'],
                capture_output=True, text=True, check=True,
            )
            return result.stdout or None
        except subprocess.CalledProcessError:
            return None

    def replace_selection(self, new_text: str) -> None:
        """Заменить выделение через буфер обмена: сохранить → wl-copy → Ctrl+V → восстановить."""
        try:
            old = subprocess.run(
                ['wl-paste', '--no-newline'],
                capture_output=True, text=True, check=True,
            ).stdout
        except subprocess.CalledProcessError:
            old = ''

        subprocess.run(['wl-copy'], input=new_text, text=True, check=True)

        self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
        self._ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
        self._ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
        self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
        self._ui.syn()

        time.sleep(self._paste_delay)

        subprocess.run(['wl-copy'], input=old, text=True, check=True)

    def inject_stop_char(self, ch: str) -> None:
        """Инжектировать стоп-символ по таблице US-раскладки."""
        entry = _STOP_CHAR_KEYS.get(ch)
        if entry is None:
            return
        keycode, shifted = entry
        if shifted:
            self._press_shifted(keycode)
        else:
            self._press(keycode)

    def close(self) -> None:
        """Закрыть uinput-устройство."""
        self._ui.close()

    def __enter__(self) -> UinputInjector:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
