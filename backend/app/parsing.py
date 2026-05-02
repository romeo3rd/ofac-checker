from __future__ import annotations

import csv
import io
import re
from pathlib import Path


HEADER_VALUES = {"name", "names", "company", "company name"}


def parse_text_names(text: str | None) -> list[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_uploaded_names(filename: str, content: bytes) -> list[str]:
    suffix = Path(filename).suffix.lower()
    text = content.decode("utf-8-sig")
    if suffix == ".csv":
        return parse_csv_names(text)
    return parse_text_names(text)


def parse_csv_names(text: str) -> list[str]:
    names: list[str] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        value = next((cell.strip() for cell in row if cell.strip()), "")
        if value:
            names.append(value)
    if names and normalize_header(names[0]) in HEADER_VALUES:
        names = names[1:]
    return names


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def dedupe_blank_only(names: list[str]) -> list[str]:
    return [name for name in names if name.strip()]
