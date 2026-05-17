# Тесты безопасности АБУ и цели (ЦБ)

## Когда читать

- **Обязательно:** нет.
- **Когда:** если нужно быстро сверить эталонную матрицу SG и тестов.
- **Можно пропустить:** да, для оценки каноничен раздел в `src_solution/docs/solution.md`.

Этот документ сохранён как справочный. Каноническая версия для оценки находится в отчёте в каталоге `src_solution/docs/`, раздел «Результаты тестов безопасности».

## Справочное соответствие SG и тестам эталона (`src_solution/tests`)

| Цель (SG) | Файлы эталона | Комментарий |
|-----------|----------------|-------------|
| SG_ADS_Authorized_critical_commands | `src_solution/tests/unit/`, `src_solution/abu/tcb/guard.py` | `authorize_step` — единственный доверенный вход для разрешения критичного шага |
| SG_ADS_Controlled_operations | `src_solution/tests/unit/`, `src_solution/tests/e2e/` | Глубина, RPM, emergency и риск проверяются в `tcb_guard` |
| SG_ADS_Security_events_store | `src_solution/tests/unit/`, `src_solution/abu/tcb/` | `event_log.py` оставлен как совместимое имя, реализация — `audit_log.py` |
| Правила политик монитора (IPC) | `src_solution/tests/unit/`, `src_solution/tests/module/` | `default deny`, малый whitelist `other -> tcb_guard/tcb_audit` |
| Процессная изоляция и IPC | `src_solution/tests/module/`, `src_solution/tests/unit/` | Event доставляется в отдельный процесс домена |
| HTTP как у ЦР/digital_mine | `src_solution/tests/integration/` | REST остаётся недоверенным и вызывает ДВБ через монитор |

Участник конкурса дополняет соответствие тестов и ЦБ для своего кода в `src_solution/` — заполняет отчёт в `src_solution/docs/solution.md`.

## Что читать дальше

- [criteria_rubric.md](criteria_rubric.md) — как раздел тестов безопасности влияет на C13 и смежные критерии.
- [quickstart_2days.md](quickstart_2days.md) — куда включить эти проверки в план 2 дней.
- [tara_abu.md](tara_abu.md) — как связать тесты с моделью угроз.
