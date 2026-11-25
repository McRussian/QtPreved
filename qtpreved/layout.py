from __future__ import annotations

import logging
import re
import subprocess

from qtpreved.switcher import LayoutManager

log = logging.getLogger(__name__)

_DEST = 'org.kde.keyboard'
_PATH = '/Layouts'
_IFACE = 'org.kde.KeyboardLayouts'


def _dbus_call(method: str, *args: str) -> str:
    """Вызвать метод KDE DBus и вернуть stdout.

    Raises subprocess.CalledProcessError при ненулевом коде возврата.
    """
    cmd = [
        'dbus-send', '--session', '--print-reply',
        f'--dest={_DEST}', _PATH,
        f'{_IFACE}.{method}',
        *args,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        log.error('DBus %s%s: код %d, %s', method, args, e.returncode, (e.stderr or '').strip())
        raise
    return result.stdout


class KDELayoutManager(LayoutManager):
    """Управление раскладкой через KDE DBus (org.kde.keyboard /Layouts)."""

    def get_current(self) -> int:
        """Вернуть индекс текущей раскладки. Возвращает 0 при ошибке парсинга."""
        output = _dbus_call('getLayout')
        match = re.search(r'uint32\s+(\d+)', output)
        return int(match.group(1)) if match else 0

    def set_layout(self, index: int) -> None:
        """Переключить раскладку по индексу через DBus."""
        log.debug('DBus setLayout %d', index)
        _dbus_call('setLayout', f'uint32:{index}')

    def list_layouts(self) -> list[str]:
        """Вернуть список xkb-имён раскладок в порядке индексов.

        DBus-вывод содержит struct с тремя string-полями на раскладку.
        Берём только первое поле каждого struct — это xkb id ('us', 'ru', …).
        """
        output = _dbus_call('getLayoutsList')
        result = []
        for struct_body in re.findall(r'struct\s*\{(.*?)\}', output, re.DOTALL):
            m = re.search(r'string\s+"([^"]*)"', struct_body)
            if m:
                result.append(m.group(1))
        return result
