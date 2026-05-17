# src_solution/abu/tcb/domain_process.py
"""Изоляция доменов ДВБ через отдельные процессы.

Реализует границу доверия между abu.tcb и abu.other
через multiprocessing — каждый домен выполняется
в изолированном процессе.

Протокол взаимодействия: request/response через очередь —
домен other отправляет request, домен tcb возвращает response.
"""

from __future__ import annotations

import multiprocessing
from typing import Any


def _worker(func_name: str, args: tuple, result_queue: multiprocessing.Queue) -> None:
    """Воркер домена ДВБ в изолированном процессе."""
    from src_solution.abu.tcb import safety, limits
    funcs = {
        "should_emergency_stop": safety.should_emergency_stop,
        "enforce_depth_cap": limits.enforce_depth_cap,
        "enforce_rpm_cap": limits.enforce_rpm_cap,
    }
    func = funcs.get(func_name)
    if func is None:
        result_queue.put(PermissionError(f"Неизвестная функция домена: {func_name}"))
        return
    try:
        result_queue.put(func(*args))
    except Exception as exc:
        result_queue.put(exc)


class DomainProcess:
    """
    Запускает функцию ДВБ в изолированном дочернем процессе.

    Граница доверия реализована через multiprocessing.Process —
    домен tcb физически отделён от домена other на уровне ОС.
    """

    def call(self, func_name: str, *args: Any) -> Any:
        """Вызвать функцию домена в отдельном процессе."""
        queue: multiprocessing.Queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_worker,
            args=(func_name, args, queue),
            daemon=True,
        )
        proc.start()
        proc.join(timeout=5)
        if proc.exitcode != 0 or queue.empty():
            raise RuntimeError(f"Домен-процесс завершился с ошибкой: {func_name}")
        result = queue.get_nowait()
        if isinstance(result, Exception):
            raise result
        return result
