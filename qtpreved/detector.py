from __future__ import annotations

import json
import logging
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

from qtpreved.config import Config
from qtpreved.kbd_map import Layout

log = logging.getLogger(__name__)

TRIGRAMS_DIR = Path(__file__).parent.parent / 'resources' / 'trigrams'

# Знаки, обычные на краю слова, и их логарифмическая «цена».
# Редкие на краю символы ('[', '`', '@', ...) стоят дорого: чаще всего это буквы
# другой раскладки ('[kt,' — 'хлеб', 'to`' — 'ещё'), а не настоящая пунктуация.
EDGE_PUNCTUATION = frozenset('.,!?:;()"\'-')
EDGE_PUNCTUATION_LOGPROB = math.log(0.05)
EDGE_OTHER_LOGPROB = -8.0


def load_trigrams(path: Path) -> dict[str, int]:
    """Загрузить таблицу триграмм (тройка символов → число вхождений) из JSON-файла.

    Таблица строится tools/build_trigrams.py. Raises FileNotFoundError, json.JSONDecodeError.
    """
    return json.loads(path.read_text(encoding='utf-8'))


class TrigramModel:
    """Символьная языковая модель на триграммах с интерполяцией.

    Вероятность символа c после ab — взвешенная сумма оценок по триграмме abc,
    биграмме bc и частоте самого c (со сглаживанием). Поэтому неизвестная тройка
    не обнуляет оценку слова, а только снижает её; символ вне алфавита языка
    (например ';' в английском варианте русского 'уже') снижает сильнее всего.

    Веса WEIGHTS (триграмма, биграмма, символ) — потолок для частых контекстов.
    Для редкого контекста вес уменьшается: λ · count / (count + CONTEXT_WEIGHT), остаток
    уходит частоте символа. Иначе случайные тройки из мусора корпуса ('ъъъ' при
    контексте 'ъъ', встреченном 5 раз) получали бы огромную вероятность.

    Слово дополняется границами как при построении таблицы: '  слово '.
    """

    WEIGHTS = (0.6, 0.3, 0.1)
    CONTEXT_WEIGHT = 20.0

    def __init__(self, trigrams: dict[str, int]) -> None:
        self._c3 = trigrams
        self._c2: Counter[str] = Counter()
        self._c1: Counter[str] = Counter()
        for tri, n in trigrams.items():
            self._c2[tri[:2]] += n
            self._c1[tri[0]] += n
        self._total = sum(self._c1.values())
        self._vocab = len(self._c1)

    def _char_prob(self, a: str, b: str, c: str) -> float:
        w3_max, w2_max, _ = self.WEIGHTS
        ab_count = self._c2.get(a + b, 0)
        p3 = self._c3.get(a + b + c, 0) / ab_count if ab_count else 0.0
        w3 = w3_max * ab_count / (ab_count + self.CONTEXT_WEIGHT)
        b_count = self._c1.get(b, 0)
        p2 = self._c2.get(b + c, 0) / b_count if b_count else 0.0
        w2 = w2_max * b_count / (b_count + self.CONTEXT_WEIGHT)
        p1 = (self._c1.get(c, 0) + 1) / (self._total + self._vocab)
        return w3 * p3 + w2 * p2 + (1 - w3 - w2) * p1

    def logprob(self, text: str) -> tuple[float, int]:
        """Сумма логарифмов вероятностей символов слова и число слагаемых (включая границу)."""
        padded = f'  {text.lower()} '
        logs = [math.log(self._char_prob(*padded[i:i + 3])) for i in range(len(padded) - 2)]
        return sum(logs), len(logs)

    def score(self, text: str) -> float:
        """Средний логарифм вероятности символа (≤ 0, чем ближе к 0 — тем правдоподобнее).

        Знаки препинания по краям оцениваются отдельно от слова: обычные
        (EDGE_PUNCTUATION) дёшево, прочие — дорого. Текст без букв — минус бесконечность.
        """
        core = strip_non_letters(text)
        if not core:
            return -math.inf
        start = text.index(core)
        edges = text[:start] + text[start + len(core):]
        total, count = self.logprob(core)
        for ch in edges:
            total += EDGE_PUNCTUATION_LOGPROB if ch in EDGE_PUNCTUATION else EDGE_OTHER_LOGPROB
        return total / (count + len(edges))


# Загружаются при старте модуля — по аналогии с раскладками
EN_MODEL = TrigramModel(load_trigrams(TRIGRAMS_DIR / 'en.json'))
RU_MODEL = TrigramModel(load_trigrams(TRIGRAMS_DIR / 'ru.json'))

