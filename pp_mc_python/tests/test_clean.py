"""Test Step 4 — Clean Message."""

from pp_mc_python.pipeline.clean import html_to_text


def test_strips_basic_tags():
    html = "<p>Hello <b>world</b></p>"
    assert html_to_text(html) == "Hello world"


def test_preserves_paragraph_structure():
    html = "<p>First paragraph.</p><p>Second paragraph.</p>"
    out = html_to_text(html)
    assert "First paragraph." in out
    assert "Second paragraph." in out
    assert "\n\n" in out


def test_drops_style_and_script():
    html = "<style>body{color:red}</style><p>Visible</p><script>alert(1)</script>"
    out = html_to_text(html)
    assert "Visible" in out
    assert "color" not in out
    assert "alert" not in out


def test_handles_line_breaks():
    html = "Line one<br/>Line two<br/>Line three"
    out = html_to_text(html)
    assert "Line one" in out and "Line two" in out and "Line three" in out


def test_empty_returns_empty():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_legacy_inconsistent_html():
    """Older MC items use inconsistent markup — the cleaner must still get a usable string."""
    html = '<DIV>Update <SPAN style="color:#000">applied</SPAN>.<BR>See <a href="x">link</a>.</DIV>'
    out = html_to_text(html)
    assert "Update" in out and "applied" in out and "link" in out
