# Live typing into the focused app — design

## Problem

Live preview shows the running transcript in the on-screen indicator. That turns
out not to be what dictation needs: the words are visible but they are in the
wrong place, so you still read one thing and wait for another. The text should
appear where you are actually dictating — in the focused application — as you
speak.

The obstacle is that Whisper does not append, it **revises**. Each pass
re-transcribes the whole buffer, and more audio can change words it already
emitted ("recognize speech" → "wreck a nice beach"). Anything already typed into
a real document may turn out to be wrong, and correcting it means sending
Backspace into that document.

## Behavior

- While recording, settled words are typed into the window that was focused when
  recording started.
- A word is **settled** once two consecutive transcription passes agree on it.
  Unsettled words are not typed. In practice text lands roughly two seconds
  behind the voice, and the remainder lands the moment recording stops.
- **Backspace is never sent to chase a revision.** While recording, typing is
  strictly append-only. Backspace is sent in exactly two places, both of them
  end-of-recording moments guarded by the focus check: Esc's undo, and the single
  reconciliation described below.
- Typing happens **only while the original window is focused**. Switch away and
  EasyType keeps listening but stops typing; switch back and it resumes from
  where it left off.
- **Esc undoes it** — backspaces exactly the characters EasyType typed — but only
  if the original window is still focused. Otherwise it stops, leaves the text,
  and says so.
- With live typing on, the indicator shows **only the timer**. The caption box is
  for when text is not going into the app; showing it in both places is noise.
- Live typing is **off by default**, with a Settings checkbox. It changes what
  happens to the user's documents, so it must be opted into.

## Mechanism

### Settling by agreement between passes

Keep the previous pass's raw transcript. On each new pass, take the longest
leading run the two agree on (compared case-insensitively — Whisper flips the
case of the opening word as context arrives), then trim back to the last complete
word. That prefix is settled.

Trimming to a word boundary is not cosmetic; it is what makes the rest of the
pipeline safe. A trailing partial word could still become a different word, and
several cleanup rules below are only prefix-stable when whole words are
committed.

Rejected alternative: committing whole Whisper *segments* instead. Segment
boundaries follow pauses, which would be tidier, but segments are still revisable
between passes, so agreement between passes would be needed anyway — the segment
API adds nothing here.

### Live typing must use the main transcription model

Preview currently runs `tiny.en` while real transcription runs the configured
model. That is the right trade when preview is only something to look at. Once
preview text becomes the text in the document, the preview model *is* the
dictation model, and dictating through `tiny.en` is a quality regression against
what EasyType does today.

So when live typing is on, the live passes run the **configured transcription
model**, ignoring `preview.model`. Two consequences, both good: what lands is the
quality the user already expects, and the final full-clip pass comes from the
same model as the settled text, so the two agree and nothing has to be undone at
the end.

The cost is the main model re-reading a growing buffer once a second. This is the
part of the design most likely to need tuning in practice.

### Cleanup moves to commit time

`polish_text` currently runs on the finished transcript. Capitalizing the first
word of a finished transcript would mean backspacing to the start, so the rules
have to apply to each chunk as it is typed instead.

Every rule in `polish_text` except the closing period is **prefix-stable** given
whole-word commits: applying it to a prefix produces a prefix of applying it to
the whole. So `polish.py` splits into:

- `polish_stream(text)` — all the existing rules except the closing period, and
  without the trailing `rstrip` (a trailing space is meaningful mid-dictation).
- `polish_text(text)` — `polish_stream`, then rstrip and the closing-period rule.
  Behavior is unchanged for every existing caller.

The closing period is typed as one final keystroke when recording stops.

Dictionary replacements apply to the whole settled text before the chunk is
sliced off, so multi-word rules ("ops plus" → "OPS+") still match across a chunk
boundary.

### Why a focus check rather than trust

`xdotool` types into whatever is focused. Recording the window id at start and
comparing before every write is what keeps typing out of the wrong document, and
it is what makes Esc's backspacing defensible: it only runs when the window that
received the text is still the one in front.

### AI cleanup is incompatible

The formatter rewrites the entire transcript globally, which cannot be reconciled
with append-only typing. When both are enabled, **live typing is skipped** and
EasyType behaves as it does today. The user's formatter setting is never silently
changed; a notification explains why live typing did not engage.

## Components

### `src/easytype/live.py` — `LiveTypist` (new)

Pure helpers, directly testable:

- `settled_prefix(previous: str, current: str) -> str` — the agreed, whole-word
  leading run. Empty when the two share no complete word.
- `pending_chunk(processed: str, already_typed: str) -> str` — the not-yet-typed
  remainder, or `""` when `processed` is not an extension of `already_typed`
  (an earlier word changed; append-only cannot fix it, so the chunk is skipped
  and `finish` reconciles).

`LiveTypist(injector, config, dictionary)`:

- `start()` — record the focused window id, clear all state.
- `feed(raw: str)` — settle, apply dictionary + `polish_stream`, slice the
  pending chunk, and type it if the original window is focused. Updates the typed
  count.
- `finish(final: str) -> str` — reconcile the document with the authoritative
  final transcript, then type the closing period. Returns the text typed.

  The final transcript is normally an extension of what was typed, since both
  come from the same model, and the remainder is simply appended. When it is not,
  `finish` backspaces back to the **divergence point only** — not the whole text
  — and types the correct remainder. This is the one corrective backspace in the
  design: it is bounded by how far back the two disagree, it runs once, and it is
  guarded by the focus check like every other write. On a focus mismatch it types
  nothing and reports what was left behind.

  The alternative, leaving divergent text in place, was rejected: it would leave
  the document holding words the final pass had already rejected, with no way for
  the user to know which.
