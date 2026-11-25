from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.word_tracker import STOP_CHARS, WordTracker


class TestStopChars(unittest.TestCase):

    def test_space_is_stop(self):
        self.assertIn(' ', STOP_CHARS)

    def test_enter_is_stop(self):
        self.assertIn('\n', STOP_CHARS)

    def test_tab_is_stop(self):
        self.assertIn('\t', STOP_CHARS)

    def test_punctuation_are_not_stops(self):
        for ch in '.,!?;:-()[]{}\"':
            with self.subTest(ch=ch):
                self.assertNotIn(ch, STOP_CHARS)

    def test_apostrophe_is_not_stop(self):
        self.assertNotIn("'", STOP_CHARS)

    def test_underscore_is_not_stop(self):
        self.assertNotIn('_', STOP_CHARS)

    def test_at_is_not_stop(self):
        self.assertNotIn('@', STOP_CHARS)

    def test_slash_is_not_stop(self):
        self.assertNotIn('/', STOP_CHARS)

    def test_backslash_is_not_stop(self):
        self.assertNotIn('\\', STOP_CHARS)


class TestWordTrackerBuffer(unittest.TestCase):

    def setUp(self):
        self.tracker = WordTracker()

    def test_initial_buffer_empty(self):
        self.assertEqual(self.tracker.get_current(), '')

    def test_add_char_accumulates(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.assertEqual(self.tracker.get_current(), 'hello')

    def test_add_multiple_chars(self):
        self.tracker.add_char('п')
        self.tracker.add_char('р')
        self.tracker.add_char('и')
        self.assertEqual(self.tracker.get_current(), 'при')

    def test_add_non_stop_chars_preserved(self):
        for ch in "don't":
            self.tracker.add_char(ch)
        self.assertEqual(self.tracker.get_current(), "don't")


class TestWordTrackerStopChar(unittest.TestCase):

    def setUp(self):
        self.tracker = WordTracker()

    def test_stop_returns_word(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        word = self.tracker.on_stop_char(' ')
        self.assertEqual(word, 'hello')

    def test_stop_resets_buffer(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.tracker.on_stop_char(' ')
        self.assertEqual(self.tracker.get_current(), '')

    def test_stop_on_empty_buffer_returns_none(self):
        self.assertIsNone(self.tracker.on_stop_char(' '))

    def test_consecutive_stops_return_none_after_first(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.tracker.on_stop_char(' ')
        self.assertIsNone(self.tracker.on_stop_char(' '))
        self.assertIsNone(self.tracker.on_stop_char('.'))

    def test_stop_char_type_does_not_affect_result(self):
        for ch in 'test':
            self.tracker.add_char(ch)
        word = self.tracker.on_stop_char('.')
        self.assertEqual(word, 'test')


class TestWordTrackerBackspace(unittest.TestCase):

    def setUp(self):
        self.tracker = WordTracker()

    def test_backspace_removes_last_char(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_current(), 'hell')

    def test_backspace_on_single_char_empties_buffer(self):
        self.tracker.add_char('a')
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_current(), '')

    def test_backspace_on_empty_buffer_does_not_crash(self):
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_current(), '')

    def test_multiple_backspaces(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.tracker.on_backspace()
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_current(), 'hel')

    def test_backspace_beyond_empty_does_not_crash(self):
        self.tracker.on_backspace()
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_current(), '')


class TestWordTrackerReset(unittest.TestCase):

    def setUp(self):
        self.tracker = WordTracker()

    def test_reset_clears_buffer(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.tracker.on_reset()
        self.assertEqual(self.tracker.get_current(), '')

    def test_reset_on_empty_buffer_does_not_crash(self):
        self.tracker.on_reset()
        self.assertEqual(self.tracker.get_current(), '')

    def test_reset_returns_nothing(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        result = self.tracker.on_reset()
        self.assertIsNone(result)

    def test_can_add_after_reset(self):
        for ch in 'hello':
            self.tracker.add_char(ch)
        self.tracker.on_reset()
        self.tracker.add_char('a')
        self.assertEqual(self.tracker.get_current(), 'a')


class TestWordTrackerProperty(unittest.TestCase):

    @given(st.lists(st.text(min_size=1, max_size=1), min_size=0, max_size=100))
    def test_get_current_never_raises(self, chars):
        tracker = WordTracker()
        for ch in chars:
            if ch in STOP_CHARS:
                tracker.on_stop_char(ch)
            elif ch == '\x08':
                tracker.on_backspace()
            else:
                tracker.add_char(ch)
        result = tracker.get_current()
        self.assertIsInstance(result, str)

    @given(st.lists(st.text(min_size=1, max_size=1), min_size=0, max_size=100))
    def test_buffer_length_never_negative(self, chars):
        tracker = WordTracker()
        for ch in chars:
            tracker.add_char(ch)
            tracker.on_backspace()
        self.assertGreaterEqual(len(tracker.get_current()), 0)



class TestWordTrackerKeys(unittest.TestCase):
    """Нажатия (keycode, shift) хранятся параллельно символам."""

    def setUp(self):
        self.tracker = WordTracker()

    def test_keys_recorded(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.add_char('H', (35, True))
        self.assertEqual(self.tracker.get_keys(), [(34, False), (35, True)])

    def test_empty_keys(self):
        self.assertEqual(self.tracker.get_keys(), [])

    def test_char_without_key_gives_none(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.add_char('h')
        self.assertIsNone(self.tracker.get_keys())

    def test_backspace_removes_key(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.add_char('h', (35, False))
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_keys(), [(34, False)])

    def test_backspace_removes_keyless_char(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.add_char('h')
        self.tracker.on_backspace()
        self.assertEqual(self.tracker.get_keys(), [(34, False)])

    def test_reset_clears_keys(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.on_reset()
        self.assertEqual(self.tracker.get_keys(), [])

    def test_stop_char_clears_keys(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.on_stop_char(' ')
        self.assertEqual(self.tracker.get_keys(), [])

    def test_get_keys_returns_copy(self):
        self.tracker.add_char('g', (34, False))
        self.tracker.get_keys().append((1, False))
        self.assertEqual(self.tracker.get_keys(), [(34, False)])

if __name__ == '__main__':
    unittest.main()
