"""Сквозные тесты: что окажется на экране после набора в неправильной раскладке.

Пользователь набирает текст, думая, что включена одна раскладка, а включена другая.
Ожидание — на экране ровно задуманный текст: слово переключено, знаки препинания,
цифры, дефисы и разделители на месте, ничего не пропало и не задвоилось.
'\\b' в тексте — нажатие Backspace.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evdev import ecodes

from qtpreved.config import Config
from tests.screen_sim import _Event, apply_backspaces, retype, type_keys, type_text

RU_IN_US = [
    # Разделители после слова
    'привет ', 'привет\n', 'привет\t',
    # Знаки препинания (набираются клавишами русской раскладки)
    'привет, ', 'привет. ', 'привет! ', 'привет? ', 'привет: ', 'привет; ',
    '(привет) ', '"привет" ', 'привет... ',
    # Буквы на клавишах , . ; \' [ ] ` в английской раскладке
    'робот ', 'уже ', 'хорошо ', 'компьютер ', 'объект ', 'жизнь ', 'это ', 'ещё ',
    'будет, ', 'неделю. ',
    # Дефис, цифры, регистр
    'кто-то ', 'работа2 ', 'Привет ',
    # Предложения: после первого переключения остаток набирается уже правильно
    'Привет, мир! ', 'Привет, как дела? Всё хорошо. ',
    # Опечатки и исправления
    'пирвет, ', 'спаисбо! ', 'приветт\b, ',
]

EN_IN_RU = [
    'hello ', 'hello\n', 'hello\t',
    'hello, ', 'hello. ', 'hello! ', 'hello? ', 'hello: ', 'hello; ',
    '(hello) ', '"hello" ', 'hello... ',
    # Буквы, которые в русской раскладке дают б ю ж э х ъ ё
    "don't ", 'keyboard, ', 'layout. ',
    'e-mail ', 'world2 ', 'Hello ',
    'Hello, world! ', 'Hello, how are you? I am fine. ',
    'hlelo, ', 'wrold! ', 'helloo\b, ',
]

RU_CORRECT = [
    'Привет, как дела? Всё хорошо. ',
    'Это мой компьютер: быстрый и тихий! ',
    'Кто-то оставил объект (жёлтый) у подъезда; ещё вчера. ',
    'В 2026 году будет 12 месяцев. ',
]

EN_CORRECT = [
    'Hello, how are you? I am fine. ',
    "Don't stop: write code; test it (always)! ",
    'Version 2 is "stable" now... ',
    'e-mail me at 10 tomorrow. ',
]


class _TypingChecks:
    def assert_screen(self, text: str, intended: str, actual: str, config: Config | None = None) -> None:
        with self.subTest(text=text, typed=retype(text, intended, actual)):
            self.assertEqual(type_text(text, intended, actual, config), apply_backspaces(text))


class TestRussianTypedInEnglishLayout(_TypingChecks, unittest.TestCase):

    def test_cases(self):
        for text in RU_IN_US:
            self.assert_screen(text, 'ru', 'us')


class TestEnglishTypedInRussianLayout(_TypingChecks, unittest.TestCase):

    def test_cases(self):
        for text in EN_IN_RU:
            self.assert_screen(text, 'us', 'ru')


class TestCorrectLayoutUntouched(_TypingChecks, unittest.TestCase):
    """Набор в правильной раскладке не должен менять ни символа."""

    def test_russian(self):
        for text in RU_CORRECT:
            self.assert_screen(text, 'ru', 'ru')

    def test_english(self):
        for text in EN_CORRECT:
            self.assert_screen(text, 'us', 'us')


class TestUppercaseSkipped(_TypingChecks, unittest.TestCase):
    """ALL CAPS по умолчанию не переключается (аббревиатуры), с skip_uppercase=False — переключается."""

    def test_skipped_by_default(self):
        for text, intended, actual in [('ПРИВЕТ ', 'ru', 'us'), ('HELLO ', 'us', 'ru')]:
            with self.subTest(text=text):
                self.assertEqual(type_text(text, intended, actual), retype(text, intended, actual))

    def test_switched_when_enabled(self):
        config = Config(skip_uppercase=False)
        self.assert_screen('ПРИВЕТ ', 'ru', 'us', config)
        self.assert_screen('HELLO ', 'us', 'ru', config)


class TestAutoSwitchDisabled(_TypingChecks, unittest.TestCase):
    """При выключенном автопереключении текст остаётся как набран."""

    def test_wrong_layout_left_as_is(self):
        config = Config(auto_switch=False)
        for text in ['привет, ', 'hello! ']:
            intended = 'ru' if text[0] in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' else 'us'
            actual = 'us' if intended == 'ru' else 'ru'
            typed = retype(text, intended, actual)
            with self.subTest(text=text):
                self.assertEqual(type_text(text, intended, actual, config), typed)



class TestNumpad(unittest.TestCase):
    """Цифры и знаки с цифрового блока: не теряются, не режут слово, точка блока пересчитывается.

    Точка блока зависит от раскладки: '.' в us, ',' в ru. Цифры и / * - + одинаковы.
    """

    CASES = [
        # (что набрано, стартовая раскладка, ожидаемый экран)
        ([('ru', 'привет'), 'KEY_KP2', ('ru', ' ')], 'us', 'привет2 '),
        ([('us', 'version'), 'KEY_KP3', 'KEY_KPDOT', ('us', ' ')], 'ru', 'version3. '),
        ([('ru', 'привет'), 'KEY_KPDOT', ('ru', ' ')], 'us', 'привет, '),
        ([('ru', 'кто'), 'KEY_KPMINUS', ('ru', 'то ')], 'us', 'кто-то '),
        ([('us', 'hello '), 'KEY_KP1', 'KEY_KP0', 'KEY_KPSLASH', 'KEY_KP2', ('us', ' ')], 'ru', 'hello 10/2 '),
        # После переключения на ru точка блока даёт запятую — как и при ручном наборе в ru
        ([('ru', 'работа '), 'KEY_KP2', 'KEY_KPDOT', 'KEY_KP5', ('ru', ' часа ')], 'us', 'работа 2,5 часа '),
        ([('ru', 'привет'), 'KEY_KPENTER'], 'us', 'привет\n'),
        (['KEY_KP1', 'KEY_KP2', 'KEY_KP3', ('us', ' ')], 'us', '123 '),
        (['KEY_KP1', 'KEY_KP2', 'KEY_KP3', ('ru', ' ')], 'ru', '123 '),
        (['KEY_KP2', 'KEY_KPASTERISK', 'KEY_KP2', 'KEY_KPPLUS', 'KEY_KP1', ('us', ' ')], 'us', '2*2+1 '),
    ]

    def test_cases(self):
        for parts, start, expected in self.CASES:
            with self.subTest(parts=parts, start=start):
                screen, _ = type_keys(parts, start)
                self.assertEqual(screen, expected)

    def test_numlock_off_navigation_resets_word(self):
        # Без NumLock KP4 — стрелка влево: курсор ушёл, набранное слово больше не перед курсором
        _, daemon = type_keys([('ru', 'привет'), 'KEY_KP4'], 'us', numlock=False)
        self.assertEqual(daemon._word_tracker.get_current(), '')

    def test_numlock_off_no_switch_after_navigation(self):
        screen, _ = type_keys([('ru', 'привет'), 'KEY_KP4', ('ru', ' ')], 'us', numlock=False)
        self.assertEqual(screen, 'ghbdtn ')

    def test_shift_with_numlock_is_navigation(self):
        _, daemon = type_keys([('ru', 'привет'), ('KEY_KP4', True)], 'us')
        self.assertEqual(daemon._word_tracker.get_current(), '')

    def test_operators_independent_of_numlock(self):
        # / * - + на блоке не зависят от NumLock
        _, daemon = type_keys([('us', 'ab'), 'KEY_KPSLASH', 'KEY_KPMINUS'], 'us', numlock=False)
        self.assertEqual(daemon._word_tracker.get_current(), 'ab/-')

    def test_numlock_unknown_resets_word(self):
        # Устройство без leds() — состояние NumLock неизвестно, безопаснее сбросить слово
        _, daemon = type_keys([('ru', 'привет')], 'us')
        daemon._device = None
        daemon._process_event(_Event(ecodes.KEY_KP2, 1))
        self.assertEqual(daemon._word_tracker.get_current(), '')

if __name__ == '__main__':
    unittest.main()
