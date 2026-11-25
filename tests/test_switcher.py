from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.kbd_map import Layout, load_default_layouts
from qtpreved.switcher import Injector, LayoutManager, Switcher


class MockInjector(Injector):
    def __init__(self, selection: str | None = None) -> None:
        self.calls: list[tuple] = []
        self._selection = selection

    def inject_backspaces(self, n: int) -> None:
        self.calls.append(('inject_backspaces', n))

    def inject_text(self, text: str, layout: Layout) -> None:
        self.calls.append(('inject_text', text, layout))

    def get_selection(self) -> str | None:
        return self._selection

    def replace_selection(self, new_text: str) -> None:
        self.calls.append(('replace_selection', new_text))

    def paste_text(self, text: str) -> None:
        self.calls.append(('paste_text', text))


class MockLayoutManager(LayoutManager):
    def __init__(self, layouts: list[str] | None = None, current: int = 0) -> None:
        self._layouts = layouts or ['us', 'ru']
        self._current = current
        self.calls: list[tuple] = []

    def get_current(self) -> int:
        return self._current

    def set_layout(self, index: int) -> None:
        self._current = index
        self.calls.append(('set_layout', index))

    def list_layouts(self) -> list[str]:
        return list(self._layouts)


def make_switcher(
    selection: str | None = None,
    layouts: list[str] | None = None,
    current: int = 0,
    stack_depth: int = 10,
) -> tuple[Switcher, MockInjector, MockLayoutManager]:
    injector = MockInjector(selection=selection)
    lm = MockLayoutManager(layouts=layouts, current=current)
    switcher = Switcher(injector, lm, stack_depth=stack_depth)
    return switcher, injector, lm


