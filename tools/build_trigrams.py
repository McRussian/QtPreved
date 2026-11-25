"""Построение таблицы триграмм языка из текстового корпуса.

Каждое слово дополняется границами: два пробела в начале и один в конце ('  привет '),
и считаются все тройки символов. Тройки с пробелами описывают, как слова языка
начинаются и кончаются. Каждое вхождение слова учитывается — частые слова весят
больше, как и при наборе. Тройки, встретившиеся реже MIN_COUNT раз, отбрасываются.

Использование:
    python3 tools/build_trigrams.py ru resources/trigrams/ru.json книга1.fb2 книга2.fb2 ...
    python3 tools/build_trigrams.py en resources/trigrams/en.json @список_файлов.txt

Аргумент вида @список.txt — файл со списком путей, по одному на строку.
fb2 читается как XML (берётся текст <body>), остальные файлы — как текст UTF-8.
Файлы с одинаковым содержимым (копии лицензий и т.п.) учитываются один раз.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

MIN_COUNT = 2

ALPHABETS = {
    'ru': 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
    'en': 'abcdefghijklmnopqrstuvwxyz',
}

# Апостроф между буквами — часть английского слова: don't, it's
WORD_PATTERNS = {
    'ru': r'[{a}]+',
    'en': r"[{a}]+(?:'[{a}]+)*",
}


def read_text(path: Path) -> str:
    raw = path.read_text(encoding='utf-8', errors='ignore')
    if path.suffix.lower() == '.fb2':
        bodies = re.findall(r'<body[^>]*>(.*?)</body>', raw, flags=re.S)
        raw = ' '.join(bodies)
        raw = re.sub(r'<binary[^>]*>.*?</binary>', ' ', raw, flags=re.S)
        raw = re.sub(r'<[^>]+>', ' ', raw)
    return raw


def count_trigrams(texts: list[str], lang: str) -> Counter[str]:
    word_re = re.compile(WORD_PATTERNS[lang].format(a=ALPHABETS[lang]))
    words: Counter[str] = Counter()
    for text in texts:
        words.update(word_re.findall(text.lower()))
    counts: Counter[str] = Counter()
    for word, n in words.items():
        padded = f'  {word} '
        for i in range(len(padded) - 2):
            counts[padded[i:i + 3]] += n
    return Counter({k: v for k, v in counts.items() if v >= MIN_COUNT})


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[1] not in ALPHABETS:
        print(__doc__)
        return 1
    lang, out = argv[1], Path(argv[2])
    files: list[Path] = []
    for arg in argv[3:]:
        if arg.startswith('@'):
            files += [Path(line) for line in Path(arg[1:]).read_text(encoding='utf-8').splitlines() if line]
        else:
            files.append(Path(arg))
    texts = list(dict.fromkeys(read_text(f) for f in files))
    counts = count_trigrams(texts, lang)
    ordered = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    out.write_text(json.dumps(ordered, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')
    print(f'{lang}: {len(files)} файлов, {len(texts)} уникальных, {sum(counts.values())} триграмм, {len(counts)} различных → {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
