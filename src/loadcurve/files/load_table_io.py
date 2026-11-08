"""Read and write Load tables as CSV or XLSX spreadsheets.

Reading is forgiving about the file and strict about the data: it accepts the
legacy Spanish headers, ``;`` separators, decimal commas and Windows encodings,
but every row is validated by the ``Load`` model. Invalid rows are skipped and
reported as ``ImportIssue`` values so the user can fix them; problems with the
file as a whole raise ``LoadTableFileError``.
"""

import io
import math
from pathlib import PurePath
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError

from loadcurve.domain.models import HOURS_PER_DAY, Load, LoadTable

FileFormat = Literal["csv", "xlsx"]

NAME_COLUMN = "Load"
POWER_COLUMN = "Rated power (W)"
USAGE_COLUMN = "Usage factor"
HOUR_COLUMNS: tuple[str, ...] = tuple(str(hour) for hour in range(HOURS_PER_DAY))
COLUMNS: tuple[str, ...] = (NAME_COLUMN, POWER_COLUMN, USAGE_COLUMN, *HOUR_COLUMNS)
REQUIRED_COLUMNS: tuple[str, ...] = (NAME_COLUMN, POWER_COLUMN, *HOUR_COLUMNS)

# Header spellings accepted on import (compared case-insensitively), including the
# Spanish headers of the legacy Streamlit template.
COLUMN_ALIASES: dict[str, str] = {
    "load": NAME_COLUMN,
    "carga": NAME_COLUMN,
    "rated power (w)": POWER_COLUMN,
    "potencia (w)": POWER_COLUMN,
    "usage factor": USAGE_COLUMN,
    "factor de uso": USAGE_COLUMN,
}

MAX_ROWS = 500
FIRST_DATA_ROW = 2  # spreadsheet row number of the first Load; row 1 is the header

_FIELD_COLUMNS = {"name": NAME_COLUMN, "rated_power_w": POWER_COLUMN, "usage_factor": USAGE_COLUMN}


class ImportIssue(BaseModel):
    """A problem with one row of an imported file. ``code`` is a stable error type."""

    model_config = ConfigDict(frozen=True)

    row: int
    column: str | None
    code: str


class ImportResult(BaseModel):
    """The valid Loads of an imported file and the issues of the rows that were skipped."""

    model_config = ConfigDict(frozen=True)

    loads: tuple[Load, ...]
    issues: tuple[ImportIssue, ...]


class LoadTableFileError(Exception):
    """The file as a whole cannot be imported (wrong type, unreadable, missing columns...)."""

    def __init__(self, code: str, columns: tuple[str, ...] = ()) -> None:
        super().__init__(code if not columns else f"{code}: {', '.join(columns)}")
        self.code = code
        self.columns = columns


def read_load_table(content: bytes, filename: str) -> ImportResult:
    """Parse a CSV or XLSX file into Loads, skipping and reporting invalid rows."""
    frame = _normalize_columns(_read_frame(content, _file_format(filename)))
    frame = frame.dropna(how="all")
    if frame.empty:
        raise LoadTableFileError("empty_file")
    if len(frame) > MAX_ROWS:
        raise LoadTableFileError("too_many_rows")

    loads: list[Load] = []
    issues: list[ImportIssue] = []
    seen_names: set[str] = set()
    for index, record in frame.iterrows():
        row = int(index) + FIRST_DATA_ROW
        try:
            load = Load(**_load_fields(record))
        except ValidationError as error:
            issues.extend(_issues_from(row, error))
            continue
        if load.name.casefold() in seen_names:
            issues.append(ImportIssue(row=row, column=NAME_COLUMN, code="duplicate_load_name"))
            continue
        seen_names.add(load.name.casefold())
        loads.append(load)

    return ImportResult(loads=tuple(loads), issues=tuple(issues))


