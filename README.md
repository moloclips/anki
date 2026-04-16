# Anki Deck Builder

This folder contains CSV sources, a config file, a builder script, and a local
editor for turning them into:

- an `.apkg` Anki package you can import or send as a file
- an `.html` preview you can open in a browser or publish on the web

## CSV files

- `models.csv`: structured model history cards
- `history.csv`: dated AI-lab history cards
- `iabied.csv`: freeform `front,back,notes,tags` cards
- `deck_config.json`: deck-wide settings plus card templates per CSV source

## Build

From the project root:

```bash
.venv/bin/python Anki/build_deck.py
```

Outputs land in `Anki/out/`.

## Card types in config

The builder understands these Anki-style note models:

- `basic`
- `basic_and_reversed`

Each CSV source can define one or more card templates in `deck_config.json`.
Templates use field tokens like `{{model}}` or `{{date}}`.

Example:

```json
{
  "name": "date",
  "note_model": "basic",
  "front": "When was {{model}} released?",
  "back": "<b>{{date}}</b><br>{{summary}}",
  "tags": ["dates"]
}
```

## Local editor

Run:

```bash
.venv/bin/python Anki/editor_server.py
```

Then open:

```text
http://127.0.0.1:8765
```

The editor lets you:

- choose a CSV source
- create or delete card definitions
- pick `basic` or `basic_and_reversed`
- drag field tokens into front/back templates
- save changes back to `deck_config.json`
- build the deck from the browser

## Live preview in Anki Desktop

If you have a test profile in Anki Desktop and the AnkiConnect add-on installed,
you can rebuild and refresh the preview deck directly in Anki:

```bash
.venv/bin/python Anki/preview_in_anki.py --profile "Your Test Profile"
```

That imports a dedicated deck named `AI Politics Prep Preview` and opens it in
Anki's Browser so you can inspect the real rendering.

## `.apkg` support

The script always builds the HTML preview.

To also build an importable Anki package:

```bash
.venv/bin/pip install genanki
.venv/bin/python Anki/build_deck.py
```

## Optional deck name

```bash
.venv/bin/python Anki/build_deck.py --deck-name "Politician Chat Prep"
```
