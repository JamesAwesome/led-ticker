"""Tests for Unicode-emoji detection, mapping, and the shared gate helper.

Covers Task 1 of the Unicode-emoji→sprite feature:
  - _UEMOJI_RE / _uemoji_runs  (detection + segmentation)
  - _emoji_key                  (normalisation)
  - _UNICODE_EMOJI_MAP          (invariant: every value in _get_registry())
  - _map_uemoji_to_slug         (per-emoji mapping)
  - has_renderable_emoji        (shared gate)

Covers Task 2 of the Unicode-emoji→sprite feature:
  - _parse_segments             (uemoji segment emission)
"""

from led_ticker.pixel_emoji import (
    _UNICODE_EMOJI_MAP,
    _get_registry,
    _map_uemoji_to_slug,
    _parse_segments,
    _uemoji_runs,
    has_renderable_emoji,
)


class TestMapInvariant:
    """Every slug value in _UNICODE_EMOJI_MAP must exist in the registry."""

    def test_all_map_values_in_registry(self):
        registry = _get_registry()
        for slug in _UNICODE_EMOJI_MAP.values():
            assert slug in registry, (
                f"_UNICODE_EMOJI_MAP target slug {slug!r} is not in _get_registry()"
            )


class TestMappingSamples:
    """Spot-checks that specific Unicode emoji map to the expected slug."""

    def test_heart_with_vs(self):
        assert _map_uemoji_to_slug("❤️") == "heart"

    def test_heart_bare_same_key(self):
        # VS-stripped key ⇒ same slug as the VS form
        assert _map_uemoji_to_slug("❤") == "heart"

    def test_star(self):
        assert _map_uemoji_to_slug("⭐") == "star"

    def test_sun_with_vs(self):
        assert _map_uemoji_to_slug("☀️") == "sun"

    def test_cat(self):
        assert _map_uemoji_to_slug("🐱") == "cat"

    def test_flower_unicode_unfolded_to_pack(self):
        # 2026-07-21 unfold: each flower unicode renders its OWN Noto pack
        # sprite; the curated :flower: slug remains but no unicode maps to
        # it anymore (a rose renders as a rose, not the generic blossom).
        assert _map_uemoji_to_slug("🌸") == "cherry_blossom"
        assert _map_uemoji_to_slug("🌹") == "rose"
        assert _map_uemoji_to_slug("💐") == "bouquet"

    def test_taco(self):
        assert _map_uemoji_to_slug("🌮") == "taco"

    def test_pride_rainbow_flag(self):
        assert _map_uemoji_to_slug("🏳️‍🌈") == "pride_rainbow"


class TestUnmapped:
    """Emoji outside the ~20-entry curated `_UNICODE_EMOJI_MAP` used to return
    None unconditionally (stripped). Since the standard-emoji pack (Task 3 of
    the emoji-pack-spec) landed, `_map_uemoji_to_slug` falls back to
    `emoji_pack.slug_for_codepoint` for any astral base or allowlisted pack
    BMP char not in the curated map — bird/dove/pin/calendar are single-
    codepoint standard emoji the pack ships, so they now resolve to a real
    slug instead of stripping. A bare BMP dingbat the pack does NOT ship
    (e.g. a plain ✓/✗/★ with no variation selector) still returns None —
    see `test_bare_unmapped_bmp_symbol_stays_none` below."""

    def test_bird_resolves_via_pack(self):
        assert _map_uemoji_to_slug("🐦") == "bird"

    def test_dove_resolves_via_pack(self):
        assert _map_uemoji_to_slug("🕊️") == "dove"

    def test_pin_resolves_via_pack(self):
        assert _map_uemoji_to_slug("📍") == "round_pushpin"

    def test_calendar_resolves_via_pack(self):
        assert _map_uemoji_to_slug("📅") == "calendar"

    def test_bare_unmapped_bmp_symbol_stays_none(self):
        # ✓ (U+2713) is neither in the curated map nor the pack's BMP
        # allowlist (`PACK_BMP`) — genuinely unmapped, still strips.
        assert _map_uemoji_to_slug("✓") is None


