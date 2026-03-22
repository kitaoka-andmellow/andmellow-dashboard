from __future__ import annotations

import csv
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def normalize_filename(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "")


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def normalize_product_text(value: str) -> str:
    value = normalize_spaces(value)
    value = value.replace("…", "").replace("...", "")
    value = re.sub(r"\([^)]*\)\s*$", "", value)
    value = re.sub(r"\[[^]]*\]", "", value)
    value = re.sub(r"[^0-9A-Za-zぁ-んァ-ン一-龥]+", "", value.lower())
    return value


def slugify(value: str) -> str:
    seed = normalize_product_text(value)
    if not seed:
        seed = "item"
    return seed[:40]


def parse_number(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    text = text.replace("￥", "").replace(",", "").replace("%", "")
    if text in {"-", "nan"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_percentage(value: object) -> float | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    return parse_number(text) / 100.0


def parse_date(value: object) -> str | None:
    text = normalize_spaces(str(value or ""))
    if not text:
        return None
    formats = (
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d",
    )
    for pattern in formats:
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def choose_file(directory: Path, keywords: Iterable[str], suffixes: Iterable[str]) -> Path | None:
    matches = list_matching_files(directory, keywords, suffixes)
    return matches[0] if matches else None


def list_matching_files(directory: Path, keywords: Iterable[str], suffixes: Iterable[str]) -> list[Path]:
    if not directory.exists():
        return []
    wanted = [normalize_filename(keyword) for keyword in keywords]
    suffix_set = {suffix.lower() for suffix in suffixes}
    matches: list[Path] = []
    for path in sorted(directory.iterdir()):
        normalized = normalize_filename(path.name)
        if path.suffix.lower() not in suffix_set:
            continue
        if all(keyword in normalized for keyword in wanted):
            matches.append(path)
    return matches


def read_csv_rows(path: Path, header_index: int = 0) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if header_index >= len(rows):
        return []
    headers = [normalize_spaces(column) for column in rows[header_index]]
    records: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        if not any(str(cell).strip() for cell in row):
            continue
        record: dict[str, str] = {}
        for index, header in enumerate(headers):
            record[header] = row[index].strip() if index < len(row) else ""
        records.append(record)
    return records


def read_csv_rows_matching(path: Path, header_match: Callable[[list[str]], bool]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    for index, row in enumerate(rows):
        normalized = [normalize_spaces(cell) for cell in row]
        if header_match(normalized):
            headers = normalized
            records: list[dict[str, str]] = []
            for data_row in rows[index + 1 :]:
                if not any(str(cell).strip() for cell in data_row):
                    continue
                record: dict[str, str] = {}
                for header_index, header in enumerate(headers):
                    record[header] = data_row[header_index].strip() if header_index < len(data_row) else ""
                records.append(record)
            return records
    return []


def _column_index(reference: str) -> int:
    index = 0
    for char in reference:
        if not char.isalpha():
            break
        index = index * 26 + ord(char.upper()) - 64
    return index


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    values: list[str] = []
    for item in root.findall(f".//{{{MAIN_NS}}}si"):
        parts = []
        for text_node in item.findall(f".//{{{MAIN_NS}}}t"):
            parts.append(text_node.text or "")
        values.append("".join(parts))
    return values


def read_xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
        }
        sheet = workbook.find(f".//{{{MAIN_NS}}}sheet")
        if sheet is None:
            return []
        relation_id = sheet.attrib.get(f"{{{OFFICE_REL_NS}}}id")
        if not relation_id or relation_id not in relationship_map:
            return []
        target = relationship_map[relation_id].lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        sheet_root = ET.fromstring(archive.read(sheet_path))
        rows: list[list[str]] = []
        for row_node in sheet_root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
            values: dict[int, str] = {}
            max_index = 0
            for cell in row_node.findall(f"{{{MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "A1")
                index = _column_index(reference)
                max_index = max(max_index, index)
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    parts = [node.text or "" for node in cell.findall(f".//{{{MAIN_NS}}}t")]
                    value = "".join(parts)
                else:
                    raw = cell.findtext(f"{{{MAIN_NS}}}v", default="")
                    if cell_type == "s" and raw:
                        shared_index = int(raw)
                        value = shared_strings[shared_index] if shared_index < len(shared_strings) else ""
                    else:
                        value = raw
                values[index] = value
            if max_index == 0:
                continue
            row = ["" for _ in range(max_index)]
            for index, value in values.items():
                row[index - 1] = str(value).strip()
            rows.append(row)
        return rows
