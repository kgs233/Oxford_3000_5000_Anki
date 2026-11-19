"""Split data/final_data.csv into A1, A2, B1, B2, and C1 CSV files."""

import argparse
import csv
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("a1", "a2", "b1", "b2", "c1")


def split_csv(source, output_dir):
    with source.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True)
        columns = reader.fieldnames
        if not columns or "cefr" not in columns:
            raise ValueError(f"{source}: missing cefr column")
        rows = {level: [] for level in LEVELS}
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{source}: malformed CSV row at line {line}")
            level = row["cefr"].strip().lower()
            if level not in rows:
                raise ValueError(f"{source}: unexpected CEFR level {row['cefr']!r} at line {line}")
            rows[level].append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    staged = {}
    try:
        for level in LEVELS:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=output_dir,
                prefix=f".{level}.csv.", suffix=".tmp", delete=False,
            ) as file:
                staged[level] = Path(file.name)
                writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows[level])
                file.flush()
                os.fsync(file.fileno())
        for level in LEVELS:
            os.replace(staged[level], output_dir / f"{level}.csv")
            print(f"{level.upper()}: {len(rows[level])} rows")
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/final_data.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    split_csv(args.input, args.output_dir)


if __name__ == "__main__":
    main()
