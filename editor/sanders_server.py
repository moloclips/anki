#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


EDITOR_DIR = Path(__file__).resolve().parent
ROOT = EDITOR_DIR.parent
DATA_DIR = ROOT / "data"
SANDERS_DATA_DIR = DATA_DIR / "sanders"
INDEX_PATH = EDITOR_DIR / "sanders_index.html"
VIDEOS_CSV = SANDERS_DATA_DIR / "videos.csv"
CARDS_CSV = DATA_DIR / "sanders.csv"
REFERENCES_CSV = SANDERS_DATA_DIR / "references.csv"
TRANSCRIPTS_DIR = SANDERS_DATA_DIR / "transcripts"
REFERENCE_FIELDS = [
    "id",
    "youtube_id",
    "start_timestamp",
    "start_segment_index",
    "start_char",
    "end_timestamp",
    "end_segment_index",
    "end_char",
]


@dataclass
class Segment:
    start: str
    stop: str
    text: str


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def parse_srt(path: Path) -> list[Segment]:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    segments: list[Segment] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        timestamp_line = lines[1] if "-->" in lines[1] else lines[0]
        if "-->" not in timestamp_line:
            continue
        start, stop = [part.strip().replace(",", ".") for part in timestamp_line.split("-->")]
        payload = lines[2:] if timestamp_line == lines[1] else lines[1:]
        segments.append(Segment(start=start, stop=stop, text=" ".join(payload).strip()))
    return segments


