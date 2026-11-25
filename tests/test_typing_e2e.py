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
    'привет ',
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
    'hello ',
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



class TestSwitchOnPunctuation(_TypingChecks, unittest.TestCase):
    """Знак, который не буква ни в одной раскладке, переключает слово сразу, без пробела.

    Это нужно для последнего слова перед Enter: 'ghbdtn/' + Enter → 'привет.' + Enter.
    """

    RU_IN_US = [
        'привет,', 'привет.', 'привет!', 'привет?', 'привет:', 'привет;',
        '(привет)', '"привет"', 'привет...', 'кто-то,',
        'привет.\n', 'Привет, мир!\n', 'Как дела?\n',
    ]
    EN_IN_RU = [
        'hello!', 'hello?', 'hello)', '(hello)', 'hello!\n', 'Hello, world!\n',
    ]

    def test_russian(self):
        for text in self.RU_IN_US:
            self.assert_screen(text, 'ru', 'us')

    def test_english(self):
        for text in self.EN_IN_RU:
            self.assert_screen(text, 'us', 'ru')

    def test_mark_before_letters_joins_word(self):
        # '(' и '"' до первой буквы слово не завершают — иначе '"' не пересчиталась бы
        _, daemon = type_keys([('ru', '"(')], 'us')
        self.assertEqual(daemon._word_tracker.get_current(), '@(')

    def test_hyphen_and_digits_stay_in_word(self):
        _, daemon = type_keys([('ru', 'кто-то2')], 'us')
        self.assertEqual(daemon._word_tracker.get_current(), 'rnj-nj2')

    def test_letter_keys_do_not_end_word(self):
        # , . ; в английской раскладке — б ю ж в русской: 'hj,jn' — это 'робот'
        _, daemon = type_keys([('ru', 'робот')], 'us')
        self.assertEqual(daemon._word_tracker.get_current(), 'hj,jn')


class TestTabEnterDoNotSwitch(unittest.TestCase):
    """Tab и Enter завершают слово без переключения: текст остаётся как набран.

    Сколько символов вставит Tab (табуляция, пробелы до позиции, автодополнение)
    или что сделает Enter (перевод строки, отправка сообщения), зависит от приложения.
    """

    def test_word_left_as_typed(self):
        for text, intended, actual in [
            ('привет\n', 'ru', 'us'), ('привет\t', 'ru', 'us'),
            ('hello\n', 'us', 'ru'), ('hello\t', 'us', 'ru'),
        ]:
            with self.subTest(text=text):
                self.assertEqual(type_text(text, intended, actual), retype(text, intended, actual))

    def test_word_after_enter_switched_normally(self):
        self.assertEqual(type_text('ghbdtn\nghbdtn ', 'us', 'us'), 'ghbdtn\nпривет ')

    def test_word_ending_with_letter_key_before_enter_not_switched(self):
        # 'hello.' в русской раскладке — 'руддщю': 'ю' — буква, знака нет, Enter не переключает.
        # Известное ограничение: исправляется вручную (Pause) до нажатия Enter.
        self.assertEqual(type_text('hello.\n', 'us', 'ru'), 'руддщю\n')

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
        # Enter с блока, как и обычный, слово не переключает
        ([('ru', 'привет'), 'KEY_KPENTER'], 'us', 'ghbdtn\n'),
        ([('ru', 'привет'), 'KEY_KPSLASH', 'KEY_KPENTER'], 'us', 'привет/\n'),
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
        # / * - + на блоке не зависят от NumLock: печатаются, а не работают как навигация
        screen, daemon = type_keys([('us', 'ab'), 'KEY_KPMINUS'], 'us', numlock=False)
        self.assertEqual(daemon._word_tracker.get_current(), 'ab-')
        screen, _ = type_keys([('us', 'ab'), 'KEY_KPSLASH', 'KEY_KPASTERISK'], 'us', numlock=False)
        self.assertEqual(screen, 'ab/*')

    def test_numlock_unknown_resets_word(self):
        # Устройство без leds() — состояние NumLock неизвестно, безопаснее сбросить слово
        _, daemon = type_keys([('ru', 'привет')], 'us')
        daemon._device = None
        daemon._process_event(_Event(ecodes.KEY_KP2, 1))
        self.assertEqual(daemon._word_tracker.get_current(), '')

if __name__ == '__main__':
    unittest.main()
