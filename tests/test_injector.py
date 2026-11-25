from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from evdev import ecodes

from qtpreved.injector import UinputInjector
from qtpreved.kbd_map import load_default_layouts


def make_injector(paste_delay: float = 0.0) -> tuple[UinputInjector, MagicMock]:
    ui = MagicMock()
    return UinputInjector(ui=ui, paste_delay=paste_delay, key_delay=0.0), ui


def _ok(stdout: str = '') -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    return m


class TestInjectBackspaces(unittest.TestCase):

    def setUp(self):
        self.inj, self.ui = make_injector()

    def test_zero_backspaces_no_calls(self):
        self.inj.inject_backspaces(0)
        self.ui.write.assert_not_called()
        self.ui.syn.assert_not_called()

    def test_one_backspace_correct_keycode(self):
        self.inj.inject_backspaces(1)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 1)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 0)

    def test_one_backspace_syn_per_event(self):
        # Нажатие и отпускание — отдельные кадры
        self.inj.inject_backspaces(1)
        self.assertEqual(self.ui.syn.call_count, 2)

    def test_three_backspaces_syn_per_event(self):
        self.inj.inject_backspaces(3)
        self.assertEqual(self.ui.syn.call_count, 6)

    def test_syn_between_press_and_release(self):
        self.inj.inject_backspaces(1)
        names = [c[0] for c in self.ui.mock_calls]
        self.assertEqual(names, ['write', 'syn', 'write', 'syn'])

    def test_key_delay_after_each_event(self):
        inj = UinputInjector(ui=self.ui, paste_delay=0.0, key_delay=0.01)
        with patch('qtpreved.injector.time.sleep') as sleep:
            inj.inject_backspaces(2)
        self.assertEqual(sleep.call_count, 4)
        sleep.assert_called_with(0.01)

    def test_zero_key_delay_no_sleep(self):
        with patch('qtpreved.injector.time.sleep') as sleep:
            self.inj.inject_backspaces(2)
        sleep.assert_not_called()

    def test_three_backspaces_six_writes(self):
        self.inj.inject_backspaces(3)
        self.assertEqual(self.ui.write.call_count, 6)

    def test_press_before_release(self):
        self.inj.inject_backspaces(1)
        calls = self.ui.write.call_args_list
        press_idx = calls.index(call(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 1))
        release_idx = calls.index(call(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 0))
        self.assertLess(press_idx, release_idx)


class TestInjectTextUnshifted(unittest.TestCase):

    def setUp(self):
        self.inj, self.ui = make_injector()
        self.en, self.ru = load_default_layouts()

    def test_empty_string_no_calls(self):
        self.inj.inject_text('', self.en)
        self.ui.write.assert_not_called()

    def test_single_lowercase_char_syn_per_event(self):
        self.inj.inject_text('g', self.en)
        self.assertEqual(self.ui.syn.call_count, 2)

    def test_single_lowercase_char_correct_keycode(self):
        keycode, _ = self.en._char_to_key['g']
        self.inj.inject_text('g', self.en)
        self.ui.write.assert_any_call(ecodes.EV_KEY, keycode, 1)
        self.ui.write.assert_any_call(ecodes.EV_KEY, keycode, 0)

    def test_unshifted_no_shift_key(self):
        self.inj.inject_text('g', self.en)
        for c in self.ui.write.call_args_list:
            self.assertNotEqual(c, call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1))

    def test_three_chars_syn_per_event(self):
        self.inj.inject_text('abc', self.en)
        self.assertEqual(self.ui.syn.call_count, 6)

    def test_unknown_char_skipped(self):
        self.inj.inject_text('漢', self.en)
        self.ui.write.assert_not_called()

    def test_mixed_known_unknown(self):
        # '漢' is unknown, 'g' is known → 2 syn (нажатие и отпускание)
        self.inj.inject_text('漢g漢', self.en)
        self.assertEqual(self.ui.syn.call_count, 2)

    def test_ru_layout_correct_char(self):
        keycode, shifted = self.ru._char_to_key['г']
        self.assertFalse(shifted)
        self.inj.inject_text('г', self.ru)
        self.ui.write.assert_any_call(ecodes.EV_KEY, keycode, 1)


class TestInjectTextShifted(unittest.TestCase):

    def setUp(self):
        self.inj, self.ui = make_injector()
        self.en, self.ru = load_default_layouts()

    def test_uppercase_includes_shift_press(self):
        self.inj.inject_text('G', self.en)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)

    def test_uppercase_includes_shift_release(self):
        self.inj.inject_text('G', self.en)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)

    def test_uppercase_shift_before_key(self):
        keycode, _ = self.en._char_to_key['G']
        self.inj.inject_text('G', self.en)
        calls = self.ui.write.call_args_list
        shift_press = calls.index(call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1))
        key_press = calls.index(call(ecodes.EV_KEY, keycode, 1))
        self.assertLess(shift_press, key_press)

    def test_uppercase_shift_after_key_release(self):
        keycode, _ = self.en._char_to_key['G']
        self.inj.inject_text('G', self.en)
        calls = self.ui.write.call_args_list
        key_release = calls.index(call(ecodes.EV_KEY, keycode, 0))
        shift_release = calls.index(call(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0))
        self.assertLess(key_release, shift_release)

    def test_uppercase_syn_per_event(self):
        # Shift↓, G↓, G↑, Shift↑ — четыре кадра
        self.inj.inject_text('G', self.en)
        self.assertEqual(self.ui.syn.call_count, 4)

    def test_uppercase_four_writes(self):
        self.inj.inject_text('G', self.en)
        self.assertEqual(self.ui.write.call_count, 4)

    def test_mixed_case_correct_syn_count(self):
        self.inj.inject_text('aB', self.en)
        self.assertEqual(self.ui.syn.call_count, 6)


