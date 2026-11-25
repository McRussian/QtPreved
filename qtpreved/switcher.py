from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

from qtpreved.kbd_map import Layout

log = logging.getLogger(__name__)


class Injector(ABC):
    """Инжект нажатий клавиш и работа с выделением/буфером обмена."""

    @abstractmethod
    def inject_backspaces(self, n: int) -> None:
        """Инжектировать n нажатий Backspace."""

    @abstractmethod
    def inject_text(self, text: str, layout: Layout) -> None:
        """Инжектировать текст посимвольно как нажатия клавиш."""

    @abstractmethod
    def get_selection(self) -> str | None:
        """Вернуть текущее выделение (primary selection). None если нет выделения."""

    @abstractmethod
    def replace_selection(self, new_text: str) -> None:
        """Заменить выделение новым текстом через буфер обмена + Ctrl+V."""

    def inject_stop_char(self, ch: str) -> None:
        """Инжектировать стоп-символ. No-op в базовом классе (переопределяется в UinputInjector)."""

    def paste_text(self, text: str) -> None:
        """Вставить текст через буфер обмена (layout-independent). No-op в базовом классе."""


class LayoutManager(ABC):
    """Управление активной раскладкой клавиатуры."""

    @abstractmethod
    def get_current(self) -> int:
        """Вернуть индекс текущей активной раскладки."""

    @abstractmethod
    def set_layout(self, index: int) -> None:
        """Переключить раскладку по индексу."""

    @abstractmethod
    def list_layouts(self) -> list[str]:
        """Вернуть список xkb-имён раскладок в порядке индексов."""


@dataclass
class _UndoEntry:
    new_text_len: int           # длина инжектированного текста (без стоп-символа)
    original_text: str          # исходный текст для восстановления
    stop_char: str              # стоп-символ, которым завершилось слово ('' при ручном switch)
    original_layout: Layout     # раскладка для инжекта исходного текста
    original_layout_idx: int    # индекс раскладки для восстановления


class Switcher:
    """Логика переключения раскладки с поддержкой undo.

    Принимает абстрактные Injector и LayoutManager — реальные или тестовые моки.
    Undo-стек хранит историю переключений с настраиваемой глубиной.
    """

    def __init__(
        self,
        injector: Injector,
        layout_manager: LayoutManager,
        stack_depth: int = 10,
    ) -> None:
        self._injector = injector
        self._layout_manager = layout_manager
        self._undo_stack: deque[_UndoEntry] = deque(maxlen=max(0, stack_depth))

    def switch_word(
        self,
        word: str,
        current_layout: Layout,
        alt_layout: Layout,
        stop_char: str = '',
        remapped: str | None = None,
    ) -> bool:
        """Переключить последнее набранное слово в альтернативную раскладку.

        stop_char — стоп-символ, уже вставленный в текст после слова (при авто-переключении).
        Если передан, удаляется как часть слова и восстанавливается после него.
        remapped — слово в альтернативной раскладке, если уже собрано по нажатиям;
        иначе вычисляется через remap_to.
        """
        if remapped is None:
            remapped = current_layout.remap_to(word, alt_layout)
        original_idx = self._layout_manager.get_current()
        new_idx = self._find_layout_index(alt_layout)

        # +1 чтобы удалить стоп-символ, уже находящийся перед курсором
        self._injector.inject_backspaces(len(word) + bool(stop_char))
        # Стоп-символ вставляется вместе со словом: вставка из буфера асинхронна,
        # и отдельное нажатие пробела приложение может обработать раньше вставки
        self._injector.paste_text(remapped + stop_char)
        self._layout_manager.set_layout(new_idx)
        log.debug('слово %r → %r, стоп %r, раскладка %d → %d', word, remapped, stop_char, original_idx, new_idx)

        self._undo_stack.append(_UndoEntry(
            new_text_len=len(remapped),
            stop_char=stop_char,
            original_text=word,
            original_layout=current_layout,
            original_layout_idx=original_idx,
        ))
        return True

    def switch_selection(self, current_layout: Layout, alt_layout: Layout) -> bool:
        """Переключить раскладку для выделенного текста.

        Читает primary selection, ремапит, заменяет через буфер обмена.
        Возвращает False если нет выделения.
        """
        selected = self._injector.get_selection()
        if not selected:
            return False

        remapped = current_layout.remap_to(selected, alt_layout)
        original_idx = self._layout_manager.get_current()
        new_idx = self._find_layout_index(alt_layout)

        self._injector.replace_selection(remapped)
        log.debug('выделение %r → %r, раскладка %d → %d', selected, remapped, original_idx, new_idx)
        self._layout_manager.set_layout(new_idx)

        self._undo_stack.append(_UndoEntry(
            new_text_len=len(remapped),
            stop_char='',
            original_text=selected,
            original_layout=current_layout,
            original_layout_idx=original_idx,
        ))
        return True

    def undo(self) -> bool:
        """Отменить последнее переключение.

        Удаляет инжектированный текст backspace-ами, вводит исходный текст,
        восстанавливает исходную раскладку. Возвращает True если было что отменять.
        """
        if not self._undo_stack:
            return False

        entry = self._undo_stack.pop()
        self._injector.inject_backspaces(entry.new_text_len + bool(entry.stop_char))
        self._injector.paste_text(entry.original_text + entry.stop_char)
        self._layout_manager.set_layout(entry.original_layout_idx)
        log.debug('отмена: стёрто %d, возвращено %r, раскладка → %d',
                  entry.new_text_len + bool(entry.stop_char), entry.original_text + entry.stop_char,
                  entry.original_layout_idx)
        return True

    def on_typing(self) -> None:
        """Сбросить undo-стек при вводе нового символа после переключения."""
        if self._undo_stack:
            log.debug('новый ввод — история отмены очищена (%d)', len(self._undo_stack))
        self._undo_stack.clear()

    @property
    def undo_stack_size(self) -> int:
        """Текущий размер undo-стека."""
        return len(self._undo_stack)

    def _find_layout_index(self, layout: Layout) -> int:
        """Найти индекс раскладки по xkb_name. Возвращает 0 если не найдена."""
        layouts = self._layout_manager.list_layouts()
        try:
            return layouts.index(layout.xkb_name)
        except ValueError:
            return 0
