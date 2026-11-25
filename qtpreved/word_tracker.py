from __future__ import annotations

STOP_CHARS: frozenset[str] = frozenset({' ', '\t', '\n', '\r'})


class WordTracker:
    """Отслеживает текущее набираемое слово на основе потока символов.

    Накапливает символы в буфере. При получении стоп-символа возвращает
    накопленное слово и сбрасывает буфер. Backspace убирает последний символ.
    Сброс (Esc, Ctrl+key) очищает буфер без возврата слова.
    """

    def __init__(self) -> None:
        self._buffer: list[str] = []
        self._keys: list[tuple[int, bool] | None] = []

    def add_char(self, ch: str, key: tuple[int, bool] | None = None) -> None:
        """Добавить символ к текущему слову.

        key — нажатие (keycode, shift), которым символ набран. Нужно, чтобы пересобрать
        слово в другой раскладке без неоднозначности обратного маппинга символов.
        """
        self._buffer.append(ch)
        self._keys.append(key)

    def on_stop_char(self, ch: str) -> str | None:
        """Зафиксировать конец слова стоп-символом.

        Возвращает накопленное слово если оно непустое, иначе None.
        Несколько стоп-символов подряд не порождают пустые слова.
        """
        word = ''.join(self._buffer)
        self._buffer.clear()
        self._keys.clear()
        return word if word else None

    def on_backspace(self) -> None:
        """Удалить последний символ из буфера. На пустом буфере — no-op."""
        if self._buffer:
            self._buffer.pop()
            self._keys.pop()

    def on_reset(self) -> None:
        """Сбросить буфер без возврата слова (Esc, Ctrl+key, Alt+key)."""
        self._buffer.clear()
        self._keys.clear()

    def get_current(self) -> str:
        """Вернуть текущее содержимое буфера."""
        return ''.join(self._buffer)

    def get_keys(self) -> list[tuple[int, bool]] | None:
        """Вернуть нажатия текущего слова. None если хотя бы один символ добавлен без нажатия."""
        if any(key is None for key in self._keys):
            return None
        return list(self._keys)
