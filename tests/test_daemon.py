from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from evdev import ecodes

from qtpreved.config import Config
from qtpreved.daemon import KeyboardDaemon, _parse_hotkey
from qtpreved.kbd_map import Layout, load_default_layouts
from qtpreved.switcher import Injector, LayoutManager


# ---------------------------------------------------------------------------
# Вспомогательные классы
# ---------------------------------------------------------------------------

class MockInjector(Injector):
    def __init__(self, selection=None):
        self.calls = []
        self._selection = selection

    def inject_backspaces(self, n):
        self.calls.append(('inject_backspaces', n))

    def inject_text(self, text, layout):
        self.calls.append(('inject_text', text))

    def get_selection(self):
        return self._selection

    def replace_selection(self, new_text):
        self.calls.append(('replace_selection', new_text))

    def paste_text(self, text):
        self.calls.append(('paste_text', text))


class MockLayoutManager(LayoutManager):
    def __init__(self, layouts=None, current=0):
        self._layouts = layouts or ['us', 'ru']
        self._current = current
        self.calls = []

    def get_current(self):
        return self._current

    def set_layout(self, index):
        self._current = index
        self.calls.append(('set_layout', index))

    def list_layouts(self):
        return list(self._layouts)


class FakeEvent:
    """Имитирует evdev EV_KEY событие."""
    def __init__(self, code: int, value: int):
        self.type = ecodes.EV_KEY
        self.code = code
        self.value = value


def dn(code: int) -> FakeEvent:
    """key_down."""
    return FakeEvent(code, 1)


def up(code: int) -> FakeEvent:
    """key_up."""
    return FakeEvent(code, 0)


# ---------------------------------------------------------------------------
# QCoreApplication (требуется для QThread/сигналов)
# ---------------------------------------------------------------------------

_app = None


def setUpModule():
    global _app
    # QApplication (а не QCoreApplication): в том же процессе тестам настроек и трея нужны виджеты
    _app = QApplication.instance() or QApplication(sys.argv[:1])


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

def make_daemon(config=None, selection=None, current_layout_idx=0) -> tuple[KeyboardDaemon, MockInjector, MockLayoutManager]:
    en, ru = load_default_layouts()
    injector = MockInjector(selection=selection)
    lm = MockLayoutManager(current=current_layout_idx)
    daemon = KeyboardDaemon(config or Config(), injector, lm, en, ru)
    return daemon, injector, lm


# ---------------------------------------------------------------------------
# Тесты парсера горячих клавиш
# ---------------------------------------------------------------------------

class TestParseHotkey(unittest.TestCase):

    def test_simple_key(self):
        keycode, ctrl, shift, alt = _parse_hotkey('Pause')
        self.assertEqual(keycode, ecodes.KEY_PAUSE)
        self.assertFalse(ctrl)
        self.assertFalse(shift)
        self.assertFalse(alt)

    def test_ctrl_modifier(self):
        keycode, ctrl, shift, alt = _parse_hotkey('Ctrl+Pause')
        self.assertEqual(keycode, ecodes.KEY_PAUSE)
        self.assertTrue(ctrl)
        self.assertFalse(shift)

    def test_shift_modifier(self):
        keycode, ctrl, shift, alt = _parse_hotkey('Shift+Pause')
        self.assertEqual(keycode, ecodes.KEY_PAUSE)
        self.assertFalse(ctrl)
        self.assertTrue(shift)

    def test_alt_modifier(self):
        keycode, ctrl, shift, alt = _parse_hotkey('Alt+Pause')
        self.assertTrue(alt)

    def test_f5_key(self):
        keycode, _, _, _ = _parse_hotkey('F5')
        self.assertEqual(keycode, ecodes.KEY_F5)

    def test_unknown_key_returns_none(self):
        keycode, _, _, _ = _parse_hotkey('Ctrl+NoSuchKey123')
        self.assertIsNone(keycode)

    def test_empty_string_returns_none(self):
        keycode, _, _, _ = _parse_hotkey('')
        self.assertIsNone(keycode)

    def test_modifier_only_returns_none(self):
        # 'Ctrl' без клавиши → key_parts пуст
        keycode, ctrl, _, _ = _parse_hotkey('Ctrl')
        self.assertIsNone(keycode)
        self.assertTrue(ctrl)


