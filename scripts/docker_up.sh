#!/usr/bin/env bash
# Запуск контейнеров в фоне.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose -f docker-compose.yaml up -d "$@"
