from __future__ import annotations

STOP_CHARS: frozenset[str] = frozenset({
    ' ', '\t', '\n', '\r',
    '.', ',', '!', '?', ';', ':', '-',
    '(', ')', '[', ']', '{', '}', '"',
})


class WordTracker:
    """Отслеживает текущее набираемое слово на основе потока символов.

    Накапливает символы в буфере. При получении стоп-символа возвращает
    накопленное слово и сбрасывает буфер. Backspace убирает последний символ.
    Сброс (Esc, Ctrl+key) очищает буфер без возврата слова.
    """

    def __init__(self) -> None:
        self._buffer: list[str] = []

    def add_char(self, ch: str) -> None:
        """Добавить символ к текущему слову."""
        self._buffer.append(ch)

    def on_stop_char(self, ch: str) -> str | None:
        """Зафиксировать конец слова стоп-символом.

        Возвращает накопленное слово если оно непустое, иначе None.
        Несколько стоп-символов подряд не порождают пустые слова.
        """
        word = ''.join(self._buffer)
        self._buffer.clear()
        return word if word else None

    def on_backspace(self) -> None:
        """Удалить последний символ из буфера. На пустом буфере — no-op."""
        if self._buffer:
            self._buffer.pop()

    def on_reset(self) -> None:
        """Сбросить буфер без возврата слова (Esc, Ctrl+key, Alt+key)."""
        self._buffer.clear()

    def get_current(self) -> str:
        """Вернуть текущее содержимое буфера."""
        return ''.join(self._buffer)