# ---------------------------------------------------------------------------
# Тест интеграции: G H B D T N SPACE → switch_word
# ---------------------------------------------------------------------------

class TestAutoSwitch(unittest.TestCase):

    def setUp(self):
        self.daemon, self.injector, self.lm = make_daemon()

    def _type(self, *codes):
        for code in codes:
            self.daemon._process_event(dn(code))

    def test_ghbdtn_space_triggers_switch(self):
        self._type(
            ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
            ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N,
            ecodes.KEY_SPACE,
        )
        bs_calls = [c for c in self.injector.calls if c[0] == 'inject_backspaces']
        self.assertTrue(len(bs_calls) > 0)

    def test_ghbdtn_space_injects_privet(self):
        self._type(
            ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
            ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N,
            ecodes.KEY_SPACE,
        )
        text_calls = [c[1] for c in self.injector.calls if c[0] == 'paste_text']
        # Пробел вставляется вместе со словом
        self.assertIn('привет ', text_calls)

    def test_correct_english_word_not_switched(self):
        # 'hello' — корректное английское слово
        self._type(
            ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L,
            ecodes.KEY_L, ecodes.KEY_O,
            ecodes.KEY_SPACE,
        )
        self.assertEqual(self.injector.calls, [])

    def test_auto_switch_disabled_no_switch(self):
        daemon, injector, _ = make_daemon(config=Config(auto_switch=False))
        for code in [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                     ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N, ecodes.KEY_SPACE]:
            daemon._process_event(dn(code))
        self.assertEqual(injector.calls, [])

    def test_short_word_not_switched(self):
        # 'gh' — меньше min_word_length (3)
        self._type(ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_SPACE)
        self.assertEqual(self.injector.calls, [])

    def test_layout_changed_signal_emitted(self):
        received = []
        self.daemon.layout_changed.connect(received.append)
        self._type(
            ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
            ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N,
            ecodes.KEY_SPACE,
        )
        self.assertEqual(received, ['ru'])


# ---------------------------------------------------------------------------
# Тест модификаторов и сброса буфера
# ---------------------------------------------------------------------------

class TestModifiers(unittest.TestCase):

    def setUp(self):
        self.daemon, self.injector, _ = make_daemon()

    def test_ctrl_key_resets_tracker(self):
        self.daemon._process_event(dn(ecodes.KEY_G))
        self.assertEqual(self.daemon._word_tracker.get_current(), 'g')
        self.daemon._process_event(dn(ecodes.KEY_LEFTCTRL))
        self.daemon._process_event(dn(ecodes.KEY_A))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')

    def test_alt_key_resets_tracker(self):
        self.daemon._process_event(dn(ecodes.KEY_G))
        self.daemon._process_event(dn(ecodes.KEY_LEFTALT))
        self.daemon._process_event(dn(ecodes.KEY_A))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')

    def test_escape_resets_tracker(self):
        self.daemon._process_event(dn(ecodes.KEY_G))
        self.daemon._process_event(dn(ecodes.KEY_ESC))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')

    def test_backspace_removes_char(self):
        self.daemon._process_event(dn(ecodes.KEY_G))
        self.daemon._process_event(dn(ecodes.KEY_H))
        self.daemon._process_event(dn(ecodes.KEY_BACKSPACE))
        self.assertEqual(self.daemon._word_tracker.get_current(), 'g')

    def test_shift_changes_char_case(self):
        self.daemon._process_event(dn(ecodes.KEY_LEFTSHIFT))
        self.daemon._process_event(dn(ecodes.KEY_G))
        self.daemon._process_event(up(ecodes.KEY_LEFTSHIFT))
        self.assertEqual(self.daemon._word_tracker.get_current(), 'G')

    def test_key_hold_ignored(self):
        self.daemon._process_event(FakeEvent(ecodes.KEY_G, 2))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')

    def test_key_up_ignored(self):
        self.daemon._process_event(up(ecodes.KEY_G))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')

    def test_unknown_key_not_in_layout_ignored(self):
        # KEY_F5 — не в layout JSON и не специальный стоп-символ
        self.daemon._process_event(dn(ecodes.KEY_F5))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')


