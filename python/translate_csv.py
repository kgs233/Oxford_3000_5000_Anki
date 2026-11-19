"""Translate data/raw_data.csv to data/chinese.csv using Azure Translator.

Progress is kept in a separate partial file. The old output is replaced only
after the new file is complete and validated.
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COLUMNS_ZH = ("definition_zh", "example_zh")
ENDPOINT = "https://api.cognitive.microsofttranslator.com"


def read_key(path):
    key = path.read_text(encoding="utf-8-sig").strip()
    if not key or any(character.isspace() for character in key):
        raise ValueError("Key file must contain one key without spaces")
    return key


def translate(texts, key, region, endpoint, timeout):
    url = endpoint.rstrip("/") + "/translate?api-version=3.0&from=en&to=zh-Hans"
    payload = json.dumps([{"Text": text} for text in texts], ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Ocp-Apim-Subscription-Key": key,
        "Ocp-Apim-Subscription-Region": region,
    }
    for attempt in range(8):
        try:
            request = Request(url, data=payload, headers=headers, method="POST")
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response)
            translations = [item["translations"][0]["text"].replace("\r", " ").replace("\n", " ") for item in result]
            if len(translations) != len(texts) or any(not isinstance(t, str) or not t.strip() for t in translations):
                raise ValueError("Azure returned missing or empty translations")
            return translations
        except HTTPError as exc:
            if exc.code not in (408, 429) and exc.code < 500:
                try:
                    detail = json.load(exc).get("error", {})
                    message = f"Azure HTTP {exc.code}, code {detail.get('code', 'unknown')}: {detail.get('message', '')}"
                except (ValueError, AttributeError):
                    message = f"Azure HTTP {exc.code}"
                raise RuntimeError(message) from exc
            error = f"Azure HTTP {exc.code}"
            retry_after = exc.headers.get("Retry-After")
            try:
                wait = max(30, int(retry_after)) if exc.code == 429 else min(2 ** attempt, 30)
            except (TypeError, ValueError):
                wait = 30
        except (URLError, TimeoutError) as exc:
            error = f"Network error: {type(exc).__name__}"
            wait = min(2 ** attempt, 30)
        if attempt < 7:
            time.sleep(wait)
    raise RuntimeError(f"Translation failed after 8 attempts: {error}")


def load_source(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True)
        columns = reader.fieldnames
        if not columns or not {"definition", "example"}.issubset(columns):
            raise ValueError("Input needs definition and example columns")
        if any(column in columns for column in COLUMNS_ZH):
            raise ValueError("Input already has translation columns")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Input contains malformed rows")
    return columns, rows


def progress(partial, source_columns, output_columns, source_rows):
    if not partial.exists():
        return 0
    completed = 0
    with partial.open("r+b") as file:
        header = file.readline()
        if not header:
            return 0
        if next(csv.reader([header.decode("utf-8")], strict=True)) != output_columns:
            raise ValueError(f"Unexpected partial file columns: {partial}")
        while True:
            offset = file.tell()
            line = file.readline()
            if not line:
                return completed
            if not line.endswith(b"\n"):
                file.truncate(offset)
                return completed
            try:
                cells = next(csv.reader([line.decode("utf-8")], strict=True))
            except (UnicodeDecodeError, csv.Error):
                file.truncate(offset)
                return completed
            if len(cells) != len(output_columns):
                file.truncate(offset)
                return completed
            if completed >= len(source_rows):
                raise ValueError("Partial file has more rows than input")
            row = dict(zip(output_columns, cells))
            if any(row[column] != source_rows[completed][column] for column in source_columns):
                raise ValueError(f"Partial file differs from input at row {completed + 1}")
            if any(not row[column].strip() for column in COLUMNS_ZH):
                file.truncate(offset)
                return completed
            completed += 1


def row_batches(rows, start, limit_rows, limit_chars):
    index = start
    while index < len(rows):
        end = index
        chars = 0
        while end < len(rows) and end - index < limit_rows:
            next_chars = len(rows[end]["definition"]) + len(rows[end]["example"])
            if next_chars > limit_chars:
                raise ValueError(f"Row {end + 1} exceeds --max-chars")
            if end > index and chars + next_chars > limit_chars:
                break
            chars += next_chars
            end += 1
        yield index, end
        index = end


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA / "raw_data.csv")
    parser.add_argument("--output", type=Path, default=DATA / "chinese.csv")
    parser.add_argument("--key-file", type=Path, default=ROOT / "key")
    parser.add_argument("--region", default="eastus")
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--chars-per-minute", type=int, default=25000)
    parser.add_argument("--replace", action="store_true", help="Replace an existing output after completion")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500 or not 1 <= args.max_chars <= 50000:
        raise ValueError("--batch-size must be 1–500 and --max-chars must be 1–50000")
    if args.chars_per_minute < 1:
        raise ValueError("--chars-per-minute must be positive")
    if args.output.exists() and not args.replace:
        raise ValueError(f"Output exists: {args.output}; pass --replace to update it")
    key = read_key(args.key_file)
    source_columns, rows = load_source(args.input)
    output_columns = source_columns + list(COLUMNS_ZH)
    partial = args.output.with_name("." + args.output.name + ".azure-partial")
    completed = progress(partial, source_columns, output_columns, rows)
    if not partial.exists():
        with partial.open("w", encoding="utf-8", newline="") as file:
            csv.writer(file, lineterminator="\n").writerow(output_columns)

    start_time = time.monotonic()
    sent_chars = 0
    with partial.open("ab") as file:
        for start, end in row_batches(rows, completed, args.batch_size, args.max_chars):
            texts = [text for row in rows[start:end] for text in (row["definition"], row["example"])]
            batch_chars = sum(len(text) for text in texts)
            target_time = start_time + (sent_chars + batch_chars) * 60 / args.chars_per_minute
            if target_time > time.monotonic():
                time.sleep(target_time - time.monotonic())
            translated = translate(texts, key, args.region, args.endpoint, args.timeout)
            sent_chars += batch_chars
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=output_columns, lineterminator="\n")
            for offset, original in enumerate(rows[start:end]):
                row = original.copy()
                row["definition_zh"] = translated[2 * offset]
                row["example_zh"] = translated[2 * offset + 1]
                writer.writerow(row)
            file.write(buffer.getvalue().encode("utf-8"))
            file.flush()
            os.fsync(file.fileno())
            print(f"Translated {end}/{len(rows)} rows", flush=True)

    if progress(partial, source_columns, output_columns, rows) != len(rows):
        raise RuntimeError("Output validation failed; existing output was not replaced")
    os.replace(partial, args.output)
    print(f"Complete: {len(rows)} rows -> {args.output}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Run again with the same options to resume.", file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
