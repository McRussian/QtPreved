from __future__ import annotations

import logging
import subprocess
import time

from evdev import UInput, ecodes

from qtpreved.kbd_map import Layout
from qtpreved.switcher import Injector

log = logging.getLogger(__name__)

# Текстовые типы буфера обмена в порядке предпочтения при сохранении
_TEXT_MIME_TYPES = ('text/plain;charset=utf-8', 'UTF8_STRING', 'text/plain')

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

    def __init__(
        self, ui: UInput | None = None, paste_delay: float = 0.05, key_delay: float = 0.005,
    ) -> None:
        self._ui = ui if ui is not None else UInput()
        self._paste_delay = paste_delay
        self._key_delay = key_delay

    def _emit(self, keycode: int, value: int) -> None:
        """Одно событие клавиши отдельным кадром (syn) с паузой после.

        Нажатие и отпускание в одном кадре и без пауз libinput/KWin обрабатывают
        ненадёжно — часть нажатий теряется (оставались недостёртые буквы).
        """
        self._ui.write(ecodes.EV_KEY, keycode, value)
        self._ui.syn()
        if self._key_delay:
            time.sleep(self._key_delay)

    def _press(self, keycode: int) -> None:
        self._emit(keycode, 1)
        self._emit(keycode, 0)

    def _press_with(self, modifier: int, keycode: int) -> None:
        self._emit(modifier, 1)
        self._press(keycode)
        self._emit(modifier, 0)

    def _press_shifted(self, keycode: int) -> None:
        self._press_with(ecodes.KEY_LEFTSHIFT, keycode)

    def inject_backspaces(self, n: int) -> None:
        log.debug('backspace ×%d', n)
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

    @staticmethod
    def _save_clipboard() -> tuple[str, bytes] | None:
        """Сохранить содержимое буфера обмена любого типа (текст, картинка) как байты.

        None — буфер пуст или прочитать не удалось. Ошибка чтения не должна срывать
        вставку: к этому моменту слово уже стёрто Backspace-ами.
        """
        try:
            types = subprocess.run(
                ['wl-paste', '--list-types'], capture_output=True, text=True, check=True,
            ).stdout.splitlines()
            types = [t for t in types if t]
            if not types:
                return None
            mime = next((t for t in _TEXT_MIME_TYPES if t in types), types[0])
            data = subprocess.run(
                ['wl-paste', '--no-newline', '--type', mime], capture_output=True, check=True,
            ).stdout
            log.debug('буфер обмена сохранён: %s, %d байт (типов %d)', mime, len(data), len(types))
            return mime, data
        except Exception:
            log.debug('буфер обмена не сохранён', exc_info=True)
            return None

    @staticmethod
    def _restore_clipboard(saved: tuple[str, bytes] | None) -> None:
        """Вернуть сохранённое содержимое буфера с исходным типом, пустой буфер — очистить."""
        try:
            if saved is None:
                subprocess.run(['wl-copy', '--clear'])
                log.debug('буфер обмена очищен')
            else:
                mime, data = saved
                subprocess.run(['wl-copy', '--type', mime], input=data)
                log.debug('буфер обмена восстановлен: %s, %d байт', mime, len(data))
        except OSError:
            log.debug('буфер обмена не восстановлен', exc_info=True)

    def replace_selection(self, new_text: str) -> None:
        """Заменить выделение через буфер обмена: сохранить → wl-copy → Ctrl+V → восстановить."""
        saved = self._save_clipboard()

        subprocess.run(['wl-copy'], input=new_text, text=True, check=True)

        self._press_with(ecodes.KEY_LEFTCTRL, ecodes.KEY_V)

        time.sleep(self._paste_delay)

        self._restore_clipboard(saved)

    def paste_text(self, text: str) -> None:
        """Вставить текст через буфер обмена.

        Отличие от replace_selection: явная задержка после wl-copy гарантирует,
        что compositor обработает запрос до прихода Ctrl+V.
        """
        log.debug('вставка %r', text)
        saved = self._save_clipboard()

        subprocess.run(['wl-copy'], input=text, text=True, check=True)
        time.sleep(self._paste_delay)  # дать compositor принять новый буфер

        self._press_with(ecodes.KEY_LEFTCTRL, ecodes.KEY_V)

        time.sleep(self._paste_delay)  # дать приложению получить буфер до восстановления
        self._restore_clipboard(saved)

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
