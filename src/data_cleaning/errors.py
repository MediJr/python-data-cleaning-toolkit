"""Exception hierarchy for the toolkit.

Every error raised deliberately by the toolkit derives from ``DataCleaningError``
so that callers (and the CLI) can distinguish expected, explainable failures
from programming errors.
"""

from __future__ import annotations


class DataCleaningError(Exception):
    """Base class for all expected toolkit errors."""


class InputFileError(DataCleaningError):
    """The input path is missing, not a file, unreadable, or of an unsupported type."""


class EmptyInputError(InputFileError):
    """The input file contains no header or no data rows."""


class MalformedInputError(InputFileError):
    """The input file could be opened but its structure is not a valid table."""


class ConfigError(DataCleaningError):
    """A cleaning rule or option is invalid."""


class MissingColumnError(ConfigError):
    """A rule refers to a column that does not exist in the dataset."""


class ColumnCollisionError(DataCleaningError):
    """Column-name normalization would give two distinct columns the same name."""


class OutputExistsError(DataCleaningError):
    """The output file already exists and overwriting was not authorized."""


class ExportError(DataCleaningError):
    """The output file could not be written or failed verification."""
