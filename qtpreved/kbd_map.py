from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from evdev import ecodes


@dataclass
class Layout:
    """Раскладка клавиатуры: маппинг evdev-кодов клавиш на символы.

    Хранит два словаря — без Shift и с Shift. Включает все печатные клавиши,
    в том числе цифровой ряд и знаки: символы на них различаются между раскладками
    (Shift+2 — '@' в EN и '"' в RU, '/' — '/' в EN и '.' в RU).
    """

    name: str
    xkb_name: str
    lower: dict[int, str]
    upper: dict[int, str]

    @cached_property
    def _char_to_key(self) -> dict[str, tuple[int, bool]]:
        """Обратный маппинг: символ → (keycode, нужен_shift).

        Строится лениво и кешируется. Пустые строки пропускаются —
        JSON может содержать "" для клавиш без символа в данной раскладке.
        """
        result: dict[str, tuple[int, bool]] = {}
        for keycode, char in self.lower.items():
            if char:
                result[char] = (keycode, False)
        for keycode, char in self.upper.items():
            if char:
                result[char] = (keycode, True)
        return result

    def remap_to(self, text: str, target: Layout) -> str:
        """Перевести текст из текущей раскладки в целевую.

        Для каждого символа находит физическую клавишу в текущей раскладке
        и берёт символ той же клавиши в целевой. Символы, не входящие
        в раскладку (цифры, эмодзи и т.п.), остаются без изменений.
        """
        result = []
        for ch in text:
            if ch in self._char_to_key:
                keycode, shifted = self._char_to_key[ch]
                table = target.upper if shifted else target.lower
                result.append(table.get(keycode, ch))
            else:
                result.append(ch)
        return ''.join(result)


def load_layout(path: Path) -> Layout:
    """Загрузить раскладку из JSON-файла.

    Имена клавиш в формате 'KEY_Q' резолвятся в числовые evdev-коды
    через evdev.ecodes. Raises FileNotFoundError, json.JSONDecodeError, KeyError.
    """
    data = json.loads(path.read_text(encoding='utf-8'))
    lower = {getattr(ecodes, key): char for key, char in data['lower'].items()}
    upper = {getattr(ecodes, key): char for key, char in data['upper'].items()}
    return Layout(name=data['name'], xkb_name=data['xkb_name'], lower=lower, upper=upper)


LAYOUTS_DIR = Path(__file__).parent.parent / 'resources' / 'layouts'


def load_default_layouts() -> tuple[Layout, Layout]:
    """Загрузить встроенные раскладки EN и RU."""
    return load_layout(LAYOUTS_DIR / 'en.json'), load_layout(LAYOUTS_DIR / 'ru.json')
