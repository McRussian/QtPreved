# Архитектура QtPreved

## Технический стек

- **Прототип:** Python 3 + PyQt6
- **Целевая версия:** C++ + Qt6
- **Чтение клавиатуры:** `evdev` (`/dev/input/event*`)
- **Инжект нажатий:** `uinput` — работает на уровне ядра, не зависит от X11/Wayland
- **Переключение раскладки:** KDE DBus (`org.kde.keyboard`)
- **Конвертация выделенного:** primary selection через `wl-paste --primary` (wl-clipboard)
- **Автозапуск:** KDE Autostart (`~/.config/autostart/qtpreved.desktop`)

## Структура проекта

```
QtPreved/
├── resources/
│   ├── layouts/
│   │   ├── en.json
│   │   └── ru.json
│   └── bigrams/
│       ├── en.json
│       └── ru.json
├── qtpreved/
│   ├── kbd_map.py       # Layout dataclass, загрузка JSON, remap_text()
│   ├── detector.py      # Загрузка биграмм, score_text(), should_switch()
│   ├── word_tracker.py  # Буфер текущего слова, чистая логика
│   ├── config.py        # Config dataclass, load/save JSON
│   ├── switcher.py      # Логика переключения, undo-стек
│   ├── layout.py        # KDE DBus обёртка (реализация LayoutManager)
│   ├── injector.py      # uinput обёртка (реализация Injector)
│   ├── daemon.py        # QThread: evdev → WordTracker → Switcher
│   ├── tray.py          # Системный трей PyQt6
│   └── settings.py      # Диалог настроек PyQt6
├── tests/
│   ├── test_kbd_map.py
│   ├── test_detector.py
│   ├── test_word_tracker.py
│   ├── test_config.py
│   └── test_switcher.py
├── ARCHITECTURE.md
├── README.md
├── .gitignore
└── requirements.txt
```

## Архитектурные решения

### Раскладки

- Хранятся как JSON-файлы в `qtpreved/layouts/`
- Формат: `KEY_Q`-имена ключей (evdev), символы lower/upper
- Числа и символы верхнего ряда не включаются (одинаковы во всех раскладках)
- Поддерживаемая пара: EN ↔ RU (QWERTY ↔ ЙЦУКЕН)
- Пользовательские раскладки — в будущем

### Детектор

- Биграммные таблицы хранятся в `detector.py`, не в `Layout`
- Алгоритм: сравниваем среднюю частоту биграмм слова в текущей и альтернативной раскладке
- Порог чувствительности настраивается в конфиге
- Минимальная длина слова для анализа настраивается в конфиге (дефолт: 3)
- Пропуск слов целиком в верхнем регистре настраивается в конфиге (дефолт: включено)

### Буфер слова (WordTracker)

**Стоп-символы** (завершают слово и запускают анализ):
пробел, Enter, Tab, `. , ! ? ; : - ( ) [ ] { } "`

