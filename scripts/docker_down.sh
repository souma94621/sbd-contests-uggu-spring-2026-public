#!/usr/bin/env bash
# Остановка и удаление контейнеров сети compose.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose -f docker-compose.yaml down "$@"
