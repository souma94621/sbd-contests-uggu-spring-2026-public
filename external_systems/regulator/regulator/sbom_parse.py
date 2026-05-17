"""Разбор CycloneDX SBOM для метрик размера и сложности."""

from __future__ import annotations

import json
from pathlib import Path


def count_sbom_metrics(sbom_path: Path) -> tuple[int, int]:
    """
    Возвращает число компонентов N и прокси сложности C (число рёбер зависимостей).

    :param sbom_path: путь к JSON CycloneDX
    :returns: (N, C)
    """
    data = json.loads(sbom_path.read_text(encoding="utf-8"))
    components = data.get("components") or []
    n = len(components)
    deps = data.get("dependencies") or []
    edges = 0
    for block in deps:
        edges += len(block.get("dependsOn") or [])
    return n, edges
