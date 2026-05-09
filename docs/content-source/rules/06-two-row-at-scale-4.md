# Rule 6: two_row at scale=4 produces a very narrow logical canvas

**SOURCE:** `validate.py` `_check_soft` (rule 6, warning); CLAUDE.md "Two-row widget" and "Per-section `content_height`".

**DETECT:** A section contains a `type = "two_row"` widget AND the section's effective `scale` is 4.

**SYMPTOM:** Config load emits a warning:

```
two_row at scale=4: logical canvas is only 64px wide — handles may scroll instead of fitting
```

**FIX:**

- Add `scale = 2` to the section so the logical canvas is 128px wide — wide enough for a typical social handle without triggering the scroll path.

At `scale = 4` the bigsign's 256 real pixels collapse to only 64 logical pixels wide. A handle like `@MoonBunny` in the default BDF font is roughly 50px, so it fits — but any longer label or larger font overflows and the bottom row starts scrolling. Setting `scale = 2` doubles the logical width to 128px, which is the recommended baseline for two-row handle layouts. `content_height` should stay ≤ 16 at `scale = 2` (hard ceiling: `content_height × scale ≤ panel_h_real`).
