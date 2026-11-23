# Antagonist loop — `fade` PRECURSOR PR (branch `fade-precursor`)

Target: the diff `origin/main..fade-precursor` (PixelBuffer Clear/Fill/SetImage +
pixel-equality tripwire; breaker helpers; runner kwargs + API (1, 5) + docs;
meta `end_firing` forward; `rgb_shape_error` relocation + import tripwires).
Design: `docs/superpowers/specs/2026-11-21-fade-design.md`. Plan:
`docs/superpowers/plans/2026-11-22-fade-transition.md`.
Rules: fresh reviewer per cycle, full diff each time, cap 5, exit when only
LOW/DOCS remain (folded in). Pre-existing issues outside the diff do not count.
Contract under test: behaviour-free for every existing config (dissolve demo
29/29 frames byte-identical vs origin/main before cycle 1).
