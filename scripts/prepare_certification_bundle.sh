#!/usr/bin/env bash
# Формирует каталог artifacts/cert_bundle и архив artifacts/abu_certification_bundle.tar.gz
# для последующей подачи в Регулятор.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/artifacts/cert_bundle"
PYTHON_BIN="${CONTEST_PYTHON:-${PYTHON_BIN:-$(command -v python)}}"
mkdir -p "$ROOT/artifacts"
rm -rf "$OUT"
mkdir -p "$OUT"

# CycloneDX: манифест и артефакты в src_starting_point/sbom/ (см. docs/sbom_guide.md).
(cd "$ROOT" && "$PYTHON_BIN" scripts/generate_sbom_cdx.py)

cp -a "$ROOT/src_starting_point" "$OUT/source"
mkdir -p "$OUT/sbom"
mkdir -p "$OUT/security"
cp "$ROOT/src_starting_point/sbom/SBOM_TCB.cdx.json" "$OUT/sbom/SBOM_TCB.cdx.json"
cp "$ROOT/src_starting_point/sbom/SBOM_OTHER.cdx.json" "$OUT/sbom/SBOM_OTHER.cdx.json"
# Совместимость: агрегированный SBOM (не используется Регулятором v2 при наличии TCB/OTHER)
cp "$ROOT/src_starting_point/sbom/abu_sbom.cdx.json" "$OUT/sbom/sbom.cdx.json"
cp "$ROOT/docs/examples/sga.json" "$OUT/security/sga.json"
VERSION="${VERSION:-0.1.0}"
(cd "$ROOT" && "$PYTHON_BIN" scripts/write_cert_bundle_manifest.py \
  --out "$OUT/manifest.json" \
  --package-name "abu-starting-point" \
  --version "${VERSION}" \
  --merge-sbom-manifest "$ROOT/src_starting_point/sbom/sbom_manifest.json")
tar -czf "$ROOT/artifacts/abu_certification_bundle.tar.gz" -C "$ROOT/artifacts" cert_bundle
echo "Пакет: $ROOT/artifacts/abu_certification_bundle.tar.gz"
