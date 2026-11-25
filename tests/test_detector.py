from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch

from qtpreved.config import Config
from qtpreved.detector import (
    EN_MODEL, MODELS, RU_MODEL, Detector, TrigramModel, _score_cached, load_trigrams, score_text,
    should_switch, strip_common_edges,
)
from qtpreved.kbd_map import Layout, load_default_layouts



class TestLoadTrigrams(unittest.TestCase):

    def test_tables_cover_languages(self):
        self.assertEqual(set(MODELS), {'en', 'ru'})

    def test_load_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_trigrams(Path('/nonexistent/trigrams.json'))

    def test_load_invalid_json_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
            f.write('not valid json{{{')
            tmp = Path(f.name)
        try:
            with self.assertRaises(json.JSONDecodeError):
                load_trigrams(tmp)
        finally:
            tmp.unlink()


class TestTrigramModel(unittest.TestCase):
    """Модель на маленькой таблице: проверяются свойства, а не конкретные числа."""

    def setUp(self):
        # Корпус из одного слова 'ab' (×10): '  a', ' ab', 'ab '
        self.model = TrigramModel({'  a': 10, ' ab': 10, 'ab ': 10})

    def test_score_is_logprob(self):
        self.assertLessEqual(self.model.score('ab'), 0.0)

    def test_known_word_better_than_unknown(self):
        self.assertGreater(self.model.score('ab'), self.model.score('ba'))

    def test_unknown_char_heavily_penalized(self):
        # 'z' нет в корпусе вообще, 'a' есть — хотя тройка 'aa' тоже неизвестна
        self.assertLess(self.model.score('az'), self.model.score('aa'))

    def test_empty_text_minus_infinity(self):
        self.assertEqual(self.model.score(''), -math.inf)

    def test_punctuation_only_minus_infinity(self):
        self.assertEqual(self.model.score('?!'), -math.inf)

    def test_case_insensitive(self):
        self.assertEqual(self.model.score('AB'), self.model.score('ab'))

    def test_logprob_counts_boundary(self):
        # 'ab' → '  ab ': три предсказываемых символа (a, b, конец слова)
        total, count = self.model.logprob('ab')
        self.assertEqual(count, 3)
        self.assertLess(total, 0.0)

    def test_common_edge_punctuation_cheap(self):
        self.assertGreater(self.model.score('ab,'), self.model.score('ab['))

    def test_edge_punctuation_lowers_score_less_than_unknown_letter(self):
        self.assertGreater(self.model.score('ab.'), self.model.score('abz'))

    def test_rare_context_damped(self):
        # Контекст 'xx' встречен 5 раз, из них 2 раза дальше 'x': без затухания
        # p('x' | 'xx') было бы 0.6 · 2/5 = 0.24
        model = TrigramModel({'  a': 1000, ' ab': 1000, 'ab ': 1000, ' xx': 3, 'xx ': 3, 'xxx': 2})
        self.assertLess(model._char_prob('x', 'x', 'x'), 0.6 * 2 / 5 / 2)

    def test_frequent_context_keeps_full_weight(self):
        # Частый контекст: веса триграммы и биграммы полные (0.6 + 0.3), p3 = p2 = 1
        model = TrigramModel({'  a': 100000, ' ab': 100000, 'ab ': 100000})
        self.assertAlmostEqual(model._char_prob(' ', 'a', 'b'), 0.9, places=3)


class TestScoreCached(unittest.TestCase):

    def test_matches_score_text(self):
        self.assertAlmostEqual(_score_cached('hello', 'en'), score_text('hello', EN_MODEL))

    def test_empty_string_minus_infinity(self):
        self.assertEqual(_score_cached('', 'en'), -math.inf)

    def test_unknown_layout_minus_infinity(self):
        self.assertEqual(_score_cached('hello', 'xx'), -math.inf)

    def test_cache_hit_same_result(self):
        self.assertEqual(_score_cached('привет', 'ru'), _score_cached('привет', 'ru'))

    def test_min_length_one_single_letter_not_switched(self):
        en, ru = load_default_layouts()
        self.assertFalse(should_switch('a', en, ru, min_length=1))


