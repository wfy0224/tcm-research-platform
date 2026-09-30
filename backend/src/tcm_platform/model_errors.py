"""Recoverable model failures, distinct from database and authorization failures."""


class ModelUnavailableError(RuntimeError):
    """Transport, capacity or circuit failure after model authorization."""


class ModelResponseError(ValueError):
    """A model returned unusable data."""


class ModelCredentialMissing(ValueError):
    """No model credential has been configured."""


class ModelCredentialUnavailable(RuntimeError):
    """The credential store cannot be read."""
