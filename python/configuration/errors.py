class ConfigurationError(Exception):
    pass


class LockError(ConfigurationError):
    pass


class SymbolError(ConfigurationError):
    pass
