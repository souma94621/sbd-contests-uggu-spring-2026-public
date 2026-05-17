#!/usr/bin/env python3
"""
Генерация SBOM_TCB.cdx.json и SBOM_OTHER.cdx.json (CycloneDX 1.5) из манифеста JSON.

По умолчанию: src_starting_point/sbom/sbom_manifest.json → SBOM_TCB.cdx.json, SBOM_OTHER.cdx.json
  в том же каталоге (заготовка для пакета сертификации).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normalize_component(c: dict[str, Any]) -> dict[str, Any]:
    """Преобразует bom_ref из манифеста в поле CycloneDX bom-ref."""
    out: dict[str, Any] = {}
    for k, v in c.items():
        if k == "bom_ref":
            out["bom-ref"] = v
        else:
            out[k] = v
    return out


def _build_cyclonedx(
    part: dict[str, Any],
    timestamp: str,
) -> dict[str, Any]:
    """Собирает один документ CycloneDX из секции tcb или other."""
    meta = part["metadata"]
    components = [_normalize_component(x) for x in part["components"]]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": part["serialNumber"],
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "component": {
                "type": meta["type"],
                "name": meta["name"],
                "version": meta["version"],
            },
        },
        "components": components,
        "dependencies": part["dependencies"],
    }


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    """Читает манифест; возвращает данные без служебных ключей и timestamp."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    ts = raw.get("timestamp", "2026-03-24T00:00:00Z")
    data = {k: v for k, v in raw.items() if not k.startswith("_")}
    if "timestamp" in data:
        del data["timestamp"]
    return data, ts


def generate(
    manifest_path: Path,
    out_tcb: Path,
    out_other: Path,
) -> None:
    data, timestamp = load_manifest(manifest_path)
    if "tcb" not in data or "other" not in data:
        raise ValueError("манифест должен содержать ключи tcb и other")
    tcb_doc = _build_cyclonedx(data["tcb"], timestamp)
    other_doc = _build_cyclonedx(data["other"], timestamp)
    out_tcb.parent.mkdir(parents=True, exist_ok=True)
    out_other.parent.mkdir(parents=True, exist_ok=True)
    for path, doc in ((out_tcb, tcb_doc), (out_other, other_doc)):
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    root = _root()
    parser = argparse.ArgumentParser(description="Генерация CycloneDX SBOM_TCB и SBOM_OTHER из манифеста.")
    sp_sbom = root / "src_starting_point" / "sbom"
    parser.add_argument(
        "--manifest",
        type=Path,
        default=sp_sbom / "sbom_manifest.json",
        help="Путь к sbom_manifest.json (заготовка: src_starting_point/sbom/)",
    )
    parser.add_argument(
        "--out-tcb",
        type=Path,
        default=sp_sbom / "SBOM_TCB.cdx.json",
        help="Выход SBOM_TCB.cdx.json",
    )
    parser.add_argument(
        "--out-other",
        type=Path,
        default=sp_sbom / "SBOM_OTHER.cdx.json",
        help="Выход SBOM_OTHER.cdx.json",
    )
    args = parser.parse_args()
    if not args.manifest.is_file():
        print(f"Не найден манифест: {args.manifest}", file=sys.stderr)
        sys.exit(1)
    generate(args.manifest, args.out_tcb, args.out_other)
    print(f"Записано: {args.out_tcb}")
    print(f"Записано: {args.out_other}")


if __name__ == "__main__":
    main()
