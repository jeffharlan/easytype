# EasyType — project instructions

Local voice-dictation tool: a PySide6 tray app + Settings GUI. Public OSS at
`github.com/jeffharlan/easytype`. Whisper transcribes, then text flows through
dictionary replacements → optional AI cleanup → deterministic polish → injection.

## How we ship changes

Every change — feature or fix — follows this flow. Do NOT commit straight to `main`.

1. **Branch** off `main` (`git checkout -b <short-name>`).
2. **TDD** — write the failing test first, watch it fail, then write the code to pass. New behavior always gets a test.
3. **Run the full suite** and confirm green before committing: `.venv/bin/python -m pytest -q`.
4. **Commit** with a clear message (`feat:` / `fix:` / `docs:` / `chore:` prefix).
5. **Push** the branch and **open a PR** (`gh pr create`). Never merge before CI runs.
6. **Wait for CI to pass** on the PR (`gh pr checks <n> --watch`). Green CI is the gate.
7. **Squash-merge and delete the branch** (`gh pr merge <n> --squash --delete-branch`), which also returns the local checkout to `main`.
8. Confirm `main` is clean and up to date afterward.

The point of the PR step even for a solo repo: CI verifies all tests on GitHub's
machines *before* anything lands on `main`, and the PR is a clean record of why
the change happened.

## Running and testing

- **Tests:** `.venv/bin/python -m pytest -q` (94+ tests; output should be pristine).
- **The app is an editable pipx install.** Code changes do NOT take effect until
  the running process is restarted. After merging or to test live, restart the
  tray app (`pkill -f easytype-gui`, then relaunch `easytype-gui` detached with
  `DISPLAY` and `XDG_RUNTIME_DIR` set). The GUI needs the system lib `libxcb-cursor0`.

## Text-cleanup pipeline (the order matters)

In `controller.py::process_audio`: transcribe → `apply_dictionary` →
`format_text` (AI, optional) → `polish_text` (deterministic, always) → inject.

- **`formatter.py`** — AI cleanup via local Ollama or OpenAI. Handles judgment
  calls only: commas, splitting run-ons, question marks. Gated on a config flag.
- **`polish.py`** — deterministic rules that always run last: capitalize sentence
  starts and standalone "I", tidy spacing, guarantee a terminal period. Rules, not
  a model, so these are correct every time even when AI cleanup is off. Question
  marks are the AI's job; the polish pass defaults to a period when none exists.
