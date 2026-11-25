from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal
from evdev import ecodes

from qtpreved.config import Config
from qtpreved.detector import Detector
from qtpreved.kbd_map import Layout
from qtpreved.switcher import Injector, LayoutManager, Switcher
from qtpreved.word_tracker import STOP_CHARS, WordTracker

# Клавиши, производящие стоп-символы, но отсутствующие в layout JSON
_STOP_KEY_CHARS: dict[int, str] = {
    ecodes.KEY_SPACE: ' ',
    ecodes.KEY_ENTER: '\n',
    ecodes.KEY_KPENTER: '\n',
    ecodes.KEY_TAB: '\t',
}

# Клавиши цифрового блока, которые без NumLock (или с Shift) работают как навигация
_KEYPAD_NUMLOCK_KEYS = frozenset(
    [getattr(ecodes, f'KEY_KP{d}') for d in '0123456789'] + [ecodes.KEY_KPDOT]
)

log = logging.getLogger(__name__)

# Завершают слово без переключения: Tab и Enter в разных приложениях ведут себя
# по-разному (пробелы вместо табуляции, автодополнение, отправка сообщения),
# и число символов, которые надо стереть, заранее неизвестно
_RESET_KEYS = frozenset({ecodes.KEY_TAB, ecodes.KEY_ENTER, ecodes.KEY_KPENTER})

# Знаки, которые остаются внутри слова и не запускают переключение: кто-то, snake_case
_IN_WORD_MARKS = frozenset('-_')

_SHIFT_KEYS = frozenset({ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT})
_CTRL_KEYS = frozenset({ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL})
_ALT_KEYS = frozenset({ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT})


def _parse_hotkey(hotkey_str: str) -> tuple[int | None, bool, bool, bool]:
    """Распарсить строку горячей клавиши в (keycode, ctrl, shift, alt).

    'Ctrl+Pause' → (KEY_PAUSE, True, False, False).
    Возвращает None для keycode если клавиша не распознана.
    """
    parts = [p.strip() for p in hotkey_str.split('+')]
    ctrl = 'Ctrl' in parts
    shift = 'Shift' in parts
    alt = 'Alt' in parts
    key_parts = [p for p in parts if p not in ('Ctrl', 'Shift', 'Alt')]
    if not key_parts:
        return None, ctrl, shift, alt
    keycode = getattr(ecodes, 'KEY_' + key_parts[0].upper(), None)
    return keycode, ctrl, shift, alt


