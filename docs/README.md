# Anki Deck Builder

This folder is organized so the root stays minimal and the builder is the
obvious entry point. The main directories are:

- `config/`: deck configuration
- `data/`: the live CSV note sources
- `downloads/`: built `.apkg` and `.html` outputs
- `editor/`: the local GUI and server
- `tools/`: utility scripts such as AnkiConnect preview import
- `docs/`: usage notes and conventions
- `research/`: source material and raw imports that feed the deck

The builder and editor turn the CSV/config data into:

- an `.apkg` Anki package you can import or send as a file
- an `.html` preview you can open in a browser or publish on the web

## CSV files

- `data/models.csv`: structured model history cards
- `data/companies.csv`: dated lab, company, policy, governance, and safety-statement history cards
- `data/science.csv`: dated technical papers, research milestones, benchmark wins, and scientific-recognition cards
- `data/people.csv`: people cards with `speaker,date,quote,source,url` for quotes or compact credential facts
- `data/iabied.csv`: freeform `front,back,notes,tags` cards
- `data/sanders.csv`: Sanders-specific quote and framing cards
- `data/sanders/`: transcript references, video list, and downloaded subtitles
- `config/deck_config.json`: deck-wide settings plus card templates per CSV source

## Build

From the project root:

```bash
.venv/bin/python Anki/build_deck.py
```

Outputs land in `Anki/downloads/`.

## Card types in config

The builder understands these Anki-style note models:

- `basic`
- `basic_and_reversed`

Each CSV source can define one or more card templates in `config/deck_config.json`.
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
.venv/bin/python Anki/editor/editor_server.py
```

Then open:

```text
http://127.0.0.1:8775
```

The editor lets you:

- choose a CSV source
- create or delete card definitions
- pick `basic` or `basic_and_reversed`
- drag field tokens into front/back templates
- save changes back to `config/deck_config.json`
- build the deck from the browser

## Live preview in Anki Desktop

If you have a test profile in Anki Desktop and the AnkiConnect add-on installed,
you can rebuild and refresh the preview deck directly in Anki:

```bash
.venv/bin/python Anki/tools/preview_in_anki.py --profile "Your Test Profile"
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
