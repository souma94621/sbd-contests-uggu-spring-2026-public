# Конкурсное задание: АБУ и цифровой рудник

Короткий вход для участника конкурса (индивидуально, лимит ~2 дня).

## Обязательные документы (только 3)

1. [docs/contest_task.md](docs/contest_task.md) — что сделать и что сдать.
2. [docs/quickstart_2days.md](docs/quickstart_2days.md) — пошаговый маршрут на 2 дня.
3. [docs/criteria_rubric.md](docs/criteria_rubric.md) — как начисляются баллы C01–C25.

Дополнительные материалы и углубление: [docs/README.md](docs/README.md).

## Единые команды самопроверки

```bash
make install
make tests-all
make evaluate-score
make certify-abu-solution
```

`make evaluate-score` использует критерии C01–C25 (сумма raw до 75).

## Что обязательно сдать

- код решения в `src_solution/`;
- тесты решения в `src_solution/tests/**`;
- отчёт в `src_solution/docs/solution.md`.

## Платформа

Эталонная среда проверки — Linux (или совместимая среда: WSL2/Codespaces/контейнер).
