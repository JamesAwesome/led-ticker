"""Every core transition name has exactly one row in the content-source fact
packs behind the docs site's `<OptionsTable source="transitions/*" />` tables
(`docs/content-source/transitions/*.md`). Counts FIRST-COLUMN cells of
pipe-table rows only; prose mentions (`cut` appears several times in Tips)
do not count. Meta types (`random` / `auto`) are listed in `special.md` too,
but as pool mechanics rather than effects, so they are checked separately."""

import re
from pathlib import Path

import pytest

from led_ticker.transitions import list_transition_names
from led_ticker.transitions.meta import META_TYPES

PACKS = sorted(
    (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "content-source"
        / "transitions"
    ).glob("*.md")
)


def _row_count(name: str) -> int:
    pattern = re.compile(rf"^\| `{re.escape(name)}` ", re.MULTILINE)
    return sum(len(pattern.findall(p.read_text())) for p in PACKS)


@pytest.mark.parametrize(
    "name",
    sorted(n for n in list_transition_names() if "." not in n and n not in META_TYPES),
)
def test_every_core_transition_has_exactly_one_fact_pack_row(name: str) -> None:
    assert _row_count(name) == 1, (
        f"{name!r}: {_row_count(name)} rows across {[p.name for p in PACKS]}"
    )


@pytest.mark.parametrize("name", sorted(META_TYPES))
def test_meta_types_have_a_row(name: str) -> None:
    assert _row_count(name) == 1
