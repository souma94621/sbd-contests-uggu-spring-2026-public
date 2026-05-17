#!/usr/bin/env bash
# Сборка образов ЦР, Регулятора и АБУ (из корня репозитория).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose -f docker-compose.yaml build "$@"
