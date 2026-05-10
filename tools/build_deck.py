#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DECK_NAME = "AI"
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DEFAULT_OUTPUT_DIR = ROOT
DEFAULT_CONFIG_PATH = CONFIG_DIR / "deck_config.json"
PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
ANSWER_HR_RE = re.compile(r"<hr\b[^>]*\bid\s*=\s*['\"]answer['\"][^>]*\s*/?>", re.IGNORECASE)
SECTION_RE = re.compile(r"{{\s*([#^])\s*([a-zA-Z0-9_]+)\s*}}(.*?){{\s*/\s*\2\s*}}", re.DOTALL)
DEFAULT_CSS = """
.card {
  font-family: arial;
  font-size: 20px;
  text-align: center;
  color: black;
  background-color: white;
}
""".strip()


@dataclass(frozen=True)
class NoteRecord:
    guid_key: str
    model_kind: str
    front: str
    back: str
    source_file: str
    card_name: str
    tags: tuple[str, ...]


def slugify(text: str) -> str:
    result = []
    for ch in text.lower():
        if ch.isalnum():
            result.append(ch)
        elif result and result[-1] != "-":
            result.append("-")
    return "".join(result).strip("-") or "deck"


def stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:15], 16)


def stable_guid(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def tag_from_source(source_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", Path(source_name).stem).strip("_").lower()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                if isinstance(value, list):
                    cleaned[key] = ",".join(part.strip() for part in value if part)
                else:
                    cleaned[key] = (value or "").strip()
            rows.append(cleaned)
        return rows


def extract_fields(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
    return [field.strip() for field in header if field.strip()]


def render_template(template: str, row: dict[str, str]) -> str:
    template = render_conditionals(template, row)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return format_display_value(key, row.get(key, ""))

    return PLACEHOLDER_RE.sub(replace, template)


def referenced_placeholder_fields(*templates: str) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for template in templates:
        raw = template or ""
        previous = None
        while previous != raw:
            previous = raw
            raw = SECTION_RE.sub("", raw)
        for match in PLACEHOLDER_RE.finditer(raw):
            key = match.group(1)
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def render_conditionals(template: str, row: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        mode = match.group(1)
        key = match.group(2)
        body = match.group(3)
        value = (row.get(key, "") or "").strip()
        should_render = bool(value) if mode == "#" else not bool(value)
        return render_conditionals(body, row) if should_render else ""

    previous = None
    while previous != template:
        previous = template
        template = SECTION_RE.sub(replace, template)
    return template


def normalize_card_content(template: str, side: str) -> str:
    template = (template or "").strip()
    if not template:
        return ""
    template = ANSWER_HR_RE.sub("", template)
    if side == "back":
        template = re.sub(r"{{\s*FrontSide\s*}}", "", template)
    return template.strip()


def format_display_value(key: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if key == "date" or key.endswith("_date"):
        return humanize_date(value)
    return value


def humanize_date(value: str) -> str:
    for fmt, out_fmt in (
        ("%Y-%m-%d", "%B %-d, %Y"),
        ("%Y-%m", "%B %Y"),
        ("%Y", "%Y"),
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime(out_fmt)
        except ValueError:
            continue
    return value


def builtin_model_specs(deck_name: str, css: str) -> dict[str, dict[str, Any]]:
    return {
        "basic": {
            "model_id": stable_int(f"{deck_name}:basic"),
            "name": f"{deck_name} Basic",
            "fields": [{"name": "Front"}, {"name": "Back"}],
            "templates": [
                {
                    "name": "Card 1",
                    "qfmt": "{{Front}}",
                    "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
                }
            ],
            "css": css,
        },
        "basic_and_reversed": {
            "model_id": stable_int(f"{deck_name}:basic-and-reversed"),
            "name": f"{deck_name} Basic And Reversed",
            "fields": [{"name": "Front"}, {"name": "Back"}],
            "templates": [
                {
                    "name": "Card 1",
                    "qfmt": "{{Front}}",
                    "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
                },
                {
                    "name": "Card 2",
                    "qfmt": "{{Back}}",
                    "afmt": '{{FrontSide}}<hr id="answer">{{Front}}',
                },
            ],
            "css": css,
        },
    }


def default_config() -> dict[str, Any]:
    return {
        "deck_name": DEFAULT_DECK_NAME,
        "css": DEFAULT_CSS,
        "sources": {
            "models.csv": {
                "tags": ["models"],
                "cards": [
                    {
                        "name": "importance",
                        "note_model": "basic",
                        "front": "What was important about {{model}}?",
                        "back": (
                            "<b>{{model}}</b><br>"
                            "Company: {{company}}<br>"
                            "Date: {{date}}<br>"
                            "Why it mattered: {{summary}}"
                        ),
                        "tags": ["models"],
                    },
                    {
                        "name": "date",
                        "note_model": "basic",
                        "front": "When was {{model}} released or introduced?",
                        "back": (
                            "<b>{{model}}</b><br>"
                            "Date: {{date}}<br>"
                            "Company: {{company}}<br>"
                            "Significance: {{summary}}"
                        ),
                        "tags": ["models", "dates"],
                    },
                ],
            },
            "companies.csv": {
                "tags": ["companies"],
                "cards": [
                    {
                        "name": "event-to-date",
                        "note_model": "basic_and_reversed",
                        "front": "When did this happen: {{event}}?",
                        "back": (
                            "<b>{{date}}</b><br>"
                            "Precision: {{precision}}<br>"
                            "Notes: {{notes}}"
                        ),
                        "tags": ["companies"],
                    }
                ],
            },
            "science.csv": {
                "tags": ["science"],
                "cards": [
                    {
                        "name": "event-to-date",
                        "note_model": "basic_and_reversed",
                        "front": "When did this happen: {{event}}?",
                        "back": (
                            "<b>{{date}}</b><br>"
                            "Precision: {{precision}}<br>"
                            "Notes: {{notes}}"
                        ),
                        "tags": ["science"],
                    }
                ],
            },
            "iabied.csv": {
                "tags": ["iabied"],
                "cards": [
                    {
                        "name": "freeform-basic",
                        "note_model": "basic",
                        "front": "{{front}}",
                        "back": "{{back}}<br><br><i>{{notes}}</i>",
                        "tags": ["iabied"],
                    }
                ],
            },
        },
    }


def ensure_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        config = default_config()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return config
    return json.loads(path.read_text(encoding="utf-8"))


def load_notes(config: dict[str, Any]) -> list[NoteRecord]:
    notes: list[NoteRecord] = []
    valid_model_kinds = {"basic", "basic_and_reversed"}
    for source_name, source_cfg in config.get("sources", {}).items():
        source_path = Path(source_name)
        if not source_path.is_absolute():
            source_path = DATA_DIR / source_path
        if not source_path.exists():
            continue
        cards = source_cfg.get("cards", [])
        rows = read_csv_rows(source_path)
        for row_index, row in enumerate(rows, start=1):
            for card_cfg in cards:
                if not card_cfg.get("front") or not card_cfg.get("back"):
                    continue
                model_kind = card_cfg.get("note_model", "basic")
                row_model_kind = (row.get("note_type", "") or "").strip()
                if row_model_kind in valid_model_kinds:
                    model_kind = row_model_kind
                front_template = normalize_card_content(card_cfg["front"], "front")
                back_template = normalize_card_content(card_cfg["back"], "back")
                required_fields = referenced_placeholder_fields(front_template, back_template)
                if any(not (row.get(field, "") or "").strip() for field in required_fields):
                    continue
                front = render_template(front_template, row)
                back = render_template(back_template, row)
                if not front.strip() or not back.strip():
                    continue
                row_identity = "|".join(f"{key}={value}" for key, value in sorted(row.items()))
                notes.append(
                    NoteRecord(
                        guid_key=f"{source_name}:{card_cfg.get('name', 'card')}:{row_index}:{row_identity}",
                        model_kind=model_kind,
                        front=front,
                        back=back,
                        source_file=source_name,
                        card_name=card_cfg.get("name", "card"),
                        tags=(tag_from_source(source_name),),
                    )
                )
    return notes


def write_html_preview(notes: list[NoteRecord], output_path: Path, deck_name: str) -> None:
    cards_html = []
    for idx, note in enumerate(notes, start=1):
        cards_html.append(
            f"""
            <article class="card">
              <div class="meta">#{idx} · {html.escape(note.source_file)} · {html.escape(note.card_name)}</div>
              <h2>Front</h2>
              <div class="face">{note.front}</div>
              <h2>Back</h2>
              <div class="face">{note.front}<hr>{note.back}</div>
            </article>
            """
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(deck_name)} Preview</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f1e8;
      --panel: #fffdf9;
      --ink: #1e1b18;
      --muted: #6c6258;
      --line: #dccfbf;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background: linear-gradient(180deg, #efe4d2 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 920px;
      margin: 0 auto;
      padding: 32px 20px 80px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      margin-top: 20px;
      box-shadow: 0 10px 30px rgba(60, 38, 14, 0.08);
    }}
    .meta {{
      font-size: 0.9rem;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .face {{
      font-size: 1.05rem;
      line-height: 1.55;
    }}
    hr {{
      border: none;
      border-top: 1px solid var(--line);
      margin: 18px 0;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(deck_name)}</h1>
    <p>{len(notes)} notes generated from deck config in {html.escape(str(ROOT))}.</p>
    {''.join(cards_html)}
  </main>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")


def write_apkg(notes: list[NoteRecord], output_path: Path, deck_name: str, css: str) -> bool:
    try:
        import genanki  # type: ignore
    except ImportError:
        return False

    specs = builtin_model_specs(deck_name, css)
    models: dict[str, Any] = {}
    for kind, spec in specs.items():
        models[kind] = genanki.Model(
            spec["model_id"],
            spec["name"],
            fields=spec["fields"],
            templates=spec["templates"],
            css=spec["css"],
        )

    deck = genanki.Deck(stable_int(f"{deck_name}:deck"), deck_name)
    for note in notes:
        if note.model_kind not in models:
            raise ValueError(f"Unknown note model: {note.model_kind}")
        deck.add_note(
            genanki.Note(
                model=models[note.model_kind],
                fields=(
                    [note.front, note.back]
                    if note.model_kind == "basic"
                    else [note.front, note.back]
                ),
                guid=stable_guid(note.guid_key),
                tags=list(note.tags),
            )
        )
    genanki.Package(deck).write_to_file(str(output_path))
    return True


def build(config_path: Path, deck_name_override: str | None, output_dir: Path) -> tuple[int, Path, Path, bool]:
    config = ensure_config(config_path)
    deck_name = deck_name_override or config.get("deck_name", DEFAULT_DECK_NAME)
    css = config.get("css", DEFAULT_CSS)
    notes = load_notes(config)
    if not notes:
        raise ValueError("No notes found. Add rows to data/*.csv or card definitions to config/deck_config.json.")

    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(deck_name)
    html_path = output_dir / f"{slug}.html"
    apkg_path = output_dir / f"{slug}.apkg"
    write_html_preview(notes, html_path, deck_name)
    wrote_apkg = write_apkg(notes, apkg_path, deck_name, css)
    return len(notes), html_path, apkg_path, wrote_apkg


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an Anki deck and HTML preview from config/deck_config.json.")
    parser.add_argument("--deck-name")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    try:
        count, html_path, apkg_path, wrote_apkg = build(args.config, args.deck_name, args.output_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Built {count} notes.")
    print(f"HTML preview: {html_path}")
    if wrote_apkg:
        print(f"Anki package: {apkg_path}")
    else:
        print("Anki package skipped: install genanki to produce .apkg")
        print("Suggested command: .venv/bin/pip install genanki")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