class TestScoreText(unittest.TestCase):

    def test_uppercase_same_as_lowercase(self):
        self.assertAlmostEqual(score_text('привет', RU_MODEL), score_text('ПРИВЕТ', RU_MODEL))

    def test_russian_word_prefers_russian_model(self):
        self.assertGreater(score_text('привет', RU_MODEL), score_text('привет', EN_MODEL) + 3)

    def test_english_word_prefers_english_model(self):
        self.assertGreater(score_text('hello', EN_MODEL), score_text('hello', RU_MODEL) + 3)

    def test_wrong_layout_text_scores_low(self):
        self.assertLess(score_text('ghbdtn', EN_MODEL), score_text('привет', RU_MODEL))

    def test_apostrophe_inside_english_word(self):
        self.assertGreater(score_text("don't", EN_MODEL), score_text('вщтэе', RU_MODEL))

    @given(st.text())
    def test_score_never_positive(self, text):
        self.assertLessEqual(score_text(text, EN_MODEL), 0.0)

    @given(st.text(alphabet='абвгдежзийклмнопрстуфхцчшщъыьэюя', min_size=1, max_size=20))
    def test_score_finite_for_letters(self, text):
        self.assertTrue(math.isfinite(score_text(text, RU_MODEL)))


class TestStripCommonEdges(unittest.TestCase):

    def test_shared_punctuation_removed(self):
        # '(' и '?'/',' — не буквы в обоих вариантах
        self.assertEqual(strip_common_edges('(ghbdtn?', '(привет,'), ('ghbdtn', 'привет'))

    def test_letter_in_other_variant_kept(self):
        # '[' и ',' — буквы х и б в русском варианте
        self.assertEqual(strip_common_edges('[kt,', 'хлеб'), ('[kt,', 'хлеб'))

    def test_digits_removed(self):
        self.assertEqual(strip_common_edges('hf,jnf2', 'работа2'), ('hf,jnf', 'работа'))

    def test_no_letters(self):
        self.assertEqual(strip_common_edges('123', '123'), ('', ''))


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

    def test_margin_blocks_ambiguous_word(self):
        # Слово 'store': хорошо читается по-английски, при ремапе даёт 'ыещку' (низкий RU-счёт)
        self.assertFalse(should_switch('store', self.en, self.ru, margin=0.25))

    def test_huge_margin_prevents_switch(self):
        self.assertFalse(should_switch('ghbdtn', self.en, self.ru, margin=999.0))

    def test_high_min_alt_logprob_prevents_switch(self):
        self.assertFalse(should_switch('ghbdtn', self.en, self.ru, min_alt_logprob=0.0))

    def test_wrong_layout_ru_to_en(self):
        self.assertTrue(should_switch('руддщ', self.ru, self.en))

    def test_letters_on_punctuation_keys(self):
        # 'хлеб' и 'ещё', набранные в английской раскладке
        self.assertTrue(should_switch('[kt,', self.en, self.ru))
        self.assertTrue(should_switch('to`', self.en, self.ru))

    def test_correct_words_with_punctuation_keys_not_switched(self):
        self.assertFalse(should_switch('ещё', self.ru, self.en))
        self.assertFalse(should_switch('хлеб', self.ru, self.en))
        self.assertFalse(should_switch('Hello,', self.en, self.ru))

    def test_previous_false_positive_kupil(self):
        self.assertFalse(should_switch('Купил', self.ru, self.en))

    # --- Неизвестная раскладка (нет биграмм) ---

    def test_unknown_layout_name_does_not_crash(self):
        # Раскладка с неизвестным именем: current_bigrams пустые (счёт=0),
        # но alt_score может быть высоким — переключение возможно, не падаем
        unknown = Layout('xx', 'xx', self.en.lower, self.en.upper)
        result = should_switch('ghbdtn', unknown, self.ru)
        self.assertIsInstance(result, bool)


