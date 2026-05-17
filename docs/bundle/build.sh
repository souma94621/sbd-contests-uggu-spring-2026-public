#!/usr/bin/env bash
# Сборка объединённого PDF из каталога docs/bundle (нужен XeLaTeX).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

MAIN="uggu_sbd_contest_2026.tex"

run_xelatex() {
  xelatex -interaction=nonstopmode -file-line-error "$@"
}

if command -v latexmk >/dev/null 2>&1; then
  latexmk -xelatex -interaction=nonstopmode -file-line-error -f "$MAIN"
else
  run_xelatex "$MAIN"
  run_xelatex "$MAIN"
  base="${MAIN%.tex}"
  if [[ -f "${base}.idx" ]] && [[ -s "${base}.idx" ]]; then
    makeindex -o "${base}.ind" "${base}.idx"
  fi
  run_xelatex "$MAIN"
fi

echo "Готово: $ROOT/${MAIN%.tex}.pdf"
