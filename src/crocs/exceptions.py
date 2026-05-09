class CrocsError(Exception):
    pass


class DataValidationError(CrocsError):
    pass


class ForecastError(CrocsError):
    pass
