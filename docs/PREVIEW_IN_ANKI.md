# Live Anki Preview

Use this when you want to check the deck in real Anki Desktop instead of the browser preview.

## One-time setup

- Create a throwaway Anki profile for previewing imports.
- Install and enable the AnkiConnect add-on.
- Open Anki Desktop on that test profile before running the command.

## Command

From the project root:

```bash
.venv/bin/python Anki/tools/preview_in_anki.py --profile "Your Test Profile"
```

That command will:

- rebuild the deck as `AI Politics Prep Preview`
- delete the previous preview deck in the active profile
- import the new `.apkg` through AnkiConnect
- open the imported deck in Anki's Browser

## Notes

- The default preview deck name is `AI Politics Prep Preview`.
- This keeps the preview pipeline separate from your publishable deck name.
- If Anki is already on the correct profile, `--profile` is optional.
- Use `--no-open` if you do not want the Browser to pop open after import.
