"""Add audio numbers to data/chinese.csv and write data/final_data.csv."""

import argparse
import csv
import os
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE_COLUMNS = (
    "id", "word", "type", "cefr", "phon_br", "phon_n_am",
    "definition", "example", "definition_zh", "example_zh",
)
OUTPUT_COLUMNS = SOURCE_COLUMNS + ("audio_number",)
MAP_COLUMNS = ("word", "audio_number")


def read_rows(path, expected_columns):
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True)
        if tuple(reader.fieldnames or ()) != expected_columns:
            raise ValueError(f"{path}: expected columns {expected_columns}, got {reader.fieldnames}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{path}: malformed CSV row")
    return rows


def build_rows(source_path, map_path):
    source = read_rows(source_path, SOURCE_COLUMNS)
    mappings = read_rows(map_path, MAP_COLUMNS)
    audio_numbers = {}
    used_numbers = set()
    for row in mappings:
        word, number = row["word"], row["audio_number"]
        if not word or not re.fullmatch(r"[0-9]{5}", number):
            raise ValueError(f"{map_path}: invalid word or audio number for {word!r}")
        if word in audio_numbers or number in used_numbers:
            raise ValueError(f"{map_path}: duplicate word or audio number: {word!r}, {number}")
        audio_numbers[word] = number
        used_numbers.add(number)

    ids = set()
    missing = set()
    output = []
    for row in source:
        if not row["id"].isdigit() or row["id"] in ids:
            raise ValueError(f"{source_path}: invalid or duplicate id: {row['id']!r}")
        ids.add(row["id"])
        number = audio_numbers.get(row["word"])
        if number is None:
            missing.add(row["word"])
            continue
        output.append({**row, "audio_number": number})
    if missing:
        sample = ", ".join(repr(word) for word in sorted(missing)[:10])
        raise ValueError(f"{map_path}: no audio number for {len(missing)} words: {sample}")
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temp_path = Path(file.name)
            writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/chinese.csv")
    parser.add_argument("--map", type=Path, default=ROOT / "audio/audio_number_map.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/final_data.csv")
    args = parser.parse_args()
    rows = build_rows(args.input, args.map)
    write_csv(args.output, rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
