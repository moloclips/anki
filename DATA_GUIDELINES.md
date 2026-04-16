# Data Guidelines

This file captures the conventions used for [models.csv](/Users/diego/Desktop/Alignment/Moloclips/Anki/models.csv) and [history.csv](/Users/diego/Desktop/Alignment/Moloclips/Anki/history.csv).

## `models.csv`

Columns:
- `model`
- `company`
- `date`
- `params`
- `special`
- `summary`
- `source`

Rules:
- `date` is the first public announcement or release date for the named model/version, not a training-completion date.
- `date` is stored in machine-friendly form:
  - exact date: `YYYY-MM-DD`
  - month only: `YYYY-MM`
  - year only: `YYYY`
- `params` is optional.
- `params` should only use clearly public values.
- For model families or release sets, `params` should be the maximum parameter count in that released set.
- For MoE models, `params` uses total parameter count, not active parameter count.
- `special` is optional and should be used only for genuinely distinctive milestone models.
- `special` should be neutral and objective, not hypey.
- Good `special` values are short noun phrases such as `chatbot interface`, `test-time reasoning`, or `open weights`.
- `summary` is a short factual explanation of why the model mattered.
- `source` should point to a primary or official source when possible.
- `source` links may use text fragments like `#:~:text=` so the page opens near the relevant wording.

What to include:
- Prefer milestone models that convey the pace or direction of progress.
- Avoid minor revisions unless they clearly changed the trajectory.
- Prefer a lean set over completeness.

## `history.csv`

Columns:
- `event`
- `date`
- `precision`
- `notes`

Rules:
- `event` should be written in compact past tense.
- Avoid clunky phrasing like `founded (incorporation)`.
- Prefer simple wording such as `incorporated`, `launched`, `announced`, `published`, `disbanded`, `became public`.
- `date` is stored in machine-friendly form:
  - exact date: `YYYY-MM-DD`
  - month only: `YYYY-MM`
  - year only: `YYYY`
- `precision` should reflect how exact the public date really is:
  - `exact`
  - `month_only`
  - `year_only`
- If a date is too low-resolution to be worth memorizing, it should usually be omitted rather than included.
- `notes` should explain what the date represents.

Card-design guidance:
- Reverse date cards are useful by default.
- If multiple events share the same reverse answer, reverse cards for those collisions should be suppressed.

## General

- Prefer exact dates when they are solidly public.
- Do not use speculative parameter counts or speculative dates.
- Keep wording concise and consistent.
- Favor objective labels over rhetorical or promotional language.
