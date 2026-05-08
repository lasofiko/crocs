class CrocsError(Exception):
    """Базовая ошибка пайплайна."""


class DataValidationError(CrocsError):
    """Некорректные входные данные или схема CSV."""


class ForecastError(CrocsError):
    """Ошибка модуля прогноза."""


class SchedulingError(CrocsError):
    """Ошибка оптимизатора расписания."""
