"""Сквозные тесты слов-исключений: исключённое слово не переключается автоматически.

Слово-исключение задаётся так, как оно набирается (в текущей раскладке):
'ghbdtn' — набранное латиницей намеренно (ник, пароль, транслит), 'США' — правильное
слово, которое детектор ошибочно считает набранным не в той раскладке.
Знаки по краям не мешают: '(ghbdtn)' тоже исключение. Ручное переключение
горячей клавишей исключения не учитывает — пользователь просит явно.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.config import Config
from tests.screen_sim import type_keys, type_mixed, type_text


class TestExcludedWordNotSwitched(unittest.TestCase):

    def test_latin_word_kept(self):
        config = Config(excluded_words=['ghbdtn'])
        self.assertEqual(type_text('ghbdtn ', 'us', 'us', config), 'ghbdtn ')

    def test_cyrillic_word_kept(self):
        config = Config(excluded_words=['руддщ'])
        self.assertEqual(type_text('руддщ ', 'ru', 'ru', config), 'руддщ ')

    def test_kept_with_punctuation_around(self):
        config = Config(excluded_words=['ghbdtn'])
        for text in ['ghbdtn, ', 'ghbdtn. ', 'ghbdtn! ', '(ghbdtn) ', '"ghbdtn" ']:
            with self.subTest(text=text):
                self.assertEqual(type_text(text, 'us', 'us', config), text)

    def test_kept_at_end_of_line(self):
        config = Config(excluded_words=['ghbdtn'])
        self.assertEqual(type_text('ghbdtn\n', 'us', 'us', config), 'ghbdtn\n')

    def test_without_exclusion_switched(self):
        # Контроль: без исключения то же слово переключается
        self.assertEqual(type_text('ghbdtn ', 'us', 'us'), 'привет ')

    def test_correct_word_detector_would_spoil(self):
        # С skip_uppercase=False детектор портит аббревиатуру США → CIF; исключение её спасает
        spoiled = type_text('США ', 'ru', 'ru', Config(skip_uppercase=False))
        self.assertEqual(spoiled, 'CIF ')
        config = Config(skip_uppercase=False, excluded_words=['США'])
        self.assertEqual(type_text('США ', 'ru', 'ru', config), 'США ')


class TestExclusionScope(unittest.TestCase):

    def test_other_words_still_switched(self):
        config = Config(excluded_words=['ghbdtn'])
        screen, _ = type_keys([('us', 'ghbdtn '), ('ru', 'тест ')], 'us', config=config)
        self.assertEqual(screen, 'ghbdtn тест ')

    def test_longer_word_containing_exclusion_switched(self):
        # 'ghbdtnbr' — 'приветик'; исключено только слово целиком
        config = Config(excluded_words=['ghbdtn'])
        self.assertEqual(type_text('ghbdtnbr ', 'us', 'us', config), 'приветик ')

    def test_several_exclusions(self):
        config = Config(excluded_words=['ghbdtn', 'руддщ'])
        self.assertEqual(type_text('ghbdtn ', 'us', 'us', config), 'ghbdtn ')
        self.assertEqual(type_text('руддщ ', 'ru', 'ru', config), 'руддщ ')

    def test_exclusion_inside_mixed_text(self):
        # Слова вокруг исключения исправляются как обычно
        config = Config(excluded_words=['evdev'])
        text = 'Пишем демон: PyQt6 плюс evdev. '
        self.assertEqual(type_mixed(text, 'ru', user_switches=False, config=config), text)

    def test_exclusion_added_at_runtime(self):
        # Детектор держит ссылку на Config — изменение подхватывается без перезапуска
        config = Config()
        _, daemon = type_keys([], 'us', config=config)
        config.excluded_words.append('ghbdtn')
        self.assertFalse(daemon._detector.should_switch('ghbdtn', daemon._en, daemon._ru))


class TestManualSwitchIgnoresExclusions(unittest.TestCase):

    def test_hotkey_switches_excluded_word(self):
        config = Config(excluded_words=['ghbdtn'])
        screen, _ = type_keys([('us', 'ghbdtn'), 'KEY_PAUSE'], 'us', config=config)
        self.assertEqual(screen, 'привет')


if __name__ == '__main__':
    unittest.main()
