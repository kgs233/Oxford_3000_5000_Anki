"""Check that the English, Chinese, final, and CEFR CSV files agree."""

import argparse
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("a1", "a2", "b1", "b2", "c1")
ENGLISH_COLUMNS = (
    "id", "word", "type", "cefr", "phon_br", "phon_n_am", "definition", "example",
)
CHINESE_COLUMNS = ENGLISH_COLUMNS + ("definition_zh", "example_zh")
FINAL_COLUMNS = CHINESE_COLUMNS + ("audio_number",)


class Report:
    def __init__(self, display_limit=20):
        self.errors = 0
        self.display_limit = display_limit

    def error(self, message):
        self.errors += 1
        if self.errors <= self.display_limit:
            print(f"ERROR: {message}")


def read_csv(path, columns, report, expected_level=None):
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True)
            if tuple(reader.fieldnames or ()) != columns:
                report.error(f"{path}: columns differ: {reader.fieldnames!r}")
                return None
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        report.error(f"{path}: cannot read CSV: {exc}")
        return None

    ids = set()
    for number, row in enumerate(rows, start=1):
        if None in row or any(value is None for value in row.values()):
            report.error(f"{path}: malformed record {number}")
            continue
        ident = row["id"]
        if not ident.isdigit():
            report.error(f"{path}: nonnumeric id {ident!r} at record {number}")
        if ident in ids:
            report.error(f"{path}: duplicate id {ident!r}")
        ids.add(ident)
        for column in columns:
            if not row[column].strip():
                report.error(f"{path}: empty {column} at id {ident!r}")
        if row["cefr"] not in LEVELS:
            report.error(f"{path}: invalid cefr {row['cefr']!r} at id {ident!r}")
        if expected_level and row["cefr"] != expected_level:
            report.error(f"{path}: id {ident!r} belongs to {row['cefr']!r}, not {expected_level!r}")
        if "audio_number" in columns and not re.fullmatch(r"[0-9]{5}", row["audio_number"]):
            report.error(f"{path}: invalid audio_number {row['audio_number']!r} at id {ident!r}")
    print(f"{path.name}: {len(rows)} rows")
    return rows


def compare_rows(parent, child, columns, parent_name, child_name, report):
    if parent is None or child is None:
        return
    def valid(row):
        return None not in row and all(value is not None for value in row.values()) and bool(row["id"])

    parent_by_id = {row["id"]: row for row in parent if valid(row)}
    child_by_id = {row["id"]: row for row in child if valid(row)}
    parent_ids = set(parent_by_id)
    child_ids = set(child_by_id)
    for ident in sorted(parent_ids - child_ids, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)):
        report.error(f"{child_name}: missing id {ident!r} from {parent_name}")
    for ident in sorted(child_ids - parent_ids, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)):
        report.error(f"{child_name}: extra id {ident!r} absent from {parent_name}")
    for row in child:
        if not valid(row) or row["id"] not in parent_by_id:
            continue
        original = parent_by_id[row["id"]]
        for column in columns:
            if row[column] != original[column]:
                report.error(
                    f"{child_name}: id {row['id']!r} ({row['word']!r}) differs in {column}: "
                    f"expected {original[column][:80]!r}, got {row[column][:80]!r}"
                )
    if parent_ids == child_ids and [row["id"] for row in parent] != [row["id"] for row in child]:
        report.error(f"{child_name}: row order differs from {parent_name}")


def check(data_dir):
    report = Report()
    english = read_csv(data_dir / "english_data.csv", ENGLISH_COLUMNS, report)
    chinese = read_csv(data_dir / "chinese.csv", CHINESE_COLUMNS, report)
    final = read_csv(data_dir / "final_data.csv", FINAL_COLUMNS, report)

    if english is not None and [row.get("id") for row in english] != [str(i) for i in range(len(english))]:
        report.error("english_data.csv: IDs are not in sequential order starting at 0")
    compare_rows(english, chinese, ENGLISH_COLUMNS, "english_data.csv", "chinese.csv", report)
    compare_rows(chinese, final, CHINESE_COLUMNS, "chinese.csv", "final_data.csv", report)

    for level in LEVELS:
        name = f"{level}.csv"
        rows = read_csv(data_dir / name, FINAL_COLUMNS, report, expected_level=level)
        expected = [row for row in final if row.get("cefr") == level] if final is not None else None
        compare_rows(expected, rows, FINAL_COLUMNS, "final_data.csv", name, report)

    if report.errors:
        if report.errors > report.display_limit:
            print(f"... {report.errors - report.display_limit} more errors not shown")
        print(f"FAILED: {report.errors} consistency errors")
    else:
        print("OK: all 8 CSV files are consistent")
    return report.errors == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    raise SystemExit(0 if check(args.data_dir) else 1)


if __name__ == "__main__":
    main()
