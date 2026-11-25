from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from qtpreved.config import Config
from qtpreved.kbd_map import Layout

BIGRAMS_DIR = Path(__file__).parent.parent / 'resources' / 'bigrams'


def load_bigrams(path: Path) -> dict[str, float]:
    """Загрузить таблицу биграмм из JSON-файла.

    Raises FileNotFoundError, json.JSONDecodeError.
    """
    return json.loads(path.read_text(encoding='utf-8'))


# Загружаются при старте модуля — по аналогии с раскладками
EN_BIGRAMS: dict[str, float] = load_bigrams(BIGRAMS_DIR / 'en.json')
RU_BIGRAMS: dict[str, float] = load_bigrams(BIGRAMS_DIR / 'ru.json')

# Маппинг имени раскладки на таблицу биграмм
BIGRAMS: dict[str, dict[str, float]] = {
    'en': EN_BIGRAMS,
    'ru': RU_BIGRAMS,
}


def score_text(text: str, bigrams: dict[str, float]) -> float:
    """Оценить текст по таблице биграмм.

    Чистая функция: принимает произвольный словарь биграмм.
    Используется в тестах и для внешних вызовов.
    Текст приводится к нижнему регистру перед оценкой.
    """
    text = text.lower()
    if len(text) < 2:
        return 0.0
    total = sum(bigrams.get(text[i:i + 2], 0.0) for i in range(len(text) - 1))
    return total / (len(text) - 1)


def strip_non_letters(text: str) -> str:
    start, end = 0, len(text)
    while start < end and not text[start].isalpha():
        start += 1
    while end > start and not text[end - 1].isalpha():
        end -= 1
    return text[start:end]


@lru_cache(maxsize=2000)
def _score_cached(text_lower: str, layout_name: str) -> float:
    """Кешированная оценка текста по имени раскладки.

    Принимает уже приведённый к нижнему регистру текст — ключ кеша должен
    быть стабильным. При добавлении новых раскладок кеш работает автоматически
    через BIGRAMS без изменений кода.
    """
    bigrams = BIGRAMS.get(layout_name, {})
    if len(text_lower) < 2:
        return 0.0
    total = sum(bigrams.get(text_lower[i:i + 2], 0.0) for i in range(len(text_lower) - 1))
    return total / (len(text_lower) - 1)


def should_switch(
    word: str,
    current_layout: Layout,
    alt_layout: Layout,
    min_length: int = 3,
    skip_uppercase: bool = True,
    threshold: float = 2.0,
    min_alt_score: float = 5.0,
    remapped: str | None = None,
) -> bool:
    """Определить, набрано ли слово не в той раскладке.

    Ремапит слово в альтернативную раскладку и сравнивает биграммные оценки.
    Переключение рекомендуется, если альтернативный вариант значимо лучше
    (в threshold раз) и превышает минимальный порог min_alt_score.

    Слова короче min_length и ALL CAPS (при skip_uppercase=True) пропускаются.
    remapped — слово в альтернативной раскладке, если уже собрано по нажатиям.
    Оценка кешируется по (слово, имя_раскладки) — масштабируется на любое
    количество раскладок без повторных вычислений.
    """
    current_core = strip_non_letters(word)
    if remapped is None:
        remapped = current_layout.remap_to(word, alt_layout)
    alt_core = strip_non_letters(remapped)
    if max(len(current_core), len(alt_core)) < min_length:
        return False
    if skip_uppercase and alt_core.isupper():
        return False

    current_score = _score_cached(current_core.lower(), current_layout.name)
    alt_score = _score_cached(alt_core.lower(), alt_layout.name)

    return alt_score > current_score * threshold and alt_score > min_alt_score


class Detector:
    """Детектор неправильной раскладки, параметры берёт из Config.

    Хранит ссылку на Config — изменения настроек подхватываются автоматически.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def should_switch(
        self, word: str, current_layout: Layout, alt_layout: Layout, remapped: str | None = None,
    ) -> bool:
        """Определить, нужно ли переключить раскладку для слова.

        Перед анализом проверяет список excluded_words из конфига.
        Параметры анализа (порог, длина, регистр) тоже берутся из конфига.
        """
        if word in self._config.excluded_words or strip_non_letters(word) in self._config.excluded_words:
            return False
        # should_switch здесь — модульная функция выше, не рекурсия
        return should_switch(
            word, current_layout, alt_layout,
            min_length=self._config.min_word_length,
            skip_uppercase=self._config.skip_uppercase,
            threshold=self._config.detection_threshold,
            min_alt_score=self._config.min_alt_score,
            remapped=remapped,
        )
