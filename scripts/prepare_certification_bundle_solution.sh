#!/usr/bin/env bash
# Формирует каталог artifacts/cert_bundle и архив artifacts/abu_certification_bundle.tar.gz
# для последующей подачи в Регулятор (для решения).

set -euo pipefail
# Для временного деревья оценки: CONTEST_REPO_ROOT=/tmp/merged …
ROOT="${CONTEST_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT="$ROOT/artifacts/cert_bundle"
PYTHON_BIN="${CONTEST_PYTHON:-${PYTHON_BIN:-$(command -v python)}}"
mkdir -p "$ROOT/artifacts"
rm -rf "$OUT"
mkdir -p "$OUT"

# CycloneDX решения: манифест src_solution/sbom/sbom_manifest.json.
SBOM_SOL_MAN="$ROOT/src_solution/sbom/sbom_manifest.json"
SBOM_SOL_TCB="$ROOT/src_solution/sbom/SBOM_TCB.cdx.json"
SBOM_SOL_OTH="$ROOT/src_solution/sbom/SBOM_OTHER.cdx.json"
(cd "$ROOT" && "$PYTHON_BIN" scripts/generate_sbom_cdx.py \
  --manifest "$SBOM_SOL_MAN" --out-tcb "$SBOM_SOL_TCB" --out-other "$SBOM_SOL_OTH")

mkdir -p "$OUT/source"
cp -a "$ROOT/src_solution/abu" "$OUT/source/abu"
cp "$ROOT/src_solution/requirements.txt" "$OUT/source/requirements.txt"
if [[ -f "$ROOT/src_solution/requirements-other.txt" ]]; then
  cp "$ROOT/src_solution/requirements-other.txt" "$OUT/source/requirements-other.txt"
fi
rm -f "$OUT/source/pytest.ini"
cat >"$OUT/source/pytest.ini" <<EOF
[pytest]
markers =
    security: тесты безопасности по ЦБ
pythonpath = .
filterwarnings =
    ignore::DeprecationWarning
EOF
rm -rf "$OUT/source/tests"
cp -a "$ROOT/src_solution/tests" "$OUT/source/tests"
find "$OUT/source/tests" -name "*.py" -exec sed -i 's/from src_solution\.abu/from abu/g' {} \;
# Fix imports in code
find "$OUT/source/abu" -name "*.py" -exec sed -i 's/from src_solution\.abu/from abu/g' {} \;

# importlib.import_module(\"src_solution.abu...\") в тестах интеграции
mkdir -p "$OUT/source/src_solution"
touch "$OUT/source/src_solution/__init__.py"
ln -snf ../abu "$OUT/source/src_solution/abu"
mkdir -p "$OUT/sbom"
mkdir -p "$OUT/security"
cp "$ROOT/src_solution/sbom/SBOM_TCB.cdx.json" "$OUT/sbom/SBOM_TCB.cdx.json"
cp "$ROOT/src_solution/sbom/SBOM_OTHER.cdx.json" "$OUT/sbom/SBOM_OTHER.cdx.json"
# Совместимость: агрегированный SBOM (не используется Регулятором v2 при наличии TCB/OTHER)
cp "$ROOT/src_starting_point/sbom/abu_sbom.cdx.json" "$OUT/sbom/sbom.cdx.json"
cp "$ROOT/docs/examples/sga.json" "$OUT/security/sga.json"
VERSION="${VERSION:-0.1.0}"
SBOM_MERGE="$ROOT/src_solution/sbom/sbom_manifest.json"
"$PYTHON_BIN" "$ROOT/scripts/write_cert_bundle_manifest.py" \
  --out "$OUT/manifest.json" \
  --package-name "abu-solution" \
  --version "${VERSION}" \
  --merge-sbom-manifest "$SBOM_MERGE"
tar -czf "$ROOT/artifacts/abu_certification_bundle.tar.gz" -C "$ROOT/artifacts" cert_bundle
echo "Пакет: $ROOT/artifacts/abu_certification_bundle.tar.gz"