"""Качество детектора на корпусе слов в обе стороны (RU→EN, EN→RU), включая опечатки.

Набор в чужой раскладке строится по полным xkb-картам (tests/screen_sim.py),
а не через Layout.remap_to — чтобы тест не наследовал пробелы JSON-раскладок.

Чистые слова проверяются поштучно. Для опечаток требуется доля распознанных
не ниже порога: часть искажённых слов честно неотличима от мусора.
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.config import Config
from qtpreved.detector import Detector
from qtpreved.kbd_map import load_default_layouts
from tests.screen_sim import retype

RU_WORDS = """
привет работа человек программа сегодня спасибо хорошо компьютер клавиатура раскладка
время деньги вопрос ответ машина дорога город страна письмо документ проект задача
система пользователь настройки файл папка окно сообщение телефон интернет новости
быстро медленно красивый большой маленький новый старый первый последний можно нужно
делать говорить думать знать хотеть видеть писать читать понимать работать
будет было объект подъезд жизнь уже тоже между здесь сейчас хлеб экран этот неделю
люблю каждый ещё всё что как для так или они
""".split()

EN_WORDS = """
hello world computer keyboard layout program system window message settings
people because should through between important without another example question
answer number problem service project develop function variable return string
quickly beautiful interesting language different children morning evening family
think know want write read understand create delete update support release
the and you that with have this from they will would there their what about which
when make like time just your good some could them other than then look only come
over also back after work first well even because these give most
""".split()

# Порог доли распознанных слов для вариантов с опечатками
TYPO_DETECTION_RATE = 0.9
# Максимальная доля ложных срабатываний на правильно набранных словах с опечатками
TYPO_FALSE_POSITIVE_RATE = 0.02


def transpose(word: str, rnd: random.Random) -> str:
    """Переставить две соседние буквы."""
    i = rnd.randrange(len(word) - 1)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def drop(word: str, rnd: random.Random) -> str:
    """Пропустить одну букву (кроме первой)."""
    i = rnd.randrange(1, len(word))
    return word[:i] + word[i + 1:]


def double(word: str, rnd: random.Random) -> str:
    """Удвоить одну букву."""
    i = rnd.randrange(len(word))
    return word[:i] + word[i] + word[i:]


TYPOS = {'transpose': transpose, 'drop': drop, 'double': double}


def typo_variants(words: list[str], kind: str) -> list[str]:
    """Детерминированно испортить слова длиной от 4 букв (seed — само слово)."""
    func = TYPOS[kind]
    return [func(w, random.Random(f'{kind}:{w}')) for w in words if len(w) >= 4]


class CorpusChecks:
    """Общая логика: home — язык слов, typed_in — раскладка, в которой их ошибочно набрали."""

    words: list[str] = []
    home_xkb = ''
    other_xkb = ''

    @classmethod
    def setUpClass(cls) -> None:
        en, ru = load_default_layouts()
        by_xkb = {en.xkb_name: en, ru.xkb_name: ru}
        cls.home = by_xkb[cls.home_xkb]
        cls.other = by_xkb[cls.other_xkb]
        cls.detector = Detector(Config())

    def detected_wrong(self, word: str) -> bool:
        """Слово набрано в чужой раскладке — детектор должен предложить переключение."""
        typed = retype(word, self.home_xkb, self.other_xkb)
        return self.detector.should_switch(typed, self.other, self.home)

    def switched_correct(self, word: str) -> bool:
        """Слово набрано правильно — детектор не должен переключать."""
        return self.detector.should_switch(word, self.home, self.other)

    def _check_rate(self, variants: list[str], predicate, min_rate: float) -> None:
        misses = [v for v in variants if not predicate(v)]
        rate = 1 - len(misses) / len(variants)
        self.assertGreaterEqual(
            rate, min_rate, f'{rate:.0%} < {min_rate:.0%}, промахи: {misses}',
        )

    # --- Чистые слова ---

    def test_clean_words_detected(self):
        for word in self.words:
            with self.subTest(word=word, typed=retype(word, self.home_xkb, self.other_xkb)):
                self.assertTrue(self.detected_wrong(word))

    def test_capitalized_words_detected(self):
        for word in self.words:
            cap = word.capitalize()
            with self.subTest(word=cap, typed=retype(cap, self.home_xkb, self.other_xkb)):
                self.assertTrue(self.detected_wrong(cap))

    def test_correct_words_not_switched(self):
        for word in self.words:
            with self.subTest(word=word):
                self.assertFalse(self.switched_correct(word))

    # --- Опечатки: набрано в чужой раскладке ---

    def test_transposed_detected(self):
        self._check_rate(typo_variants(self.words, 'transpose'), self.detected_wrong, TYPO_DETECTION_RATE)

    def test_dropped_letter_detected(self):
        self._check_rate(typo_variants(self.words, 'drop'), self.detected_wrong, TYPO_DETECTION_RATE)

    def test_doubled_letter_detected(self):
        self._check_rate(typo_variants(self.words, 'double'), self.detected_wrong, TYPO_DETECTION_RATE)

    # --- Опечатки: набрано правильно, переключать нельзя ---

    def test_typos_in_correct_layout_not_switched(self):
        variants = [v for kind in TYPOS for v in typo_variants(self.words, kind)]
        self._check_rate(
            variants, lambda v: not self.switched_correct(v), 1 - TYPO_FALSE_POSITIVE_RATE,
        )


class TestRussianTypedInEnglish(CorpusChecks, unittest.TestCase):
    words = RU_WORDS
    home_xkb = 'ru'
    other_xkb = 'us'


class TestEnglishTypedInRussian(CorpusChecks, unittest.TestCase):
    words = EN_WORDS
    home_xkb = 'us'
    other_xkb = 'ru'


if __name__ == '__main__':
    unittest.main()
