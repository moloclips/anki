#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from build_deck import DEFAULT_CONFIG_PATH, DEFAULT_OUTPUT_DIR, build, ensure_config, extract_fields, read_csv_rows
from Sanders.server import (
    CARDS_CSV as SANDERS_CARDS_CSV,
    INDEX_PATH as SANDERS_INDEX_PATH,
    REFERENCE_FIELDS as SANDERS_REFERENCE_FIELDS,
    REFERENCES_CSV as SANDERS_REFERENCES_CSV,
    VIDEOS_CSV as SANDERS_VIDEOS_CSV,
    next_card_id,
    read_csv as read_generic_csv,
    resolve_reference,
    search_transcripts,
    transcript_index,
    write_csv as write_generic_csv,
)


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "editor.html"
VISIBLE_ANKI_CSVS = (
    ("models.csv", BASE_DIR / "models.csv"),
    ("history.csv", BASE_DIR / "history.csv"),
    ("iabied.csv", BASE_DIR / "iabied.csv"),
    ("sanders.csv", BASE_DIR / "sanders.csv"),
)


def list_csv_sources() -> list[dict]:
    sources = []
    for name, path in VISIBLE_ANKI_CSVS:
        if not path.exists():
            continue
        fields = extract_fields(path)
        rows = read_csv_rows(path)
        sources.append(
            {
                "name": name,
                "fields": fields,
                "sample_row": rows[0] if rows else {},
                "row_count": len(rows),
                "rows": rows,
            }
        )
    return sources


def load_state() -> dict:
    return {
        "config": ensure_config(DEFAULT_CONFIG_PATH),
        "sources": list_csv_sources(),
        "note_models": [
            {
                "id": "basic",
                "label": "Basic",
                "description": "One card: front to back.",
            },
            {
                "id": "basic_and_reversed",
                "label": "Basic + Reversed",
                "description": "Two cards: front to back and back to front.",
            },
        ],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "AnkiEditor/0.1"

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, text: str, status: int = HTTPStatus.OK) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            self._send_html(INDEX_PATH.read_text(encoding="utf-8"))
            return
        if self.path in {"/sanders", "/sanders/index.html"}:
            self._send_html(SANDERS_INDEX_PATH.read_text(encoding="utf-8"))
            return
        if self.path == "/api/state":
            self._send_json(load_state())
            return
        if self.path == "/sanders/api/state":
            transcripts = transcript_index()
            self._send_json(
                {
                    "videos": read_generic_csv(SANDERS_VIDEOS_CSV),
                    "cards": read_generic_csv(SANDERS_CARDS_CSV),
                    "references": read_generic_csv(SANDERS_REFERENCES_CSV),
                    "transcripts": [
                        {
                            "video_id": item["video_id"],
                            "title": item["title"],
                            "date": item["date"],
                            "segments": len(item["segments"]),
                            "chars": len(item["full_text"]),
                            "full_text": item["full_text"],
                        }
                        for item in transcripts.values()
                    ],
                }
            )
            return
        if self.path.startswith("/sanders/api/search"):
            from urllib.parse import parse_qs, urlparse

            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._send_json({"results": search_transcripts(query)})
            return
        if self.path.startswith("/sanders/api/transcript"):
            from urllib.parse import parse_qs, urlparse

            video_id = parse_qs(urlparse(self.path).query).get("video_id", [""])[0]
            transcripts = transcript_index()
            if video_id not in transcripts:
                self._send_json({"error": "Unknown video_id"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json({"transcript": transcripts[video_id]})
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/config":
            payload = self._read_json()
            config = payload.get("config")
            if not isinstance(config, dict):
                self._send_json({"error": "Expected config object"}, status=HTTPStatus.BAD_REQUEST)
                return
            DEFAULT_CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            self._send_json({"ok": True})
            return
        if self.path == "/api/build":
            try:
                count, html_path, apkg_path, wrote_apkg = build(
                    DEFAULT_CONFIG_PATH, None, DEFAULT_OUTPUT_DIR
                )
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(
                {
                    "ok": True,
                    "count": count,
                    "html_path": str(html_path),
                    "apkg_path": str(apkg_path),
                    "wrote_apkg": wrote_apkg,
                }
            )
            return
        if self.path == "/sanders/api/cards":
            payload = self._read_json()
            cards = payload.get("cards")
            if not isinstance(cards, list):
                self._send_json({"error": "Expected cards list"}, status=HTTPStatus.BAD_REQUEST)
                return
            normalized = [{"front": card.get("front", ""), "back": card.get("back", "")} for card in cards]
            write_generic_csv(SANDERS_CARDS_CSV, ["front", "back"], normalized)
            self._send_json({"ok": True})
            return
        if self.path == "/sanders/api/card/create":
            cards = read_generic_csv(SANDERS_CARDS_CSV)
            new_card = {"front": "", "back": ""}
            cards.append(new_card)
            write_generic_csv(SANDERS_CARDS_CSV, ["front", "back"], cards)
            self._send_json({"ok": True, "card": {"id": next_card_id(cards), **new_card}})
            return
        if self.path == "/sanders/api/references":
            payload = self._read_json()
            references = payload.get("references")
            if not isinstance(references, list):
                self._send_json({"error": "Expected references list"}, status=HTTPStatus.BAD_REQUEST)
                return
            write_generic_csv(
                SANDERS_REFERENCES_CSV,
                SANDERS_REFERENCE_FIELDS,
                references,
            )
            self._send_json({"ok": True})
            return
        if self.path == "/sanders/api/resolve-reference":
            payload = self._read_json()
            video_id = payload.get("video_id", "")
            start_abs_char = int(payload.get("start_abs_char", 0))
            end_abs_char = int(payload.get("end_abs_char", 0))
            transcripts = transcript_index()
            if video_id not in transcripts:
                self._send_json({"error": "Unknown video_id"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                {"reference": resolve_reference(video_id, start_abs_char, end_abs_char)}
            )
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def main() -> int:
    port = 8765
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Anki editor running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
