from __future__ import annotations

from qtpreved.kbd_map import Layout

# Частоты биграмм на 1000 биграмм в типичном тексте (по корпусным данным)

RU_BIGRAMS: dict[str, float] = {
    'ст': 29.3, 'но': 27.7, 'то': 27.2, 'на': 25.5, 'ен': 23.7,
    'ть': 22.7, 'ни': 22.4, 'ра': 22.1, 'во': 20.8, 'ко': 20.5,
    'го': 20.2, 'по': 19.8, 'ро': 19.5, 'де': 18.4, 'ле': 17.9,
    'ат': 17.3, 'ер': 17.0, 'ан': 16.8, 'ти': 16.5, 'ес': 16.2,
    'ой': 15.9, 'ов': 15.6, 'ал': 15.3, 'пр': 15.0, 'ие': 14.7,
    'от': 14.4, 'ве': 14.1, 'тр': 13.8, 'ем': 13.5, 'ос': 13.2,
    'та': 12.9, 'ло': 12.6, 'ел': 12.3, 'он': 12.0, 'об': 11.7,
    'не': 11.4, 'за': 11.1, 'ка': 10.8, 'до': 10.5, 'тс': 10.2,
    'те': 9.9,  'ли': 9.0,  'ри': 8.1,  'ит': 8.4,  'ор': 8.0,
    'ет': 7.5,  'вс': 7.5,  'ши': 7.0,  'ок': 7.2,  'ак': 6.8,
}

EN_BIGRAMS: dict[str, float] = {
    'th': 35.6, 'he': 30.7, 'in': 24.3, 'er': 20.5, 'an': 19.9,
    're': 18.5, 'on': 17.6, 'at': 14.9, 'en': 14.5, 'nd': 13.5,
    'ti': 13.4, 'es': 13.3, 'or': 12.8, 'te': 12.0, 'of': 11.7,
    'ed': 11.3, 'is': 11.0, 'it': 10.9, 'al': 10.6, 'ar': 10.5,
    'st': 10.5, 'to': 10.4, 'nt': 10.4, 'ng': 9.5,  'se': 9.3,
    'ha': 9.2,  'as': 8.7,  'ou': 8.7,  'io': 8.3,  'le': 8.0,
    've': 7.9,  'co': 7.9,  'me': 7.9,  'de': 7.7,  'hi': 7.6,
    'ri': 7.5,  'ro': 7.4,  'ic': 7.4,  'ne': 7.3,  'ea': 7.3,
    'ra': 7.2,  'ce': 7.1,  'li': 7.0,  'ch': 6.9,  'ur': 6.7,
    'si': 6.5,  'el': 6.5,  'be': 6.4,  'ma': 6.3,  'ho': 6.2,
    'ca': 6.1,  'lo': 5.5,  'no': 5.2,  'la': 5.0,  'wo': 4.0,
}

# Маппинг имени раскладки на таблицу биграмм
BIGRAMS: dict[str, dict[str, float]] = {
    'en': EN_BIGRAMS,
    'ru': RU_BIGRAMS,
}


def score_text(text: str, bigrams: dict[str, float]) -> float:
    """Оценить текст по таблице биграмм.

    Возвращает среднюю частоту биграмм на символ. Нормализация по длине
    позволяет сравнивать слова разной длины. Текст приводится к нижнему
    регистру перед оценкой.
    """
    text = text.lower()
    if len(text) < 2:
        return 0.0
    total = sum(bigrams.get(text[i:i + 2], 0.0) for i in range(len(text) - 1))
    return total / (len(text) - 1)


def should_switch(
    word: str,
    current_layout: Layout,
    alt_layout: Layout,
    min_length: int = 3,
    skip_uppercase: bool = True,
    threshold: float = 2.0,
    min_alt_score: float = 5.0,
) -> bool:
    """Определить, набрано ли слово не в той раскладке.

    Ремапит слово в альтернативную раскладку и сравнивает биграммные оценки.
    Переключение рекомендуется, если альтернативный вариант значимо лучше
    (в threshold раз) и превышает минимальный порог min_alt_score.

    Слова короче min_length и ALL CAPS (при skip_uppercase=True) пропускаются.
    """
    if len(word) < min_length:
        return False
    if skip_uppercase and word.isupper():
        return False

    current_bigrams = BIGRAMS.get(current_layout.name, {})
    alt_bigrams = BIGRAMS.get(alt_layout.name, {})

    remapped = current_layout.remap_to(word, alt_layout)
    current_score = score_text(word, current_bigrams)
    alt_score = score_text(remapped, alt_bigrams)

    return alt_score > current_score * threshold and alt_score > min_alt_score
