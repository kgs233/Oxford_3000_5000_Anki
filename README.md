# Generate Anki packages
Thanks a lot for ChatGPT's great support

Thanks to winterdl for providing [the raw data](https://github.com/winterdl/oxford-5000-vocabulary-audio-definition)

And everyone listed under 'Resources and credit' in raw data repo.

---

Run from the project root:

```bash
python -m pip install -r python/requirements-anki.txt
python python/generate_apkg.py --accent us
python python/generate_apkg.py --accent uk
# Or generate both:
python python/generate_apkg.py --accent both
```

Outputs: `output/Oxford_3000_and_5000_us.apkg` and
`output/Oxford_3000_and_5000_uk.apkg`. Rebuilding replaces the selected package.
All default paths are relative to the project, regardless of the current working
directory. Use `--data-dir`, `--card-dir`, `--audio-dir`, or `--output-dir` to override.

The note type and card template are named `KGS_English_Card`. The parent deck is
`Oxford 3000 and 5000`, with A1, A2, B1, B2, C1 subdecks. Each CSV record becomes
one note and one card. `id` retains the source value and is the note type's sort
field; it is not referenced in either face. New-card positions use numeric ID + 1.
`Image` is empty. Plain CSV text is HTML-escaped before insertion into the fields.

US uses `phon_n_am` and `audio/us/us_<audio_number>.opus`; UK uses `phon_br` and
`audio/uk/uk_<audio_number>.opus`. Packages contain the referenced audio files.
Missing audio, duplicate IDs and malformed data stop generation with an error.

The two packages are alternative pronunciations of the same notes: model IDs,
deck IDs and note GUIDs are stable across versions and rebuilds. Importing another
version is subject to Anki's existing-note update settings; these are not two
independent collections of cards. Choose the desired pronunciation when importing.
The ID must continue to identify the same record on future rebuilds.

Templates and CSS are loaded verbatim from `card/front.html`, `card/back.html`,
and `card/style.css`. Playback and appearance should be checked on the actual Anki
client, particularly when using Opus audio on mobile.

# License
Except for the data and audio folders, everything else is under the Unlicense.

For the rest, see the [raw data repo](https://github.com/winterdl/oxford-5000-vocabulary-audio-definition)