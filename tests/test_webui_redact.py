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
