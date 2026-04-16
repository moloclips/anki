#!/usr/bin/env python3
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
VIDEOS_CSV = BASE_DIR / "videos.csv"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
YT_DLP = "/opt/homebrew/bin/yt-dlp"


def youtube_id_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.netloc in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/")
    if parsed.netloc.endswith("youtube.com"):
        return parse_qs(parsed.query).get("v", [""])[0]
    return ""


def read_videos() -> list[dict[str, str]]:
    with VIDEOS_CSV.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fetch_video(url: str) -> int:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        YT_DLP,
        "--skip-download",
        "--write-auto-sub",
        "--write-sub",
        "--sub-langs",
        "en.*",
        "--sub-format",
        "srt",
        "-o",
        str(TRANSCRIPTS_DIR / "%(id)s.%(ext)s"),
        url,
    ]
    print(f"Fetching subtitles for {url}")
    return subprocess.call(command)


def main() -> int:
    failures = 0
    seen: set[str] = set()
    for row in read_videos():
        url = (row.get("url") or "").strip()
        if not url:
            continue
        video_id = youtube_id_from_url(url)
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        code = fetch_video(url)
        if code != 0:
            failures += 1
    if failures:
        print(f"Finished with {failures} subtitle fetch failures.", file=sys.stderr)
        return 1
    print("Finished fetching subtitles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