class TestUemojiRuns:
    """_uemoji_runs yields (start, end, chars) for each detected run."""

    def test_two_runs_with_correct_spans(self):
        text = "❤️ hi 🐦"
        runs = list(_uemoji_runs(text))
        assert len(runs) == 2
        s0, e0, ch0 = runs[0]
        s1, e1, ch1 = runs[1]
        # ❤ (index 0) + FE0F (index 1) → span [0, 2)
        assert s0 == 0
        assert e0 == 2
        assert ch0 == "❤️"
        # 🐦 is a single Python char at index 6 → span [6, 7)
        assert s1 == 6
        assert e1 == 7
        assert ch1 == "🐦"

    def test_zwj_sequence_is_one_run(self):
        # 🐦 ZWJ ⬛  (black bird emoji — ZWJ sequence absorbs the black square).
        # Pin the exact span: ⬛ (U+2B1B) is a bare BMP symbol (not an allowlist
        # base), so it can't match on its own — the whole sequence being one
        # run PROVES the post-ZWJ _BMP_SYM class absorbs it. `len==1` alone
        # would pass with just 🐦 matched (review teeth-gap).
        runs = list(_uemoji_runs("🐦‍⬛"))
        assert len(runs) == 1
        assert runs[0][2] == "🐦‍⬛"

    def test_rainbow_flag_is_one_run(self):
        # 🏳️ ZWJ 🌈  (white flag + VS + ZWJ + rainbow)
        runs = list(_uemoji_runs("🏳️‍🌈"))
        assert len(runs) == 1
        assert runs[0][2] == "🏳️‍🌈"

    def test_unqualified_flag_maps_same_as_qualified(self):
        # Feeds routinely emit the UNQUALIFIED flag (no internal U+FE0F). It
        # must key identically to the qualified form → pride_rainbow. This is
        # the real-world path AND the only test pinning that `_emoji_key`
        # strips ALL variation selectors, not just a trailing one (review).
        assert _map_uemoji_to_slug("🏳‍🌈") == "pride_rainbow"
        assert _map_uemoji_to_slug("🏳‍🌈") == _map_uemoji_to_slug("🏳️‍🌈")
        assert len(list(_uemoji_runs("🏳‍🌈"))) == 1

    def test_skin_tone_is_one_run(self):
        # 👍 + medium skin tone modifier
        runs = list(_uemoji_runs("👍🏽"))
        assert len(runs) == 1

    def test_keycap_is_one_run(self):
        # 1️⃣ = '1' + FE0F + U+20E3
        runs = list(_uemoji_runs("1️⃣"))
        assert len(runs) == 1

    def test_single_regional_flag_is_one_run(self):
        # 🇺🇸 = U+1F1FA + U+1F1F8 (exactly two regional indicator letters)
        runs = list(_uemoji_runs("🇺🇸"))
        assert len(runs) == 1

    def test_two_regional_flags_are_two_runs(self):
        # 🇺🇸🇬🇧 = four regional indicator letters → two pairs
        runs = list(_uemoji_runs("🇺🇸🇬🇧"))
        assert len(runs) == 2


class TestF5Passthrough:
    """Bare BMP symbols that are NOT in an allowlist (curated `_MAPPED_BMP`
    OR the pack's generated `PACK_BMP`) must stay plain text.

    Since Task 3 of the emoji-pack-spec spliced `PACK_BMP` into the same
    base-allowlist character class as `_MAPPED_BMP` (`pixel_emoji.py`'s
    `_UEMOJI_RE`), a bare BMP char the pack ships (e.g. ➡ / ⚡) is now a
    real detected run without needing a variation selector — see
    `TestPackBmpNowRecognized` below. ✓ / ✗ / ★ / ☆ are NOT in the pack
    and still require FE0F, so the allowlist-exclusion behavior this class
    documents still holds for them."""

    def test_checkmark_cross_are_text(self):
        # ✓ ✗ are BMP symbols in neither allowlist; without FE0F they do
        # not match any alternative.
        assert list(_uemoji_runs("✓ done ✗ fail")) == []

    def test_stars_are_text(self):
        # ★ and ☆ are BMP dingbats but bare (no FE0F) — must stay text.
        assert list(_uemoji_runs("★★★★☆ 4/5")) == []

    def test_vs_qualified_checkmark_is_one_run(self):
        # ✓️ = ✓ + FE0F → matches the "ambiguous char + required VS" branch.
        runs = list(_uemoji_runs("✓️"))
        assert len(runs) == 1

    def test_vs_qualified_arrow_is_one_run(self):
        # ➡️ = ➡ + FE0F → matches the pack-BMP allowlist branch (or the
        # VS-required branch structurally — either way a single run).
        runs = list(_uemoji_runs("➡️"))
        assert len(runs) == 1