def write_load_table(load_table: LoadTable, fmt: FileFormat) -> bytes:
    """Serialize a Load table with the canonical English headers."""
    frame = pd.DataFrame(
        [
            {
                NAME_COLUMN: load.name,
                POWER_COLUMN: load.rated_power_w,
                USAGE_COLUMN: load.usage_factor,
                **dict(zip(HOUR_COLUMNS, load.schedule, strict=True)),
            }
            for load in load_table.loads
        ],
        columns=list(COLUMNS),
    )
    if fmt == "csv":
        # utf-8-sig adds the byte-order mark Excel needs to show accents correctly.
        return frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False, sheet_name="Load table", engine="openpyxl")
    return buffer.getvalue()


def _file_format(filename: str) -> FileFormat:
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    raise LoadTableFileError("unsupported_file_type")


def _read_frame(content: bytes, fmt: FileFormat) -> pd.DataFrame:
    """Load the raw cells; every value is kept as text or number for row-level validation."""
    if not content.strip():
        raise LoadTableFileError("empty_file")
    try:
        if fmt == "csv":
            # sep=None lets pandas sniff "," or ";" (Spanish-locale Excel saves with ";").
            return pd.read_csv(io.StringIO(_decode(content)), sep=None, engine="python", dtype=str)
        return pd.read_excel(io.BytesIO(content), dtype=object, engine="openpyxl")
    except pd.errors.EmptyDataError as error:
        raise LoadTableFileError("empty_file") from error
    except Exception as error:  # any parser failure means the upload is not a usable sheet
        raise LoadTableFileError("unreadable_file") from error


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")  # Excel's default on Windows


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Map accepted header spellings to canonical names and drop every other column."""
    renamed = {column: _canonical_column(column) for column in frame.columns}
    frame = frame.rename(columns=renamed)
    frame = frame.loc[:, [column for column in frame.columns if column in COLUMNS]]
    frame = frame.loc[:, ~frame.columns.duplicated()]

    missing = tuple(column for column in REQUIRED_COLUMNS if column not in frame.columns)
    if missing:
        raise LoadTableFileError("missing_columns", missing)
    return frame


def _canonical_column(header: Any) -> str:
    text = str(header).strip()
    if text.casefold() in COLUMN_ALIASES:
        return COLUMN_ALIASES[text.casefold()]
    try:
        number = float(text)  # Excel may store hour headers as numbers (0, 1.0, ...)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def _load_fields(record: pd.Series) -> dict[str, Any]:
    """Turn one spreadsheet row into keyword arguments for ``Load``."""
    fields: dict[str, Any] = {
        "name": "" if _is_blank(record[NAME_COLUMN]) else str(record[NAME_COLUMN]),
        # A blank hour cell means the Load is off in that hour.
        "schedule": [0 if _is_blank(record[h]) else _number(record[h]) for h in HOUR_COLUMNS],
    }
    if not _is_blank(record[POWER_COLUMN]):
        fields["rated_power_w"] = _number(record[POWER_COLUMN])
    usage = record.get(USAGE_COLUMN)
    if not _is_blank(usage):
        fields["usage_factor"] = _number(usage)
    return fields


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def _number(value: Any) -> Any:
    """Parse numbers written as text, including decimal commas ("350,5").

    Text that is not a number is returned unchanged so that ``Load`` reports it.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return value


def _issues_from(row: int, error: ValidationError) -> list[ImportIssue]:
    issues = []
    for detail in error.errors():
        location = detail["loc"]
        field = location[0] if location else None
        if location == ("schedule",):
            # The schedule always has 24 cells here, so a length error is only the
            # echo of an invalid cell that is already reported on its own.
            continue
        if field == "schedule" and len(location) > 1 and isinstance(location[1], int):
            column = HOUR_COLUMNS[location[1]]
        else:
            column = _FIELD_COLUMNS.get(str(field))
        issues.append(ImportIssue(row=row, column=column, code=detail["type"]))
    return issues