class KeyboardDaemon(QThread):
    """Демон клавиатуры: читает evdev, детектирует и переключает раскладку.

    Работает в отдельном QThread. Связывает WordTracker + Detector + Switcher.
    Сигнал layout_changed эмитируется при каждом переключении.
    """

    layout_changed = pyqtSignal(str)  # имя новой раскладки ('en' / 'ru')

    def __init__(
        self,
        config: Config,
        injector: Injector,
        layout_manager: LayoutManager,
        en_layout: Layout,
        ru_layout: Layout,
        device: object | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._layout_manager = layout_manager
        self._en = en_layout
        self._ru = ru_layout
        self._device = device

        self._word_tracker = WordTracker()
        self._after_word = False
        self._word_layout = ''
        self._detector = Detector(config)
        self._switcher = Switcher(injector, layout_manager, config.undo_stack_depth)

        self._shift = False
        self._ctrl = False
        self._alt = False

        self._current_window = ''
        self._excluded_windows: set[str] = set()

        self._hotkeys = self._build_hotkeys()
        self._running = False

    def _build_hotkeys(self) -> list[tuple[int, bool, bool, bool, object]]:
        """Построить список (keycode, ctrl, shift, alt, action) из конфига."""
        mapping = [
            (self._config.hotkey_switch_word, self._on_switch_word),
            (self._config.hotkey_switch_selection, self._on_switch_selection),
            (self._config.hotkey_undo, self._on_undo),
            (self._config.hotkey_toggle_window, self._on_toggle_window),
        ]
        result = []
        for hotkey_str, action in mapping:
            keycode, ctrl, shift, alt = _parse_hotkey(hotkey_str)
            if keycode is not None:
                result.append((keycode, ctrl, shift, alt, action))
        return result

    # --- QThread ---

    def run(self) -> None:
        """Главный цикл: читает evdev-события до вызова stop()."""
        self._running = True
        for event in self._device.read_loop():
            if not self._running:
                break
            if event.type == ecodes.EV_KEY:
                self._process_event(event)

    def stop(self) -> None:
        """Остановить цикл событий."""
        self._running = False

    def reload_hotkeys(self) -> None:
        """Перестроить список горячих клавиш из текущего конфига."""
        self._hotkeys = self._build_hotkeys()

    # --- Управление исключёнными окнами ---

    def set_active_window(self, window_name: str) -> None:
        """Обновить имя текущего активного окна."""
        self._current_window = window_name

    def toggle_current_window(self) -> None:
        """Временно включить/отключить автопереключение для текущего окна."""
        if self._current_window in self._excluded_windows:
            self._excluded_windows.discard(self._current_window)
        else:
            self._excluded_windows.add(self._current_window)

    def is_window_excluded(self, window_name: str = '') -> bool:
        name = window_name or self._current_window
        return name in self._excluded_windows

    # --- Раскладки ---

    @property
    def current_layout(self) -> Layout:
        """Определить текущую раскладку по индексу из LayoutManager."""
        idx = self._layout_manager.get_current()
        layouts = self._layout_manager.list_layouts()
        if idx < len(layouts) and layouts[idx] == self._ru.xkb_name:
            return self._ru
        return self._en

    @property
    def alt_layout(self) -> Layout:
        return self._ru if self.current_layout is self._en else self._en

    # --- Обработка событий ---

    def _process_event(self, event: object) -> None:
        """Обработать одно EV_KEY событие (down/up/hold)."""
        code: int = event.code
        value: int = event.value  # 0=up 1=down 2=hold

        if code in _SHIFT_KEYS:
            self._shift = value != 0
            return
        if code in _CTRL_KEYS:
            self._ctrl = value != 0
            return
        if code in _ALT_KEYS:
            self._alt = value != 0
            return

        if value == 2:
            log.debug('автоповтор клавиши %d — не учитывается', code)
        if value != 1:  # только key_down
            return

        # Проверить горячие клавиши
        for keycode, req_ctrl, req_shift, req_alt, action in self._hotkeys:
            if (code == keycode
                    and self._ctrl == req_ctrl
                    and self._shift == req_shift
                    and self._alt == req_alt):
                log.info('горячая клавиша %d: %s', code, action.__name__)
                action()
                return

        self._handle_typing(code)

    def _handle_typing(self, code: int) -> None:
        if self._ctrl or self._alt:
            self._reset_word(f'сочетание с Ctrl/Alt, клавиша {code}')
            return

        if code == ecodes.KEY_ESC:
            self._reset_word('Esc')
            return

        if code == ecodes.KEY_BACKSPACE:
            self._word_tracker.on_backspace()
            log.debug('backspace, буфер %r', self._word_tracker.get_current())
            return

        if code in _RESET_KEYS:
            self._reset_word(f'Tab/Enter (клавиша {code}) — без переключения')
            return

        ch = self._resolve_char(code)
        if ch is None:
            self._reset_word(f'клавиша {code} без символа (навигация, F-клавиши, блок без NumLock)')
            return

        log.debug('key %d → %r, буфер %r', code, ch, self._word_tracker.get_current())
        if ch in STOP_CHARS:
            keys = self._word_tracker.get_keys()
            word = self._word_tracker.on_stop_char(ch)
            if word and self._config.auto_switch:
                self._auto_switch(word, ch, keys)
            self._after_word = self._after_word or bool(word)
        else:
            self._check_layout_unchanged()
            self._word_tracker.add_char(ch, (code, self._shift))
            self._switcher.on_typing()
            if self._ends_word(code):
                self._finish_word_on_mark()

    def _ends_word(self, code: int) -> bool:
        """Знак, который завершает слово: не буква, не цифра и не дефис ни в одной раскладке.

        ',' '.' ';' '[' ... в английской раскладке — буквы русской, поэтому слово не завершают.
        """
        key = [(code, self._shift)]
        chars = self._en.render(key) + self._ru.render(key)
        return bool(chars) and not any(c.isalpha() or c.isdigit() or c in _IN_WORD_MARKS for c in chars)

    def _finish_word_on_mark(self) -> None:
        """Слово со знаком на конце ('ghbdtn?') переключается сразу, без пробела.

        Знак до первой буквы ('(' или '"' перед словом) слово не завершает, а входит в него.
        """
        word = self._word_tracker.get_current()
        keys = self._word_tracker.get_keys()
        remapped = self._remap(word, keys, self.current_layout, self.alt_layout)
        if not any(c.isalpha() for c in word + remapped):
            return
        self._word_tracker.on_reset()
        if self._config.auto_switch:
            self._auto_switch(word, '', keys)
        self._after_word = True

    def _check_layout_unchanged(self) -> None:
        """Сбросить слово, если раскладку сменили посреди него (вручную, мимо демона).

        Буквы до смены раскладки к новому слову не относятся: иначе 'цпу' + смена
        раскладки + 'wge' склеивались в одно слово 'цпуwge' и переключались целиком.
        """
        layout = self.current_layout.name
        if self._word_tracker.get_current() and layout != self._word_layout:
            self._reset_word(f'раскладка сменилась посреди слова ({self._word_layout} → {layout})')
        self._word_layout = layout

    def _reset_word(self, reason: str = '') -> None:
        if self._word_tracker.get_current():
            log.debug('слово %r сброшено: %s', self._word_tracker.get_current(), reason or 'сброс')
        self._word_tracker.on_reset()
        self._after_word = False

    def _resolve_char(self, code: int) -> str | None:
        if code in _STOP_KEY_CHARS:
            return _STOP_KEY_CHARS[code]
        layout = self.current_layout
        if code in layout.keypad:
            if code in _KEYPAD_NUMLOCK_KEYS:
                numlock = self._numlock_on()
                log.debug('цифровой блок %d: NumLock %s, Shift %s', code, numlock, self._shift)
                if self._shift or not numlock:
                    return None
            return layout.keypad[code]
        return layout.upper.get(code) if self._shift else layout.lower.get(code)

    def _numlock_on(self) -> bool:
        """Состояние NumLock по светодиоду устройства. Не удалось прочитать — False."""
        leds = getattr(self._device, 'leds', None)
        if leds is None:
            return False
        try:
            return ecodes.LED_NUML in leds()
        except OSError:
            return False

    @staticmethod
    def _remap(word: str, keys: list[tuple[int, bool]] | None, current: Layout, alt: Layout) -> str:
        return alt.render(keys) if keys is not None else current.remap_to(word, alt)

    def _auto_switch(
        self, word: str, stop_char: str = '', keys: list[tuple[int, bool]] | None = None,
    ) -> None:
        if self._current_window in self._excluded_windows:
            log.debug('слово %r: окно %r исключено', word, self._current_window)
            return
        if any(app in self._current_window for app in self._config.excluded_apps):
            log.debug('слово %r: приложение окна %r исключено', word, self._current_window)
            return
        current = self.current_layout
        alt = self.alt_layout
        remapped = self._remap(word, keys, current, alt)
        switch = self._detector.should_switch(word, current, alt, remapped)
        log.debug('слово %r → %r (%s→%s), стоп %r: %s', word, remapped, current.name, alt.name,
                  stop_char, 'переключаем' if switch else 'нет')
        if switch:
            if self._after_word:
                prefix = 0
                while prefix < len(word) and not word[prefix].isalpha() and not remapped[prefix].isalpha():
                    prefix += 1
                word, remapped = word[prefix:], remapped[prefix:]
            try:
                self._switcher.switch_word(word, current, alt, stop_char, remapped)
            except Exception:
                log.exception('ошибка переключения слова %r', word)
                return
            log.info('переключено %r → %r, раскладка %s', word, remapped, alt.name)
            self.layout_changed.emit(alt.name)

    # --- Действия горячих клавиш ---

    def _on_switch_word(self) -> None:
        word = self._word_tracker.get_current()
        if word:
            current = self.current_layout
            alt = self.alt_layout
            remapped = self._remap(word, self._word_tracker.get_keys(), current, alt)
            log.info('ручное переключение %r → %r (%s→%s)', word, remapped, current.name, alt.name)
            self._switcher.switch_word(word, current, alt, remapped=remapped)
            self._word_tracker.on_reset()
            self.layout_changed.emit(alt.name)
        else:
            log.info('ручное переключение: слова в буфере нет')

    def _on_switch_selection(self) -> None:
        current = self.current_layout
        alt = self.alt_layout
        if self._switcher.switch_selection(current, alt):
            log.info('выделение переключено (%s→%s)', current.name, alt.name)
            self.layout_changed.emit(alt.name)
        else:
            log.info('переключение выделения: выделения нет')

    def _on_undo(self) -> None:
        log.info('отмена переключения: %s', 'выполнена' if self._switcher.undo() else 'отменять нечего')

    def _on_toggle_window(self) -> None:
        self.toggle_current_window()
        log.info('окно %r: автопереключение %s', self._current_window,
                 'выключено' if self.is_window_excluded() else 'включено')
