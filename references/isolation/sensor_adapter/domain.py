"""Недоверенный домен, поставляющий телеметрию."""

DOMAIN_ID = "sensor_adapter"


def read_depth(parameters: dict) -> float:
    """Вернуть глубину при вызове из рабочего цикла домена."""
    return float(parameters.get("depth_m", 0.0))
