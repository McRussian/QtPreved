from __future__ import annotations

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

        if value != 1:  # только key_down
            return

        # Проверить горячие клавиши
        for keycode, req_ctrl, req_shift, req_alt, action in self._hotkeys:
            if (code == keycode
                    and self._ctrl == req_ctrl
                    and self._shift == req_shift
                    and self._alt == req_alt):
                action()
                return

        self._handle_typing(code)

    def _handle_typing(self, code: int) -> None:
        if self._ctrl or self._alt:
            self._word_tracker.on_reset()
            return

        if code == ecodes.KEY_ESC:
            self._word_tracker.on_reset()
            return

        if code == ecodes.KEY_BACKSPACE:
            self._word_tracker.on_backspace()
            return

        ch = self._resolve_char(code)
        if ch is None:
            return

        if ch in STOP_CHARS:
            word = self._word_tracker.on_stop_char(ch)
            if word and self._config.auto_switch:
                self._auto_switch(word)
        else:
            self._word_tracker.add_char(ch)
            self._switcher.on_typing()

    def _resolve_char(self, code: int) -> str | None:
        if code in _STOP_KEY_CHARS:
            return _STOP_KEY_CHARS[code]
        layout = self.current_layout
        return layout.upper.get(code) if self._shift else layout.lower.get(code)

    def _auto_switch(self, word: str) -> None:
        if self._current_window in self._excluded_windows:
            return
        if any(app in self._current_window for app in self._config.excluded_apps):
            return
        current = self.current_layout
        alt = self.alt_layout
        if self._detector.should_switch(word, current, alt):
            self._switcher.switch_word(word, current, alt)
            self.layout_changed.emit(alt.name)

    # --- Действия горячих клавиш ---

    def _on_switch_word(self) -> None:
        word = self._word_tracker.get_current()
        if word:
            current = self.current_layout
            alt = self.alt_layout
            self._switcher.switch_word(word, current, alt)
            self._word_tracker.on_reset()
            self.layout_changed.emit(alt.name)

    def _on_switch_selection(self) -> None:
        current = self.current_layout
        alt = self.alt_layout
        if self._switcher.switch_selection(current, alt):
            self.layout_changed.emit(alt.name)

    def _on_undo(self) -> None:
        self._switcher.undo()

    def _on_toggle_window(self) -> None:
        self.toggle_current_window()
