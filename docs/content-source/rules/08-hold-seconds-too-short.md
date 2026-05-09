# Rule 8: hold_seconds too short (< 50 ms)

**SOURCE:** `validate.py` `_check_static` (rule 8); CLAUDE.md "Footgun validation" inside "GIF widget and Still-image widget".

**DETECT:** A widget specifies `hold_seconds` and the value is less than `0.05`.

**SYMPTOM:** Config load reports an error (where `<N>` is the configured value):

```
hold_seconds=<N> is too short (< 50 ms), likely a typo
```

**FIX:**

- Raise `hold_seconds` to at least `0.05` (50 ms).
- If you intended milliseconds, divide by 1000: e.g. `hold_seconds = 3000` → `hold_seconds = 3.0`.

`hold_seconds` is expressed in **seconds**, not milliseconds. Values below 50 ms are almost certainly a unit error — a `hold_seconds = 0.03` intended as 30 ms would actually hold for 30 microseconds, producing a widget that vanishes before the panel can display it. The validator catches this at config-load rather than letting the display silently flash.
