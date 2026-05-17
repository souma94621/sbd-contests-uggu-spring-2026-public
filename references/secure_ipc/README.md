# Пример `secure_ipc`

Минимальный пример IPC с `default deny`, белым списком маршрутов и многослойным контролем.

## Что показывает пример

- три домена (`tcb_guard`, `tcb_audit`, `operator_ui`);
- единый `ipc_policies.json` для разрешённых маршрутов;
- блокировку недопустимого запроса `1 -> 3`;
- process-изоляцию и доставку через брокер.

## Быстрый запуск

```bash
pipenv run pytest -q references/secure_ipc/tests
```

## Шаг -> файл -> тест -> критерий

| Шаг | Файл | Тест | Критерий (ориентир) |
|---|---|---|---|
| Канонический формат IPC | `ipc.py` | `tests/test_secure_ipc.py::test_event_contract` | C18 |
| Маршрутные политики | `ipc_policies.json`, `route_monitor.py` | `tests/test_secure_ipc.py::test_blocked_direct_route_1_to_3` | C18, C24 |
| Process-изоляция | `domain_process.py` | `tests/test_secure_ipc.py::test_domain_process_bridge` | C19 |
| Многослойный контроль | `message_broker.py`, `domain_guard.py`, `parameter_guard.py` | `tests/test_secure_ipc.py::test_parameter_guard_rejects_wrong_payload` | C18, C25 |

## Обязательные негативные проверки

- блокировка запроса `tcb_guard -> operator_ui` при отсутствии политики;
- отклонение события с неверной формой или параметрами;
- отказ в доставке при нарушении локальной политики домена.

## Анти-паттерны (накрутки)

- одно «глобальное разрешение» вместо точечных политик;
- расширение `ipc_policies.json` «на всякий случай» для обхода отказов;
- имитация процесса без реального разделения исполнения.

## Формат политики

```json
{"from": "domain_a", "to": "domain_b", "func": "operation"}
```

Чем меньше разрешающих политик на домен, тем проще верификация и лучше перспектива по C24.

## Чек-лист перед переносом в `src_solution`

- тесты примера проходят;
- есть тест блокировки недопустимого маршрута;
- политики минимальны и отражают только нужные взаимодействия;
- итоговый self-check решения: `make tests-all`, `make evaluate-score`, `make certify-abu-solution`.
