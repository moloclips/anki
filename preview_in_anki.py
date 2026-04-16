#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import build_deck


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "deck_config.json"
DEFAULT_OUTPUT_DIR = ROOT / "out"
DEFAULT_PREVIEW_DECK_NAME = "AI Politics Prep Preview"
ANKI_CONNECT_URL = "http://127.0.0.1:8765"


class AnkiConnectError(RuntimeError):
    pass


def invoke(action: str, params: dict[str, Any] | None = None) -> Any:
    payload = {
        "action": action,
        "version": 5,
        "params": params or {},
    }
    request = urllib.request.Request(
        ANKI_CONNECT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise AnkiConnectError(
            "Could not reach AnkiConnect at http://127.0.0.1:8765. "
            "Open Anki Desktop on your test profile and make sure the AnkiConnect add-on is enabled."
        ) from exc
    except json.JSONDecodeError as exc:
        raise AnkiConnectError("AnkiConnect returned invalid JSON.") from exc

    if body.get("error"):
        raise AnkiConnectError(str(body["error"]))
    return body.get("result")


def normalize_query_deck_name(deck_name: str) -> str:
    return deck_name.replace('"', '\\"')


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a preview .apkg and refresh it into a live Anki Desktop profile via AnkiConnect."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--deck-name",
        default=DEFAULT_PREVIEW_DECK_NAME,
        help="Deck name to use inside the test Anki profile.",
    )
    parser.add_argument(
        "--profile",
        help="Optional Anki profile name to switch to before importing.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Build and import without opening the deck browser afterward.",
    )
    args = parser.parse_args()

    try:
        count, _, apkg_path, wrote_apkg = build_deck.build(args.config, args.deck_name, args.output_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not wrote_apkg:
        print("This preview flow needs genanki to write an .apkg file.", file=sys.stderr)
        print("Install it with: .venv/bin/pip install genanki", file=sys.stderr)
        return 1

    try:
        version = invoke("version")
        if args.profile:
            active_profile = invoke("getActiveProfile")
            if active_profile != args.profile:
                invoke("loadProfile", {"name": args.profile})
                active_profile = invoke("getActiveProfile")
                if active_profile != args.profile:
                    raise AnkiConnectError(
                        f"Anki is still on profile '{active_profile}', not '{args.profile}'."
                    )

        deck_names = invoke("deckNames")
        if args.deck_name in deck_names:
            invoke("deleteDecks", {"decks": [args.deck_name], "cardsToo": True})

        invoke("importPackage", {"path": str(apkg_path)})

        if not args.no_open:
            query = f'deck:"{normalize_query_deck_name(args.deck_name)}"'
            invoke("guiBrowse", {"query": query})
    except AnkiConnectError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Built and imported {count} notes into '{args.deck_name}'.")
    print(f"Preview package: {apkg_path}")
    print(f"AnkiConnect version: {version}")
    if args.profile:
        print(f"Profile: {args.profile}")
    if not args.no_open:
        print("Opened the imported deck in Anki Browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
