from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.layout import KDELayoutManager, _dbus_call

_DBUS_BASE = [
    'dbus-send', '--session', '--print-reply',
    '--dest=org.kde.keyboard', '/Layouts',
]


def _ok(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    return m


_OUT_LAYOUT_0 = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
    '   uint32 0\n'
)
_OUT_LAYOUT_1 = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
    '   uint32 1\n'
)
_OUT_LAYOUT_42 = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
    '   uint32 42\n'
)
_OUT_LAYOUTS_2 = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
    '   array [\n'
    '      struct {\n'
    '         string "us"\n'
    '         string ""\n'
    '         string "English (US)"\n'
    '      }\n'
    '      struct {\n'
    '         string "ru"\n'
    '         string ""\n'
    '         string "Russian"\n'
    '      }\n'
    '   ]\n'
)
_OUT_LAYOUTS_3 = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
    '   array [\n'
    '      struct {\n'
    '         string "de"\n'
    '         string ""\n'
    '         string "German"\n'
    '      }\n'
    '      struct {\n'
    '         string "us"\n'
    '         string ""\n'
    '         string "English (US)"\n'
    '      }\n'
    '      struct {\n'
    '         string "ru"\n'
    '         string ""\n'
    '         string "Russian"\n'
    '      }\n'
    '   ]\n'
)
_OUT_LAYOUTS_EMPTY = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
    '   array [\n'
    '   ]\n'
)
_OUT_SET_OK = (
    'method return time=1.0 sender=:1.1 -> destination=:1.2 serial=1 reply_serial=2\n'
)


class TestDbusCall(unittest.TestCase):

    def test_calls_dbus_send(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            _dbus_call('getLayout')
            cmd = mock.call_args[0][0]
            self.assertEqual(cmd[0], 'dbus-send')

    def test_uses_session_bus(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            _dbus_call('getLayout')
            cmd = mock.call_args[0][0]
            self.assertIn('--session', cmd)

    def test_includes_print_reply(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            _dbus_call('getLayout')
            cmd = mock.call_args[0][0]
            self.assertIn('--print-reply', cmd)

    def test_correct_dest(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            _dbus_call('getLayout')
            cmd = mock.call_args[0][0]
            self.assertIn('--dest=org.kde.keyboard', cmd)

    def test_correct_path(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            _dbus_call('getLayout')
            cmd = mock.call_args[0][0]
            self.assertIn('/Layouts', cmd)

    def test_method_name_in_command(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            _dbus_call('getLayout')
            cmd = mock.call_args[0][0]
            self.assertIn('org.kde.KeyboardLayouts.getLayout', cmd)

    def test_extra_args_appended(self):
        with patch('subprocess.run', return_value=_ok(_OUT_SET_OK)) as mock:
            _dbus_call('setLayout', 'uint32:1')
            cmd = mock.call_args[0][0]
            self.assertIn('uint32:1', cmd)

    def test_check_true_propagates_error(self):
        with patch('subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'dbus-send')):
            with self.assertRaises(subprocess.CalledProcessError):
                _dbus_call('getLayout')

    def test_returns_stdout(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)):
            result = _dbus_call('getLayout')
            self.assertEqual(result, _OUT_LAYOUT_0)


class TestGetCurrent(unittest.TestCase):

    def test_returns_zero(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)):
            self.assertEqual(KDELayoutManager().get_current(), 0)

    def test_returns_one(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_1)):
            self.assertEqual(KDELayoutManager().get_current(), 1)

    def test_returns_large_index(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_42)):
            self.assertEqual(KDELayoutManager().get_current(), 42)

    def test_fallback_to_zero_on_bad_output(self):
        with patch('subprocess.run', return_value=_ok('unexpected garbage\n')):
            self.assertEqual(KDELayoutManager().get_current(), 0)

    def test_sends_getLayout_method(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUT_0)) as mock:
            KDELayoutManager().get_current()
            cmd = mock.call_args[0][0]
            self.assertIn('org.kde.KeyboardLayouts.getLayout', cmd)

    def test_propagates_subprocess_error(self):
        with patch('subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'dbus-send')):
            with self.assertRaises(subprocess.CalledProcessError):
                KDELayoutManager().get_current()


class TestSetLayout(unittest.TestCase):

    def test_sends_setLayout_method(self):
        with patch('subprocess.run', return_value=_ok(_OUT_SET_OK)) as mock:
            KDELayoutManager().set_layout(1)
            cmd = mock.call_args[0][0]
            self.assertIn('org.kde.KeyboardLayouts.setLayout', cmd)

    def test_sends_correct_index_zero(self):
        with patch('subprocess.run', return_value=_ok(_OUT_SET_OK)) as mock:
            KDELayoutManager().set_layout(0)
            cmd = mock.call_args[0][0]
            self.assertIn('uint32:0', cmd)

    def test_sends_correct_index_one(self):
        with patch('subprocess.run', return_value=_ok(_OUT_SET_OK)) as mock:
            KDELayoutManager().set_layout(1)
            cmd = mock.call_args[0][0]
            self.assertIn('uint32:1', cmd)

    def test_sends_correct_large_index(self):
        with patch('subprocess.run', return_value=_ok(_OUT_SET_OK)) as mock:
            KDELayoutManager().set_layout(5)
            cmd = mock.call_args[0][0]
            self.assertIn('uint32:5', cmd)

    def test_returns_none(self):
        with patch('subprocess.run', return_value=_ok(_OUT_SET_OK)):
            result = KDELayoutManager().set_layout(0)
            self.assertIsNone(result)

    def test_propagates_subprocess_error(self):
        with patch('subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'dbus-send')):
            with self.assertRaises(subprocess.CalledProcessError):
                KDELayoutManager().set_layout(0)


class TestListLayouts(unittest.TestCase):

    def test_returns_two_layouts(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUTS_2)):
            result = KDELayoutManager().list_layouts()
            self.assertEqual(result, ['us', 'ru'])

    def test_returns_three_layouts(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUTS_3)):
            result = KDELayoutManager().list_layouts()
            self.assertEqual(result, ['de', 'us', 'ru'])

    def test_returns_empty_list_for_empty_array(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUTS_EMPTY)):
            result = KDELayoutManager().list_layouts()
            self.assertEqual(result, [])

    def test_returns_empty_list_on_bad_output(self):
        with patch('subprocess.run', return_value=_ok('unexpected garbage\n')):
            result = KDELayoutManager().list_layouts()
            self.assertEqual(result, [])

    def test_returns_list(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUTS_2)):
            result = KDELayoutManager().list_layouts()
            self.assertIsInstance(result, list)

    def test_sends_getLayoutsList_method(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUTS_2)) as mock:
            KDELayoutManager().list_layouts()
            cmd = mock.call_args[0][0]
            self.assertIn('org.kde.KeyboardLayouts.getLayoutsList', cmd)

    def test_propagates_subprocess_error(self):
        with patch('subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'dbus-send')):
            with self.assertRaises(subprocess.CalledProcessError):
                KDELayoutManager().list_layouts()

    def test_layout_names_are_strings(self):
        with patch('subprocess.run', return_value=_ok(_OUT_LAYOUTS_2)):
            result = KDELayoutManager().list_layouts()
            for name in result:
                self.assertIsInstance(name, str)


if __name__ == '__main__':
    unittest.main()
