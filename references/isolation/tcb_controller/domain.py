"""Доверенный домен с одним малым safety-решением."""

DOMAIN_ID = "tcb_controller"


def approve_depth(parameters: dict) -> bool:
    """Разрешить глубину при вызове из рабочего цикла домена."""
    return float(parameters["depth_m"]) <= float(parameters["max_depth_m"])
