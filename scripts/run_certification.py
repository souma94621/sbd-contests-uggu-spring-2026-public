"""
Запуск процедуры сертификации через API Регулятора (локальный TestClient).

Печатает результат, стоимость и сертификат-хэш пакета.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def main() -> None:
    """Вызывает Регулятор и печатает итог сертификации."""
    root = Path(__file__).resolve().parents[1]
    bundle = root / "artifacts" / "abu_certification_bundle.tar.gz"
    if not bundle.is_file():
        print(
            "Сначала выполните: make prepare-cert-bundle или "
            "make prepare-cert-bundle-solution",
            file=sys.stderr,
        )
        sys.exit(1)

    expected_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()

    sys.path.insert(0, str(root / "scripts"))
    from regulator_certification import request_certification

    data = request_certification(root)

    success = data.get("success", False)
    cost = float(data.get("estimated_cost", 0.0) or 0.0)
    cert = data.get("certificate_id")
    loc = int(data.get("tcb_lines_of_code", 0) or 0)
    cc = int(data.get("tcb_cyclomatic_sum", 0) or 0)

    if success:
        print("Результат сертификации: успешно")
    else:
        print("Результат сертификации: неуспешно")
    print(f"Стоимость (усл. ед.): {cost:.2f}")
    print(f"ДВБ: строк кода abu={loc}, суммарная цикломатика={cc}")
    if cert:
        print(f"Сертификат (SHA-256 пакета): {cert}")
        if cert != expected_hash:
            print("Ошибка: хэш сертификата не совпадает с SHA-256 архива", file=sys.stderr)
            sys.exit(1)
    else:
        print("Сертификат (SHA-256 пакета): —")
        if data.get("message"):
            print(f"Сообщение: {data['message'][:500]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