class TestSwitchWord(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()
        self.switcher, self.injector, self.lm = make_switcher()

    def test_returns_true(self):
        self.assertTrue(self.switcher.switch_word('ghbdtn', self.en, self.ru))

    def test_injects_backspaces_for_word_length(self):
        self.switcher.switch_word('ghbdtn', self.en, self.ru)
        self.assertEqual(self.injector.calls[0], ('inject_backspaces', 6))

    def test_injects_remapped_text(self):
        self.switcher.switch_word('ghbdtn', self.en, self.ru)
        kind, text = self.injector.calls[1]
        self.assertEqual(kind, 'paste_text')
        self.assertEqual(text, 'привет')

    def test_backspaces_before_text_injection(self):
        self.switcher.switch_word('ghbdtn', self.en, self.ru)
        self.assertEqual(self.injector.calls[0][0], 'inject_backspaces')
        self.assertEqual(self.injector.calls[1][0], 'paste_text')

    def test_sets_alt_layout(self):
        self.switcher.switch_word('ghbdtn', self.en, self.ru)
        self.assertEqual(self.lm.calls, [('set_layout', 1)])

    def test_ru_to_en(self):
        lm = MockLayoutManager(current=1)
        s = Switcher(self.injector, lm)
        s.switch_word('привет', self.ru, self.en)
        self.assertEqual(self.injector.calls[1], ('paste_text', 'ghbdtn'))
        self.assertIn(('set_layout', 0), lm.calls)

    def test_pushes_undo_entry(self):
        self.switcher.switch_word('ghbdtn', self.en, self.ru)
        self.assertEqual(self.switcher.undo_stack_size, 1)

    def test_single_char_word(self):
        self.switcher.switch_word('g', self.en, self.ru)
        self.assertEqual(self.injector.calls[0], ('inject_backspaces', 1))


class TestSwitchSelection(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_no_selection_returns_false(self):
        s, _, _ = make_switcher(selection=None)
        self.assertFalse(s.switch_selection(self.en, self.ru))

    def test_empty_selection_returns_false(self):
        s, _, _ = make_switcher(selection='')
        self.assertFalse(s.switch_selection(self.en, self.ru))

    def test_no_selection_does_not_inject(self):
        s, injector, lm = make_switcher(selection=None)
        s.switch_selection(self.en, self.ru)
        self.assertEqual(injector.calls, [])
        self.assertEqual(lm.calls, [])

    def test_selection_returns_true(self):
        s, _, _ = make_switcher(selection='ghbdtn')
        self.assertTrue(s.switch_selection(self.en, self.ru))

    def test_selection_calls_replace_with_remapped(self):
        s, injector, _ = make_switcher(selection='ghbdtn')
        s.switch_selection(self.en, self.ru)
        self.assertIn(('replace_selection', 'привет'), injector.calls)

    def test_selection_switches_layout(self):
        s, _, lm = make_switcher(selection='ghbdtn')
        s.switch_selection(self.en, self.ru)
        self.assertIn(('set_layout', 1), lm.calls)

    def test_selection_pushes_undo_entry(self):
        s, _, _ = make_switcher(selection='ghbdtn')
        s.switch_selection(self.en, self.ru)
        self.assertEqual(s.undo_stack_size, 1)

    def test_no_selection_no_undo_entry(self):
        s, _, _ = make_switcher(selection=None)
        s.switch_selection(self.en, self.ru)
        self.assertEqual(s.undo_stack_size, 0)


class TestUndo(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_empty_stack_returns_false(self):
        s, _, _ = make_switcher()
        self.assertFalse(s.undo())

    def test_empty_stack_does_not_inject(self):
        s, injector, lm = make_switcher()
        s.undo()
        self.assertEqual(injector.calls, [])
        self.assertEqual(lm.calls, [])

    def test_after_switch_word_returns_true(self):
        s, injector, _ = make_switcher()
        s.switch_word('ghbdtn', self.en, self.ru)
        injector.calls.clear()
        self.assertTrue(s.undo())

    def test_undo_injects_backspaces_for_remapped_length(self):
        s, injector, _ = make_switcher()
        s.switch_word('ghbdtn', self.en, self.ru)  # remapped='привет', len=6
        injector.calls.clear()
        s.undo()
        self.assertEqual(injector.calls[0], ('inject_backspaces', 6))

    def test_undo_reinjects_original_word(self):
        s, injector, _ = make_switcher()
        s.switch_word('ghbdtn', self.en, self.ru)
        injector.calls.clear()
        s.undo()
        self.assertEqual(injector.calls[1], ('paste_text', 'ghbdtn'))

    def test_undo_restores_original_layout(self):
        s, _, lm = make_switcher(current=0)
        s.switch_word('ghbdtn', self.en, self.ru)
        lm.calls.clear()
        s.undo()
        self.assertEqual(lm.calls, [('set_layout', 0)])

    def test_undo_pops_stack(self):
        s, injector, _ = make_switcher()
        s.switch_word('ghbdtn', self.en, self.ru)
        injector.calls.clear()
        s.undo()
        self.assertEqual(s.undo_stack_size, 0)

    def test_second_undo_returns_false(self):
        s, injector, _ = make_switcher()
        s.switch_word('ghbdtn', self.en, self.ru)
        injector.calls.clear()
        s.undo()
        self.assertFalse(s.undo())

    def test_double_undo(self):
        injector = MockInjector()
        lm = MockLayoutManager(current=0)
        s = Switcher(injector, lm)
        s.switch_word('ghbdtn', self.en, self.ru)   # en→ru
        lm._current = 1
        s.switch_word('ещё', self.ru, self.en)      # ru→en
        injector.calls.clear()
        lm.calls.clear()
        self.assertTrue(s.undo())
        self.assertTrue(s.undo())
        self.assertFalse(s.undo())

    def test_undo_after_selection_switch(self):
        s, injector, lm = make_switcher(selection='ghbdtn', current=0)
        s.switch_selection(self.en, self.ru)
        injector.calls.clear()
        lm.calls.clear()
        result = s.undo()
        self.assertTrue(result)
        self.assertEqual(injector.calls[0], ('inject_backspaces', 6))
        self.assertEqual(injector.calls[1], ('paste_text', 'ghbdtn'))
        self.assertEqual(lm.calls, [('set_layout', 0)])


class TestUndoStack(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_stack_depth_zero_nothing_pushed(self):
        s, _, _ = make_switcher(stack_depth=0)
        s.switch_word('hello', self.en, self.ru)
        self.assertEqual(s.undo_stack_size, 0)

    def test_undo_on_depth_zero_stack_returns_false(self):
        s, _, _ = make_switcher(stack_depth=0)
        s.switch_word('hello', self.en, self.ru)
        self.assertFalse(s.undo())

    def test_stack_depth_one_keeps_latest(self):
        s, _, _ = make_switcher(stack_depth=1)
        s.switch_word('hello', self.en, self.ru)
        s.switch_word('world', self.en, self.ru)
        self.assertEqual(s.undo_stack_size, 1)

    def test_stack_exactly_at_depth(self):
        s, _, _ = make_switcher(stack_depth=3)
        for _ in range(3):
            s.switch_word('hello', self.en, self.ru)
        self.assertEqual(s.undo_stack_size, 3)

    def test_stack_drops_oldest_at_overflow(self):
        s, injector, lm = make_switcher(stack_depth=2)
        s.switch_word('aaa', self.en, self.ru)
        s.switch_word('bbb', self.en, self.ru)
        s.switch_word('ccc', self.en, self.ru)  # 'aaa' should be dropped
        self.assertEqual(s.undo_stack_size, 2)
        self.assertTrue(s.undo())
        self.assertTrue(s.undo())
        self.assertFalse(s.undo())

    def test_depth_respected_with_many_switches(self):
        s, _, _ = make_switcher(stack_depth=5)
        for _ in range(20):
            s.switch_word('hello', self.en, self.ru)
        self.assertEqual(s.undo_stack_size, 5)

    def test_on_typing_clears_stack(self):
        s, _, _ = make_switcher(stack_depth=5)
        s.switch_word('hello', self.en, self.ru)
        s.switch_word('world', self.en, self.ru)
        s.on_typing()
        self.assertEqual(s.undo_stack_size, 0)

    def test_on_typing_on_empty_stack_does_not_raise(self):
        s, _, _ = make_switcher()
        s.on_typing()
        self.assertEqual(s.undo_stack_size, 0)

    def test_undo_after_on_typing_returns_false(self):
        s, _, _ = make_switcher()
        s.switch_word('hello', self.en, self.ru)
        s.on_typing()
        self.assertFalse(s.undo())


class TestFindLayoutIndex(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    def test_finds_ru_at_index_1(self):
        s, _, lm = make_switcher(layouts=['us', 'ru'])
        s.switch_word('ghbdtn', self.en, self.ru)
        self.assertIn(('set_layout', 1), lm.calls)

    def test_finds_en_at_index_0(self):
        s, injector, lm = make_switcher(layouts=['us', 'ru'], current=1)
        s.switch_word('привет', self.ru, self.en)
        self.assertIn(('set_layout', 0), lm.calls)

    def test_ru_first_in_list(self):
        s, _, lm = make_switcher(layouts=['ru', 'us'])
        s.switch_word('ghbdtn', self.en, self.ru)
        self.assertIn(('set_layout', 0), lm.calls)

    def test_unknown_layout_falls_back_to_zero(self):
        unknown = Layout('xx', 'xx', self.en.lower, self.en.upper)
        s, injector, lm = make_switcher(layouts=['us', 'ru'], selection='ghbdtn')
        s.switch_selection(self.en, unknown)
        self.assertIn(('set_layout', 0), lm.calls)

    def test_three_layouts(self):
        s, _, lm = make_switcher(layouts=['de', 'us', 'ru'])
        s.switch_word('ghbdtn', self.en, self.ru)
        self.assertIn(('set_layout', 2), lm.calls)


class TestHypothesis(unittest.TestCase):

    def setUp(self):
        self.en, self.ru = load_default_layouts()

    @given(st.integers(min_value=0, max_value=20))
    def test_undo_stack_never_exceeds_depth(self, depth):
        s, _, _ = make_switcher(stack_depth=depth)
        for _ in range(depth + 5):
            s.switch_word('hello', self.en, self.ru)
        self.assertLessEqual(s.undo_stack_size, max(0, depth))

    @given(st.integers(min_value=1, max_value=10))
    def test_undo_count_matches_stack_size(self, switches):
        s, injector, _ = make_switcher(stack_depth=switches + 5)
        for _ in range(switches):
            s.switch_word('hello', self.en, self.ru)
        undo_count = 0
        while s.undo():
            injector.calls.clear()
            undo_count += 1
        self.assertEqual(undo_count, switches)

    @given(st.integers(min_value=0, max_value=15))
    @settings(max_examples=30)
    def test_on_typing_always_empties_stack(self, switches):
        s, _, _ = make_switcher(stack_depth=switches + 5)
        for _ in range(switches):
            s.switch_word('hello', self.en, self.ru)
        s.on_typing()
        self.assertEqual(s.undo_stack_size, 0)



class TestSwitchWordRemapped(unittest.TestCase):
    """Готовый remapped (собранный по нажатиям) используется вместо remap_to."""

    def setUp(self):
        self.en, self.ru = load_default_layouts()
        self.switcher, self.injector, self.lm = make_switcher()

    def test_remapped_pasted(self):
        self.switcher.switch_word('ghbdtn.', self.en, self.ru, remapped='привет,')
        self.assertIn(('paste_text', 'привет,'), self.injector.calls)

    def test_backspaces_by_original_length(self):
        self.switcher.switch_word('ghbdtn.', self.en, self.ru, ' ', remapped='привет,')
        self.assertEqual(self.injector.calls[0], ('inject_backspaces', 8))

    def test_undo_uses_remapped_length(self):
        self.switcher.switch_word('ab', self.en, self.ru, remapped='xyz')
        self.injector.calls.clear()
        self.switcher.undo()
        self.assertEqual(self.injector.calls[0], ('inject_backspaces', 3))
        self.assertIn(('paste_text', 'ab'), self.injector.calls)

    def test_none_falls_back_to_remap_to(self):
        self.switcher.switch_word('ghbdtn', self.en, self.ru, remapped=None)
        self.assertIn(('paste_text', 'привет'), self.injector.calls)

if __name__ == '__main__':
    unittest.main()