class TestPackBmpNowRecognized:
    """BMP chars the standard-emoji pack ships (`PACK_BMP`) are spliced into
    the SAME base-allowlist class as the curated `_MAPPED_BMP` (Task 3) —
    they match bare, with no variation selector required, and fold to a
    real pack slug via `_map_uemoji_to_slug`."""

    def test_lightning_is_recognized_and_resolves(self):
        # ⚡ (U+26A1) is in PACK_BMP — matches bare and folds via the pack.
        runs = list(_uemoji_runs("⚡ Flash"))
        assert len(runs) == 1
        assert _map_uemoji_to_slug(runs[0][2]) == "high_voltage"

    def test_arrow_is_recognized_and_resolves(self):
        # ➡ (U+27A1) is in PACK_BMP — matches bare and folds via the pack.
        runs = list(_uemoji_runs("➡ next"))
        assert len(runs) == 1
        assert _map_uemoji_to_slug(runs[0][2]) == "right_arrow"


class TestHasRenderableEmoji:
    """has_renderable_emoji: true for registry :slug: or any Unicode-emoji run."""

    def test_slug_in_registry(self):
        assert has_renderable_emoji(":star:") is True

    def test_unicode_heart_emoji(self):
        assert has_renderable_emoji("❤️") is True

    def test_unicode_emoji_inline_in_text(self):
        assert has_renderable_emoji("a 🐦 b") is True

    def test_plain_text_is_false(self):
        assert has_renderable_emoji("hello world") is False

    def test_bare_bmp_symbol_is_false(self):
        # Bare ✓ is plain text — no FE0F → does not trigger the gate.
        assert has_renderable_emoji("✓ done") is False

    def test_unregistered_slug_is_false(self):
        # `:notaslug:` matches EMOJI_PATTERN but is not in the registry.
        assert has_renderable_emoji(":notaslug:") is False


class TestParseSegmentsUemoji:
    """_parse_segments now emits ("uemoji", chars) for Unicode-emoji runs."""

    def test_pure_unicode_emoji_and_text(self):
        # Task 2: two emoji runs with a text span in between.
        assert _parse_segments("❤️ hi 🐦") == [
            ("uemoji", "❤️"),
            ("text", " hi "),
            ("uemoji", "🐦"),
        ]

    def test_slug_and_unicode_emoji_coexist(self):
        # :star: slug keeps ("emoji","star"); ⭐ emits ("uemoji","⭐").
        assert _parse_segments(":star: ⭐ x") == [
            ("emoji", "star"),
            ("text", " "),
            ("uemoji", "⭐"),
            ("text", " x"),
        ]

    def test_plain_text_unchanged(self):
        # No emoji of any kind — single text segment, unchanged from today.
        assert _parse_segments("hello") == [("text", "hello")]

    def test_f5_bare_bmp_stays_text(self):
        # ✓ is a bare BMP symbol (no FE0F) — must stay as text (F5 passthrough).
        assert _parse_segments("✓ ok") == [("text", "✓ ok")]

    def test_ascii_round_trip(self):
        # Pure ASCII: concatenated segment values must equal the input.
        s = "Speed: 42 mph, Temp: 72F"
        result = _parse_segments(s)
        assert all(kind == "text" for kind, _ in result)
        assert "".join(v for _, v in result) == s


class TestMeasureWidthUemoji:
    """measure_width mirrors the draw loop: a mapped Unicode emoji adds the
    same width as its :slug: twin; an unmapped run is stripped (0 width)."""

    def test_unmapped_strip_adds_no_width(self):
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.pixel_emoji import measure_width

        # 🐦 (bird) is unmapped → stripped → contributes no width.
        assert measure_width(FONT_SMALL, "a🐦b") == measure_width(FONT_SMALL, "ab")

    def test_mapped_uemoji_matches_slug_width(self):
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.pixel_emoji import measure_width

        # ❤️ maps to :heart: — same measured width in the same context.
        assert measure_width(FONT_SMALL, "x ❤️ y") == measure_width(
            FONT_SMALL, "x :heart: y"
        )
