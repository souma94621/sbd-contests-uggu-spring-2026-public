"""Хэш сертификационного пакета (архив)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """
    Вычисляет SHA-256 содержимого файла (например .tar.gz пакета).

    :param path: путь к файлу
    :returns: шестнадцатеричная строка
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
