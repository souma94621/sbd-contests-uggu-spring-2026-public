#!/usr/bin/env bash
# Создаёт виртуальное окружение через Pipenv и устанавливает зависимости из Pipfile.
# Пакеты не ставятся в системный Python (см. docs/quality_requirements.md).

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v pipenv >/dev/null 2>&1; then
  echo "Установите Pipenv, например: python3 -m pip install --user pipenv" >&2
  echo "Затем добавьте каталог с pip в PATH (часто ~/.local/bin)." >&2
  exit 1
fi

# Виртуальное окружение в каталоге проекта (.venv), чтобы путь был предсказуем.
export PIPENV_VENV_IN_PROJECT=1
pipenv install --dev

echo "Готово. Выполняйте команды через: pipenv run <команда>"
echo "Или активируйте оболочку: pipenv shell"
