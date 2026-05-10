#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = ROOT / "METR" / "time_horizons_combined.csv"
OUTPUT_CSV = ROOT / "metr.csv"
EXCLUDED_MODELS = {"gpt_4_1106"}
MODEL_NAMES = {
    "gpt2": "GPT-2",
    "davinci_002": "GPT-3",
    "gpt_3_5_turbo_instruct": "GPT-3.5",
    "gpt_4": "GPT-4",
    "gpt_4_1106": "GPT-4 1106",
    "gpt_4o": "GPT-4o",
    "claude_3_5_sonnet_20240620": "Claude 3.5 Sonnet (Jun 2024)",
    "o1_preview": "o1-preview",
    "claude_3_5_sonnet_20241022": "Claude 3.5 Sonnet (Oct 2024)",
    "o1": "o1",
    "claude_3_7_sonnet": "Claude 3.7 Sonnet",
    "o3": "o3",
    "gpt_5_2025_08_07": "GPT-5",
    "gemini_3_pro": "Gemini 3 Pro",
    "claude_opus_4_5": "Claude Opus 4.5",
    "gpt_5_2": "GPT-5.2",
    "claude_opus_4_6": "Claude Opus 4.6",
}


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def normalize_model_id(model_id: str) -> str:
    return model_id.removesuffix("_inspect")


def display_model_name(model_id: str) -> str:
    return MODEL_NAMES.get(model_id, model_id)


def choose_unit(minutes: float) -> str:
    total_seconds = minutes * 60
    if total_seconds < 60:
        return "sec"
    if minutes < 90:
        return "min"
    return "hr"


def format_value_in_unit(minutes: float, unit: str) -> str:
    if unit == "sec":
        seconds = round(minutes * 60)
        return str(seconds)
    if unit == "min":
        if minutes < 1:
            rounded = round(minutes, 1)
        elif minutes < 10:
            rounded = round(minutes, 1)
        else:
            rounded = round(minutes)
        return str(int(rounded)) if float(rounded).is_integer() else str(rounded)
    hours = minutes / 60
    rounded = round(hours, 1)
    return str(int(rounded)) if float(rounded).is_integer() else str(rounded)


def format_minutes_for_humans(value: str) -> str:
    minutes = float(value)
    unit = choose_unit(minutes)
    return f"{format_value_in_unit(minutes, unit)} {unit}"


def format_ci(low: str, high: str) -> str:
    low_minutes = float(low)
    high_minutes = float(high)
    unit_order = {"sec": 0, "min": 1, "hr": 2}
    unit = choose_unit(low_minutes)
    high_unit = choose_unit(high_minutes)
    if unit_order[high_unit] > unit_order[unit]:
        unit = high_unit
    return f"{format_value_in_unit(low_minutes, unit)}-{format_value_in_unit(high_minutes, unit)} {unit}"


def main() -> None:
    with SOURCE_CSV.open(newline="") as infile:
        reader = csv.DictReader(infile)
        th11_candidates: dict[str, dict[str, str]] = {}
        for row in reader:
            if not is_truthy(row.get("is_sota", "")):
                continue
            if row.get("dataset") != "TH1.1":
                continue
            model_key = normalize_model_id(row["model_id"])
            if model_key in EXCLUDED_MODELS:
                continue
            candidate = {
                "model": display_model_name(model_key),
                "benchmark": row["dataset"],
                "date": row["release_date"],
                "p50": format_minutes_for_humans(row["p50_estimate"]),
                "p50_ci": format_ci(row["p50_ci_low"], row["p50_ci_high"]),
                "p80": format_minutes_for_humans(row["p80_estimate"]),
            }
            th11_candidates[model_key] = candidate

        rows = list(th11_candidates.values())

    rows.sort(key=lambda row: (row["date"], row["model"]))

    fieldnames = ["model", "benchmark", "date", "p50", "p50_ci", "p80"]

    with OUTPUT_CSV.open("w", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} SOTA rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
