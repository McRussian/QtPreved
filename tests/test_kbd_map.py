from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.kbd_map import Layout, load_default_layouts, load_layout

EN_LOWER_CHARS = list('qwertyuiopasdfghjklzxcvbnm')
EN_UPPER_CHARS = list('QWERTYUIOPASDFGHJKLZXCVBNM')
RU_LOWER_CHARS = list('йцукенгшщзфывапролдячсмитьбю')
RU_UPPER_CHARS = list('ЙЦУКЕНГШЩЗФЫВАПРОЛДЯЧСМИТЬБЮ')


class TestLoadLayout(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_en_name(self):
        self.assertEqual(self.en.name, 'en')

    def test_en_xkb_name(self):
        self.assertEqual(self.en.xkb_name, 'us')

    def test_ru_name(self):
        self.assertEqual(self.ru.name, 'ru')

    def test_ru_xkb_name(self):
        self.assertEqual(self.ru.xkb_name, 'ru')

    def test_en_lower_contains_all_letters(self):
        chars = set(self.en.lower.values())
        for ch in EN_LOWER_CHARS:
            self.assertIn(ch, chars)

    def test_ru_lower_contains_all_letters(self):
        chars = set(self.ru.lower.values())
        for ch in RU_LOWER_CHARS:
            self.assertIn(ch, chars)

    def test_load_nonexistent_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_layout(Path('/nonexistent/layout.json'))

    def test_load_invalid_json_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
            f.write('not valid json{{{')
            tmp = Path(f.name)
        try:
            with self.assertRaises(json.JSONDecodeError):
                load_layout(tmp)
        finally:
            tmp.unlink()

    def test_load_missing_key_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False, encoding='utf-8') as f:
            json.dump({'name': 'en', 'lower': {}}, f)
            tmp = Path(f.name)
        try:
            with self.assertRaises(KeyError):
                load_layout(tmp)
        finally:
            tmp.unlink()


class TestRemapText(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_ghbdtn_to_privet(self):
        self.assertEqual(self.en.remap_to('ghbdtn', self.ru), 'привет')

    def test_privet_to_ghbdtn(self):
        self.assertEqual(self.ru.remap_to('привет', self.en), 'ghbdtn')

    def test_empty_string(self):
        self.assertEqual(self.en.remap_to('', self.ru), '')

    def test_space_preserved(self):
        result = self.en.remap_to('a b', self.ru)
        self.assertEqual(result[1], ' ')

    def test_digit_preserved(self):
        result = self.en.remap_to('a1b', self.ru)
        self.assertEqual(result[1], '1')

    def test_unknown_char_preserved(self):
        result = self.en.remap_to('a!b', self.ru)
        self.assertEqual(result[1], '!')

    def test_uppercase_first_char(self):
        result = self.en.remap_to('Hello', self.ru)
        self.assertEqual(result[0], 'Р')

    def test_uppercase_rest_is_lowercase(self):
        result = self.en.remap_to('Hello', self.ru)
        self.assertTrue(result[1:].islower())

    def test_all_uppercase_stays_uppercase(self):
        result = self.en.remap_to('HELLO', self.ru)
        self.assertTrue(all(c.isupper() for c in result))

    def test_remap_to_same_layout_is_identity(self):
        self.assertEqual(self.en.remap_to('hello world', self.en), 'hello world')

    def test_remap_special_chars_en_to_ru(self):
        self.assertEqual(self.en.remap_to('[', self.ru), 'х')
        self.assertEqual(self.en.remap_to(']', self.ru), 'ъ')
        self.assertEqual(self.en.remap_to(';', self.ru), 'ж')
        self.assertEqual(self.en.remap_to("'", self.ru), 'э')
        self.assertEqual(self.en.remap_to(',', self.ru), 'б')
        self.assertEqual(self.en.remap_to('.', self.ru), 'ю')


class TestLayoutWithEmptyChars(unittest.TestCase):

    def test_empty_char_in_lower_is_skipped(self):
        layout = Layout('test', 'test', {16: '', 17: 'w'}, {16: 'W', 17: 'W'})
        self.assertNotIn('', layout._char_to_key)
        self.assertIn('w', layout._char_to_key)

    def test_empty_char_in_upper_is_skipped(self):
        layout = Layout('test', 'test', {16: 'q'}, {16: '', 17: 'W'})
        self.assertNotIn('', layout._char_to_key)
        self.assertIn('W', layout._char_to_key)


class TestRemapRoundtrip(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    @given(st.text(alphabet=EN_LOWER_CHARS, min_size=0, max_size=50))
    def test_roundtrip_en_lower(self, text):
        self.assertEqual(self.ru.remap_to(self.en.remap_to(text, self.ru), self.en), text)

    @given(st.text(alphabet=EN_UPPER_CHARS, min_size=0, max_size=50))
    def test_roundtrip_en_upper(self, text):
        self.assertEqual(self.ru.remap_to(self.en.remap_to(text, self.ru), self.en), text)

    @given(st.text(alphabet=RU_LOWER_CHARS, min_size=0, max_size=50))
    def test_roundtrip_ru_lower(self, text):
        self.assertEqual(self.en.remap_to(self.ru.remap_to(text, self.en), self.ru), text)

    @given(st.text(alphabet=RU_UPPER_CHARS, min_size=0, max_size=50))
    def test_roundtrip_ru_upper(self, text):
        self.assertEqual(self.en.remap_to(self.ru.remap_to(text, self.en), self.ru), text)

    @given(st.text(alphabet=EN_LOWER_CHARS + EN_UPPER_CHARS, min_size=0, max_size=50))
    def test_remap_to_same_layout_is_always_identity(self, text):
        self.assertEqual(self.en.remap_to(text, self.en), text)


if __name__ == '__main__':
    unittest.main()
