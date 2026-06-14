# Calendar widget — hardening retrospective + class-closing harness

**Date:** 2026-06-14
**Context:** After shipping the calendar widget (PR #208) we ran an adversarial
review loop. Eight productive rounds surfaced **29 confirmed defects**. This
document synthesizes those findings into root-cause CLASSES and defines a small
set of permanent guards that close each class — so the loop becomes a
confirmation pass instead of a whack-a-mole grind.

## Root-cause classes (what the 29 defects really were)

| Class | Rounds | ~n | Root cause |
|---|---|---|---|
| **A. Real-`.ics` feed quirks** | 1,2,3,4,6,7 | ~10 | `parse_ics` / `_fetch_ics` written against an idealized `.ics`; real Google/iCloud/Outlook output leaked one quirk at a time (BOM, `webcal://`, percent-encoding, `file://localhost`, non-UTF-8 read, `STATUS:CANCELLED`, SUMMARY newlines, multi-`RRULE`, all-day `DTEND` spans). |
| **B. Recurrence-expansion cost/DoS** | 2,5,6,7,8 | ~5 | `recurring_ical_events` walks from `DTSTART` unbounded in both directions; patched one direction/frequency per round (OOM → sub-hourly → HOURLY-forward → HOURLY-pre-now → warning). |
| **C. Timezone correctness** | 1,3,8 | ~3 | tz-awareness fixed piecemeal (naive/aware crash → fixed-offset-vs-IANA DST → naive subtraction DST). |
| **D. next-mode selection semantics** | 2,3,4,8 | ~5 | "What is the *next* event" underspecified; priority over {future / in-progress / ongoing} × {timed / all-day} discovered case by case. |
| **E. validate ↔ runtime drift** | 1,5,6,7,8 | ~5 | `validate_config` didn't reject everything build/draw chokes on (time_format, bool, empty/whitespace strings, lookahead, OSError). |
| **F. Repo-wide contract / process** | 3 | ~2 | RED-suite (`highlight_color` ∉ `_EFFECT_ATTRS`) + `--list-fields` collision slipped because per-fix we ran only the calendar test file, not the full suite. |

## Class-closing guards (build once; permanent regression tests)

1. **Real-`.ics` corpus** (class A) — `tests/fixtures/calendar_corpus/*.ics`, one
   fixture per real-world shape + every quirk found, run through `parse_ics`
   and `update()` in a parametrized test. Each fixture asserts it parses without
   raising and yields the expected events. Adding a new real-world quirk = drop
   in a fixture.
2. **Recurrence cost-matrix** (class B) — parametrized over
   {SECONDLY, MINUTELY, HOURLY, DAILY} × {past, future DTSTART} ×
   {none, COUNT, UNTIL, BY*}; asserts `parse_ics` returns in bounded time and
   `<= _MAX_OCCURRENCES`, sub-hourly dropped, clamp-equivalence holds.
3. **next-selection truth table** (class D) — enumerate
   {future-timed, in-progress-timed, ongoing-all-day, today-all-day,
   future-all-day, none} combinations; assert which event `_NextEventWidget`
   selects and the rendered string, per the documented priority.
4. **validate ⟹ no-crash property test** (class E) — feed `validate_config` a
   battery of bad/edge configs (wrong types, out-of-range, empty/whitespace
   strings, bad enums); for every config it ACCEPTS, assert build + draw does
   not raise. Encodes "validate rejects everything runtime can't handle".
5. **tz/DST invariant** (class C) — assert every `CalendarEvent.start` is
   tz-aware; a DST-boundary fixture produces correct labels/countdowns; default
   (unset) tz resolves to a concrete zone.
6. **Process fix** (class F) — every fix runs the **full suite + pyright**, not
   the widget test file. (Documented here; behavioral. The relevant
   meta-tripwires already exist — `test_frame_aware`, drift tests — they just
   must be run.)

## Documented next-mode selection priority (the spec D was missing)

`_NextEventWidget.draw` picks, in order:
1. soonest **future timed** event (`start > now`) — the actionable countdown;
2. else **ongoing all-day** (`all_day and start.date() <= today`) — "today";
3. else soonest **future all-day** — "in Nd";
4. else most-recently-started **in-progress timed** event (`start <= now`) — "now";
5. else `empty_text`.

## Smarter re-loop

After the harness is green, run ONE category-guided adversary round whose
`priorKnown` includes the class map above, instructing adversaries to hunt
genuinely NEW classes (not variants of A–F). The harness is the cheap first
filter; adversary tokens go only to fresh ground.

## Out of scope

- Re-litigating accepted trade-offs (`:slug:` emoji agenda-only; static agenda
  day-labels between refreshes; non-uniform far-past recurrences not clamped).
- New widget features.
