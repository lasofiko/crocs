from __future__ import annotations

import pandas as pd


def validate_schedule(
    schedule: pd.DataFrame,
    staff_limits: pd.DataFrame,
    sched: pd.DataFrame,
) -> list[str]:
    """
    Возвращает список нарушений правил ТЗ (пустой список = ок).
    Заготовка: допишите проверки (1 смена/день, лимиты, доступность, покрытие…).
    """
    violations: list[str] = []
    if schedule is None or schedule.empty:
        violations.append("Расписание пустое")
    return violations
