import pytest
from tools.film.manifest import ManifestError, film_names


def test_names_in_order_skipping_slates():
    text = (
        '[[playlist.section]]\nmode="slideshow"\n'
        "[[playlist.section]]  # film: color-rainbow\n"
        "[[playlist.section]]\n"
        "[[playlist.section]] # film: border-bands\n"
    )
    assert film_names(text) == ["color-rainbow", "border-bands"]


def test_duplicate_name_is_error():
    text = "[[playlist.section]] # film: a\n[[playlist.section]] # film: a\n"
    with pytest.raises(ManifestError):
        film_names(text)


def test_bad_name_is_error():
    with pytest.raises(ManifestError):
        film_names("[[playlist.section]] # film: Bad_Name\n")


def test_no_names_returns_empty():
    assert film_names("[display]\nrows = 16\n") == []
