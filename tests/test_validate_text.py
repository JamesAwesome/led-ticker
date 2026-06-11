"""validate_config_text parity with the file-path entry point."""

from led_ticker.validate import validate_config, validate_config_text

# Matches the shape used by existing validator tests (test_validate.py::GOOD_CONFIG).
GOOD = """\
[display]
rows = 32
cols = 64
chain_length = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 3

[[playlist.section.widget]]
type = "message"
text = "hello"
"""

# Unknown widget type is a hard error (see test_unknown_widget_type_returns_error).
BAD = GOOD + '\n[[playlist.section.widget]]\ntype = "no_such_widget"\n'


async def test_text_and_path_agree_on_valid(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(GOOD)
    from_path = await validate_config(p)
    from_text = await validate_config_text(GOOD)
    assert from_text.valid == from_path.valid is True


async def test_text_and_path_agree_on_invalid(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(BAD)
    from_path = await validate_config(p)
    from_text = await validate_config_text(BAD)
    assert from_text.valid == from_path.valid is False
    assert [e.message for e in from_text.errors] == [
        e.message for e in from_path.errors
    ]


async def test_text_broken_toml_is_a_result_not_a_raise():
    # validate_config wraps load_config exceptions into a ValidationResult,
    # so broken TOML returns an invalid result rather than raising.
    result = await validate_config_text("this is [not toml")
    assert result.valid is False


async def test_text_non_ascii_content_is_validated(tmp_path):
    # The temp-file write must be explicit UTF-8: the sidecar process that
    # calls this can't control its locale, and TOML mandates UTF-8 — a
    # platform-default encoding would either raise UnicodeEncodeError
    # (breaking the never-raise contract) or feed tomllib mojibake.
    accented = GOOD.replace('text = "hello"', 'text = "café ☕"')
    p = tmp_path / "config.toml"
    p.write_text(accented, encoding="utf-8")
    from_path = await validate_config(p)
    from_text = await validate_config_text(accented)
    assert from_text.valid == from_path.valid is True
