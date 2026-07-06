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

    def test_flower(self):
        assert _map_uemoji_to_slug("🌸") == "flower"

    def test_taco(self):
        assert _map_uemoji_to_slug("🌮") == "taco"

    def test_pride_rainbow_flag(self):
        assert _map_uemoji_to_slug("🏳️‍🌈") == "pride_rainbow"


class TestUnmapped:
    """Unmapped emoji return None."""

    def test_bird_is_unmapped(self):
        assert _map_uemoji_to_slug("🐦") is None

    def test_dove_is_unmapped(self):
        assert _map_uemoji_to_slug("🕊️") is None

    def test_pin_is_unmapped(self):
        assert _map_uemoji_to_slug("📍") is None

    def test_calendar_is_unmapped(self):
        assert _map_uemoji_to_slug("📅") is None


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
    """Bare BMP symbols that are NOT in the allowlist must stay plain text."""

    def test_checkmark_cross_arrow_are_text(self):
        # ✓ ✗ ➡ are BMP symbols but NOT in _MAPPED_BMP; without FE0F they
        # do not match any alternative — the allowlist holds structurally.
        assert list(_uemoji_runs("✓ done ✗ fail ➡ next")) == []

    def test_stars_are_text(self):
        # ★ and ☆ are BMP dingbats but bare (no FE0F) — must stay text.
        assert list(_uemoji_runs("★★★★☆ 4/5")) == []

    def test_lightning_is_text(self):
        # ⚡ is a BMP symbol; bare (no FE0F) — must stay text.
        assert list(_uemoji_runs("⚡ Flash")) == []

    def test_vs_qualified_checkmark_is_one_run(self):
        # ✓️ = ✓ + FE0F → matches the "ambiguous char + required VS" branch.
        runs = list(_uemoji_runs("✓️"))
        assert len(runs) == 1

    def test_vs_qualified_arrow_is_one_run(self):
        # ➡️ = ➡ + FE0F → matches the "ambiguous char + required VS" branch.
        runs = list(_uemoji_runs("➡️"))
        assert len(runs) == 1


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
