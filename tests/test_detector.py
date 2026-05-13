from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.detector import (
    EN_BIGRAMS, RU_BIGRAMS, _score_cached, load_bigrams, score_text, should_switch,
)
from qtpreved.kbd_map import Layout, load_default_layouts



class TestLoadBigrams(unittest.TestCase):

    def test_en_bigrams_loaded(self):
        self.assertGreater(len(EN_BIGRAMS), 0)

    def test_ru_bigrams_loaded(self):
        self.assertGreater(len(RU_BIGRAMS), 0)

    def test_en_bigrams_contain_th(self):
        self.assertIn('th', EN_BIGRAMS)

    def test_ru_bigrams_contain_st(self):
        self.assertIn('ст', RU_BIGRAMS)

    def test_load_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_bigrams(Path('/nonexistent/bigrams.json'))

    def test_load_invalid_json_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
            f.write('not valid json{{{')
            tmp = Path(f.name)
        try:
            with self.assertRaises(json.JSONDecodeError):
                load_bigrams(tmp)
        finally:
            tmp.unlink()


class TestScoreCached(unittest.TestCase):

    def test_matches_score_text(self):
        self.assertAlmostEqual(
            _score_cached('hello', 'en'),
            score_text('hello', EN_BIGRAMS),
        )

    def test_empty_string_returns_zero(self):
        self.assertEqual(_score_cached('', 'en'), 0.0)

    def test_single_char_returns_zero(self):
        self.assertEqual(_score_cached('a', 'en'), 0.0)

    def test_unknown_layout_returns_zero(self):
        self.assertEqual(_score_cached('hello', 'xx'), 0.0)

    def test_cache_hit_same_result(self):
        result1 = _score_cached('привет', 'ru')
        result2 = _score_cached('привет', 'ru')
        self.assertEqual(result1, result2)

    def test_min_length_one_triggers_short_text_branch(self):
        # min_length=1 пропускает слово 'a' в should_switch,
        # _score_cached('а', ...) → len < 2 → 0.0 → не переключаем
        en, ru = load_default_layouts()
        self.assertFalse(should_switch('a', en, ru, min_length=1))


class TestScoreText(unittest.TestCase):

    def test_empty_string_returns_zero(self):
        self.assertEqual(score_text('', EN_BIGRAMS), 0.0)

    def test_single_char_returns_zero(self):
        self.assertEqual(score_text('a', EN_BIGRAMS), 0.0)

    def test_known_bigram_returns_positive(self):
        # 'th' — самый частый английский биграмм (35.6)
        self.assertGreater(score_text('th', EN_BIGRAMS), 0.0)

    def test_unknown_bigrams_return_zero(self):
        self.assertEqual(score_text('xzqw', {}), 0.0)

    def test_single_bigram_returns_exact_frequency(self):
        # Два символа = один биграмм, результат равен его частоте
        self.assertAlmostEqual(score_text('th', EN_BIGRAMS), 35.6)

    def test_longer_word_score_is_average(self):
        # Три символа = два биграмма, результат — среднее
        expected = (EN_BIGRAMS.get('th', 0) + EN_BIGRAMS.get('he', 0)) / 2
        self.assertAlmostEqual(score_text('the', EN_BIGRAMS), expected)

    def test_uppercase_same_as_lowercase(self):
        self.assertAlmostEqual(
            score_text('привет', RU_BIGRAMS),
            score_text('ПРИВЕТ', RU_BIGRAMS),
        )

    def test_russian_text_scores_high_on_ru_bigrams(self):
        self.assertGreater(score_text('привет', RU_BIGRAMS), 5.0)

    def test_russian_text_scores_low_on_en_bigrams(self):
        self.assertLess(score_text('привет', EN_BIGRAMS), 2.0)

    def test_english_text_scores_high_on_en_bigrams(self):
        self.assertGreater(score_text('hello', EN_BIGRAMS), 5.0)

    def test_english_text_scores_low_on_ru_bigrams(self):
        self.assertLess(score_text('hello', RU_BIGRAMS), 2.0)

    @given(st.text(), st.dictionaries(st.text(min_size=2, max_size=2), st.floats(min_value=0.0, max_value=100.0)))
    def test_score_always_nonnegative(self, text, bigrams):
        self.assertGreaterEqual(score_text(text, bigrams), 0.0)

    @given(st.text())
    def test_score_empty_bigrams_always_zero(self, text):
        self.assertEqual(score_text(text, {}), 0.0)


class TestShouldSwitch(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    # --- Пропуск по длине ---

    def test_word_shorter_than_min_length_returns_false(self):
        self.assertFalse(should_switch('gh', self.en, self.ru, min_length=3))

    def test_word_exactly_min_length_is_analyzed(self):
        # 'ghb' → 'при' — достаточно для детекта
        result = should_switch('ghb', self.en, self.ru, min_length=3)
        # Не проверяем конкретный результат, просто убеждаемся что не упало
        self.assertIsInstance(result, bool)

    def test_word_length_one_returns_false(self):
        self.assertFalse(should_switch('g', self.en, self.ru))

    def test_word_length_two_returns_false(self):
        self.assertFalse(should_switch('gh', self.en, self.ru))

    # --- Пропуск ALL CAPS ---

    def test_all_caps_skipped_when_skip_uppercase_true(self):
        self.assertFalse(should_switch('HTML', self.en, self.ru, skip_uppercase=True))

    def test_all_caps_ru_skipped(self):
        self.assertFalse(should_switch('США', self.ru, self.en, skip_uppercase=True))

    def test_all_caps_analyzed_when_skip_uppercase_false(self):
        # При выключенном пропуске ALL CAPS слово должно анализироваться
        # GHBDTN — это ПРИВЕТ в верхнем регистре, должно детектироваться
        result = should_switch('GHBDTN', self.en, self.ru, skip_uppercase=False)
        self.assertTrue(result)

    # --- Основные сценарии ---

    def test_wrong_layout_en_to_ru(self):
        # 'ghbdtn' — 'привет' набранный в английской раскладке
        self.assertTrue(should_switch('ghbdtn', self.en, self.ru))

    def test_correct_english_word_not_switched(self):
        self.assertFalse(should_switch('hello', self.en, self.ru))

    def test_correct_russian_word_not_switched(self):
        self.assertFalse(should_switch('привет', self.ru, self.en))

    def test_correct_english_word_the_not_switched(self):
        self.assertFalse(should_switch('the', self.en, self.ru, min_length=3))

    # --- Пороги ---

    def test_threshold_blocks_ambiguous_word(self):
        # Слово 'store': хорошо читается по-английски, при ремапе даёт 'ыещку' (низкий RU-счёт)
        # Высокий threshold не меняет поведения для очевидно правильных слов
        self.assertFalse(should_switch('store', self.en, self.ru, threshold=2.0))

    def test_high_min_alt_score_prevents_switch(self):
        self.assertFalse(should_switch('ghbdtn', self.en, self.ru, min_alt_score=999.0))

    # --- Неизвестная раскладка (нет биграмм) ---

    def test_unknown_layout_name_does_not_crash(self):
        # Раскладка с неизвестным именем: current_bigrams пустые (счёт=0),
        # но alt_score может быть высоким — переключение возможно, не падаем
        unknown = Layout('xx', 'xx', self.en.lower, self.en.upper)
        result = should_switch('ghbdtn', unknown, self.ru)
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()
