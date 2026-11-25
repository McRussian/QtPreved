"""Модель «экрана» для сквозных тестов: нажатия клавиш → KeyboardDaemon → итоговый текст.

Экран печатает символы по полным xkb-картам (буквы, цифры, знаки — как реальная система),
а Injector и LayoutManager демона меняют этот же экран. Так проверяется, что именно
увидит пользователь после автопереключения, а не какие вызовы сделал демон.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).parent.parent))

from evdev import ecodes

from qtpreved.config import Config
from qtpreved.daemon import KeyboardDaemon
from qtpreved.injector import _STOP_CHAR_KEYS
from qtpreved.kbd_map import load_default_layouts
from qtpreved.switcher import Injector, LayoutManager

_KEY_NAMES = (
    [f'KEY_{c}' for c in 'QWERTYUIOP'] + ['KEY_LEFTBRACE', 'KEY_RIGHTBRACE']
    + [f'KEY_{c}' for c in 'ASDFGHJKL'] + ['KEY_SEMICOLON', 'KEY_APOSTROPHE']
    + [f'KEY_{c}' for c in 'ZXCVBNM'] + ['KEY_COMMA', 'KEY_DOT', 'KEY_SLASH', 'KEY_GRAVE']
    + [f'KEY_{d}' for d in '1234567890'] + ['KEY_MINUS', 'KEY_EQUAL', 'KEY_SPACE']
    + ['KEY_ENTER', 'KEY_TAB']
)
_US_LOWER = 'qwertyuiop[]asdfghjkl;\'zxcvbnm,./`1234567890-= \n\t'
_US_UPPER = 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?~!@#$%^&*()_+ \n\t'
_RU_LOWER = 'йцукенгшщзхъфывапролджэячсмитьбю.ё1234567890-= \n\t'
_RU_UPPER = 'ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,Ё!"№;%:?*()_+ \n\t'

XKB_NAMES = ['us', 'ru']

XKB: dict[str, dict[int, tuple[str, str]]] = {
    'us': {getattr(ecodes, k): (lo, up) for k, lo, up in zip(_KEY_NAMES, _US_LOWER, _US_UPPER, strict=True)},
    'ru': {getattr(ecodes, k): (lo, up) for k, lo, up in zip(_KEY_NAMES, _RU_LOWER, _RU_UPPER, strict=True)},
}

# Символ → (keycode, нужен_shift). Без Shift приоритетнее (пробел, Enter, Tab есть в обоих).
_CHAR_TO_KEY: dict[str, dict[str, tuple[int, bool]]] = {}
for _name, _table in XKB.items():
    _rev: dict[str, tuple[int, bool]] = {}
    for _code, (_lo, _up) in _table.items():
        _rev.setdefault(_up, (_code, True))
    for _code, (_lo, _up) in _table.items():
        _rev[_lo] = (_code, False)
    _CHAR_TO_KEY[_name] = _rev


def retype(text: str, intended: str, actual: str) -> str:
    """Что появится на экране, если набирать `text` в раскладке `intended`, а включена `actual`."""
    result = []
    for ch in text:
        if ch == '\b':
            result.append(ch)
            continue
        code, shift = _CHAR_TO_KEY[intended][ch]
        result.append(XKB[actual][code][1 if shift else 0])
    return ''.join(result)


class Screen:
    """Текстовое поле с курсором в конце и активной раскладкой."""

    def __init__(self, layout: str) -> None:
        self.text = ''
        self.layout_idx = XKB_NAMES.index(layout)

    def press(self, code: int, shift: bool) -> None:
        if code == ecodes.KEY_BACKSPACE:
            self.text = self.text[:-1]
            return
        self.text += XKB[XKB_NAMES[self.layout_idx]][code][1 if shift else 0]


class ScreenInjector(Injector):
    def __init__(self, screen: Screen) -> None:
        self._screen = screen

    def inject_backspaces(self, n: int) -> None:
        for _ in range(n):
            self._screen.press(ecodes.KEY_BACKSPACE, False)

    def inject_text(self, text: str, layout: object) -> None:
        self._screen.text += text

    def get_selection(self) -> str | None:
        return None

    def replace_selection(self, new_text: str) -> None:
        pass

    def paste_text(self, text: str) -> None:
        self._screen.text += text

    def inject_stop_char(self, ch: str) -> None:
        # Как UinputInjector: нажатие клавиши по таблице, печатается в текущей раскладке экрана
        entry = _STOP_CHAR_KEYS.get(ch)
        if entry is not None:
            self._screen.press(*entry)


class ScreenLayoutManager(LayoutManager):
    def __init__(self, screen: Screen) -> None:
        self._screen = screen

    def get_current(self) -> int:
        return self._screen.layout_idx

    def set_layout(self, index: int) -> None:
        self._screen.layout_idx = index

    def list_layouts(self) -> list[str]:
        return list(XKB_NAMES)


class _Event:
    def __init__(self, code: int, value: int) -> None:
        self.type = ecodes.EV_KEY
        self.code = code
        self.value = value


def type_text(text: str, intended: str, actual: str, config: Config | None = None) -> str:
    """Пользователь набирает `text`, думая что включена `intended`, а включена `actual`.

    Символ '\\b' в тексте — нажатие Backspace. Возвращает итоговый текст на экране.
    Символ попадает на экран раньше, чем демон обработает событие: так и в реальности —
    демон считает, что стоп-символ уже стоит перед курсором.
    """
    en, ru = load_default_layouts()
    screen = Screen(actual)
    daemon = KeyboardDaemon(
        config or Config(), ScreenInjector(screen), ScreenLayoutManager(screen), en, ru,
    )
    for ch in text:
        if ch == '\b':
            code, shift = ecodes.KEY_BACKSPACE, False
        else:
            code, shift = _CHAR_TO_KEY[intended][ch]
        if shift:
            daemon._process_event(_Event(ecodes.KEY_LEFTSHIFT, 1))
        screen.press(code, shift)
        daemon._process_event(_Event(code, 1))
        daemon._process_event(_Event(code, 0))
        if shift:
            daemon._process_event(_Event(ecodes.KEY_LEFTSHIFT, 0))
    return screen.text


def apply_backspaces(text: str) -> str:
    """Применить '\\b' к тексту — так он будет выглядеть на экране."""
    result: list[str] = []
    for ch in text:
        if ch == '\b':
            if result:
                result.pop()
        else:
            result.append(ch)
    return ''.join(result)


_CYRILLIC = frozenset('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')


def letter_layout(ch: str) -> str | None:
    """Раскладка, в которой задумана буква: кириллица → ru, латиница → us, иначе None."""
    if ch in _CYRILLIC:
        return 'ru'
    if ch.isascii() and ch.isalpha():
        return 'us'
    return None


def intended_layouts(text: str) -> list[str]:
    """Задуманная раскладка для каждого символа смешанного текста.

    Буквы — по алфавиту. Знаки, цифры, пробелы — в раскладке предыдущего слова
    (человек ставит запятую после русского слова русской запятой). До первой буквы —
    в раскладке первой буквы текста.
    """
    first = next((lay for ch in text if (lay := letter_layout(ch))), 'us')
    result, current = [], first
    for ch in text:
        current = letter_layout(ch) or current
        result.append(current)
    return result


def type_mixed(text: str, start: str, user_switches: bool, config: Config | None = None) -> str:
    """Набор смешанного RU/EN текста. Возвращает итоговый текст на экране.

    start — раскладка, включённая перед началом набора.
    user_switches=False — пользователь сам раскладку не меняет, всё делает автопереключение.
    user_switches=True — пользователь сам переключает раскладку перед символом другого языка.
    """
    en, ru = load_default_layouts()
    screen = Screen(start)
    daemon = KeyboardDaemon(
        config or Config(), ScreenInjector(screen), ScreenLayoutManager(screen), en, ru,
    )
    for ch, intended in zip(text, intended_layouts(text)):
        if user_switches:
            screen.layout_idx = XKB_NAMES.index(intended)
        code, shift = _CHAR_TO_KEY[intended][ch]
        if shift:
            daemon._process_event(_Event(ecodes.KEY_LEFTSHIFT, 1))
        screen.press(code, shift)
        daemon._process_event(_Event(code, 1))
        daemon._process_event(_Event(code, 0))
        if shift:
            daemon._process_event(_Event(ecodes.KEY_LEFTSHIFT, 0))
    return screen.text