# ---------------------------------------------------------------------------
# Тест горячих клавиш
# ---------------------------------------------------------------------------

class TestHotkeys(unittest.TestCase):

    def setUp(self):
        self.daemon, self.injector, self.lm = make_daemon()

    def test_pause_switches_word_in_buffer(self):
        for code in [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                     ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N]:
            self.daemon._process_event(dn(code))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        bs_calls = [c for c in self.injector.calls if c[0] == 'inject_backspaces']
        self.assertTrue(len(bs_calls) > 0)

    def test_pause_with_empty_buffer_does_nothing(self):
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        self.assertEqual(self.injector.calls, [])

    def test_ctrl_pause_switch_selection(self):
        self.injector._selection = 'ghbdtn'
        self.daemon._process_event(dn(ecodes.KEY_LEFTCTRL))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        replace_calls = [c for c in self.injector.calls if c[0] == 'replace_selection']
        self.assertTrue(len(replace_calls) > 0)

    def test_ctrl_pause_no_selection_does_nothing(self):
        self.injector._selection = None
        self.daemon._process_event(dn(ecodes.KEY_LEFTCTRL))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        self.assertEqual(self.injector.calls, [])

    def test_shift_pause_undo(self):
        # Сначала делаем переключение, потом undo
        for code in [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                     ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N]:
            self.daemon._process_event(dn(code))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        self.injector.calls.clear()
        self.lm.calls.clear()
        # Undo
        self.daemon._process_event(dn(ecodes.KEY_LEFTSHIFT))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        bs_calls = [c for c in self.injector.calls if c[0] == 'inject_backspaces']
        self.assertTrue(len(bs_calls) > 0)

    def test_alt_pause_toggles_window_exclusion(self):
        self.daemon.set_active_window('terminal')
        self.daemon._process_event(dn(ecodes.KEY_LEFTALT))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        self.daemon._process_event(up(ecodes.KEY_LEFTALT))
        self.assertTrue(self.daemon.is_window_excluded('terminal'))

    def test_pause_clears_buffer_after_switch(self):
        for code in [ecodes.KEY_G, ecodes.KEY_H]:
            self.daemon._process_event(dn(code))
        self.daemon._process_event(dn(ecodes.KEY_PAUSE))
        self.assertEqual(self.daemon._word_tracker.get_current(), '')


# ---------------------------------------------------------------------------
# Тест исключений окон
# ---------------------------------------------------------------------------

class TestWindowExclusion(unittest.TestCase):

    def setUp(self):
        self.daemon, self.injector, _ = make_daemon()

    def test_toggle_adds_window(self):
        self.daemon.set_active_window('konsole')
        self.daemon.toggle_current_window()
        self.assertTrue(self.daemon.is_window_excluded('konsole'))

    def test_toggle_removes_window(self):
        self.daemon.set_active_window('konsole')
        self.daemon.toggle_current_window()
        self.daemon.toggle_current_window()
        self.assertFalse(self.daemon.is_window_excluded('konsole'))

    def test_excluded_window_prevents_auto_switch(self):
        self.daemon.set_active_window('konsole')
        self.daemon.toggle_current_window()
        for code in [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                     ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N, ecodes.KEY_SPACE]:
            self.daemon._process_event(dn(code))
        self.assertEqual(self.injector.calls, [])

    def test_excluded_app_prevents_auto_switch(self):
        daemon, injector, _ = make_daemon(config=Config(excluded_apps=['konsole']))
        daemon.set_active_window('konsole - bash')
        for code in [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                     ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N, ecodes.KEY_SPACE]:
            daemon._process_event(dn(code))
        self.assertEqual(injector.calls, [])

    def test_non_excluded_window_allows_switch(self):
        self.daemon.set_active_window('kate')
        for code in [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                     ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N, ecodes.KEY_SPACE]:
            self.daemon._process_event(dn(code))
        bs_calls = [c for c in self.injector.calls if c[0] == 'inject_backspaces']
        self.assertTrue(len(bs_calls) > 0)


