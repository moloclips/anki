#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from build_deck import DATA_DIR, DEFAULT_CONFIG_PATH, DEFAULT_OUTPUT_DIR, build, ensure_config, extract_fields, read_csv_rows
from sanders_server import (
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

BASE_DIR = HERE
INDEX_PATH = BASE_DIR / "editor.html"
VISIBLE_ANKI_CSVS = (
    ("models.csv", DATA_DIR / "models.csv"),
    ("companies.csv", DATA_DIR / "companies.csv"),
    ("science.csv", DATA_DIR / "science.csv"),
    ("people.csv", DATA_DIR / "people.csv"),
    ("iabied.csv", DATA_DIR / "iabied.csv"),
    ("metr.csv", DATA_DIR / "metr.csv"),
    ("sanders.csv", DATA_DIR / "sanders.csv"),
)


class AutoBuilder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._status = "idle"
        self._message = "Waiting for changes."
        self._error = ""
        self._count = 0
        self._html_path = ""
        self._apkg_path = ""
        self._wrote_apkg = False
        self._last_attempt = 0.0
        self._last_success = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def state(self) -> dict:
        with self._lock:
            return {
                "version": self._version,
                "status": self._status,
                "message": self._message,
                "error": self._error,
                "count": self._count,
                "html_path": self._html_path,
                "apkg_path": self._apkg_path,
                "wrote_apkg": self._wrote_apkg,
                "last_attempt": self._last_attempt,
                "last_success": self._last_success,
            }

    def _set_state(self, **updates: object) -> None:
        with self._lock:
            for key, value in updates.items():
                setattr(self, f"_{key}", value)
            self._version += 1

    def watch_paths(self) -> tuple[Path, ...]:
        return (DEFAULT_CONFIG_PATH, *(path for _, path in VISIBLE_ANKI_CSVS))

    def _snapshot(self) -> tuple[tuple[str, int | None], ...]:
        rows: list[tuple[str, int | None]] = []
        for path in self.watch_paths():
            try:
                stamp: int | None = path.stat().st_mtime_ns
            except FileNotFoundError:
                stamp = None
            rows.append((str(path), stamp))
        return tuple(rows)

    def rebuild(self) -> dict:
        started = time.time()
        self._set_state(status="building", message="Rebuilding deck...", error="", last_attempt=started)
        try:
            count, html_path, apkg_path, wrote_apkg = build(
                DEFAULT_CONFIG_PATH, None, DEFAULT_OUTPUT_DIR
            )
        except Exception as exc:  # noqa: BLE001
            self._set_state(
                status="error",
                message="Auto-build failed.",
                error=str(exc),
                last_attempt=started,
            )
            raise
        self._set_state(
            status="ok",
            message=f"Auto-built {count} notes.",
            error="",
            count=count,
            html_path=str(html_path),
            apkg_path=str(apkg_path),
            wrote_apkg=wrote_apkg,
            last_attempt=started,
            last_success=time.time(),
        )
        return self.state()

    def _run(self) -> None:
        previous = self._snapshot()
        pending_since: float | None = None
        while not self._stop.is_set():
            current = self._snapshot()
            if current != previous:
                previous = current
                pending_since = time.monotonic()
                self._set_state(
                    status="pending",
                    message="Changes detected. Waiting for edits to settle...",
                    error="",
                )
            if pending_since is not None and (time.monotonic() - pending_since) >= 0.8:
                try:
                    self.rebuild()
                except Exception:  # noqa: BLE001
                    pass
                pending_since = None
            self._stop.wait(0.35)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            self.rebuild()
        except Exception:  # noqa: BLE001
            pass
        self._thread = threading.Thread(target=self._run, name="anki-auto-builder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


AUTO_BUILDER = AutoBuilder()


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
        "build_status": AUTO_BUILDER.state(),
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
        if self.path == "/api/build-status":
            self._send_json(AUTO_BUILDER.state())
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
                result = AUTO_BUILDER.rebuild()
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"ok": True, **result})
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
    port = 8775
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    AUTO_BUILDER.start()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Anki editor running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        AUTO_BUILDER.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
