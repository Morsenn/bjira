import pytest
from bjira._text import resolve_body_source, format_comment


def test_resolve_body_from_positional(tmp_path):
    assert resolve_body_source(positional="hi there", from_file=None) == "hi there"


def test_resolve_body_from_file(tmp_path):
    p = tmp_path / "body.md"
    p.write_text("file body\nline 2")
    assert resolve_body_source(positional=None, from_file=str(p)) == "file body\nline 2"


def test_resolve_body_rejects_both_sources():
    with pytest.raises(ValueError, match="mutually exclusive"):
        resolve_body_source(positional="x", from_file="/tmp/x")


def test_resolve_body_rejects_neither_source():
    with pytest.raises(ValueError, match="required"):
        resolve_body_source(positional=None, from_file=None)


def test_resolve_body_rejects_empty_positional():
    with pytest.raises(ValueError, match="empty"):
        resolve_body_source(positional="", from_file=None)


def test_resolve_body_rejects_missing_file():
    with pytest.raises(ValueError, match="cannot read"):
        resolve_body_source(positional=None, from_file="/no/such/path.md")


def test_format_comment_basic():
    c = {
        "id": "11506156",
        "created": "2026-04-23T20:59:12.000+0300",
        "author": {"displayName": "Молтянинов Илья"},
        "body": "test body",
    }
    out = format_comment(c)
    assert "[2026-04-23 20:59]" in out
    assert "Молтянинов Илья" in out
    assert "(id=11506156)" in out
    assert "test body" in out
    assert out.endswith("---\n") or out.endswith("---")