class TestDetectorClass(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def _make(self, **kwargs) -> Detector:
        return Detector(Config(**kwargs))

    # --- Основные сценарии ---

    def test_wrong_layout_returns_true(self):
        d = self._make()
        self.assertTrue(d.should_switch('ghbdtn', self.en, self.ru))

    def test_correct_layout_returns_false(self):
        d = self._make()
        self.assertFalse(d.should_switch('hello', self.en, self.ru))

    # --- Excluded words ---

    def test_excluded_word_returns_false(self):
        d = self._make(excluded_words=['ghbdtn'])
        self.assertFalse(d.should_switch('ghbdtn', self.en, self.ru))

    def test_excluded_word_case_insensitive(self):
        d = self._make(excluded_words=['ghbdtn'], skip_uppercase=False)
        for word in ['Ghbdtn', 'GHBDTN', 'gHbDtN']:
            with self.subTest(word=word):
                self.assertFalse(d.should_switch(word, self.en, self.ru))

    def test_excluded_word_in_list_with_capitals(self):
        d = self._make(excluded_words=['Ghbdtn'])
        self.assertFalse(d.should_switch('ghbdtn', self.en, self.ru))

    def test_excluded_cyrillic_case_insensitive(self):
        d = self._make(excluded_words=['руддщ'])
        self.assertFalse(d.should_switch('Руддщ', self.ru, self.en))

    def test_excluded_case_insensitive_with_punctuation(self):
        d = self._make(excluded_words=['ghbdtn'])
        self.assertFalse(d.should_switch('Ghbdtn,', self.en, self.ru))

    def test_empty_excluded_words_no_effect(self):
        d = self._make(excluded_words=[])
        self.assertTrue(d.should_switch('ghbdtn', self.en, self.ru))

    def test_excluded_words_do_not_affect_others(self):
        d = self._make(excluded_words=['hello'])
        self.assertTrue(d.should_switch('ghbdtn', self.en, self.ru))

    def test_multiple_excluded_words(self):
        d = self._make(excluded_words=['ghbdtn', 'world'])
        self.assertFalse(d.should_switch('ghbdtn', self.en, self.ru))
        self.assertFalse(d.should_switch('world', self.en, self.ru))

    # --- Параметры из конфига ---

    def test_min_word_length_respected(self):
        d = self._make(min_word_length=10)
        self.assertFalse(d.should_switch('ghbdtn', self.en, self.ru))

    def test_skip_uppercase_respected(self):
        d = self._make(skip_uppercase=True)
        self.assertFalse(d.should_switch('GHBDTN', self.en, self.ru))

    def test_skip_uppercase_false_analyzes_caps(self):
        d = self._make(skip_uppercase=False)
        self.assertTrue(d.should_switch('GHBDTN', self.en, self.ru))

    def test_high_min_alt_logprob_prevents_switch(self):
        d = self._make(min_alt_logprob=0.0)
        self.assertFalse(d.should_switch('ghbdtn', self.en, self.ru))

    def test_detection_margin_passed_to_function(self):
        # Проверяем напрямую, что параметр передаётся в модульную функцию.
        with patch('qtpreved.detector.should_switch', return_value=False) as mock_fn:
            d = self._make(detection_margin=7.5)
            d.should_switch('ghbdtn', self.en, self.ru)
            self.assertEqual(mock_fn.call_args[1]['margin'], 7.5)

    # --- Config обновляется динамически ---

    def test_config_change_reflected_immediately(self):
        config = Config()
        d = Detector(config)
        self.assertTrue(d.should_switch('ghbdtn', self.en, self.ru))
        config.excluded_words.append('ghbdtn')
        self.assertFalse(d.should_switch('ghbdtn', self.en, self.ru))



class TestShouldSwitchRemapped(unittest.TestCase):
    """Готовый remapped используется вместо remap_to, знаки по краям не мешают."""

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_remapped_overrides_remap(self):
        # 'hello' с подсунутым русским вариантом 'привет' — сравниваются именно они
        self.assertTrue(should_switch('xqzw', self.en, self.ru, remapped='привет'))

    def test_remapped_garbage_prevents_switch(self):
        self.assertFalse(should_switch('ghbdtn', self.en, self.ru, remapped='ъъъъъъ'))

    def test_punctuation_around_word_ignored(self):
        self.assertTrue(should_switch('(ghbdtn?', self.en, self.ru))

    def test_no_letters_in_current_layout_not_switched(self):
        # '...' в английской раскладке — 'ююю' в русской
        en, ru = load_default_layouts()
        self.assertFalse(should_switch('...', en, ru))

    def test_only_punctuation_not_switched(self):
        self.assertFalse(should_switch('?!...', self.en, self.ru))

    def test_detector_passes_remapped(self):
        d = Detector(Config())
        self.assertTrue(d.should_switch('xqzw', self.en, self.ru, remapped='привет'))

    def test_excluded_word_with_punctuation(self):
        d = Detector(Config(excluded_words=['ghbdtn']))
        self.assertFalse(d.should_switch('ghbdtn?', self.en, self.ru))

if __name__ == '__main__':
    unittest.main()
