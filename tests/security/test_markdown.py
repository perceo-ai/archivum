from archivum.security.markdown import sanitize_markdown


def test_sanitize_markdown_handles_empty_values():
    assert sanitize_markdown(None) == ""
    assert sanitize_markdown("") == ""


def test_sanitize_markdown_strips_raw_html_outside_code_fences():
    markdown = "# Title\n<script>alert(1)</script><b>bold</b>\n"

    assert sanitize_markdown(markdown) == "# Title\nalert(1)bold\n"


def test_sanitize_markdown_preserves_html_inside_code_fences():
    markdown = "before <em>x</em>\n```\n<script>alert(1)</script>\n```\nafter <b>y</b>\n"

    assert sanitize_markdown(markdown) == "before x\n```\n<script>alert(1)</script>\n```\nafter y\n"
