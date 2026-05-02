from backend.app.ofac import classify_result, safe_filename_part
from backend.app.parsing import parse_csv_names, parse_text_names


def test_parse_text_names_skips_blank_lines() -> None:
    assert parse_text_names(" Alice \n\nBob Inc\n") == ["Alice", "Bob Inc"]


def test_parse_csv_names_uses_first_non_empty_cell_and_skips_header() -> None:
    assert parse_csv_names("name,notes\n,skip\nAcme LLC,x\nJane Doe,\n") == ["skip", "Acme LLC", "Jane Doe"]


def test_classify_result() -> None:
    assert classify_result("Lookup Results: 0 Found") == "no_hit"
    assert classify_result("Lookup Results: 1 Found") == "hit_found"


def test_safe_filename_part() -> None:
    assert safe_filename_part("ACME: Holdings / Global") == "ACME Holdings Global"
