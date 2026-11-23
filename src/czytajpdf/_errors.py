"""Exception hierarchy. Every class also inherits a builtin so older ``except`` clauses keep working."""


class CzytajPDFError(Exception):
    """Base class for all czytajpdf errors."""


class InvalidPDFError(CzytajPDFError, ValueError):
    """The input is not a readable PDF."""


class PasswordRequiredError(CzytajPDFError, ValueError):
    """The PDF is encrypted and the password is missing or wrong."""


class MissingDependencyError(CzytajPDFError, ImportError):
    """An optional dependency (extra) required for the requested feature is not installed."""


class ModelNotFoundError(CzytajPDFError, OSError):
    """An OCR model is unavailable (offline mode, unknown language, or missing local file)."""
