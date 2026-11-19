"""Generate Oxford Anki packages from graded CSV files and card templates."""

import argparse
import csv
import hashlib
import html
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("a1", "a2", "b1", "b2", "c1")
DECK_NAME = "Oxford 3000 and 5000"
MODEL_NAME = "KGS_English_Card"
FIELDS = ("id", "Word", "IPA", "Audio", "POS", "Meaning", "MeaningChinese",
          "Example", "ExampleChinese", "Image")
REQUIRED = {"id", "word", "type", "cefr", "phon_br", "phon_n_am", "definition",
            "example", "definition_zh", "example_zh", "audio_number"}
POS_ABBREVIATIONS = {
    "noun": "n.",
    "verb": "v.",
    "adjective": "adj.",
    "adverb": "adv.",
    "pronoun": "pron.",
    "preposition": "prep.",
    "determiner": "det.",
    "number": "num.",
    "conjunction": "conj.",
    "exclamation": "interj.",
    "modal verb": "modal v.",
    "ordinal number": "ord. num.",
    "auxiliary verb": "aux. v.",
    "indefinite article": "indef. art.",
    "definite article": "def. art.",
    "infinitive marker": "inf. mark.",
    "linking verb": "link v.",
}


def stable_id(name):
    # Keep these names and the algorithm stable when regenerating a deck.
    return 1_000_000_000 + int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big") % 1_000_000_000


def field_text(value):
    return html.escape(value, quote=True).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def read_templates(directory):
    front = (directory / "front.html").read_text(encoding="utf-8-sig")
    back = (directory / "back.html").read_text(encoding="utf-8-sig")
    css = (directory / "style.css").read_text(encoding="utf-8-sig")
    for template in (front, back):
        for expression in re.findall(r"{{\s*(.*?)\s*}}", template):
            name = expression.lstrip("#^/").split(":")[-1].strip()
            if name == "id":
                raise ValueError("id must remain hidden: remove its reference from the template")
            if name not in FIELDS and name not in {"FrontSide", "Tags", "Deck", "Subdeck", "Type", "Card"}:
                raise ValueError(f"Unknown template field: {name}")
    return front, back, css


def read_rows(directory):
    groups = {}
    seen = set()
    for level in LEVELS:
        path = directory / f"{level}.csv"
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True)
            if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
                raise ValueError(f"{path}: missing columns {sorted(REQUIRED - set(reader.fieldnames or []))}")
            rows = list(reader)
        for row in rows:
            if None in row or any(row.get(field) is None or not row[field].strip() for field in REQUIRED):
                raise ValueError(f"{path}: malformed or incomplete row {row.get('id')}")
            ident = row["id"]
            if not re.fullmatch(r"0|[1-9][0-9]*", ident) or ident in seen:
                raise ValueError(f"{path}: invalid or duplicate id {ident}")
            if row["cefr"] != level:
                raise ValueError(f"{path}: id {ident} has CEFR {row['cefr']}")
            if row["type"] not in POS_ABBREVIATIONS:
                raise ValueError(f"{path}: id {ident} has an unknown part of speech: {row['type']}")
            if not re.fullmatch(r"[0-9]{5}", row["audio_number"]):
                raise ValueError(f"{path}: id {ident} has an invalid audio_number")
            seen.add(ident)
        groups[level] = sorted(rows, key=lambda row: int(row["id"]))
    return groups


def build(accent, groups, templates, audio_dir, output_dir):
    import genanki

    front, back, css = templates
    model = genanki.Model(
        stable_id("kgs:oxford:model:v1"), MODEL_NAME,
        fields=[{"name": field} for field in FIELDS],
        templates=[{"name": MODEL_NAME, "qfmt": front, "afmt": back}],
        css=css, sort_field_index=0,
    )
    parent = genanki.Deck(stable_id("kgs:oxford:deck"), DECK_NAME)
    decks = [parent]
    media = set()
    ipa_column = "phon_n_am" if accent == "us" else "phon_br"
    for level, rows in groups.items():
        deck = genanki.Deck(stable_id(f"kgs:oxford:deck:{level}"), f"{DECK_NAME}::{level.upper()}")
        for row in rows:
            audio = audio_dir / accent / f"{accent}_{row['audio_number']}.opus"
            if not audio.is_file() or audio.stat().st_size == 0:
                raise ValueError(f"Missing audio for {row['word']} (id {row['id']}): {audio}")
            media.add(audio)
            values = [row["id"], field_text(row["word"]), field_text(row[ipa_column]),
                      f"[sound:{audio.name}]", POS_ABBREVIATIONS[row["type"]],
                      field_text(row["definition"]), field_text(row["definition_zh"]),
                      field_text(row["example"]), field_text(row["example_zh"]), ""]
            deck.add_note(genanki.Note(
                model=model, fields=values,
                guid=genanki.guid_for("kgs:oxford:note:v1", row["id"]),
                # Anki separates tags on spaces, so retain full words joined by underscores.
                tags=[f"CEFR::{level.upper()}", "POS::" + row["type"].replace(" ", "_")],
                due=int(row["id"]) + 1,
            ))
        decks.append(deck)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"Oxford_3000_and_5000_{accent}.apkg"
    handle, temporary = tempfile.mkstemp(dir=output_dir, prefix=target.stem + ".", suffix=".tmp")
    os.close(handle)
    try:
        package = genanki.Package(decks, media_files=[str(path) for path in sorted(media)])
        package.write_to_file(temporary)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f"{accent.upper()}: {sum(map(len, groups.values()))} notes/cards, {len(media)} audio files -> {target}")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accent", choices=("us", "uk", "both"), required=True,
                        help="us: American; uk: British; both: generate two packages")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--card-dir", type=Path, default=ROOT / "card")
    parser.add_argument("--audio-dir", type=Path, default=ROOT / "audio")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    templates = read_templates(args.card_dir)
    groups = read_rows(args.data_dir)
    for accent in (("us", "uk") if args.accent == "both" else (args.accent,)):
        build(accent, groups, templates, args.audio_dir, args.output_dir)


if __name__ == "__main__":
    try:
        main()
    except ModuleNotFoundError as exc:
        print(f"Missing dependency: {exc.name}. Install python/requirements-anki.txt in your virtual environment.", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
