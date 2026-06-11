"""Redaction of sensitive values from TOML text. Over-redaction is safe;
under-redaction is the worst failure in a read-only design."""

from led_ticker.webui.redact import redact_toml


def test_redacts_token():
    assert 'token = "•••"' in redact_toml('token = "abc123"')


def test_redacts_key_suffixed_names():
    out = redact_toml('weatherapi_key = "k-123"\napi_key = "k-456"')
    assert "k-123" not in out and "k-456" not in out
    assert out.count('"•••"') == 2


def test_redacts_inside_inline_tables():
    out = redact_toml('busy = { source = "http", token = "hunter2", port = 8080 }')
    assert "hunter2" not in out
    assert 'source = "http"' in out
    assert "port = 8080" in out


def test_preserves_comments_and_structure():
    src = "# my comment\n[display]\nrows = 16  # trailing\n"
    assert redact_toml(src) == src


def test_redacts_secret_password_webhook():
    out = redact_toml('secret = "a"\npassword = "b"\nslack_webhook = "c"')
    for leaked in ('"a"', '"b"', '"c"'):
        assert leaked not in out


def test_non_sensitive_values_untouched():
    src = 'text = "my token of appreciation"\ncolor = [255, 0, 0]'
    # Values are never scanned — only key NAMES trigger redaction.
    assert redact_toml(src) == src


def test_over_redaction_of_keylike_names_is_accepted():
    # "monkey" contains "key": redacted. Documented behavior — safe direction.
    assert "•••" in redact_toml('monkey = "bananas"')


def test_sensitive_word_inside_quoted_value_does_not_corrupt():
    # "token" appears INSIDE a quoted string value, not as a key name.
    # The regex must not corrupt the outer key's value by matching the
    # interior ``token = abc`` fragment.
    src = 'note = "set token = abc here"'
    assert redact_toml(src) == src


def test_sensitive_word_in_value_does_not_corrupt_inline_table():
    # Same guard inside an inline table: the value string contains "key = x"
    # but only the outer key name matters.
    src = 'info = { label = "api_key = hidden", port = 9000 }'
    out = redact_toml(src)
    # "hidden" must still be present — it's inside a non-sensitive-named value.
    assert "hidden" in out


def test_indented_keys_are_still_redacted():
    # TOML allows leading whitespace before keys. The line-start anchor must
    # tolerate indentation — missing these would be under-redaction, the one
    # unacceptable failure for this function.
    out = redact_toml('  token = "LEAK1"\n\tapi_key = "LEAK2"')
    assert "LEAK1" not in out and "LEAK2" not in out
    assert out.count("•••") == 2


def test_multiline_string_values_are_fully_redacted():
    # Triple-quoted TOML strings span lines; the single-line quote branch
    # alone would match the empty "" at the start of """ and leak the body.
    basic = 'token = """abc123secret"""'
    literal = "api_key = '''line1\nline2secret\n'''"
    for src, leak in ((basic, "abc123secret"), (literal, "line2secret")):
        out = redact_toml(src)
        assert leak not in out, f"multiline secret leaked: {out!r}"
        assert "•••" in out


def test_quoted_key_form_is_redacted():
    # TOML quoted keys: `"my-token" = "x"` is a legal key spelling.
    out = redact_toml('"my-token" = "LEAK"\n"weather api_key" = "LEAK2"')
    assert "LEAK" not in out
    assert out.count("•••") == 2


def test_dotted_key_with_quoted_segment_is_redacted():
    # Legal TOML: a dotted key whose final segment is quoted. The dotted
    # prefix must not defeat the quoted-key match.
    out = redact_toml(
        'slack."webhook url" = "https://hooks.slack/SECRET"\nsite."api key" = "LEAK3"'
    )
    assert "SECRET" not in out and "LEAK3" not in out
    assert out.count("•••") == 2


def test_comma_then_sensitive_word_inside_value_over_redacts():
    # Known limitation, documented: a sensitive word following a comma INSIDE
    # a quoted value matches the inline-table anchor and gets rewritten.
    # Over-redaction (display corruption of that value) is accepted — fixing
    # it needs a real tokenizer. The load-bearing assertion: nothing that
    # looks like a secret survives.
    out = redact_toml('note = "a, token = b"')
    assert "token = b" not in out
