"""Сквозные тесты на смешанный текст: русские и английские слова вперемешку, разный регистр.

Задуманная раскладка определяется по буквам (tests/screen_sim.intended_layouts).
Два сценария пользователя:
- забывает переключать: сам раскладку не трогает, исправляет только автопереключение —
  на экране должен оказаться ровно задуманный текст при любой стартовой раскладке;
- переключает сам: перед словом другого языка меняет раскладку — текст не должен
  измениться ни на символ (нет ложных срабатываний).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.config import Config
from tests.screen_sim import type_mixed

# Без слов короче 3 букв и без ALL CAPS — они вынесены в отдельные классы ниже
MIXED = [
    'Сегодня запускаю Python скрипт. ',
    'Открой браузер Firefox, потом зайди сюда. ',
    'Привет! Hello, world! Пока. ',
    'Пишем демон: PyQt6 плюс evdev. ',
    'Meeting tomorrow: обсудим проект, then lunch. ',
    'Компьютер Lenovo работает хорошо, keyboard тоже. ',
    'Отправь письмо через Gmail, пожалуйста! ',
    'Ошибка ImportError: модуль evdev недоступен. ',
    'Version 2: исправлены баги, добавлен tray. ',
    'The meeting прошла хорошо, thanks! ',
    'GitHub хранит код проекта. ',
    'Файл config.json лежит здесь. ',
    'Скажи "hello" ему (просто так). ',
    'Купил Samsung? Нет, Xiaomi. ',
]

# Короткие слова (меньше min_word_length) — по одному слову язык не определить
MIXED_SHORT_WORDS = [
    'Я использую Qt и Python. ',
    'Это не bug, а feature. ',
    'Работаю в Go уже давно. ',
    'Open the файл, please. ',
]

# ALL CAPS — аббревиатуры
MIXED_ALL_CAPS = [
    'Формат HTML удобен. ',
    'Новости США сегодня, NASA молчит. ',
    'Протокол HTTP поверх TCP работает. ',
]


class _MixedChecks:
    def check_forgets(self, texts: list[str], config: Config | None = None) -> None:
        for text in texts:
            for start in ('ru', 'us'):
                with self.subTest(text=text, start=start):
                    self.assertEqual(type_mixed(text, start, user_switches=False, config=config), text)

    def check_switches(self, texts: list[str], config: Config | None = None) -> None:
        for text in texts:
            for start in ('ru', 'us'):
                with self.subTest(text=text, start=start):
                    self.assertEqual(type_mixed(text, start, user_switches=True, config=config), text)


class TestMixedUserForgetsToSwitch(_MixedChecks, unittest.TestCase):

    def test_mixed(self):
        self.check_forgets(MIXED)

    def test_short_words(self):
        self.check_forgets(MIXED_SHORT_WORDS)

    def test_all_caps_when_enabled(self):
        self.check_forgets(MIXED_ALL_CAPS, Config(skip_uppercase=False))


class TestMixedUserSwitchesManually(_MixedChecks, unittest.TestCase):
    """Всё набрано правильно — автопереключение не должно ничего трогать."""

    def test_mixed(self):
        self.check_switches(MIXED)

    def test_short_words(self):
        self.check_switches(MIXED_SHORT_WORDS)

    def test_all_caps(self):
        self.check_switches(MIXED_ALL_CAPS)
        self.check_switches(MIXED_ALL_CAPS, Config(skip_uppercase=False))


class TestMixedAllCapsSkippedByDefault(unittest.TestCase):
    """С skip_uppercase=True аббревиатура в чужой раскладке остаётся как набрана."""

    def test_caps_word_left_as_typed(self):
        # HTML набран в русской раскладке → РЕЬД, раскладка не меняется, остальное верно
        self.assertEqual(type_mixed('Формат HTML удобен. ', 'ru', user_switches=False), 'Формат РЕЬД удобен. ')

    def test_caps_word_left_as_typed_en(self):
        # США набран в английской раскладке → CIF
        self.assertEqual(type_mixed('Visit США today. ', 'us', user_switches=False), 'Visit CIF today. ')


if __name__ == '__main__':
    unittest.main()
