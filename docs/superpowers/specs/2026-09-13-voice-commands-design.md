# Voice commands and spoken punctuation — design

Date: 2026-09-13
Status: approved, not yet implemented

## Problem

Two complaints, one root cause: EasyType treats every dictation as a complete,
standalone sentence.

1. `polish_text` forces a trailing period onto every transcript. Stopping
   mid-thought therefore produces `I think this is.` and the next dictation
   opens a new capitalised sentence — `A good idea.` The user stops and starts
   constantly, so this is a daily irritation.
2. There is no way to speak a line break, a paragraph break, or a correction.
   Whisper never emits `\n`, so multi-line dictation is impossible, and a
   misspoken sentence can only be fixed by hand.

PR #15 (space between back-to-back dictations) fixed the run-together case
(`…EasyType.Here is…`). It did not address either item above.

## Scope

In scope: spoken punctuation, spoken line breaks, `scratch that`, removal of
the forced terminal period, one on/off setting, README documentation, tests.

Out of scope: a user-editable command list (the existing dictionary covers
custom word swaps), Wayland support (deferred to February 2027 by decision on
2026-09-12), wake words, and continuous/streaming command recognition.

## Command set

Built in, not user-editable.

| Spoken phrase | Result |
| --- | --- |
| `period` | `.` |
| `comma` | `,` |
| `question mark` | `?` |
| `exclamation point` | `!` |
| `new line` | `\n` |
| `new paragraph` | `\n\n` |
| `scratch that` | action — see below |

Matching rules:

- Case-insensitive, whole-phrase, on word boundaries.
- A trailing `.` or `,` that Whisper attached to the phrase is absorbed by the
  match. Whisper commonly returns `New paragraph.` rather than `new paragraph`.
- `newline` (one word) is accepted as an alias of `new line`, because Whisper
  emits both.
- Commands are matched **after** the user dictionary and **after** the optional
  AI formatter, and **before** `polish_text`. Polish must see the real
  punctuation characters so its capitalisation and spacing rules fire on them.

Known and accepted trade-off: a phrase used as a command can no longer be
dictated literally. This is standard for dictation tools.

## New module: `src/easytype/commands.py`

Pure text transformation, no I/O, so it is trivially testable.

```
apply_commands(text: str) -> str
```

Applies the swap table above. `scratch that` is *not* handled here — it is an
action, and needs controller state.

```
split_scratch(text: str) -> str
```

Returns the portion of `text` after the final `scratch that`, or the whole
string when the phrase is absent. Whether anything preceded it is what tells
the controller how far back to delete (see below).

## Pipeline placement

`controller.py::process_audio` becomes:

    transcribe
      → apply_dictionary
      → format_text        (AI, optional)
      → apply_commands     (new)
      → polish_text
      → scratch handling   (new)
      → inject

`LiveTypist.feed` also runs `apply_commands` on the settled prefix, alongside
the dictionary it already applies. The swap table is a whole-word replacement
and so preserves the prefix-stability invariant `live.py` depends on.
`scratch that` is deliberately **not** applied live — it would require
backspacing during append-only typing. The literal words appear on screen while
you speak and are removed by the existing reconciliation in `finish()`.

## `polish.py` changes

1. Delete the forced terminal period. `polish_text` keeps the `rstrip()` and
   the trailing-comma cleanup, but no longer appends `.` when the transcript
   ends bare. Whisper's own punctuation stands.
2. Add a rule that capitalises the first letter after a line break, so
   `new paragraph` starts a proper sentence. The existing `_AFTER_SENTENCE`
   rule only fires after `.!?`.

Both rules must remain prefix-stable so `polish_stream` stays safe for live
typing: for any whole-word prefix `p` of `t`, `polish_stream(t)` must start
with `polish_stream(p)`.

## `scratch that` semantics

Let `tail` be the text after the final `scratch that` in this transcript.

- **Phrase at the start** (nothing said before it): delete the previous
  dictation from the document, then type `tail` (usually empty).
- **Phrase partway through**: discard everything before it, type `tail`. The
  previous dictation is left alone.
- **Focus moved**: if the focused window is not the one the previous dictation
  landed in, nothing is deleted. Print the same style of warning `LiveTypist`
  already prints, and type `tail` only.

Deleting the previous dictation reuses state PR #15 introduced:
`Controller._last_window`, `Controller._lead_in`, and `Controller.last_transcript`.
The number of characters to remove is `len(self._lead_in + self.last_transcript)`.

Order of operations when a previous dictation must be removed and live typing
is active:

1. `live.undo()` — remove everything typed during this dictation.
2. `injector.backspace(n)` — remove the previous dictation.
3. Inject `tail`.

Doing it in this order matters: the previous dictation sits *before* the
current one in the document, so it cannot be backspaced until the current text
is gone.

After a successful scratch, `last_transcript` is cleared and `_last_window` is
reset, so a second `scratch that` does not delete text the app no longer owns.

## Configuration

One new key:

```toml
voice_commands = true
```

Exposed in the Settings window as a single checkbox, **Voice commands**,
default on.

It exists for one concrete hazard: in Slack, Teams, and most chat inputs a line
break is Enter, which sends the message. There is no reliable way from outside
the application to tell a chat box from a document, so the escape hatch is an
off switch rather than detection.

When off, `apply_commands` and `scratch that` are both skipped and spoken
punctuation words are typed literally.

## Pre-work: measure Whisper's punctuation

Removing the forced period is only safe if Whisper reliably ends sentences.
Before touching `polish.py`, write a throwaway script that records roughly a
minute of ordinary speech and prints the **raw** transcript, before any
dictionary, formatter, or polish pass. Count how many utterances came back
with terminal punctuation.

If the rate is poor, stop and report rather than shipping the change. The rest
of the design (commands, `scratch that`, the setting) does not depend on this
result and can proceed either way.

**Measured 2026-09-13, `small.en`, eight utterances: 7 of 8 ended with `.`,
`!` or `?`.** The single bare result was `'I guess so not really sure'` — a
genuine trailing-off, which is exactly the case that should not receive a
period. Change approved on that evidence.

## Testing

Unit, no hardware:

- `commands.py`: each swap, case-insensitivity, absorbed trailing punctuation,
  the `newline` alias, phrases inside longer sentences, and a phrase that must
  *not* match a substring of another word.
- `split_scratch`: absent, at the start, partway through, repeated.
- `polish.py`: a bare ending stays bare, an existing period survives, a word
  after a line break is capitalised, and `polish_stream` prefix-stability holds
  across a line break.
- `controller.py`: scratch at start deletes the previous dictation; scratch
  partway does not; a moved window deletes nothing; `voice_commands = false`
  types the words literally; history and repaste keep the final text.
- `live.py`: swaps apply to the live stream; `scratch that` does not.

Full suite must be green (`\.venv/bin/python -m pytest -q`) before the PR.

## Delivery

One branch, one PR, per the project workflow in `CLAUDE.md`. The measurement
script is throwaway and is not committed.