def youtube_id_from_url(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[-1]
    return url.rstrip("/").split("/")[-1]


def build_transcript_payload(video_id: str, path: Path, videos: dict[str, dict[str, str]]) -> dict:
    segments = parse_srt(path)
    full_parts: list[str] = []
    segment_rows: list[dict] = []
    cursor = 0
    for index, segment in enumerate(segments):
        text = segment.text
        start_offset = cursor
        full_parts.append(text)
        cursor += len(text)
        end_offset = cursor
        if index < len(segments) - 1:
            full_parts.append("\n")
            cursor += 1
        segment_rows.append(
            {
                "index": index,
                "start": segment.start,
                "stop": segment.stop,
                "text": text,
                "start_offset": start_offset,
                "end_offset": end_offset,
            }
        )
    return {
        "video_id": video_id,
        "title": videos.get(video_id, {}).get("title", video_id),
        "date": videos.get(video_id, {}).get("date", ""),
        "path": str(path),
        "full_text": "".join(full_parts),
        "segments": segment_rows,
    }


def transcript_index() -> dict[str, dict]:
    videos = {youtube_id_from_url(video["url"]): video for video in read_csv(VIDEOS_CSV)}
    indexed: dict[str, dict] = {}
    if not TRANSCRIPTS_DIR.exists():
        return indexed
    preferred: dict[str, Path] = {}
    for path in sorted(TRANSCRIPTS_DIR.glob("*.srt")):
        video_id = path.name.split(".")[0]
        current = preferred.get(video_id)
        if current is None or ".en-orig." in path.name:
            preferred[video_id] = path
    for video_id, path in preferred.items():
        indexed[video_id] = build_transcript_payload(video_id, path, videos)
    return indexed


def search_transcripts(query: str) -> list[dict]:
    if not query.strip():
        return []
    needle = query.casefold()
    results: list[dict] = []
    for video_id, transcript in transcript_index().items():
        haystack = transcript["full_text"].casefold()
        start = 0
        while True:
            found = haystack.find(needle, start)
            if found == -1:
                break
            end = found + len(query)
            snippet_start = max(0, found - 180)
            snippet_end = min(len(transcript["full_text"]), end + 180)
            snippet = transcript["full_text"][snippet_start:snippet_end]
            results.append(
                {
                    "video_id": video_id,
                    "title": transcript["title"],
                    "date": transcript["date"],
                    "snippet": snippet,
                    "match_start": found,
                    "match_end": end,
                    "context_start": snippet_start,
                    "context_end": snippet_end,
                }
            )
            start = found + max(1, len(query))
    return results


def next_card_id(cards: list[dict[str, str]]) -> str:
    return str(len(cards) + 1)


def locate_char(transcript: dict, absolute_char: int) -> tuple[int, int]:
    segments = transcript["segments"]
    if not segments:
        return 0, 0
    for segment in segments:
        if segment["start_offset"] <= absolute_char <= segment["end_offset"]:
            local = max(0, min(absolute_char - segment["start_offset"], len(segment["text"])))
            return segment["index"], local
    last = segments[-1]
    return last["index"], len(last["text"])


def resolve_reference(video_id: str, start_abs_char: int, end_abs_char: int) -> dict:
    transcripts = transcript_index()
    transcript = transcripts[video_id]
    ordered_start = min(start_abs_char, end_abs_char)
    ordered_end = max(start_abs_char, end_abs_char)
    start_segment_index, start_char = locate_char(transcript, ordered_start)
    end_segment_index, end_char = locate_char(transcript, ordered_end)
    start_segment = transcript["segments"][start_segment_index]
    end_segment = transcript["segments"][end_segment_index]
    next_index = min(end_segment_index + 1, len(transcript["segments"]) - 1)
    if next_index > end_segment_index:
        end_timestamp = transcript["segments"][next_index]["start"]
    else:
        end_timestamp = end_segment["stop"]
    return {
        "youtube_id": video_id,
        "start_timestamp": start_segment["start"],
        "start_segment_index": str(start_segment_index),
        "start_char": str(start_char),
        "end_timestamp": end_timestamp,
        "end_segment_index": str(end_segment_index),
        "end_char": str(end_char),
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(INDEX_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path == "/api/state":
            transcripts = transcript_index()
            self._send_json(
                {
                    "videos": read_csv(VIDEOS_CSV),
                    "cards": read_csv(CARDS_CSV),
                    "references": read_csv(REFERENCES_CSV),
                    "transcripts": [
                        {
                            "video_id": item["video_id"],
                            "title": item["title"],
                            "date": item["date"],
                            "segments": len(item["segments"]),
                            "chars": len(item["full_text"]),
                        }
                        for item in transcripts.values()
                    ],
                }
            )
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._send_json({"results": search_transcripts(query)})
            return
        if parsed.path == "/api/transcript":
            video_id = parse_qs(parsed.query).get("video_id", [""])[0]
            transcripts = transcript_index()
            if video_id not in transcripts:
                self._send_json({"error": "Unknown video_id"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"transcript": transcripts[video_id]})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/cards":
            payload = self._read_json()
            cards = payload.get("cards")
            if not isinstance(cards, list):
                self._send_json({"error": "Expected cards list"}, HTTPStatus.BAD_REQUEST)
                return
            normalized = [{"front": card.get("front", ""), "back": card.get("back", "")} for card in cards]
            write_csv(CARDS_CSV, ["front", "back"], normalized)
            self._send_json({"ok": True})
            return
        if self.path == "/api/card/create":
            cards = read_csv(CARDS_CSV)
            new_card = {"front": "", "back": ""}
            cards.append(new_card)
            write_csv(CARDS_CSV, ["front", "back"], cards)
            self._send_json({"ok": True, "card": {"id": next_card_id(cards), **new_card}})
            return
        if self.path == "/api/references":
            payload = self._read_json()
            references = payload.get("references")
            if not isinstance(references, list):
                self._send_json({"error": "Expected references list"}, HTTPStatus.BAD_REQUEST)
                return
            write_csv(REFERENCES_CSV, REFERENCE_FIELDS, references)
            self._send_json({"ok": True})
            return
        if self.path == "/api/resolve-reference":
            payload = self._read_json()
            video_id = payload.get("video_id", "")
            start_abs_char = int(payload.get("start_abs_char", 0))
            end_abs_char = int(payload.get("end_abs_char", 0))
            transcripts = transcript_index()
            if video_id not in transcripts:
                self._send_json({"error": "Unknown video_id"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"reference": resolve_reference(video_id, start_abs_char, end_abs_char)})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 8776), Handler)
    print("Sanders transcript editor running at http://127.0.0.1:8776")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
