#!/usr/bin/env bash
# Сборка PDF презентации Beamer (XeLaTeX + polyglossia).
# Запуск: из каталога docs/slides — ./build_pdf.sh
# или из корня репозитория: bash docs/slides/build_pdf.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
MAIN="presentation.tex"
if ! command -v xelatex >/dev/null 2>&1; then
  echo "Ошибка: не найден xelatex. Установите TeX Live / MiKTeX и пакеты: xelatex, polyglossia, fontspec, beamer." >&2
  exit 1
fi
echo "Сборка ${MAIN} (два прохода для перекрёстных ссылок)..."
xelatex -interaction=nonstopmode -halt-on-error "$MAIN"
xelatex -interaction=nonstopmode -halt-on-error "$MAIN"
PDF="${MAIN%.tex}.pdf"
if [[ -f "$PDF" ]]; then
  echo "Готово: $(pwd)/$PDF"
else
  echo "Ошибка: $PDF не создан." >&2
  exit 1
fi