# Маппинг имени раскладки на языковую модель
MODELS: dict[str, TrigramModel] = {
    'en': EN_MODEL,
    'ru': RU_MODEL,
}


def score_text(text: str, model: TrigramModel) -> float:
    """Оценить текст языковой моделью.

    Чистая функция: принимает произвольную модель.
    Используется в тестах и для внешних вызовов.
    Текст приводится к нижнему регистру перед оценкой.
    """
    return model.score(text)


def strip_non_letters(text: str) -> str:
    start, end = 0, len(text)
    while start < end and not text[start].isalpha():
        start += 1
    while end > start and not text[end - 1].isalpha():
        end -= 1
    return text[start:end]


def strip_common_edges(text: str, remapped: str) -> tuple[str, str]:
    """Отрезать по краям символы, которые не буквы в обоих вариантах слова.

    '[kt,' / 'хлеб' → без изменений: '[' и ',' — буквы в русском варианте.
    '(ghbdtn?' / '(привет,' → 'ghbdtn?' / 'привет,' — '(' не буква ни там, ни там.
    Варианты одной длины (посимвольный пересчёт), обрезаются по одним позициям.
    """
    start, end = 0, len(text)
    while start < end and not text[start].isalpha() and not remapped[start].isalpha():
        start += 1
    while end > start and not text[end - 1].isalpha() and not remapped[end - 1].isalpha():
        end -= 1
    return text[start:end], remapped[start:end]


@lru_cache(maxsize=2000)
def _score_cached(text_lower: str, layout_name: str) -> float:
    """Кешированная оценка текста по имени раскладки.

    Принимает уже приведённый к нижнему регистру текст — ключ кеша должен
    быть стабильным. При добавлении новых раскладок кеш работает автоматически
    через MODELS без изменений кода. Раскладка без модели — минус бесконечность.
    """
    model = MODELS.get(layout_name)
    return model.score(text_lower) if model else -math.inf


def should_switch(
    word: str,
    current_layout: Layout,
    alt_layout: Layout,
    min_length: int = 3,
    skip_uppercase: bool = True,
    margin: float = 0.25,
    min_alt_logprob: float = -6.0,
    remapped: str | None = None,
) -> bool:
    """Определить, набрано ли слово не в той раскладке.

    Ремапит слово в альтернативную раскладку и сравнивает оценки языковых моделей.
    Переключение рекомендуется, если альтернативный вариант правдоподобнее текущего
    больше чем на margin и сам достаточно правдоподобен (оценка выше min_alt_logprob).

    Слова короче min_length и ALL CAPS (при skip_uppercase=True) пропускаются.
    remapped — слово в альтернативной раскладке, если уже собрано по нажатиям.
    Оценка кешируется по (слово, имя_раскладки) — масштабируется на любое
    количество раскладок без повторных вычислений.
    """
    if remapped is None:
        remapped = current_layout.remap_to(word, alt_layout)
    current_core, alt_core = strip_common_edges(word, remapped)
    if len(current_core) < min_length or not any(ch.isalpha() for ch in current_core):
        log.debug('%r: короче %d символов или без букв — не анализируется', word, min_length)
        return False
    if skip_uppercase and alt_core.isupper():
        log.debug('%r: верхний регистр — пропуск', word)
        return False

    current_score = _score_cached(current_core.lower(), current_layout.name)
    alt_score = _score_cached(alt_core.lower(), alt_layout.name)

    result = alt_score - current_score > margin and alt_score > min_alt_logprob
    log.debug('%r [%s %.2f] / %r [%s %.2f]: разница %+.2f (запас %.2f, минимум %.1f) → %s',
              current_core, current_layout.name, current_score, alt_core, alt_layout.name, alt_score,
              alt_score - current_score, margin, min_alt_logprob, 'переключать' if result else 'нет')
    return result


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

        Перед анализом проверяет список excluded_words из конфига — без учёта регистра
        и знаков по краям ('Ghbdtn,' исключено при 'ghbdtn' в списке).
        Параметры анализа (порог, длина, регистр) тоже берутся из конфига.
        """
        excluded = {w.casefold() for w in self._config.excluded_words}
        if word.casefold() in excluded or strip_non_letters(word).casefold() in excluded:
            log.debug('%r: в словах-исключениях', word)
            return False
        # should_switch здесь — модульная функция выше, не рекурсия
        return should_switch(
            word, current_layout, alt_layout,
            min_length=self._config.min_word_length,
            skip_uppercase=self._config.skip_uppercase,
            margin=self._config.detection_margin,
            min_alt_logprob=self._config.min_alt_logprob,
            remapped=remapped,
        )
