"""Typed errors shared across the bot's infrastructure and domain layers."""


class BotError(Exception):
    """Base class for expected application errors."""


class StorageError(BotError):
    """A JSON store could not be read or persisted safely."""


class DataValidationError(BotError):
    """Incoming or imported data does not satisfy its canonical schema."""


class ExternalServiceError(BotError):
    """A remote service operation failed after local validation."""