- `undo() -> bool` — backspace the typed count when the original window is
  focused; returns whether it ran.
- `active: bool` — whether anything has been typed this session.

Every method is a no-op when the window check fails, and window-check failures
are logged once, not per pass.

### `src/easytype/preview.py`

`PreviewWorker` loses its `indicator` dependency and takes an `on_text` callback
instead. The controller supplies either `indicator.caption` or `LiveTypist.feed`.
The worker no longer knows what consumes its transcripts, which is why the
"caption or type, never both" rule needs no flag inside it.

### `src/easytype/injector/x11.py`

- `type_text(text)` — raw incremental typing, no method switching.
- `backspace(count)` — `xdotool key --clearmodifiers --repeat <n> BackSpace`.
- `active_window() -> str` — `xdotool getactivewindow`; `""` on failure, which
  the focus check treats as "not the original window", i.e. it fails closed.

### `src/easytype/controller.py`

- Takes a `live` collaborator, default `None`, guarded at each call site as
  `media` and `preview` already are.
- `_start()` → `self._live.start()` before the preview worker starts.
- `on_cancel()` recording branch → `self._live.undo()`.
- `process_audio()` → when live typing is active, `self._live.finish(text)`
  replaces the injector call. History still records the full final text, and
  `last_transcript` is unchanged so F8 repaste still re-injects the whole thing.

### `src/easytype/engine.py`

Decides the preview sink and which model backs it:

- Live typing on and formatter off → live passes use `config.model`; the worker's
  `on_text` is `LiveTypist.feed`; the indicator gets no captions.
- Otherwise → today's behavior: `config.preview_model` and `indicator.caption`.
- Only one transcriber is built when live typing is on, since preview and final
  share the model — loading a second `medium.en` would cost roughly 1.5 GB of
  VRAM for no benefit.

### `src/easytype/transcriber.py`

Sharing one `Transcriber` between the preview thread and the final pass means two
threads can call `transcribe` at once: `PreviewWorker.stop()` joins with a short
timeout by design, so a pass may still be in flight when the final transcription
begins. `faster_whisper.WhisperModel` makes no thread-safety guarantee, so
`Transcriber.transcribe` takes an instance lock.

The lock is what lets `stop()` keep its short join: the final pass simply waits
out the in-flight preview pass (under a second) instead of the controller having
to coordinate.

### `src/easytype/config.py`, `gui/settings.py`

- New `Config.inject_live: bool`, default `False`, from `[preview] inject_live`.
- Settings → Indicator gains "Type text into the app as I speak (experimental)"
  with a tooltip covering the two-second lag and that it overrides the preview
  model.

## Testing (TDD — tests written first)

- `test_live.py`
  - `settled_prefix`: pure append; a revision partway through; case-only
    difference in the opening word; no shared complete word → `""`; identical
    input → whole text minus any trailing partial word.
  - `pending_chunk`: normal extension; unrelated rewrite → `""`; nothing new → `""`.
  - `LiveTypist.feed` across a sequence of passes types each chunk exactly once
    and never types the same text twice.
  - A multi-word dictionary rule spanning a chunk boundary is applied.
  - `feed` types nothing when the focused window differs from the start window,
    and resumes when it matches again.
  - `undo` backspaces exactly the typed count, and does nothing on a window
    mismatch.
  - `finish` types only the unsettled remainder plus the closing period.
  - `finish` on a divergent final transcript backspaces to the divergence point
    and no further, then types the corrected remainder.
  - `finish` on a focus mismatch types nothing.
- `test_transcriber.py`
  - Concurrent `transcribe` calls are serialized — a fake model that would
    observe re-entrancy never does.
- `test_polish.py`
  - `polish_stream` is prefix-stable over whole-word prefixes of a sentence.
  - `polish_stream` adds no closing period and preserves a trailing space.
  - Existing `polish_text` tests are unchanged and still pass.
- `test_injector_x11.py`
  - `backspace` builds the expected `xdotool` argv.
  - `active_window` returns `""` when `xdotool` fails.
- `test_preview.py` — the worker calls `on_text` rather than an indicator.
- `test_controller.py` — live start on record; `undo` on cancel; `finish` instead
  of `inject` when live is active; history still written; no live collaborator
  still works.
- `test_config.py` — `inject_live` default and round-trip.

Fakes throughout: no test runs `xdotool`, loads a model, or opens a window.

## Out of scope

- **Backspacing to correct revisions during dictation.** Explicitly rejected: it
  is what makes live typing dangerous in a real document.
- **Making the formatter work with live typing.** A global rewrite cannot be
  applied append-only.
- **Undo history beyond the current recording.** Esc undoes the session it is in;
  earlier dictations are the application's own undo problem.

## Known trade-offs

- **Text lands about two seconds behind the voice.** Inherent to requiring
  agreement between passes; it is the price of never backspacing.
- **The main model runs once a second during recording.** Heavier GPU load than
  preview's `tiny.en`, sharing the card with Ollama. If it cannot keep up, the
  fallback is configuring a smaller model for transcription generally, or turning
  live typing off.
- **`type_delay_ms` is 40ms on this machine**, so a 20-character chunk takes
  0.8s while chunks arrive about every second. Fast speech will fall behind. A
  lower delay for live chunks is the likely fix, but the number should come from
  real use rather than a guess, so no new setting is added up front.
- **A word can settle wrongly.** Two passes agreeing is strong but not proof; a
  third pass can still revise. When that happens the wrong word stays typed,
  because fixing it would require Backspace.
