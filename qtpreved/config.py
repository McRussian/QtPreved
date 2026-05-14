from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

CONFIG_PATH = Path.home() / '.config' / 'qtpreved' / 'config.json'


@dataclass
class Config:
    """Конфигурация приложения. Все поля имеют разумные дефолты."""

    # Горячие клавиши
    hotkey_switch_word: str = 'Pause'
    hotkey_switch_selection: str = 'Ctrl+Pause'
    hotkey_undo: str = 'Shift+Pause'
    hotkey_toggle_window: str = 'Alt+Pause'

    # Автопереключение
    auto_switch: bool = True
    min_word_length: int = 3
    skip_uppercase: bool = True
    detection_threshold: float = 2.0
    min_alt_score: float = 2.0

    # Undo
    undo_stack_depth: int = 10

    # Исключения
    excluded_words: list[str] = field(default_factory=list)
    excluded_apps: list[str] = field(default_factory=list)

    # Автозапуск
    autostart: bool = False


def load(path: Path = CONFIG_PATH) -> Config:
    """Загрузить конфиг из JSON-файла.

    При отсутствии файла или невалидном JSON возвращает Config с дефолтами.
    Неизвестные поля игнорируются, отсутствующие заполняются дефолтами.
    """
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return Config()

    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def save(config: Config, path: Path = CONFIG_PATH) -> None:
    """Сохранить конфиг в JSON-файл. Создаёт родительские директории если нужно."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
