import io

import pandas as pd
import pytest

from loadcurve.domain.models import LoadTable
from loadcurve.files.load_table_io import (
    HOUR_COLUMNS,
    MAX_ROWS,
    ImportIssue,
    LoadTableFileError,
    read_load_table,
    write_load_table,
)
from loadcurve.files.sample import SAMPLE_LOAD_TABLE, template

HEADER = "Load,Rated power (W),Usage factor," + ",".join(HOUR_COLUMNS)
ALWAYS_ON = ",".join(["1"] * 24)
ALWAYS_OFF = ",".join(["0"] * 24)


def read_csv_text(text: str, encoding: str = "utf-8") -> tuple:
    result = read_load_table(text.encode(encoding), "loads.csv")
    return result.loads, result.issues


def xlsx_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    return buffer.getvalue()


class TestRoundTrip:
    @pytest.mark.parametrize("fmt", ["csv", "xlsx"])
    def test_written_files_read_back_unchanged(self, fmt: str) -> None:
        result = read_load_table(write_load_table(SAMPLE_LOAD_TABLE, fmt), f"loads.{fmt}")

        assert result.issues == ()
        assert LoadTable(loads=result.loads) == SAMPLE_LOAD_TABLE

    @pytest.mark.parametrize("fmt", ["csv", "xlsx"])
    def test_template_is_the_sample_table(self, fmt: str) -> None:
        result = read_load_table(template(fmt), f"template.{fmt}")

        assert LoadTable(loads=result.loads) == SAMPLE_LOAD_TABLE

    def test_csv_starts_with_a_byte_order_mark_for_excel(self) -> None:
        assert write_load_table(SAMPLE_LOAD_TABLE, "csv").startswith(b"\xef\xbb\xbf")


class TestLegacyFiles:
    def test_reads_spanish_headers_semicolons_and_decimal_commas(self) -> None:
        hours = ";".join(HOUR_COLUMNS)
        text = f"Item;Carga;Potencia (W);{hours}\n1;Nevera;350,5;{';'.join(['1'] * 24)}\n"

        loads, issues = read_csv_text(text)

        assert issues == ()
        assert loads[0].name == "Nevera"
        assert loads[0].rated_power_w == 350.5
        assert loads[0].usage_factor == 1.0

    def test_reads_windows_encoded_csv(self) -> None:
        loads, _ = read_csv_text(f"{HEADER}\nCalefacción,1000,1,{ALWAYS_ON}\n", "cp1252")

        assert loads[0].name == "Calefacción"

    def test_reads_xlsx_with_numeric_hour_headers(self) -> None:
        frame = pd.DataFrame(
            [["Pump", 750] + [1] * 24], columns=["Carga", "Potencia (W)", *range(24)]
        )

        result = read_load_table(xlsx_bytes(frame), "legacy.xlsx")

        assert result.loads[0].rated_power_w == 750
        assert result.loads[0].schedule == (1,) * 24


class TestBlankCells:
    def test_blank_hours_are_off_and_blank_usage_factor_is_full(self) -> None:
        sparse_hours = "1" + "," * 23  # hour 0 on, hours 1-23 left empty
        loads, issues = read_csv_text(f"{HEADER}\nLamp,60,,{sparse_hours}\n")

        assert issues == ()
        assert loads[0].schedule == (1,) + (0,) * 23
        assert loads[0].usage_factor == 1.0

    def test_empty_rows_are_skipped_without_shifting_row_numbers(self) -> None:
        text = f"{HEADER}\nLamp,60,1,{ALWAYS_ON}\n" + "," * 26 + f"\nBad,-5,1,{ALWAYS_ON}\n"

        loads, issues = read_csv_text(text)

        assert [load.name for load in loads] == ["Lamp"]
        assert issues == (ImportIssue(row=4, column="Rated power (W)", code="greater_than"),)


class TestRowIssues:
    def test_invalid_rows_are_reported_and_valid_rows_kept(self) -> None:
        bad_hour = ",".join(["0"] * 5 + ["2"] + ["0"] * 18)
        text = (
            f"{HEADER}\n"
            f"Fridge,350,0.4,{ALWAYS_ON}\n"  # row 2: valid
            f",100,1,{ALWAYS_ON}\n"  # row 3: no name
            f"Heater,lots,1,{ALWAYS_ON}\n"  # row 4: power is not a number
            f"Pump,500,1.5,{ALWAYS_ON}\n"  # row 5: usage factor above 1
            f"Fan,80,1,{bad_hour}\n"  # row 6: hour 5 is neither 0 nor 1
            f"Router,,1,{ALWAYS_ON}\n"  # row 7: power missing
        )

        loads, issues = read_csv_text(text)

        assert [load.name for load in loads] == ["Fridge"]
        assert issues == (
            ImportIssue(row=3, column="Load", code="string_too_short"),
            ImportIssue(row=4, column="Rated power (W)", code="float_parsing"),
            ImportIssue(row=5, column="Usage factor", code="less_than_equal"),
            ImportIssue(row=6, column="5", code="literal_error"),
            ImportIssue(row=7, column="Rated power (W)", code="missing"),
        )

    def test_repeated_names_keep_the_first_row(self) -> None:
        text = f"{HEADER}\nFridge,350,1,{ALWAYS_ON}\nFRIDGE,200,1,{ALWAYS_OFF}\n"

        loads, issues = read_csv_text(text)

        assert [load.rated_power_w for load in loads] == [350]
        assert issues == (ImportIssue(row=3, column="Load", code="duplicate_load_name"),)


class TestFileErrors:
    def test_unsupported_extension(self) -> None:
        with pytest.raises(LoadTableFileError) as excinfo:
            read_load_table(b"anything", "loads.txt")

        assert excinfo.value.code == "unsupported_file_type"

    def test_corrupt_xlsx(self) -> None:
        with pytest.raises(LoadTableFileError) as excinfo:
            read_load_table(b"this is not a zip archive", "loads.xlsx")

        assert excinfo.value.code == "unreadable_file"

    def test_missing_columns_are_listed(self) -> None:
        with pytest.raises(LoadTableFileError) as excinfo:
            read_csv_text("Load,Rated power (W),0,1\nLamp,60,1,1\n")

        assert excinfo.value.code == "missing_columns"
        assert excinfo.value.columns == HOUR_COLUMNS[2:]

    @pytest.mark.parametrize("text", ["", HEADER + "\n"])
    def test_file_without_loads(self, text: str) -> None:
        with pytest.raises(LoadTableFileError) as excinfo:
            read_csv_text(text)

        assert excinfo.value.code == "empty_file"

    def test_too_many_rows(self) -> None:
        rows = "".join(f"Load {i},10,1,{ALWAYS_ON}\n" for i in range(MAX_ROWS + 1))

        with pytest.raises(LoadTableFileError) as excinfo:
            read_csv_text(f"{HEADER}\n{rows}")

        assert excinfo.value.code == "too_many_rows"