# ---------------------------------------------------------------------------
# Тест current_layout / alt_layout
# ---------------------------------------------------------------------------

class TestStopAndRun(unittest.TestCase):

    def test_stop_sets_running_false(self):
        daemon, _, _ = make_daemon()
        daemon._running = True
        daemon.stop()
        self.assertFalse(daemon._running)

    def test_run_processes_events_via_device(self):
        daemon, injector, _ = make_daemon()

        class FakeDevice:
            def __init__(self):
                self._events = [
                    FakeEvent(ecodes.KEY_G, 1),
                    FakeEvent(ecodes.KEY_H, 1),
                ]
                self._stop = None

            def read_loop(self):
                for ev in self._events:
                    yield ev
                daemon.stop()  # завершить после 2 событий

        daemon._device = FakeDevice()
        daemon.run()  # синхронно — цикл завершится сам после stop()
        self.assertEqual(daemon._word_tracker.get_current(), 'gh')


class TestLayoutResolution(unittest.TestCase):

    def test_current_layout_en_when_index_0(self):
        daemon, _, _ = make_daemon(current_layout_idx=0)
        en, _ = load_default_layouts()
        self.assertEqual(daemon.current_layout.name, en.name)

    def test_current_layout_ru_when_index_1(self):
        daemon, _, _ = make_daemon(current_layout_idx=1)
        _, ru = load_default_layouts()
        self.assertEqual(daemon.current_layout.name, ru.name)

    def test_alt_layout_is_opposite(self):
        daemon, _, _ = make_daemon(current_layout_idx=0)
        en, ru = load_default_layouts()
        self.assertEqual(daemon.alt_layout.name, ru.name)



class TestNumlock(unittest.TestCase):
    """Состояние NumLock читается со светодиода устройства."""

    class _Device:
        def __init__(self, leds=None, error=False):
            self._leds = leds or []
            self._error = error

        def leds(self):
            if self._error:
                raise OSError('device gone')
            return self._leds

    def _daemon(self, device):
        daemon, _, _ = make_daemon()
        daemon._device = device
        return daemon

    def test_led_on(self):
        self.assertTrue(self._daemon(self._Device([ecodes.LED_NUML]))._numlock_on())

    def test_led_off(self):
        self.assertFalse(self._daemon(self._Device([ecodes.LED_CAPSL]))._numlock_on())

    def test_no_device(self):
        self.assertFalse(self._daemon(None)._numlock_on())

    def test_read_error(self):
        self.assertFalse(self._daemon(self._Device(error=True))._numlock_on())

    def test_keypad_digit_with_numlock(self):
        daemon = self._daemon(self._Device([ecodes.LED_NUML]))
        daemon._process_event(dn(ecodes.KEY_KP7))
        self.assertEqual(daemon._word_tracker.get_current(), '7')

    def test_keypad_digit_without_numlock_resets(self):
        daemon = self._daemon(self._Device([]))
        daemon._process_event(dn(ecodes.KEY_G))
        daemon._process_event(dn(ecodes.KEY_KP7))
        self.assertEqual(daemon._word_tracker.get_current(), '')

if __name__ == '__main__':
    unittest.main()
