#!/usr/bin/env python3
"""Пишет manifest.json для архива сертификации, опционально подмешивает поля из sbom_manifest.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_MERGE_KEYS = (
    "domain_ipc_untrusted_boundary_edges",
    "domain_ipc_trusted_boundary_edges",
    "cost_domains_schema_version",
    "ipc_policies_bundle_path",
)
_MERGE_OBJECTS = ("security_cost_domains",)


def main() -> None:
    p = argparse.ArgumentParser(description="Сгенерировать cert_bundle/manifest.json")
    p.add_argument("--out", required=True, help="путь manifest.json в артефакте")
    p.add_argument("--package-name", required=True)
    p.add_argument("--version", default="0.1.0")
    p.add_argument(
        "--merge-sbom-manifest",
        default=None,
        help="путь sbom_manifest.json: подмешать целые поля доменного IPC для Регулятора",
    )
    args = p.parse_args()
    out = Path(args.out)
    base: dict = {
        "version": args.version,
        "package_name": args.package_name,
        "tests_root": "tests",
        "python_requirements": "requirements.txt",
        "source_subdir": "source",
    }
    if args.merge_sbom_manifest:
        raw = Path(args.merge_sbom_manifest)
        data = json.loads(raw.read_text(encoding="utf-8"))
        for k in _MERGE_KEYS:
            if k in data:
                base[k] = data[k]
        for ko in _MERGE_OBJECTS:
            if ko in data:
                base[ko] = data[ko]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
