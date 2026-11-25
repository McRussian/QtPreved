from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from qtpreved.config import Config, load, save


def _tmp_path(suffix='.json') -> Path:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return Path(f.name)


class TestConfigDefaults(unittest.TestCase):

    def setUp(self):
        self.config = Config()

    def test_hotkey_switch_word(self):
        self.assertEqual(self.config.hotkey_switch_word, 'Pause')

    def test_hotkey_switch_selection(self):
        self.assertEqual(self.config.hotkey_switch_selection, 'Ctrl+Pause')

    def test_hotkey_undo(self):
        self.assertEqual(self.config.hotkey_undo, 'Shift+Pause')

    def test_hotkey_toggle_window(self):
        self.assertEqual(self.config.hotkey_toggle_window, 'Alt+Pause')

    def test_auto_switch_enabled(self):
        self.assertTrue(self.config.auto_switch)

    def test_min_word_length(self):
        self.assertEqual(self.config.min_word_length, 3)

    def test_skip_uppercase(self):
        self.assertTrue(self.config.skip_uppercase)

    def test_detection_margin(self):
        self.assertEqual(self.config.detection_margin, 0.25)

    def test_min_alt_logprob(self):
        self.assertEqual(self.config.min_alt_logprob, -6.0)

    def test_undo_stack_depth(self):
        self.assertEqual(self.config.undo_stack_depth, 10)

    def test_excluded_words_empty(self):
        self.assertEqual(self.config.excluded_words, [])

    def test_excluded_apps_empty(self):
        self.assertEqual(self.config.excluded_apps, [])

    def test_autostart_disabled(self):
        self.assertFalse(self.config.autostart)

    def test_excluded_words_are_independent_instances(self):
        # default_factory — каждый экземпляр получает свой список
        c1, c2 = Config(), Config()
        c1.excluded_words.append('test')
        self.assertEqual(c2.excluded_words, [])


class TestLoadConfig(unittest.TestCase):

    def test_load_nonexistent_returns_defaults(self):
        config = load(Path('/nonexistent/config.json'))
        self.assertEqual(config, Config())

    def test_load_invalid_json_returns_defaults(self):
        tmp = _tmp_path()
        try:
            tmp.write_text('not valid json{{{', encoding='utf-8')
            config = load(tmp)
            self.assertEqual(config, Config())
        finally:
            tmp.unlink()

    def test_load_empty_json_object_returns_defaults(self):
        tmp = _tmp_path()
        try:
            tmp.write_text('{}', encoding='utf-8')
            config = load(tmp)
            self.assertEqual(config, Config())
        finally:
            tmp.unlink()

    def test_load_partial_config_fills_defaults(self):
        tmp = _tmp_path()
        try:
            tmp.write_text(json.dumps({'min_word_length': 5}), encoding='utf-8')
            config = load(tmp)
            self.assertEqual(config.min_word_length, 5)
            self.assertEqual(config.auto_switch, Config().auto_switch)
        finally:
            tmp.unlink()

    def test_load_unknown_fields_ignored(self):
        tmp = _tmp_path()
        try:
            tmp.write_text(json.dumps({'unknown_field': 42}), encoding='utf-8')
            config = load(tmp)
            self.assertEqual(config, Config())
        finally:
            tmp.unlink()

    def test_load_excluded_words(self):
        tmp = _tmp_path()
        try:
            tmp.write_text(json.dumps({'excluded_words': ['OK', 'PDF']}), encoding='utf-8')
            config = load(tmp)
            self.assertEqual(config.excluded_words, ['OK', 'PDF'])
        finally:
            tmp.unlink()


class TestSaveConfig(unittest.TestCase):

    def test_save_creates_file(self):
        tmp = _tmp_path()
        tmp.unlink()
        try:
            save(Config(), tmp)
            self.assertTrue(tmp.exists())
        finally:
            tmp.unlink(missing_ok=True)

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'nested' / 'dir' / 'config.json'
            save(Config(), path)
            self.assertTrue(path.exists())

    def test_save_writes_valid_json(self):
        tmp = _tmp_path()
        try:
            save(Config(), tmp)
            data = json.loads(tmp.read_text(encoding='utf-8'))
            self.assertIsInstance(data, dict)
        finally:
            tmp.unlink()

    def test_save_contains_all_fields(self):
        tmp = _tmp_path()
        try:
            save(Config(), tmp)
            data = json.loads(tmp.read_text(encoding='utf-8'))
            field_names = {f.name for f in fields(Config)}
            self.assertEqual(set(data.keys()), field_names)
        finally:
            tmp.unlink()


class TestConfigRoundtrip(unittest.TestCase):

    def _roundtrip(self, config: Config) -> Config:
        tmp = _tmp_path()
        try:
            save(config, tmp)
            return load(tmp)
        finally:
            tmp.unlink()

    def test_roundtrip_defaults(self):
        self.assertEqual(self._roundtrip(Config()), Config())

    def test_roundtrip_modified_values(self):
        config = Config(
            min_word_length=5,
            skip_uppercase=False,
            undo_stack_depth=20,
            excluded_words=['OK', 'PDF'],
            excluded_apps=['konsole'],
            autostart=True,
        )
        self.assertEqual(self._roundtrip(config), config)

    @given(
        min_word_length=st.integers(min_value=1, max_value=20),
        undo_stack_depth=st.integers(min_value=1, max_value=100),
        auto_switch=st.booleans(),
        skip_uppercase=st.booleans(),
        excluded_words=st.lists(st.text(max_size=20), max_size=10),
    )
    def test_roundtrip_hypothesis(self, min_word_length, undo_stack_depth,
                                   auto_switch, skip_uppercase, excluded_words):
        config = Config(
            min_word_length=min_word_length,
            undo_stack_depth=undo_stack_depth,
            auto_switch=auto_switch,
            skip_uppercase=skip_uppercase,
            excluded_words=excluded_words,
        )
        self.assertEqual(self._roundtrip(config), config)


if __name__ == '__main__':
    unittest.main()