class TestGetSelection(unittest.TestCase):

    def setUp(self):
        self.inj, _ = make_injector()

    def test_returns_selected_text(self):
        with patch('subprocess.run', return_value=_ok('ghbdtn')):
            self.assertEqual(self.inj.get_selection(), 'ghbdtn')

    def test_returns_none_for_empty_stdout(self):
        with patch('subprocess.run', return_value=_ok('')):
            self.assertIsNone(self.inj.get_selection())

    def test_returns_none_on_process_error(self):
        with patch('subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'wl-paste')):
            self.assertIsNone(self.inj.get_selection())

    def test_calls_wl_paste_primary(self):
        with patch('subprocess.run', return_value=_ok('text')) as mock:
            self.inj.get_selection()
            cmd = mock.call_args[0][0]
            self.assertIn('wl-paste', cmd)
            self.assertIn('--primary', cmd)

    def test_uses_no_newline_flag(self):
        with patch('subprocess.run', return_value=_ok('text')) as mock:
            self.inj.get_selection()
            cmd = mock.call_args[0][0]
            self.assertIn('--no-newline', cmd)

    def test_multiline_selection_preserved(self):
        with patch('subprocess.run', return_value=_ok('line1\nline2')):
            self.assertEqual(self.inj.get_selection(), 'line1\nline2')


class TestReplaceSelection(unittest.TestCase):

    def setUp(self):
        self.inj, self.ui = make_injector(paste_delay=0.0)

    def _patch_subprocess(self, old_clipboard: str = 'old') -> patch:
        def side_effect(cmd, **kwargs):
            if 'wl-paste' in cmd:
                return _ok(old_clipboard)
            return _ok()
        return patch('subprocess.run', side_effect=side_effect)

    def test_calls_wl_copy_with_new_text(self):
        with self._patch_subprocess() as mock:
            self.inj.replace_selection('привет')
            wl_copy_calls = [
                c for c in mock.call_args_list
                if 'wl-copy' in c[0][0]
            ]
            inputs = [c[1].get('input') for c in wl_copy_calls]
            self.assertIn('привет', inputs)

    def test_restores_old_clipboard(self):
        with self._patch_subprocess(old_clipboard='original') as mock:
            self.inj.replace_selection('new')
            wl_copy_calls = [
                c for c in mock.call_args_list
                if 'wl-copy' in c[0][0]
            ]
            inputs = [c[1].get('input') for c in wl_copy_calls]
            self.assertIn('original', inputs)

    def test_injects_ctrl_v(self):
        with self._patch_subprocess():
            self.inj.replace_selection('text')
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_V, 1)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_V, 0)
        self.ui.write.assert_any_call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)

    def test_ctrl_before_v(self):
        with self._patch_subprocess():
            self.inj.replace_selection('text')
        calls = self.ui.write.call_args_list
        ctrl_press = calls.index(call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1))
        v_press = calls.index(call(ecodes.EV_KEY, ecodes.KEY_V, 1))
        self.assertLess(ctrl_press, v_press)

    def test_ctrl_release_after_v_release(self):
        with self._patch_subprocess():
            self.inj.replace_selection('text')
        calls = self.ui.write.call_args_list
        v_release = calls.index(call(ecodes.EV_KEY, ecodes.KEY_V, 0))
        ctrl_release = calls.index(call(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0))
        self.assertLess(v_release, ctrl_release)

    def test_ctrl_v_each_event_own_frame(self):
        with patch('qtpreved.injector.subprocess.run', return_value=_ok('')):
            self.inj.paste_text('привет')
        names = [c[0] for c in self.ui.mock_calls]
        self.assertEqual(names, ['write', 'syn'] * 4)

    def test_syn_after_ctrl_v(self):
        with self._patch_subprocess():
            self.inj.replace_selection('text')
        self.ui.syn.assert_called()

    def test_handles_failed_wl_paste_for_old_clipboard(self):
        def side_effect(cmd, **kwargs):
            if 'wl-paste' in cmd:
                raise subprocess.CalledProcessError(1, 'wl-paste')
            return _ok()

        with patch('subprocess.run', side_effect=side_effect) as mock:
            self.inj.replace_selection('new')
            # Should still call wl-copy to restore (with empty string)
            wl_copy_calls = [
                c for c in mock.call_args_list
                if 'wl-copy' in c[0][0]
            ]
            inputs = [c[1].get('input') for c in wl_copy_calls]
            self.assertIn('', inputs)

    def test_new_text_set_before_ctrl_v(self):
        """wl-copy с новым текстом должен быть вызван до Ctrl+V."""
        call_order = []

        def side_effect(cmd, **kwargs):
            if 'wl-paste' in cmd:
                return _ok('old')
            call_order.append('wl-copy')
            return _ok()

        def write_side_effect(*args):
            if args == (ecodes.EV_KEY, ecodes.KEY_V, 1):
                call_order.append('key_v')

        with patch('subprocess.run', side_effect=side_effect):
            self.ui.write.side_effect = write_side_effect
            self.inj.replace_selection('new')

        self.assertEqual(call_order.index('wl-copy'), 0)
        self.assertEqual(call_order.index('key_v'), 1)


class TestContextManager(unittest.TestCase):

    def test_close_calls_ui_close(self):
        inj, ui = make_injector()
        inj.close()
        ui.close.assert_called_once()

    def test_context_manager_calls_close(self):
        inj, ui = make_injector()
        with inj:
            pass
        ui.close.assert_called_once()

    def test_context_manager_returns_self(self):
        inj, _ = make_injector()
        with inj as result:
            self.assertIs(result, inj)


if __name__ == '__main__':
    unittest.main()