**Не стоп-символы** (часть слова): `'` `_` `@` `/` `\`

**Сброс буфера без анализа:** Escape, любой Ctrl+key, любой Alt+key

Backspace удаляет последний символ из буфера.

### Dependency Injection

`Switcher` принимает абстрактные интерфейсы:
- `Injector` — инжект нажатий (реальный: uinput, тестовый: mock)
- `LayoutManager` — управление раскладкой (реальный: KDE DBus, тестовый: mock)

Это позволяет тестировать всю логику переключения без железа и KDE.

### Конвертация выделенного текста

1. Читаем primary selection через `wl-paste --primary` — не трогает clipboard
2. Ремапим текст
3. Кладём результат в clipboard через Qt
4. Инжектируем Ctrl+V — заменяет выделение
5. Переключаем раскладку
6. Восстанавливаем clipboard

### Undo-стек

- Хранится в `Switcher`
- Глубина стека настраивается в конфиге
- Стек сбрасывается при вводе нового символа после переключения

### Исключения

- **По приложению** — постоянные, хранятся в конфиге
- **По текущему окну** — временные, только в рантайме, сбрасываются при закрытии окна

## Стратегия тестирования

### Инструменты

- `unittest` — встроенный фреймворк, запуск: `coverage run -m unittest discover -s tests`
- `coverage` — покрытие строк и веток: `coverage report --branch`
- `hypothesis` — property-based тестирование, работает с `unittest.TestCase`

### Целевое покрытие

| Модуль | Цель |
|---|---|
| `kbd_map`, `detector`, `word_tracker` | 100% branch coverage |
| `config`, `switcher` | ~90% branch coverage |
| `daemon` | интеграционный тест, ~70% |
| `tray`, `settings` | базовые smoke-тесты |

### Методы поиска крайних случаев

1. **Классы эквивалентности** — группы входных данных с одинаковым поведением: пустое слово / короткое / нормальное / ALL CAPS / смешанный регистр / только спецсимволы
2. **Граничные значения** — ровно на границе: слово длиной `min_word_length`, стек undo ровно на максимуме и `max + 1`
3. **Property-based (hypothesis)** — инварианты: двойной ремап даёт исходный текст, score ≥ 0, и т.д.

### Ключевые property-тесты

- `remap_text(remap_text(text, en, ru), ru, en) == text` — roundtrip
- `score_text(text, bigrams) >= 0` — score неотрицателен
- `WordTracker` после любой последовательности событий не падает

## Декомпозиция задач

### Задача 1 — `Layout` + JSON-файлы ✅
- [x] Создать `en.json` и `ru.json`
- [x] `Layout` dataclass (name, xkb_name, lower, upper)
- [x] `load_layout(path)` — загрузка из JSON, резолв KEY_Q → keycode
- [x] `remap_text(text, from_layout, to_layout)` — чистая функция
- [x] Тесты: загрузка файлов, `"ghbdtn" → "привет"`, обратно, верхний регистр, неизвестные символы сохраняются

### Задача 2 — `Detector` ✅ (биграммы вынесены в `qtpreved/bigrams/`)
- [x] Биграммные таблицы EN и RU
- [x] `score_text(text, bigrams) → float`
- [x] `should_switch(word, current_layout, alt_layout) → bool`
- [x] Тесты: `"ghbdtn"` в EN → True, `"hello"` в EN → False, `"привет"` в RU → False, слово < 3 символов → False, `"HTML"` → False, `"США"` → False

### Задача 3 — `WordTracker` ✅
- [x] Класс `WordTracker`: буфер, `add_char()`, `on_stop_char()`, `on_backspace()`, `on_reset()`
- [x] Тесты: накопление буфера, стоп-символ возвращает слово и сбрасывает, backspace убирает символ, reset очищает, несколько стоп-символов подряд не дают пустое слово

### Задача 4 — `Config` ✅
- [x] `Config` dataclass со всеми полями и дефолтами, включая `min_word_length` (3) и `skip_uppercase` (True)
- [x] `load(path) → Config`, `save(config, path)`
- [x] Тесты: дефолты при пустом файле, roundtrip, отсутствующие поля → дефолт, битый JSON не падает

### Задача 5 — `Switcher` + интерфейсы
- [ ] Абстрактный `Injector`: `inject_backspaces(n)`, `inject_text(text, layout)`
- [ ] Абстрактный `LayoutManager`: `get_current()`, `set_layout(index)`, `list_layouts()`
- [ ] `Switcher`: `switch_word()`, `switch_selection()`, `undo()`
- [ ] Undo-стек с настраиваемой глубиной
- [ ] Тесты: через моки — правильная последовательность вызовов, undo возвращает оригинал, undo на пустом стеке не падает, сброс стека при новом вводе

### Задача 6 — `LayoutManager` (KDE DBus)
- [ ] `KDELayoutManager` реализует `LayoutManager`
- [ ] `get_current()`, `set_layout(index)`, `list_layouts()`
- [ ] Тесты: мок subprocess, правильные dbus-send команды, парсинг вывода

### Задача 7 — `Injector` (uinput)
- [ ] `UinputInjector` реализует `Injector`
- [ ] `inject_backspaces(n)`, `inject_text(text, layout)`
- [ ] Логика: символ → (keycode, shift) → press/release/syn
- [ ] Тесты: логика перевода символа в keycode без железа (мок uinput)

### Задача 8 — `Daemon`
- [ ] `KeyboardDaemon(QThread)`: открывает evdev, главный цикл
- [ ] Связывает `WordTracker` + `Detector` + `Switcher`
- [ ] Qt-сигналы для трея (смена раскладки, статус)
- [ ] Тест: мок evdev, последовательность `[G,H,B,D,T,N,SPACE]` → вызов `switch_word()`

### Задача 9 — `Tray` + `Settings`
- [ ] `TrayIcon`: иконка, меню, отображение текущей раскладки
- [ ] `SettingsDialog`: все настройки, список исключений
- [ ] Тесты (pytest-qt): виджеты создаются, базовые взаимодействия
